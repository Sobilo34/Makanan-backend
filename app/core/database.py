import uuid
import logging
from typing import AsyncGenerator
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy import select
from app.core.config import settings

logger = logging.getLogger("makanan.database")

Base = declarative_base()


def get_clean_database_url(url: str) -> str:
    """
    Normalizes PostgreSQL connection strings for asyncpg.
    Converts standard postgres:// or postgresql:// to postgresql+asyncpg://
    and adapts cloud provider SSL parameters (sslmode -> ssl).
    """
    if not url:
        return url
    clean = url.strip()
    if clean.startswith("postgres://"):
        clean = clean.replace("postgres://", "postgresql+asyncpg://", 1)
    elif clean.startswith("postgresql://") and not clean.startswith("postgresql+asyncpg://"):
        clean = clean.replace("postgresql://", "postgresql+asyncpg://", 1)
    clean = clean.replace("sslmode=require", "ssl=require").replace("sslmode=prefer", "ssl=prefer")
    return clean


clean_db_url = get_clean_database_url(settings.DATABASE_URL)

# Engine optimized for cloud and containerized PostgreSQL
engine = create_async_engine(
    clean_db_url,
    echo=False,
    pool_size=10,
    max_overflow=5,
    pool_pre_ping=True,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with AsyncSessionLocal() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """
    Auto-initializes tables and initial meal plans on application startup.
    Ensures zero manual migration steps required on cloud hosts like Render or Railway.
    """
    try:
        from app import models  # register models with Base.metadata
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)

        # Seed initial production meal plans if table is fresh
        from app.models import MealPlan
        async with AsyncSessionLocal() as session:
            res = await session.execute(select(MealPlan).limit(1))
            if not res.scalar_one_or_none():
                logger.info("Initializing production meal plans in database...")
                default_plans = [
                    MealPlan(
                        id=uuid.UUID("a1111111-1111-1111-1111-111111111111"),
                        name="Lite Saver",
                        tier="value",
                        price_myr=150.00,
                        credits=20,
                        description="Perfect for light eaters — 20 meals per month at RM7.50/meal",
                        is_active=True,
                    ),
                    MealPlan(
                        id=uuid.UUID("a2222222-2222-2222-2222-222222222222"),
                        name="Value Regular",
                        tier="value",
                        price_myr=250.00,
                        credits=60,
                        description="Affordable daily meals — 60 meals per month at RM4.17/meal",
                        is_active=True,
                    ),
                    MealPlan(
                        id=uuid.UUID("a3333333-3333-3333-3333-333333333333"),
                        name="Value Flex",
                        tier="value",
                        price_myr=250.00,
                        credits=40,
                        description="Affordable meals with flexibility — 40 meals per month at RM6.25/meal",
                        is_active=True,
                    ),
                    MealPlan(
                        id=uuid.UUID("a4444444-4444-4444-4444-444444444444"),
                        name="Standard Regular",
                        tier="standard",
                        price_myr=300.00,
                        credits=60,
                        description="Balanced quality and frequency — 60 meals per month at RM5.00/meal",
                        is_active=True,
                    ),
                    MealPlan(
                        id=uuid.UUID("a5555555-5555-5555-5555-555555555555"),
                        name="Standard Flex",
                        tier="standard",
                        price_myr=300.00,
                        credits=40,
                        description="Better meals with flexibility — 40 meals per month at RM7.50/meal",
                        is_active=True,
                    ),
                    MealPlan(
                        id=uuid.UUID("a6666666-6666-6666-6666-666666666666"),
                        name="Premium Regular",
                        tier="premium",
                        price_myr=400.00,
                        credits=60,
                        description="Premium meals every day — 60 meals per month at RM6.67/meal",
                        is_active=True,
                    ),
                    MealPlan(
                        id=uuid.UUID("a7777777-7777-7777-7777-777777777777"),
                        name="Premium Flex",
                        tier="premium",
                        price_myr=400.00,
                        credits=40,
                        description="Top quality, fewer meals — 40 meals per month at RM10.00/meal",
                        is_active=True,
                    ),
                ]
                session.add_all(default_plans)
                await session.commit()
                logger.info("Production meal plans initialized successfully.")
    except Exception as e:
        logger.warning(f"Database auto-initialization skipped or encountered issue: {e}")
