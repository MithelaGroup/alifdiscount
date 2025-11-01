# app/views.py
from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import select, func
from sqlalchemy.orm import Session

from app.database import get_db
from app.utils import get_current_user
from app.models import User, Contact, CouponRequest

BASE_DIR = Path(__file__).resolve().parents[1]
templates_fallback = Jinja2Templates(directory=str(BASE_DIR / "templates"))

def render(request: Request, template_name: str, context: dict):
    tmpl = getattr(request.app.state, "templates", templates_fallback)
    return tmpl.TemplateResponse(template_name, context)

router = APIRouter()

def _require_login(request: Request, db: Session) -> User:
    user = get_current_user(request, db)
    if not user:
        return None  # We'll redirect below instead of raising
    return user

def _is_admin(user: User) -> bool:
    role = (user.role or "").upper()
    return role in {"ADMIN", "SUPERADMIN"}

def _display_name_and_mobile(req: CouponRequest) -> tuple[str, str]:
    name = ""
    mobile = ""
    if getattr(req, "contact", None):
        c = req.contact
        name = (getattr(c, "full_name", None) or getattr(c, "name", "") or "").strip()
        mobile = (getattr(c, "mobile", "") or "").strip()
    name = name or getattr(req, "customer_name", "") or ""
    mobile = mobile or getattr(req, "customer_mobile", "") or ""
    return name, mobile

@router.get("/")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = get_current_user(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/", status_code=307)

    q_base = select(CouponRequest).order_by(CouponRequest.created_at.desc())

    pending = db.execute(q_base.where(CouponRequest.status == "PENDING")).scalars().all()
    approved = db.execute(q_base.where(CouponRequest.status == "APPROVED")).scalars().all()
    done = db.execute(q_base.where(CouponRequest.status == "DONE")).scalars().all()

    def _augment(rows):
        out = []
        for r in rows:
            name, mobile = _display_name_and_mobile(r)
            ref_user = getattr(r, "reference_user", None)
            ref_username = getattr(ref_user, "username", "") if ref_user else ""
            assigned = getattr(r, "assigned_coupon", None)
            assigned_code = getattr(assigned, "code", "") if assigned else ""
            out.append(
                {
                    "id": r.id,
                    "request_code": getattr(r, "request_code", ""),
                    "status": r.status,
                    "created_at": r.created_at,
                    "discount_percent": getattr(r, "discount_percent", None),
                    "invoice_number": getattr(r, "invoice_number", ""),
                    "customer_name": name,
                    "customer_mobile": mobile,
                    "reference_username": ref_username,
                    "assigned_coupon_code": assigned_code,
                }
            )
        return out

    ctx = {
        "request": request,
        "user": user,
        "pending": _augment(pending),
        "approved": _augment(approved),
        "done": _augment(done),
        "can_act": _is_admin(user),
    }
    return render(request, "dashboard.html", ctx)

@router.get("/dashboard")
def dashboard_alias():
    return RedirectResponse(url="/", status_code=307)

@router.get("/contacts")
def contacts(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/contacts", status_code=307)

    items = db.execute(
        select(Contact).order_by(
            func.coalesce(Contact.full_name, Contact.name),
            Contact.id.asc(),
        )
    ).scalars().all()
    return render(request, "contacts.html", {"request": request, "user": user, "items": items})

@router.get("/requests")
def requests_list(request: Request, db: Session = Depends(get_db)):
    user = _require_login(request, db)
    if not user:
        return RedirectResponse(url="/login?next=/requests", status_code=307)

    rows = db.execute(select(CouponRequest).order_by(CouponRequest.created_at.desc())).scalars().all()

    data = []
    for r in rows:
        name, mobile = _display_name_and_mobile(r)
        ref_user = getattr(r, "reference_user", None)
        ref_username = getattr(ref_user, "username", "") if ref_user else ""
        data.append(
            {
                "id": r.id,
                "request_code": getattr(r, "request_code", ""),
                "status": r.status,
                "created_at": r.created_at,
                "customer_name": name,
                "customer_mobile": mobile,
                "reference_username": ref_username,
            }
        )

    return render(
        request,
        "requests.html",
        {"request": request, "user": user, "items": data, "can_act": _is_admin(user)},
    )
