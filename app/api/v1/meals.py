import uuid
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.models import Meal, Partner
from app.schemas import MealOut

router = APIRouter(prefix="/meals", tags=["Meals"])


@router.get("", response_model=List[MealOut])
async def list_meals(
    category: Optional[str] = Query(None),
    tier: Optional[str] = Query(None),
    partner_id: Optional[uuid.UUID] = Query(None),
    db: AsyncSession = Depends(get_db),
):
    stmt = select(Meal).options(selectinload(Meal.partner)).where(Meal.is_active == True)

    if category:
        stmt = stmt.where(Meal.category == category)
    if tier:
        stmt = stmt.where(Meal.tier == tier)
    if partner_id:
        stmt = stmt.where(Meal.partner_id == partner_id)

    res = await db.execute(stmt)
    meals = res.scalars().all()

    # Shape response with partner relation
    result = []
    for m in meals:
        data = MealOut.model_validate(m)
        if m.partner:
            data.partners = m.partner
        result.append(data)
    return result


@router.get("/{meal_id}", response_model=MealOut)
async def get_meal(meal_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    stmt = select(Meal).options(selectinload(Meal.partner)).where(Meal.id == meal_id)
    res = await db.execute(stmt)
    meal = res.scalar_one_or_none()
    if not meal:
        raise HTTPException(status_code=404, detail="Meal not found")

    data = MealOut.model_validate(meal)
    if meal.partner:
        data.partners = meal.partner
    return data
