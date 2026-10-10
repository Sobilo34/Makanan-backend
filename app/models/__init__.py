import uuid
from datetime import datetime, timezone
from sqlalchemy import (
    Column,
    String,
    Boolean,
    Integer,
    Numeric,
    DateTime,
    ForeignKey,
    Text,
    CheckConstraint,
    ARRAY,
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship
from app.core.database import Base


def utcnow():
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), default="", nullable=False)
    student_id = Column(String(100), nullable=True)
    role = Column(String(50), default="student", nullable=False, index=True)
    avatar_url = Column(Text, nullable=True)
    phone = Column(String(50), nullable=True)
    university = Column(String(255), default="Albukhary International University")
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    partner = relationship("Partner", back_populates="user", uselist=False)
    subscriptions = relationship("Subscription", back_populates="user", cascade="all, delete-orphan")
    redemptions = relationship("Redemption", back_populates="user")
    payments = relationship("Payment", back_populates="user")
    wallet_transactions = relationship("WalletTransaction", back_populates="user")


class MealPlan(Base):
    __tablename__ = "meal_plans"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    tier = Column(String(50), nullable=False)
    price_myr = Column(Numeric(10, 2), nullable=False)
    credits = Column(Integer, nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    subscriptions = relationship("Subscription", back_populates="meal_plan")


class Partner(Base):
    __tablename__ = "partners"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    name = Column(String(255), nullable=False)
    location = Column(String(255), nullable=True)
    image_url = Column(Text, nullable=True)
    email = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    description = Column(Text, nullable=True)
    status = Column(String(50), default="active", nullable=False)
    rating = Column(Numeric(3, 1), default=4.5)
    meals_available = Column(Integer, default=0)
    meals_redeemed = Column(Integer, default=0)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="partner")
    meals = relationship("Meal", back_populates="partner", cascade="all, delete-orphan")
    settlements = relationship("Settlement", back_populates="partner", cascade="all, delete-orphan")


