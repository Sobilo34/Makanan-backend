import uuid
from datetime import datetime, timezone
from typing import Optional, Dict, Any
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from app.core.security import generate_qr_token, verify_qr_token
from app.models import Subscription, Meal, Partner, Redemption, WalletTransaction, User


class RedemptionService:
    @staticmethod
    async def create_redemption(
        db: AsyncSession,
        user_id: uuid.UUID,
        subscription_id: uuid.UUID,
        meal_id: uuid.UUID,
        partner_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        try:
            # 1. Row-level exclusive lock on the student's active subscription
            stmt = (
                select(Subscription)
                .where(
                    Subscription.id == subscription_id,
                    Subscription.user_id == user_id,
                    Subscription.status == "active",
                )
                .with_for_update()  # SELECT ... FOR UPDATE (Prevents race conditions)
            )
            result = await db.execute(stmt)
            sub = result.scalar_one_or_none()

            if not sub:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="No active meal subscription found",
                )

            credits_remaining = sub.credits_total - sub.credits_used
            if credits_remaining <= 0:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No meal credits remaining on this plan",
                )

            # 2. Fetch meal details
            meal_stmt = select(Meal).where(Meal.id == meal_id, Meal.is_active == True)
            meal_res = await db.execute(meal_stmt)
            meal = meal_res.scalar_one_or_none()
            if not meal:
                raise HTTPException(status_code=404, detail="Selected meal is not available")

            resolved_partner_id = partner_id or meal.partner_id

            # 3. Deduct credit
            sub.credits_used += 1

            # 4. Generate dynamic signed QR token
            redemption_id = uuid.uuid4()
            qr_token = generate_qr_token(
                redemption_id=str(redemption_id),
                user_id=str(user_id),
                meal_id=str(meal.id),
                partner_id=str(resolved_partner_id),
                expiry_seconds=300,  # 5-minute validity window
            )
            short_qr_code = f"MKN-{str(meal.id)[:6].upper()}-{uuid.uuid4().hex[:8].upper()}"

            # 5. Insert redemption record
            now = datetime.now(timezone.utc)
            redemption = Redemption(
                id=redemption_id,
                user_id=user_id,
                subscription_id=sub.id,
                meal_id=meal.id,
                partner_id=resolved_partner_id,
                status="pending",
                qr_token=qr_token,
                qr_code=short_qr_code,
                created_at=now,
            )
            db.add(redemption)
            await db.flush()

            # 6. Insert immutable ledger record
            ledger = WalletTransaction(
                user_id=user_id,
                subscription_id=sub.id,
                redemption_id=redemption.id,
                description=f"Meal redeemed — {meal.name}",
                credits_delta=-1,
                balance_after=credits_remaining - 1,
            )
            db.add(ledger)

            # Fetch partner name for display
            partner_stmt = select(Partner).where(Partner.id == resolved_partner_id)
            partner_res = await db.execute(partner_stmt)
            partner = partner_res.scalar_one_or_none()

            await db.commit()

            return {
                "redemption_id": redemption_id,
                "status": "pending",
                "qr_token": qr_token,
                "qr_code": short_qr_code,
                "credits_remaining": credits_remaining - 1,
                "meal_name": meal.name,
                "partner_name": partner.name if partner else "Cafeteria",
                "created_at": now,
            }
        except Exception:
            await db.rollback()
            raise

    @staticmethod
    async def verify_qr(
        db: AsyncSession,
        qr_code_or_token: str,
        partner_id: Optional[uuid.UUID] = None,
    ) -> Dict[str, Any]:
        # 1. Try cryptographic token decode first
        token_payload = verify_qr_token(qr_code_or_token)

        redemption = None
        if token_payload and "rid" in token_payload:
            try:
                rid = uuid.UUID(token_payload["rid"])
                stmt = select(Redemption).where(Redemption.id == rid)
                res = await db.execute(stmt)
                redemption = res.scalar_one_or_none()
            except Exception:
                pass

        # 2. If not found by signed token, search by short alphanumeric code
        if not redemption:
            stmt = select(Redemption).where(
                (Redemption.qr_code == qr_code_or_token.strip())
                | (Redemption.qr_token == qr_code_or_token.strip())
            )
            res = await db.execute(stmt)
            redemption = res.scalar_one_or_none()

        if not redemption:
            return {
                "valid": False,
                "student_name": "",
                "meal_name": "",
                "plan_name": "",
                "error": "Invalid or expired QR code",
            }

        # 3. Fetch details
        user_stmt = select(User).where(User.id == redemption.user_id)
        user_res = await db.execute(user_stmt)
        user = user_res.scalar_one_or_none()

        meal_stmt = select(Meal).where(Meal.id == redemption.meal_id)
        meal_res = await db.execute(meal_stmt)
        meal = meal_res.scalar_one_or_none()

        sub_stmt = select(Subscription).where(Subscription.id == redemption.subscription_id)
        sub_res = await db.execute(sub_stmt)
        sub = sub_res.scalar_one_or_none()

        is_already_confirmed = redemption.status == "confirmed"
        is_valid = redemption.status == "pending"

        return {
            "valid": is_valid,
            "already_confirmed": is_already_confirmed,
            "student_name": user.full_name if user else "Student",
            "meal_name": meal.name if meal else "Meal",
            "plan_name": "Student Meal Plan",
            "redemption_id": redemption.id,
            "subscription_id": redemption.subscription_id,
            "partner_id": redemption.partner_id,
            "credits_remaining": (sub.credits_total - sub.credits_used) if sub else 0,
        }

    @staticmethod
    async def confirm_redemption(
        db: AsyncSession,
        redemption_id: uuid.UUID,
        partner_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """Atomically confirms a scanned redemption at the cafeteria counter."""
        try:
            stmt = select(Redemption).where(Redemption.id == redemption_id).with_for_update()
            res = await db.execute(stmt)
            redemption = res.scalar_one_or_none()

            if not redemption:
                raise HTTPException(status_code=404, detail="Redemption record not found")

            if redemption.status == "confirmed":
                return {"success": True, "already_confirmed": True, "redemption_id": redemption.id}

            now = datetime.now(timezone.utc)
            redemption.status = "confirmed"
            redemption.partner_id = partner_id
            redemption.redeemed_at = now

            # Increment meal counters
            await db.execute(
                update(Meal)
                .where(Meal.id == redemption.meal_id)
                .values(redemption_count=Meal.redemption_count + 1)
            )

            # Increment partner counters
            await db.execute(
                update(Partner)
                .where(Partner.id == partner_id)
                .values(meals_redeemed=Partner.meals_redeemed + 1)
            )

            await db.commit()
            return {"success": True, "redemption_id": redemption_id}
        except Exception:
            await db.rollback()
            raise
