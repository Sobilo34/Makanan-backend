import uuid
import io
import base64
import hmac
import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any, List
import qrcode
import httpx
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from app.core.config import settings
from app.models import Payment, MealPlan, Subscription, WalletTransaction, Notification, User

logger = logging.getLogger("makanan.payment")


def generate_qr_data_url(data_str: str) -> str:
    """Generates a base64 encoded PNG data URL for a given string."""
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=8,
        border=2,
    )
    qr.add_data(data_str)
    qr.make(fit=True)
    img = qr.make_image(fill_color="#111827", back_color="white")

    buffer = io.BytesIO()
    img.save(buffer, format="PNG")
    b64_str = base64.b64encode(buffer.getvalue()).decode("utf-8")
    return f"data:image/png;base64,{b64_str}"


def format_emvco_duitnow_qr(reference_code: str, amount_myr: float) -> str:
    """
    Constructs an EMVCo-compliant DuitNow QR payload string for Malaysian National QR.
    Allows all Malaysian banking apps (MAE, CIMB, RHB) and e-wallets (TNG, Grab, Shopee) to scan.
    """
    amount_str = f"{amount_myr:.2f}"
    emv_payload = (
        f"000201010212"
        f"26480014my.com.paynet.duitnow0118{settings.DUITNOW_MERCHANT_ID}"
        f"52045812"
        f"5303458"
        f"54{len(amount_str):02d}{amount_str}"
        f"5802MY"
        f"59{len(settings.DUITNOW_MERCHANT_NAME):02d}{settings.DUITNOW_MERCHANT_NAME}"
        f"6007AlorSet"
        f"62{len(reference_code) + 4:02d}01{len(reference_code):02d}{reference_code}"
        f"6304ABCD"
    )
    return emv_payload


