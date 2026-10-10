from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User
from app.schemas import CreatePaymentOrderRequest, PaymentOrderOut, PaymentStatusOut
from app.services.payment_service import PaymentService

router = APIRouter(prefix="/payments", tags=["Payments"])


@router.post("/create-order", response_model=PaymentOrderOut)
async def create_payment_order(
    req: CreatePaymentOrderRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Creates an authoritative payment order and returns a DuitNow QR or e-wallet intent.
    Price and credits are looked up directly from the database to prevent tampering.
    """
    result = await PaymentService.create_payment_order(
        db=db,
        user_id=current_user.id,
        plan_id=req.plan_id,
        payment_method=req.payment_method,
    )
    return result


@router.get("/status/{reference_code}", response_model=PaymentStatusOut)
async def get_payment_status(
    reference_code: str,
    db: AsyncSession = Depends(get_db),
):
    """Pollable endpoint for the frontend to detect when payment has cleared."""
    return await PaymentService.get_payment_status(db=db, reference_code=reference_code)


@router.post("/simulate-success/{reference_code}")
async def simulate_payment_success(
    reference_code: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Simulates a Malaysian bank / e-wallet scanning the DuitNow QR code and remitting funds.
    Enables instant end-to-end testing in sandbox/development mode.
    """
    result = await PaymentService.process_successful_payment(
        db=db,
        reference_code=reference_code,
        gateway_txn_id=f"SIMULATED-SCAN-{reference_code}",
    )
    return result


@router.post("/webhook")
async def payment_gateway_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Server-to-server webhook callback from payment gateway (Curlec, Revenue Monster, PayNet).
    """
    payload = await request.json()
    reference_code = payload.get("reference_code") or payload.get("order_id")
    gateway_status = payload.get("status")

    if not reference_code:
        raise HTTPException(status_code=400, detail="Missing order reference")

    if gateway_status in ["paid", "completed", "SUCCESS", "00"]:
        await PaymentService.process_successful_payment(
            db=db,
            reference_code=reference_code,
            gateway_txn_id=payload.get("transaction_id"),
        )

    return {"received": True}
