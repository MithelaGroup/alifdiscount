from datetime import datetime
from enum import Enum
from sqlalchemy import (
    Integer, String, Boolean, DateTime, ForeignKey, Enum as SAEnum, Text, UniqueConstraint
)
from sqlalchemy.orm import relationship, Mapped, mapped_column, synonym

from app.database import Base


class Role(str, Enum):
    SUPERADMIN = "superadmin"
    ADMIN = "admin"
    CASHIER = "cashier"


class RequestStatus(str, Enum):
    PENDING = "pending"
    APPROVED = "approved"
    DONE = "done"


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    email: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    mobile_bd: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[Role] = mapped_column(SAEnum(Role, native_enum=False), default=Role.CASHIER, nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_email_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    requests_created = relationship(
        "CouponRequest", back_populates="cashier_user",
        foreign_keys="CouponRequest.cashier_user_id",
    )
    requests_referred = relationship(
        "CouponRequest", back_populates="reference_user",
        foreign_keys="CouponRequest.reference_user_id",
    )
    requests_approved = relationship(
        "CouponRequest", back_populates="approved_by_user",
        foreign_keys="CouponRequest.approved_by_user_id",
    )


class Contact(Base):
    """
    Matches your current DB:
      - has 'mobile' (NOT 'mobile_bd')
      - has 'full_name' and legacy 'name'
    We expose 'mobile_bd' as a synonym so old code that reads Contact.mobile_bd still works.
    """
    __tablename__ = "contacts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    # allow NULL here to be lenient with legacy rows; UI enforces a value on create
    full_name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    # actual column in DB
    mobile: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    # alias to keep compatibility with any code referencing mobile_bd
    mobile_bd = synonym("mobile")

    # legacy column still present in DB on some installs
    name: Mapped[str | None] = mapped_column(String(120), nullable=True)

    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CouponGroup(Base):
    __tablename__ = "coupon_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True, nullable=False)
    percent: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    coupons = relationship("Coupon", back_populates="group", cascade="all, delete-orphan")


class Coupon(Base):
    __tablename__ = "coupons"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(80), unique=True, nullable=False)
    group_id: Mapped[int] = mapped_column(ForeignKey("coupon_groups.id"), nullable=False)
    enlisted_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    assigned_request_id: Mapped[int | None] = mapped_column(ForeignKey("coupon_requests.id"), unique=True, nullable=True)
    assigned_to_name: Mapped[str | None] = mapped_column(String(120), nullable=True)
    assigned_to_mobile: Mapped[str | None] = mapped_column(String(20), nullable=True)
    assigned_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    assigned_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    group = relationship("CouponGroup", back_populates="coupons")

    assigned_request = relationship(
        "CouponRequest",
        back_populates="assigned_coupon",
        uselist=False,
        foreign_keys=[assigned_request_id],
    )


class CouponRequest(Base):
    __tablename__ = "coupon_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    request_code: Mapped[str] = mapped_column(String(32), unique=True, nullable=False)

    customer_name: Mapped[str] = mapped_column(String(120), nullable=False)
    customer_mobile: Mapped[str] = mapped_column(String(20), nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)

    discount_percent: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[RequestStatus] = mapped_column(SAEnum(RequestStatus, native_enum=False), default=RequestStatus.PENDING)

    cashier_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    reference_user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    approved_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)

    group_id: Mapped[int | None] = mapped_column(ForeignKey("coupon_groups.id"), nullable=True)
    invoice_number: Mapped[str | None] = mapped_column(String(64), nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    done_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    cashier_user = relationship("User", foreign_keys=[cashier_user_id], back_populates="requests_created")
    reference_user = relationship("User", foreign_keys=[reference_user_id], back_populates="requests_referred")
    approved_by_user = relationship("User", foreign_keys=[approved_by_user_id], back_populates="requests_approved")

    discount_group = relationship("CouponGroup")

    assigned_coupon = relationship(
        "Coupon",
        back_populates="assigned_request",
        uselist=False,
        primaryjoin="Coupon.assigned_request_id == CouponRequest.id",
    )


class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class PushSubscription(Base):
    __tablename__ = "push_subscriptions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    endpoint: Mapped[str] = mapped_column(Text, nullable=False)
    p256dh: Mapped[str] = mapped_column(Text, nullable=False)
    auth: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

    __table_args__ = (UniqueConstraint("endpoint", name="uq_push_endpoint"),)
