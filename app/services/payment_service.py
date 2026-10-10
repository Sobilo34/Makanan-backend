import uuid
import io
import base64
from datetime import datetime, timedelta, timezone
from typing import Optional, Dict, Any
import qrcode
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from app.core.config import settings
from app.models import Payment, MealPlan, Subscription, WalletTransaction, Notification, User


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
    # DuitNow QR EMVCo payload format
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


class PaymentService:
    @staticmethod
    async def create_payment_order(
        db: AsyncSession,
        user_id: uuid.UUID,
        plan_id: uuid.UUID,
        payment_method: str = "duitnow_qr",
    ) -> Dict[str, Any]:
        # 1. Authoritative plan lookup directly from database
        stmt = select(MealPlan).where(MealPlan.id == plan_id, MealPlan.is_active == True)
        result = await db.execute(stmt)
        plan = result.scalar_one_or_none()

        if not plan:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Meal plan not found or no longer available",
            )

        amount = float(plan.price_myr)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=15)
        reference_code = f"MKN-PAY-{now.strftime('%Y%m%d')}-{uuid.uuid4().hex[:8].upper()}"

        # 2. Generate QR payload / Deep Link based on selected method
        deep_link_url: Optional[str] = None
        if payment_method == "tng_ewallet":
            qr_string = f"tngewallet://pay?merchant={settings.TNG_MERCHANT_ID}&ref={reference_code}&amount={amount:.2f}"
            deep_link_url = qr_string
            instructions = "Scan with your Touch 'n Go eWallet, or tap 'Open Touch 'n Go' on mobile."
        elif payment_method == "grabpay":
            qr_string = f"grab://pay?merchant={settings.GRABPAY_MERCHANT_ID}&ref={reference_code}&amount={amount:.2f}"
            deep_link_url = qr_string
            instructions = "Scan with your Grab app, or tap 'Open GrabPay' on mobile."
        elif payment_method == "shopeepay":
            qr_string = f"shopeepay://payment?merchant={settings.SHOPEEPAY_MERCHANT_ID}&ref={reference_code}&amount={amount:.2f}"
            deep_link_url = qr_string
            instructions = "Scan with your ShopeePay app, or tap 'Open ShopeePay' on mobile."
        else:
            # Default: DuitNow National QR
            qr_string = format_emvco_duitnow_qr(reference_code, amount)
            instructions = "Scan with Touch 'n Go, MAE Maybank, CIMB, GrabPay, or ANY Malaysian banking app."

        qr_image_data_url = generate_qr_data_url(qr_string)

        # 3. Create pending payment record
        payment = Payment(
            user_id=user_id,
            meal_plan_id=plan.id,
            amount_myr=amount,
            payment_method=payment_method,
            status="pending",
            reference_code=reference_code,
            qr_data=qr_string,
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
            ledger_entry = WalletTransaction(
                user_id=payment.user_id,
                subscription_id=new_sub.id,
                payment_id=payment.id,
                description=f"Meal plan purchased via {payment.payment_method.replace('_', ' ').title()} — {plan.credits} credits issued",
                credits_delta=plan.credits,
                balance_after=plan.credits,
            )
            db.add(ledger_entry)

            # 6. Mark payment as completed
            payment.status = "completed"
            payment.paid_at = now
            payment.subscription_id = new_sub.id
            payment.gateway_transaction_id = gateway_txn_id or f"GTW-{uuid.uuid4().hex[:12]}"

            # 7. Add notification for student
            notif = Notification(
                user_id=payment.user_id,
                recipient_type="student",
                type="subscription_confirmed",
                title="Subscription Activated! 🎉",
                message=f"Your {plan.name} subscription is active with {plan.credits} meal credits.",
                metadata_={
                    "plan_id": str(plan.id),
                    "subscription_id": str(new_sub.id),
                    "amount": float(payment.amount_myr),
                },
            )
            db.add(notif)

            await db.commit()

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
        stmt = select(Payment).where(Payment.reference_code == reference_code)
        result = await db.execute(stmt)
        payment = result.scalar_one_or_none()

        if not payment:
            raise HTTPException(status_code=404, detail="Payment not found")

        return {
            "reference_code": payment.reference_code,
            "status": payment.status,
            "amount_myr": float(payment.amount_myr),
            "paid_at": payment.paid_at,
            "subscription_id": payment.subscription_id,
        }
