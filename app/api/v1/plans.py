import uuid
from typing import List
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models import MealPlan
from app.schemas import MealPlanOut

router = APIRouter(prefix="/plans", tags=["Meal Plans"])


@router.get("", response_model=List[MealPlanOut])
async def list_plans(db: AsyncSession = Depends(get_db)):
    stmt = select(MealPlan).where(MealPlan.is_active == True).order_by(MealPlan.price_myr.asc())
    res = await db.execute(stmt)
    return res.scalars().all()


@router.get("/{plan_id}", response_model=MealPlanOut)
async def get_plan(plan_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(MealPlan).where(MealPlan.id == plan_id)
    res = await db.execute(stmt)
    plan = res.scalar_one_or_none()
    if not plan:
        raise HTTPException(status_code=404, detail="Meal plan not found")
    return plan
