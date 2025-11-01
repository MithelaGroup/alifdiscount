# app/utils.py
from __future__ import annotations

import os
import re
from datetime import datetime
from typing import Optional

from fastapi import Request
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from passlib.context import CryptContext
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.models import User, CouponRequest, Role

# -------------------------------------------------------------------
# Password hashing / verification
# Use ONLY pbkdf2_sha256 to match your existing $pbkdf2-sha256$ hashes
# -------------------------------------------------------------------
_pwd_ctx = CryptContext(schemes=["pbkdf2_sha256"], deprecated="auto")

def hash_password(password: str) -> str:
    return _pwd_ctx.hash(password)

def verify_password(password: str, hashed: str) -> bool:
    try:
        return _pwd_ctx.verify(password, hashed)
    except Exception:
        return False

# -------------------------------------------------------------------
# Email verification tokens
# -------------------------------------------------------------------
def get_verification_serializer() -> URLSafeTimedSerializer:
    secret = getattr(settings, "SECRET_KEY", None) or os.getenv("SECRET_KEY", "change-this-secret")
    return URLSafeTimedSerializer(secret_key=secret, salt="email-verify")

def generate_email_token(email: str) -> str:
    return get_verification_serializer().dumps(email)

def confirm_email_token(token: str, max_age: int = 60 * 60 * 24 * 2) -> Optional[str]:
    s = get_verification_serializer()
    try:
        return s.loads(token, max_age=max_age)
    except (BadSignature, SignatureExpired):
        return None

# Alias some code may import
verify_email_token = confirm_email_token

# -------------------------------------------------------------------
# Sessions / auth helpers
# -------------------------------------------------------------------
def login_user(request: Request, user: User) -> None:
    request.session.clear()
    request.session["uid"] = user.id
    request.session["username"] = user.username
    request.session["role"] = getattr(user.role, "value", user.role)

def logout_user(request: Request) -> None:
    request.session.clear()

def get_current_user(request: Request, db: Session) -> Optional[User]:
    uid = request.session.get("uid")
    if not uid:
        return None
    return db.get(User, uid)

def user_has_role(user: User, roles: list[Role]) -> bool:
    return user.role in roles

# -------------------------------------------------------------------
# Phone normalization (Bangladesh)
# -------------------------------------------------------------------
def normalize_bd_mobile(raw: str) -> str:
    """
    Normalize to +8801XXXXXXXXX. Accepts 01XXXXXXXXX, 8801XXXXXXXXX, +8801XXXXXXXXX.
    """
    digits = re.sub(r"\D", "", raw or "")
    if digits.startswith("8801") and len(digits) == 13:
        rest = digits[3:]
    elif digits.startswith("01") and len(digits) == 11:
        rest = digits
    elif len(digits) == 10 and digits.startswith("1"):
        rest = "0" + digits
    else:
        if len(digits) >= 10 and digits[-10:].startswith("1"):
            rest = "0" + digits[-10:]
        else:
            rest = digits
    if rest.startswith("0"):
        rest = rest[1:]
    return "+880" + rest

# -------------------------------------------------------------------
# Request code generator
# -------------------------------------------------------------------
def generate_request_code(db: Session, now: Optional[datetime] = None) -> str:
    """
    Format: 'YY-MMNNNN' e.g. '25-10001' for the first request in Oct 2025.
    """
    now = now or datetime.utcnow()
    yy = now.year % 100
    mm = now.month
    prefix = f"{yy:02d}-{mm:02d}"
    last = db.execute(
        select(CouponRequest.request_code)
        .where(CouponRequest.request_code.like(f"{prefix}%"))
        .order_by(CouponRequest.id.desc())
        .limit(1)
    ).scalar_one_or_none()
    if last and last.startswith(prefix):
        tail = last.replace(prefix, "")
        try:
            seq = int(tail) + 1
        except ValueError:
            seq = 1
    else:
        seq = 1
    return f"{prefix}{seq:04d}"
