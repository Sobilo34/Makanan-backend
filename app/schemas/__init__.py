import uuid
from typing import Optional, List, Any
from datetime import datetime
from pydantic import BaseModel, EmailStr, Field


# ── Auth & Users ─────────────────────────────────────────────────────────────
class UserRegister(BaseModel):
    email: EmailStr
    password: str = Field(min_length=6)
    full_name: str = ""
    student_id: Optional[str] = None
    role: Optional[str] = "student"


class UserLogin(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: uuid.UUID
    email: str
    full_name: str
    student_id: Optional[str] = None
    role: str
    avatar_url: Optional[str] = None
    phone: Optional[str] = None
    university: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    user: UserOut


# ── Meal Plans ───────────────────────────────────────────────────────────────
class MealPlanOut(BaseModel):
    id: uuid.UUID
    name: str
    tier: str
    price_myr: float
    credits: int
    description: Optional[str] = None
    is_active: bool
    created_at: datetime

    class Config:
        from_attributes = True


# ── Partners ─────────────────────────────────────────────────────────────────
class PartnerOut(BaseModel):
    id: uuid.UUID
    name: str
    location: Optional[str] = None
    image_url: Optional[str] = None
    email: Optional[str] = None
    phone: Optional[str] = None
    description: Optional[str] = None
    status: str
    rating: float
    meals_available: int
    meals_redeemed: int
    is_active: bool

    class Config:
        from_attributes = True


class PartnerApplyRequest(BaseModel):
    business_name: str
    owner_name: str
    email: EmailStr
    password: str = Field(min_length=6)
    phone: str
    location: str
    address: Optional[str] = None
    opening_time: Optional[str] = "07:00"
    closing_time: Optional[str] = "22:00"
    operating_days: Optional[List[str]] = []
    description: Optional[str] = ""
    cuisine_types: Optional[List[str]] = []
    seating_capacity: Optional[int] = None


# ── Meals ────────────────────────────────────────────────────────────────────
class MealOut(BaseModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    name: str
    description: Optional[str] = None
    category: str
    tier: str
    price_myr: float
    calories: Optional[int] = None
    prep_time_minutes: Optional[int] = None
    rating: float
    image_url: Optional[str] = None
    availability: str
    is_active: bool
    redemption_count: int
    partners: Optional[PartnerOut] = None

    class Config:
        from_attributes = True


class MealCreate(BaseModel):
    name: str
    description: Optional[str] = None
    category: str
    tier: str
    price_myr: float = 5.00
    calories: Optional[int] = None
    prep_time_minutes: Optional[int] = None
    image_url: Optional[str] = None
    availability: str = "available"


class MealUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    category: Optional[str] = None
    tier: Optional[str] = None
    price_myr: Optional[float] = None
    calories: Optional[int] = None
    prep_time_minutes: Optional[int] = None
    image_url: Optional[str] = None
    availability: Optional[str] = None
    is_active: Optional[bool] = None


# ── Subscriptions ────────────────────────────────────────────────────────────
class SubscriptionOut(BaseModel):
    id: uuid.UUID
    user_id: uuid.UUID
    meal_plan_id: uuid.UUID
    status: str
    credits_total: int
    credits_used: int
    credits_remaining: int = 0
    starts_at: datetime
    expires_at: Optional[datetime] = None
    meal_plans: Optional[MealPlanOut] = None

    class Config:
        from_attributes = True


# ── Malaysian Payments (DuitNow QR & E-Wallets) ──────────────────────────────
class CreatePaymentOrderRequest(BaseModel):
    plan_id: uuid.UUID
    payment_method: str = "duitnow_qr"  # Supported for launch: 'duitnow_qr', 'tng_ewallet'


class PaymentOrderOut(BaseModel):
    payment_id: uuid.UUID
    reference_code: str
    amount_myr: float
    credits: int
    plan_name: str
    payment_method: str
    qr_data: str
    qr_image_url: Optional[str] = None
    deep_link_url: Optional[str] = None
    checkout_url: Optional[str] = None
    hitpay_request_id: Optional[str] = None
    expires_at: datetime
    instructions: str



class PaymentStatusOut(BaseModel):
    reference_code: str
    status: str  # pending, completed, failed, expired
    amount_myr: float
    paid_at: Optional[datetime] = None
    subscription_id: Optional[uuid.UUID] = None


# ── Redemptions ──────────────────────────────────────────────────────────────
class RedemptionRequest(BaseModel):
    subscription_id: uuid.UUID
    meal_id: uuid.UUID
    partner_id: Optional[uuid.UUID] = None


class RedemptionOut(BaseModel):
    redemption_id: uuid.UUID
    status: str
    qr_token: str
    qr_code: str
    credits_remaining: int
    meal_name: str
    partner_name: Optional[str] = None
    redeemed_at: Optional[datetime] = None
    created_at: datetime


class VerifyQRRequest(BaseModel):
    qr_code_or_token: str


class VerifyQROut(BaseModel):
    valid: bool
    already_confirmed: bool = False
    student_name: str
    meal_name: str
    plan_name: str
    redemption_id: Optional[uuid.UUID] = None
    subscription_id: Optional[uuid.UUID] = None
    partner_id: Optional[uuid.UUID] = None
    credits_remaining: Optional[int] = None
    error: Optional[str] = None


class ConfirmRedemptionRequest(BaseModel):
    redemption_id: uuid.UUID


# ── Wallet & Ledger ──────────────────────────────────────────────────────────
class WalletTransactionOut(BaseModel):
    id: uuid.UUID
    description: str
    credits_delta: int
    balance_after: int
    created_at: datetime

    class Config:
        from_attributes = True


class WalletSummaryOut(BaseModel):
    active_subscription: Optional[SubscriptionOut] = None
    credits_remaining: int = 0
    credits_used: int = 0
    total_meals_purchased: int = 0
    recent_transactions: List[WalletTransactionOut] = []


class CancelSubscriptionRequest(BaseModel):
    subscription_id: uuid.UUID


# ── Settlements ──────────────────────────────────────────────────────────────
class SettlementOut(BaseModel):
    id: uuid.UUID
    partner_id: uuid.UUID
    period_start: datetime
    period_end: datetime
    total_redemptions: int
    total_amount_myr: float
    settlement_rate_myr: float
    status: str
    notes: Optional[str] = None
    payout_requested_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    payment_reference: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True
