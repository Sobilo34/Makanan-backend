import uuid
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, Notification

router = APIRouter(prefix="/notifications", tags=["Notifications"])


class MarkReadRequest(BaseModel):
    notification_ids: Optional[List[uuid.UUID]] = None
    all_read: Optional[bool] = False


@router.get("")
async def get_my_notifications(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(Notification)
        .where(
            (Notification.user_id == current_user.id)
            | (Notification.recipient_type == current_user.role)
        )
        .order_by(Notification.created_at.desc())
        .limit(50)
    )
    res = await db.execute(stmt)
    notifications = res.scalars().all()
    unread_count = sum(1 for n in notifications if not n.is_read)
    return {
        "notifications": notifications,
        "unread_count": unread_count,
    }


@router.post("/read")
async def mark_notifications_read(
    req: MarkReadRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if req.all_read:
        stmt = (
            update(Notification)
            .where(
                (Notification.user_id == current_user.id)
                | (Notification.recipient_type == current_user.role)
            )
            .values(is_read=True)
        )
        await db.execute(stmt)
        await db.commit()
    elif req.notification_ids:
        stmt = (
            update(Notification)
            .where(Notification.id.in_(req.notification_ids))
            .values(is_read=True)
        )
        await db.execute(stmt)
        await db.commit()

    return {"success": True}
