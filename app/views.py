from typing import Any, Dict, List, Optional
from datetime import datetime

from fastapi import Request
from starlette.responses import RedirectResponse, Response
from sqlalchemy.orm import joinedload

# DB session
from app.database import SessionLocal

# Models (import what exists; ignore if a file is missing)
from app.models import (
    User,
    Coupon,
    CouponRequest,
    DiscountGroup,
)  # type: ignore

try:
    from app.models_contact import Contact  # type: ignore
except Exception:  # pragma: no cover
    Contact = None  # optional table in your repo


# ---------- helpers ----------

def current_user(request: Request) -> Optional[Dict[str, Any]]:
    """
    Your auth logic stores a user dict in session (auth.py).
    This reads it safely for templates and guards.
    """
    user = request.session.get("user")
    return user


def render(request: Request, template_name: str, context: Dict[str, Any]) -> Response:
    """
    Single place to render templates and always inject common values:
      - user (for header & permissions)
      - conf (for APP_BASE_URL and similar)
    """
    base = {
        "request": request,
        "user": current_user(request),
        "conf": getattr(request.app.state, "conf", None),
    }
    base.update(context)
    return request.app.state.templates.TemplateResponse(template_name, base)  # type: ignore[attr-defined]


def require_login(request: Request) -> Optional[RedirectResponse]:
    """Redirect unauthenticated users to /login."""
    if not current_user(request):
        return RedirectResponse("/login", status_code=302)
    return None


# ---------- pages ----------

def dashboard(request: Request):
    # Optional login wall: uncomment if you want dashboard locked down
    # guard = require_login(request)
    # if guard: return guard

    db = SessionLocal()
    try:
        # counts by status (be lenient with enum/strings)
        def _count(st: str) -> int:
            try:
                return (
                    db.query(CouponRequest)
                    .filter(CouponRequest.status == st)  # type: ignore[attr-defined]
                    .count()
                )
            except Exception:
                return 0

        counts = {
            "pending": _count("requested"),
            "approved": _count("approved"),
            "done": _count("completed"),
        }

        # latest 10 requests (no heavy joins to avoid model attr mismatches)
        try:
            latest = (
                db.query(CouponRequest)
                .order_by(CouponRequest.created_at.desc())  # type: ignore[attr-defined]
                .limit(10)
                .all()
            )
        except Exception:
            latest = []

        return render(
            request,
            "dashboard.html",
            {
                "counts": counts,
                "latest_requests": latest,
            },
        )
    finally:
        db.close()


def contacts(request: Request):
    # guard = require_login(request)
    # if guard: return guard

    db = SessionLocal()
    try:
        rows = []
        if Contact:
            try:
                rows = db.query(Contact).order_by(Contact.id.desc()).all()  # type: ignore[attr-defined]
            except Exception:
                rows = []
        return render(request, "contacts.html", {"rows": rows})
    finally:
        db.close()


def enlist(request: Request):
    # Only allow logged-in staff
    guard = require_login(request)
    if guard:
        return guard

    db = SessionLocal()
    try:
        groups = []
        coupons = []
        try:
            groups = db.query(DiscountGroup).order_by(DiscountGroup.created_at.desc()).all()  # type: ignore[attr-defined]
        except Exception:
            groups = []

        try:
            coupons = (
                db.query(Coupon)
                .order_by(Coupon.created_at.desc())  # type: ignore[attr-defined]
                .all()
            )
        except Exception:
            coupons = []

        return render(
            request,
            "enlist.html",
            {
                "groups": groups,
                "coupons": coupons,
            },
        )
    finally:
        db.close()


def users(request: Request):
    guard = require_login(request)
    if guard:
        return guard

    db = SessionLocal()
    try:
        rows = []
        try:
            rows = db.query(User).order_by(User.id.desc()).all()  # type: ignore[attr-defined]
        except Exception:
            rows = []
        return render(request, "users.html", {"rows": rows})
    finally:
        db.close()


def requests_list(request: Request):
    guard = require_login(request)
    if guard:
        return guard

    db = SessionLocal()
    try:
        try:
            latest = (
                db.query(CouponRequest)
                .order_by(CouponRequest.created_at.desc())  # type: ignore[attr-defined]
                .limit(10)
                .all()
            )
        except Exception:
            latest = []

        return render(
            request,
            "requests.html",
            {"rows": latest},
        )
    finally:
        db.close()


def request_new(request: Request):
    guard = require_login(request)
    if guard:
        return guard

    db = SessionLocal()
    try:
        # Load simple dropdown data if needed (cashiers, refs, etc.)
        try:
            refs = db.query(User).all()  # type: ignore[attr-defined]
        except Exception:
            refs = []
        return render(request, "request_new.html", {"refs": refs})
    finally:
        db.close()


def settings(request: Request):
    guard = require_login(request)
    if guard:
        return guard

    # conf is injected by render(); nothing else is required here
    return render(request, "settings.html", {})


def pwa(request: Request):
    return render(request, "pwa.html", {})


# ---------- route registration ----------

def register_routes(app):
    """
    One function that registers all page routes on the FastAPI app.
    Keeping routes together makes it easy to compare with your repo.
    """
    app.add_api_route("/dashboard", dashboard, methods=["GET"], name="dashboard")
    app.add_api_route("/", dashboard, methods=["GET"], name="home")

    app.add_api_route("/contacts", contacts, methods=["GET"], name="contacts")
    app.add_api_route("/enlist", enlist, methods=["GET"], name="enlist")

    app.add_api_route("/users", users, methods=["GET"], name="users")

    app.add_api_route("/requests", requests_list, methods=["GET"], name="requests")
    app.add_api_route("/request/create", request_new, methods=["GET"], name="request_create")

    app.add_api_route("/settings", settings, methods=["GET"], name="settings")
    app.add_api_route("/pwa", pwa, methods=["GET"], name="pwa")
