import uuid
from typing import Optional, List
from pydantic import BaseModel
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.dependencies import get_current_user
from app.models import User, SupportTicket, Feedback

router = APIRouter(prefix="/support", tags=["Support & Feedback"])


class CreateTicketRequest(BaseModel):
    category: str = "other"
    subject: str
    description: str


class CreateFeedbackRequest(BaseModel):
    redemption_id: Optional[uuid.UUID] = None
    meal_id: Optional[uuid.UUID] = None
    partner_id: Optional[uuid.UUID] = None
    rating: int
    comment: Optional[str] = None


@router.get("/tickets")
async def get_my_tickets(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(SupportTicket)
        .where(SupportTicket.user_id == current_user.id)
        .order_by(SupportTicket.created_at.desc())
        .limit(50)
    )
    res = await db.execute(stmt)
    return res.scalars().all()


@router.post("/tickets")
async def create_ticket(
    req: CreateTicketRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    ticket = SupportTicket(
        user_id=current_user.id,
        category=req.category,
        subject=req.subject.strip(),
        description=req.description.strip(),
        status="open",
    )
    db.add(ticket)
    await db.commit()
    await db.refresh(ticket)
    return ticket


@router.post("/feedback")
async def submit_feedback(
    req: CreateFeedbackRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    fb = Feedback(
        user_id=current_user.id,
        redemption_id=req.redemption_id,
        meal_id=req.meal_id,
        partner_id=req.partner_id,
        rating=max(1, min(5, req.rating)),
        comment=req.comment.strip() if req.comment else None,
    )
    db.add(fb)
    await db.commit()
    await db.refresh(fb)
    return {"success": True, "feedback_id": fb.id}
