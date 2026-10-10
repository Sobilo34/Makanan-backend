import uuid
from typing import List
from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import decode_access_token
from app.models import User, Partner

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)


async def get_current_user(
    token: str = Depends(oauth2_scheme),
    db: AsyncSession = Depends(get_db),
) -> User:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials or session expired",
        headers={"WWW-Authenticate": "Bearer"},
    )

    if not token:
        raise credentials_exception

    payload = decode_access_token(token)
    if not payload:
        raise credentials_exception

    user_id = payload.get("sub")
    if not user_id:
        raise credentials_exception

    try:
        user_uuid = uuid.UUID(str(user_id))
    except (ValueError, TypeError):
        raise credentials_exception

    # 1. Lookup by UUID
    stmt = select(User).where(User.id == user_uuid, User.is_active == True)
    result = await db.execute(stmt)
    user = result.scalar_one_or_none()

    # 2. Lookup by email if not found by UUID
    if not user and payload.get("email"):
        stmt = select(User).where(User.email == payload["email"].lower().strip(), User.is_active == True)
        result = await db.execute(stmt)
        user = result.scalar_one_or_none()

    if not user:
        raise credentials_exception

    return user


def require_role(allowed_roles: List[str]):
    async def role_checker(current_user: User = Depends(get_current_user)) -> User:
        if current_user.role not in allowed_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation not permitted. Required role: {allowed_roles}, your role: {current_user.role}",
            )
        return current_user

    return role_checker


async def get_current_partner(
    current_user: User = Depends(require_role(["partner", "admin"])),
    db: AsyncSession = Depends(get_db),
) -> Partner:
    stmt = select(Partner).where(Partner.user_id == current_user.id)
    result = await db.execute(stmt)
    partner = result.scalar_one_or_none()

    if not partner and current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No partner profile registered for this account",
        )

    return partner