class PartnerApplication(Base):
    __tablename__ = "partner_applications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    business_name = Column(String(255), nullable=False)
    owner_name = Column(String(255), nullable=False)
    email = Column(String(255), nullable=False)
    phone = Column(String(50), nullable=False)
    location = Column(String(255), nullable=False)
    address = Column(Text, nullable=True)
    opening_time = Column(String(20), nullable=True)
    closing_time = Column(String(20), nullable=True)
    operating_days = Column(ARRAY(Text), nullable=True)
    description = Column(Text, nullable=True)
    cuisine_types = Column(ARRAY(Text), nullable=True)
    seating_capacity = Column(Integer, nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    admin_notes = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class Meal(Base):
    __tablename__ = "meals"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id = Column(UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    name = Column(String(255), nullable=False)
    description = Column(Text, nullable=True)
    category = Column(String(50), nullable=False)
    tier = Column(String(50), nullable=False)
    price_myr = Column(Numeric(10, 2), default=5.00, nullable=False)
    calories = Column(Integer, nullable=True)
    prep_time_minutes = Column(Integer, nullable=True)
    rating = Column(Numeric(3, 1), default=4.5)
    image_url = Column(Text, nullable=True)
    availability = Column(String(50), default="available", nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    redemption_count = Column(Integer, default=0, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    partner = relationship("Partner", back_populates="meals")


class Subscription(Base):
    __tablename__ = "subscriptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    meal_plan_id = Column(UUID(as_uuid=True), ForeignKey("meal_plans.id"), nullable=False)
    status = Column(String(50), default="active", nullable=False)
    credits_total = Column(Integer, nullable=False)
    credits_used = Column(Integer, default=0, nullable=False)
    starts_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    __table_args__ = (
        CheckConstraint("credits_used <= credits_total", name="chk_sub_credits_used_max"),
        CheckConstraint("credits_used >= 0", name="chk_sub_credits_used_min"),
    )

    user = relationship("User", back_populates="subscriptions")
    meal_plan = relationship("MealPlan", back_populates="subscriptions")
    redemptions = relationship("Redemption", back_populates="subscription")


class Settlement(Base):
    __tablename__ = "settlements"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    partner_id = Column(UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=False)
    period_start = Column(DateTime(timezone=True), nullable=False)
    period_end = Column(DateTime(timezone=True), nullable=False)
    total_redemptions = Column(Integer, default=0, nullable=False)
    total_amount_myr = Column(Numeric(10, 2), default=0.00, nullable=False)
    settlement_rate_myr = Column(Numeric(10, 2), default=0.00, nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    notes = Column(Text, nullable=True)
    payout_requested_at = Column(DateTime(timezone=True), nullable=True)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    payment_reference = Column(String(100), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    partner = relationship("Partner", back_populates="settlements")
    redemptions = relationship("Redemption", back_populates="settlement")


class Redemption(Base):
    __tablename__ = "redemptions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="CASCADE"), nullable=False)
    meal_id = Column(UUID(as_uuid=True), ForeignKey("meals.id", ondelete="RESTRICT"), nullable=False)
    partner_id = Column(UUID(as_uuid=True), ForeignKey("partners.id", ondelete="SET NULL"), nullable=True)
    settlement_id = Column(UUID(as_uuid=True), ForeignKey("settlements.id", ondelete="SET NULL"), nullable=True)
    status = Column(String(50), default="pending", nullable=False)
    qr_token = Column(Text, nullable=False)
    qr_code = Column(String(100), nullable=True)
    redeemed_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="redemptions")
    subscription = relationship("Subscription", back_populates="redemptions")
    meal = relationship("Meal")
    settlement = relationship("Settlement", back_populates="redemptions")


class Payment(Base):
    __tablename__ = "payments"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    meal_plan_id = Column(UUID(as_uuid=True), ForeignKey("meal_plans.id"), nullable=False)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    amount_myr = Column(Numeric(10, 2), nullable=False)
    payment_method = Column(String(50), default="duitnow_qr", nullable=False)
    status = Column(String(50), default="pending", nullable=False)
    reference_code = Column(String(100), unique=True, nullable=False, index=True)
    qr_data = Column(Text, nullable=True)
    gateway_transaction_id = Column(String(255), nullable=True)
    expires_at = Column(DateTime(timezone=True), nullable=False)
    paid_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)

    user = relationship("User", back_populates="payments")
    meal_plan = relationship("MealPlan")


class WalletTransaction(Base):
    __tablename__ = "wallet_transactions"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    subscription_id = Column(UUID(as_uuid=True), ForeignKey("subscriptions.id", ondelete="SET NULL"), nullable=True)
    redemption_id = Column(UUID(as_uuid=True), ForeignKey("redemptions.id", ondelete="SET NULL"), nullable=True)
    payment_id = Column(UUID(as_uuid=True), ForeignKey("payments.id", ondelete="SET NULL"), nullable=True)
    description = Column(String(255), nullable=False)
    credits_delta = Column(Integer, nullable=False)
    balance_after = Column(Integer, nullable=False)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)

    user = relationship("User", back_populates="wallet_transactions")


class Notification(Base):
    __tablename__ = "notifications"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=True)
    partner_id = Column(UUID(as_uuid=True), ForeignKey("partners.id", ondelete="CASCADE"), nullable=True)
    recipient_type = Column(String(20), default="student", nullable=False)
    type = Column(String(50), nullable=False)
    title = Column(String(255), nullable=False)
    message = Column(Text, nullable=False)
    is_read = Column(Boolean, default=False, nullable=False)
    metadata_ = Column("metadata", JSONB, default=dict)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class SupportTicket(Base):
    __tablename__ = "support_tickets"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    redemption_id = Column(UUID(as_uuid=True), ForeignKey("redemptions.id", ondelete="SET NULL"), nullable=True)
    category = Column(String(50), default="other", nullable=False)
    subject = Column(String(255), nullable=False)
    description = Column(Text, nullable=False)
    status = Column(String(50), default="open", nullable=False)
    admin_notes = Column(Text, nullable=True)
    resolved_at = Column(DateTime(timezone=True), nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at = Column(DateTime(timezone=True), default=utcnow, onupdate=utcnow, nullable=False)


class Feedback(Base):
    __tablename__ = "feedback"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    user_id = Column(UUID(as_uuid=True), ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    redemption_id = Column(UUID(as_uuid=True), ForeignKey("redemptions.id", ondelete="SET NULL"), nullable=True)
    meal_id = Column(UUID(as_uuid=True), ForeignKey("meals.id", ondelete="SET NULL"), nullable=True)
    partner_id = Column(UUID(as_uuid=True), ForeignKey("partners.id", ondelete="SET NULL"), nullable=True)
    rating = Column(Integer, nullable=False)
    comment = Column(Text, nullable=True)
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)


class WaitlistSignup(Base):
    __tablename__ = "waitlist_signup"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    email = Column(String(255), unique=True, nullable=False)
    full_name = Column(String(255), default="")
    created_at = Column(DateTime(timezone=True), default=utcnow, nullable=False)
