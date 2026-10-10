from pydantic import BaseModel, EmailStr
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models import WaitlistSignup

router = APIRouter(prefix="/waitlist", tags=["Waitlist"])


class WaitlistRequest(BaseModel):
    email: EmailStr
    full_name: str = ""


@router.get("/count")
async def get_waitlist_count(db: AsyncSession = Depends(get_db)):
    stmt = select(func.count()).select_from(WaitlistSignup)
    res = await db.execute(stmt)
    count = res.scalar() or 0
    return {"count": count}


@router.post("")
async def join_waitlist(req: WaitlistRequest, db: AsyncSession = Depends(get_db)):
    email_clean = req.email.lower().strip()
    stmt = select(WaitlistSignup).where(WaitlistSignup.email == email_clean)
    res = await db.execute(stmt)
    existing = res.scalar_one_or_none()
    if existing:
        return {"success": True, "message": "Already on the waitlist"}

    entry = WaitlistSignup(
        email=email_clean,
        full_name=req.full_name.strip(),
    )
    db.add(entry)
    await db.commit()
    return {"success": True, "message": "Successfully joined the waitlist"}
