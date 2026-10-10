import pytest
import pytest_asyncio
from typing import AsyncGenerator
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select
from app.main import app
from app.core.database import AsyncSessionLocal, engine
from app.core.security import create_access_token
from app.models import User, Partner, Meal, Subscription


@pytest_asyncio.fixture(scope="function")
async def db_session() -> AsyncGenerator:
    """Provides a transactional database session for tests."""
    async with AsyncSessionLocal() as session:
        yield session
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def client() -> AsyncGenerator[AsyncClient, None]:
    """Provides an ASGI test client making real asynchronous HTTP calls to the app."""
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


@pytest_asyncio.fixture(scope="function")
async def admin_auth_headers(db_session) -> dict:
    stmt = select(User).where(User.role == "admin").limit(1)
    res = await db_session.execute(stmt)
    admin = res.scalar_one_or_none()
    assert admin is not None, "Admin user must exist in database"
    token = create_access_token({"sub": str(admin.id), "email": admin.email, "role": admin.role})
    return {"Authorization": f"Bearer {token}"}


@pytest_asyncio.fixture(scope="function")
async def partner_auth_headers(db_session) -> dict:
    stmt = select(User).where(User.role == "partner").limit(1)
    res = await db_session.execute(stmt)
    partner = res.scalar_one_or_none()
    assert partner is not None, "Partner user must exist in database"
    token = create_access_token({"sub": str(partner.id), "email": partner.email, "role": partner.role})
    return {"Authorization": f"Bearer {token}"}


import uuid
from app.core.security import get_password_hash

@pytest_asyncio.fixture(scope="function")
async def student_user(db_session) -> User:
    stmt = select(User).where(User.email == "test_runner@makanan.test")
    res = await db_session.execute(stmt)
    student = res.scalar_one_or_none()
    if not student:
        student = User(
            id=uuid.uuid4(),
            email="test_runner@makanan.test",
            password_hash=get_password_hash("testpass123"),
            full_name="Test Runner Student",
            role="student",
        )
        db_session.add(student)
        await db_session.commit()
        await db_session.refresh(student)
    return student


@pytest_asyncio.fixture(scope="function")
async def student_auth_headers(student_user) -> dict:
    token = create_access_token({"sub": str(student_user.id), "email": student_user.email, "role": student_user.role})
    return {"Authorization": f"Bearer {token}"}

