import uuid
from datetime import datetime, timezone
from typing import Dict, Any, List
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, status
from app.models import Settlement, Redemption, Meal, Partner


class SettlementService:
    @staticmethod
    async def request_payout(
        db: AsyncSession,
        partner_id: uuid.UUID,
    ) -> Dict[str, Any]:
        """
        Calculates and locks unsettled redemptions, assigning them a settlement_id.
        Eliminates duplicate payouts by design.
        """
        try:
            # 1. Fetch all confirmed redemptions that have NEVER been settled
            stmt = (
                select(Redemption, Meal.price_myr)
                .join(Meal, Redemption.meal_id == Meal.id)
                .where(
                    Redemption.partner_id == partner_id,
                    Redemption.status == "confirmed",
                    Redemption.settlement_id.is_(None),  # Must be unsettled
                )
                .with_for_update(of=Redemption)
            )
            res = await db.execute(stmt)
            rows = res.all()

            if not rows:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="No unsettled meal redemptions available for payout request",
                )

            redemptions = [r[0] for r in rows]
            total_amount = sum(float(r[1]) for r in rows)
            count = len(redemptions)

            period_start = min(r.redeemed_at or r.created_at for r in redemptions)
            now = datetime.now(timezone.utc)

            # 2. Create settlement record
            settlement = Settlement(
                partner_id=partner_id,
                period_start=period_start,
                period_end=now,
                total_redemptions=count,
                total_amount_myr=total_amount,
                settlement_rate_myr=(total_amount / count) if count > 0 else 0.0,
                status="requested",
                payout_requested_at=now,
            )
            db.add(settlement)
            await db.flush()  # assign settlement ID

            # 3. Associate redemptions to this settlement ID
            matched_ids = [r.id for r in redemptions]
            await db.execute(
                update(Redemption)
                .where(Redemption.id.in_(matched_ids))
                .values(settlement_id=settlement.id)
            )

            await db.commit()

            return {
                "success": True,
                "settlement_id": settlement.id,
                "total_redemptions": count,
                "total_amount_myr": total_amount,
                "status": "requested",
            }
        except Exception:
            await db.rollback()
            raise