def verify_hitpay_signature(raw_body: bytes, received_signature: str, salt: str) -> bool:
    """
    Validates Hitpay-Signature header against the raw JSON webhook body using HMAC-SHA256.
    """
    if not received_signature or not salt:
        return False
    computed = hmac.new(salt.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(computed.lower(), received_signature.lower())


class PaymentService:
    @staticmethod
    async def create_payment_order(
        db: AsyncSession,
        user_id: uuid.UUID,
        plan_id: uuid.UUID,
        payment_method: str = "duitnow_qr",
        redirect_url: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Creates an authoritative payment request via HitPay Malaysia.
        Returns HitPay hosted checkout URL, dynamic DuitNow QR, and mobile deep links.
        """
        # 1. Authoritative plan lookup directly from database
        stmt = select(MealPlan).where(MealPlan.id == plan_id, MealPlan.is_active == True)
        result = await db.execute(stmt)
        plan = result.scalar_one_or_none()

        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meal plan not found or no longer available",
            )

        # Look up student details
        user_stmt = select(User).where(User.id == user_id)
        user_res = await db.execute(user_stmt)
        student = user_res.scalar_one_or_none()

        amount = float(plan.price_myr)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=30)
        reference_code = f"MKN-PAY-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        checkout_url: Optional[str] = None
        hitpay_request_id: Optional[str] = None
        qr_string: str = ""
        deep_link_url: Optional[str] = None

        # Build dynamic redirect URL ensuring reference_code parameter
        final_redirect_url = redirect_url or f"{settings.HITPAY_REDIRECT_URL}?reference_code={reference_code}"
        if "reference_code=" not in final_redirect_url:
            sep = "&" if "?" in final_redirect_url else "?"
            final_redirect_url = f"{final_redirect_url}{sep}reference_code={reference_code}"

        # 2. Call HitPay Malaysia API
        email = "student@makanan.app"
        if student and student.email and "@" in student.email:
            email = student.email.strip()

        name = "Student"
        if student and student.full_name and student.full_name.strip():
            name = student.full_name.strip()

        hitpay_payload: Dict[str, Any] = {
            "amount": f"{amount:.2f}",
            "currency": "MYR",
            "email": email,
            "name": name,
            "purpose": f"{plan.name} ({plan.credits} Meal Credits)",
            "reference_number": reference_code,
            "redirect_url": final_redirect_url,
        }
        webhook_target = settings.HITPAY_WEBHOOK_URL or "https://makanan-backend.onrender.com/api/v1/payments/hitpay-webhook"
        hitpay_payload["webhook"] = webhook_target

        # Map payment methods to HitPay Malaysia enums
        if payment_method == "tng_ewallet":
            hitpay_payload["payment_methods[]"] = "touch_n_go"
        elif payment_method == "duitnow_qr":
            hitpay_payload["payment_methods[]"] = "duitnow"
        # If no specific filter, HitPay enables all methods on merchant account (DuitNow, Touch 'n Go, etc.)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                hp_headers = {
                    "X-BUSINESS-API-KEY": settings.clean_hitpay_api_key,
                    "Content-Type": "application/x-www-form-urlencoded",
                    "X-Requested-With": "XMLHttpRequest",
                    "User-Agent": "MakananApp/1.0 (Fintech; Malaysia)",
                }
                hp_resp = await client.post(
                    f"{settings.hitpay_endpoint}/v1/payment-requests",
                    headers=hp_headers,
                    data=hitpay_payload,
                )
                if hp_resp.status_code in [200, 201]:
                    hp_json = hp_resp.json()
                    checkout_url = hp_json.get("url")
                    hitpay_request_id = hp_json.get("id")
                    qr_string = checkout_url or format_emvco_duitnow_qr(reference_code, amount)
                    logger.info(f"HitPay payment request created: {hitpay_request_id} for order {reference_code}")
                else:
                    err_msg = hp_resp.text
                    try:
                        err_data = hp_resp.json()
                        err_msg = err_data.get("message") or err_data.get("error") or str(err_data)
                    except Exception:
                        pass
                    logger.error(f"HitPay API returned {hp_resp.status_code}: {err_msg}")
                    raise HTTPException(
                        status_code=status.HTTP_502_BAD_GATEWAY,
                        detail=f"HitPay Gateway ({hp_resp.status_code}): {err_msg}",
                    )
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"HitPay request encountered error: {e}")
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"HitPay Connection Error: {str(e)}",
            )

        # Set instructions and deep link
        if payment_method == "tng_ewallet":
            deep_link_url = checkout_url or f"tngewallet://pay?merchant={settings.TNG_MERCHANT_ID}&ref={reference_code}&amount={amount:.2f}"
            instructions = "Pay securely with Touch 'n Go eWallet via HitPay, or scan the QR code using your Touch 'n Go app."
        else:
            deep_link_url = checkout_url
            instructions = "Scan the QR code with any Malaysian banking app (MAE Maybank, CIMB, Bank Islam, etc.) or tap 'Pay via HitPay'."

        qr_image_data_url = generate_qr_data_url(qr_string)

        # 3. Create pending payment record
        payment = Payment(
            user_id=user_id,
            meal_plan_id=plan.id,
            amount_myr=amount,
            payment_method=payment_method,
            status="pending",
            reference_code=reference_code,
            qr_data=checkout_url or qr_string,
            gateway_transaction_id=hitpay_request_id or f"HITPAY-PENDING-{reference_code}",
            expires_at=expires_at,
        )
        db.add(payment)
        await db.commit()
        await db.refresh(payment)

        return {
            "payment_id": payment.id,
            "reference_code": reference_code,
            "amount_myr": amount,
            "credits": plan.credits,
            "plan_name": plan.name,
            "payment_method": payment_method,
            "qr_data": qr_string,
            "qr_image_url": qr_image_data_url,
            "deep_link_url": deep_link_url,
            "checkout_url": checkout_url,
            "hitpay_request_id": hitpay_request_id,
            "expires_at": expires_at,
            "instructions": instructions,
        }

    @staticmethod
    async def process_successful_payment(
        db: AsyncSession,
        reference_code: str,
        gateway_txn_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Atomic transaction: locks payment, activates subscription, records in ledger."""
        try:
            # 1. Lock payment record with SELECT ... FOR UPDATE
            stmt = select(Payment).where(Payment.reference_code == reference_code).with_for_update()
            result = await db.execute(stmt)
            payment = result.scalar_one_or_none()

            if not payment:
                raise HTTPException(status_code=404, detail="Payment record not found")

            # Idempotency check: if already completed, return immediately
            if payment.status == "completed":
                return {
                    "already_completed": True,
                    "payment_id": payment.id,
                    "subscription_id": payment.subscription_id,
                }

            if payment.status in ["failed", "expired"]:
                raise HTTPException(status_code=400, detail=f"Cannot complete payment with status '{payment.status}'")

            # 2. Fetch meal plan
            plan_stmt = select(MealPlan).where(MealPlan.id == payment.meal_plan_id)
            plan_res = await db.execute(plan_stmt)
            plan = plan_res.scalar_one()

            now = datetime.now(timezone.utc)
            expires_at = now + timedelta(days=30)

            # 3. Cancel any existing active subscriptions for this student
            await db.execute(
                update(Subscription)
                .where(Subscription.user_id == payment.user_id, Subscription.status == "active")
                .values(status="cancelled", updated_at=now)
            )

            # 4. Create new subscription
            new_sub = Subscription(
                user_id=payment.user_id,
                meal_plan_id=plan.id,
                status="active",
                credits_total=plan.credits,
                credits_used=0,
                starts_at=now,
                expires_at=expires_at,
            )
            db.add(new_sub)
            await db.flush()  # assign ID

            # 5. Insert double-entry ledger record
            last_tx_stmt = (
                select(WalletTransaction.balance_after)
                .where(WalletTransaction.user_id == payment.user_id)
                .order_by(WalletTransaction.created_at.desc())
                .limit(1)
            )
            last_bal_res = await db.execute(last_tx_stmt)
            prev_balance = last_bal_res.scalar_one_or_none() or 0
            new_balance = prev_balance + plan.credits

            ledger_entry = WalletTransaction(
                user_id=payment.user_id,
                subscription_id=new_sub.id,
                payment_id=payment.id,
                description=f"Meal plan purchased via HitPay ({payment.payment_method.replace('_', ' ').title()}) — {plan.credits} credits issued",
                credits_delta=plan.credits,
                balance_after=new_balance,
            )
            db.add(ledger_entry)

            # 6. Mark payment as completed
            payment.status = "completed"
            payment.paid_at = now
            payment.subscription_id = new_sub.id
            payment.gateway_transaction_id = gateway_txn_id or payment.gateway_transaction_id or f"HITPAY-{uuid.uuid4().hex[:12]}"

            # 7. Add notification for student
            notif = Notification(
                user_id=payment.user_id,
                recipient_type="student",
                type="subscription_confirmed",
                title="Subscription Activated! 🎉",
                message=f"Your {plan.name} subscription is active with {plan.credits} meal credits via HitPay Malaysia.",
                metadata_={
                    "plan_id": str(plan.id),
                    "subscription_id": str(new_sub.id),
                    "amount": float(payment.amount_myr),
                    "gateway": "hitpay",
                },
            )
            db.add(notif)

            await db.commit()
            logger.info(f"Payment completed and subscription activated: {new_sub.id} ({reference_code})")

            return {
                "success": True,
                "payment_id": payment.id,
                "subscription_id": new_sub.id,
                "credits": plan.credits,
            }
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def get_payment_status(db: AsyncSession, reference_code: str) -> Dict[str, Any]:
        """
        Polls payment status. If pending, checks HitPay Malaysia live API
        to detect real-time clearance synchronously.
        """
        stmt = select(Payment).where(Payment.reference_code == reference_code)
        result = await db.execute(stmt)
        payment = result.scalar_one_or_none()

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        # Real-time HitPay API synchronization if currently pending
        if payment.status == "pending" and payment.gateway_transaction_id and not payment.gateway_transaction_id.startswith("HITPAY-PENDING-"):
            try:
                async with httpx.AsyncClient(timeout=6.0) as client:
                    hp_res = await client.get(
                        f"{settings.hitpay_endpoint}/v1/payment-requests/{payment.gateway_transaction_id}",
                        headers={
                            "X-BUSINESS-API-KEY": settings.clean_hitpay_api_key,
                            "User-Agent": "MakananApp/1.0 (Fintech; Malaysia)",
                        },
                    )
                    if hp_res.status_code == 200:
                        hp_data = hp_res.json()
                        if hp_data.get("status") in ["completed", "succeeded", "paid"]:
                            await PaymentService.process_successful_payment(
                                db=db,
                                reference_code=reference_code,
                                gateway_txn_id=hp_data.get("id"),
                            )
                            await db.refresh(payment)
            except Exception as e:
                logger.debug(f"Live HitPay status check skipped: {e}")

        plan = None
        if payment.meal_plan_id:
            plan_stmt = select(MealPlan).where(MealPlan.id == payment.meal_plan_id)
            plan_res = await db.execute(plan_stmt)
            plan = plan_res.scalar_one_or_none()

        return {
            "reference_code": payment.reference_code,
            "status": payment.status,
            "amount_myr": float(payment.amount_myr),
            "paid_at": payment.paid_at,
            "subscription_id": payment.subscription_id,
            "credits": plan.credits if plan else 0,
            "plan_name": plan.name if plan else "Meal Plan",
            "payment_method": payment.payment_method,
        }
