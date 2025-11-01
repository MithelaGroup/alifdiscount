# app/views.py
from __future__ import annotations

from contextlib import contextmanager
from typing import Any, Dict, Iterable, Optional

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from starlette.status import HTTP_302_FOUND

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import (
    Coupon,
    CouponGroup,
    CouponRequest,
    RequestStatus,
    User,
)

# ------------------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------------------

@contextmanager
def get_session() -> Iterable[Session]:
    """
    Wrap the FastAPI-style generator `get_db()` in a context manager
    so existing `with get_session() as db:` usages work and the session
    is always closed.
    """
    gen = get_db()
    db = next(gen)
    try:
        yield db
    finally:
        try:
            gen.close()
        except Exception:
            pass


def render(request: Request, template_name: str, ctx: Dict[str, Any]) -> Any:
    # `now()` is already registered in main.py, we only pass context here
    context = {"request": request, **ctx}
    return request.app.state.templates.TemplateResponse(template_name, context)  # type: ignore[attr-defined]


# ------------------------------------------------------------------------------
# Pages
# ------------------------------------------------------------------------------

def home(request: Request):
    return RedirectResponse("/dashboard", status_code=HTTP_302_FOUND)


def dashboard(request: Request):
    with get_session() as db:
        # counts
        pending_count = db.scalar(
            select(func.count(CouponRequest.id)).where(CouponRequest.status == RequestStatus.PENDING)
        ) or 0
        approved_count = db.scalar(
            select(func.count(CouponRequest.id)).where(CouponRequest.status == RequestStatus.APPROVED)
        ) or 0
        done_count = db.scalar(
            select(func.count(CouponRequest.id)).where(CouponRequest.status == RequestStatus.DONE)
        ) or 0

        # latest 10 requests w/ relationships
        latest = (
            db.query(CouponRequest)
            .options(
                joinedload(CouponRequest.cashier_user),
                joinedload(CouponRequest.reference_user),
                joinedload(CouponRequest.approved_by_user),
                joinedload(CouponRequest.assigned_coupon).joinedload(Coupon.group),
                joinedload(CouponRequest.discount_group),
            )
            .order_by(CouponRequest.id.desc())
            .limit(10)
            .all()
        )

        return render(
            request,
            "dashboard.html",
            {
                "pending_count": pending_count,
                "approved_count": approved_count,
                "done_count": done_count,
                "latest_requests": latest,
            },
        )


def contacts(request: Request):
    with get_session() as db:
        rows = db.execute(select(User).order_by(User.username.asc())).scalars().all()
        return render(request, "contacts.html", {"users": rows})


def requests_list(request: Request):
    with get_session() as db:
        rows = (
            db.query(CouponRequest)
            .options(
                joinedload(CouponRequest.cashier_user),
                joinedload(CouponRequest.reference_user),
                joinedload(CouponRequest.approved_by_user),
                joinedload(CouponRequest.assigned_coupon).joinedload(Coupon.group),
                joinedload(CouponRequest.discount_group),
            )
            .order_by(CouponRequest.id.desc())
            .limit(50)
            .all()
        )
        return render(request, "requests.html", {"rows": rows})


def users(request: Request):
    with get_session() as db:
        rows = db.execute(select(User).order_by(User.username.asc())).scalars().all()
        return render(request, "users.html", {"rows": rows})


def settings(request: Request):
    return render(request, "settings.html", {})


def pwa_page(request: Request):
    return render(request, "placeholder.html", {"title": "PWA"})


# --- Enlist page (GET only, keep your existing forms/templates) ----------------

def enlist_get(request: Request):
    with get_session() as db:
        groups = db.execute(select(CouponGroup).order_by(CouponGroup.percent)).scalars().all()
        coupons = (
            db.query(Coupon)
            .options(joinedload(Coupon.group), joinedload(Coupon.assigned_request))
            .order_by(Coupon.id.desc())
            .limit(500)
            .all()
        )
        return render(request, "coupon_enlist.html", {"groups": groups, "coupons": coupons})


# ------------------------------------------------------------------------------
# Route registration (called from app/main.py)
# ------------------------------------------------------------------------------

def register_routes(app: FastAPI) -> None:
    app.get("/", name="home")(home)
    app.get("/dashboard", name="dashboard")(dashboard)

    app.get("/contacts", name="contacts")(contacts)
    app.get("/requests", name="requests")(requests_list)
    app.get("/users", name="users")(users)
    app.get("/settings", name="settings")(settings)
    app.get("/pwa", name="pwa")(pwa_page)

    app.get("/enlist", name="enlist")(enlist_get)
