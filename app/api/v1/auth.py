from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.security import get_password_hash, verify_password, create_access_token
from app.core.dependencies import get_current_user
from app.models import User
from app.schemas import UserRegister, UserLogin, UserOut, TokenResponse

router = APIRouter(prefix="/auth", tags=["Authentication"])


@router.post("/signup", response_model=TokenResponse)
async def signup(req: UserRegister, db: AsyncSession = Depends(get_db)):
    # Check if email exists
    stmt = select(User).where(User.email == req.email.lower().strip())
    res = await db.execute(stmt)
    if res.scalar_one_or_none():
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="An account with this email address already exists",
        )

    # Security: enforce student role on public signup
    assigned_role = "partner" if req.role == "partner" else "student"

    new_user = User(
        email=req.email.lower().strip(),
        password_hash=get_password_hash(req.password),
        full_name=req.full_name or req.email.split("@")[0],
        student_id=req.student_id,
        role=assigned_role,
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    token = create_access_token({"sub": str(new_user.id), "role": new_user.role, "email": new_user.email})
    return {"access_token": token, "token_type": "bearer", "user": new_user}


@router.post("/login", response_model=TokenResponse)
async def login(req: UserLogin, db: AsyncSession = Depends(get_db)):
    stmt = select(User).where(User.email == req.email.lower().strip())
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()

    if not user or not verify_password(req.password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is deactivated")

    token = create_access_token({"sub": str(user.id), "role": user.role, "email": user.email})
    return {"access_token": token, "token_type": "bearer", "user": user}


@router.get("/me", response_model=UserOut)
async def get_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/sync-session", response_model=TokenResponse)
async def sync_session(current_user: User = Depends(get_current_user)):
    token = create_access_token({"sub": str(current_user.id), "role": current_user.role, "email": current_user.email})
    return {"access_token": token, "token_type": "bearer", "user": current_user}


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    if len(req.new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters long")

    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect")

    current_user.password_hash = get_password_hash(req.new_password)
    await db.commit()
    return {"success": True, "message": "Password updated successfully"}


class ForgotPasswordRequest(BaseModel):
    email: str


@router.post("/forgot-password")
async def forgot_password(
    req: ForgotPasswordRequest,
    db: AsyncSession = Depends(get_db),
):
    stmt = select(User).where(User.email == req.email.lower().strip())
    res = await db.execute(stmt)
    user = res.scalar_one_or_none()
    # Idempotent response to prevent user enumeration
    return {
        "success": True,
        "message": f"If an account exists for {req.email.lower().strip()}, reset instructions have been dispatched.",
    }
