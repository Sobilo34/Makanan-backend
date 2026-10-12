import json
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.core.config import settings
from app.models import User, Payment
from app.schemas import CreatePaymentOrderRequest, PaymentOrderOut, PaymentStatusOut
from app.services.payment_service import PaymentService, verify_hitpay_signature

logger = logging.getLogger("makanan.payments.api")

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/create-order", response_model=PaymentOrderOut)
async def create_payment_order(
    req: CreatePaymentOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates an authoritative HitPay Malaysia payment request.
    Strictly restricted to launch options: 'duitnow_qr' (DuitNow QR) and 'tng_ewallet' (Touch 'n Go eWallet).
    """
    if req.payment_method not in ["duitnow_qr", "tng_ewallet"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only 'duitnow_qr' (DuitNow QR) and 'tng_ewallet' (Touch 'n Go eWallet) are supported for launch.",
        )

    result = await PaymentService.create_payment_order(
        db=db,
        user_id=current_user.id,
        plan_id=req.plan_id,
        payment_method=req.payment_method,
        redirect_url=req.redirect_url,
    )
    return result


@router.get("/status/{reference_code}", response_model=PaymentStatusOut)
async def get_payment_status(
    reference_code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Pollable endpoint for frontend.
    Synchronously verifies live status against HitPay Malaysia API if pending.
    """
    return await PaymentService.get_payment_status(db=db, reference_code=reference_code)


@router.post("/sandbox-complete/{reference_code}")
async def sandbox_complete_payment(
    reference_code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Authorizes and completes an active HitPay payment request in Sandbox / Test mode.
    Enables realistic testing of Malaysian local payment methods (Touch 'n Go & DuitNow)
    which HitPay sandbox does not clear natively. Strictly forbidden in production.
    """
    if settings.PAYMENT_MODE == "production" and not settings.HITPAY_SANDBOX:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Sandbox payment authorization is disabled in production mode.",
        )

    result = await PaymentService.process_successful_payment(
        db=db,
        reference_code=reference_code,
        gateway_txn_id=f"HITPAY-SANDBOX-AUTH-{reference_code}",
    )
    return result


@router.post("/hitpay-webhook")
@router.post("/webhook")
async def hitpay_payment_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Server-to-server webhook callback from HitPay Malaysia.
    Validates HMAC-SHA256 signature with HitPay Salt.
    """
    raw_body = await request.body()
    signature = (
        request.headers.get("Hitpay-Signature")
        or request.headers.get("hitpay-signature")
        or request.headers.get("X-Hitpay-Signature")
    )

    # 1. Parse JSON or Form payload
    payload = {}
    if raw_body:
        try:
            payload = json.loads(raw_body.decode("utf-8"))
        except Exception:
            try:
                form = await request.form()
                payload = dict(form)
            except Exception:
                payload = {}

    # 2. Cryptographic HMAC validation if salt & signature are provided
    is_valid_sig = True
    if settings.clean_hitpay_salt and signature:
        is_valid_sig = verify_hitpay_signature(raw_body, signature, settings.clean_hitpay_salt)

    reference_code = (
        payload.get("reference_number")
        or payload.get("reference")
        or payload.get("reference_code")
        or payload.get("order_id")
    )
    gateway_status = payload.get("status")
    payment_id = payload.get("payment_id") or payload.get("id") or payload.get("payment_request_id")

    if not payment_id and isinstance(payload.get("payment_provider"), dict):
        charge = payload["payment_provider"].get("charge")
        if isinstance(charge, dict):
            payment_id = charge.get("id")

    if not reference_code:
        # Check nested payment_request object if present
        pr = payload.get("payment_request") or payload.get("order")
        if isinstance(pr, dict):
            reference_code = pr.get("reference_number") or pr.get("reference")
            gateway_status = gateway_status or pr.get("status")
            payment_id = payment_id or pr.get("id")

    if not reference_code and payment_id:
        # Match by gateway_transaction_id in database
        pay_stmt = select(Payment).where(
            (Payment.gateway_transaction_id == payment_id) |
            (Payment.gateway_transaction_id.like(f"%{payment_id}%"))
        )
        pay_res = await db.execute(pay_stmt)
        matched_pay = pay_res.scalar_one_or_none()
        if matched_pay:
            reference_code = matched_pay.reference_code

    # If signature verification failed, check HitPay live API directly as authoritative verification
    if settings.HITPAY_SALT and signature and not is_valid_sig:
        logger.warning("HitPay webhook signature mismatch! Verifying via live HitPay API...")
        verified_live = False
        check_id = payment_id or reference_code
        if check_id:
            try:
                async with httpx.AsyncClient(timeout=4.0) as client:
                    hp_res = await client.get(
                        f"{settings.hitpay_endpoint}/v1/payment-requests/{check_id}",
                        headers={
                            "X-BUSINESS-API-KEY": settings.HITPAY_API_KEY,
                            "User-Agent": "MakananApp/1.0 (Fintech; Malaysia)",
                        },
                    )
                    if hp_res.status_code == 200:
                        hp_json = hp_res.json()
                        if str(hp_json.get("status", "")).lower() in ["completed", "succeeded", "paid"]:
                            verified_live = True
                            gateway_status = hp_json.get("status")
            except Exception as e:
                logger.debug(f"Direct API fallback check failed: {e}")
        if not verified_live:
            raise HTTPException(status_code=400, detail="Invalid Hitpay-Signature HMAC")

    if not reference_code:
        logger.warning(f"HitPay webhook missing reference_number. Payload: {payload}")
        return {"received": True, "processed": False, "reason": "Missing reference"}

    if str(gateway_status).lower() in ["completed", "succeeded", "paid", "success", "00"]:
        logger.info(f"HitPay webhook confirmed payment for order {reference_code} (Status: {gateway_status})")
        await PaymentService.process_successful_payment(
            db=db,
            reference_code=reference_code,
            gateway_txn_id=payment_id,
        )
        return {"received": True, "processed": True}

    logger.info(f"HitPay webhook received order {reference_code} with status: {gateway_status}")
    return {"received": True, "processed": False, "status": gateway_status}
