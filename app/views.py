from typing import Any, Dict, Optional
from fastapi import Request
from starlette.responses import RedirectResponse, Response

from app.database import SessionLocal

# import models *safely* so missing tables don't crash the app
import app.models as models  # type: ignore
try:
    import app.models_contact as models_contact  # type: ignore
except Exception:  # pragma: no cover
    models_contact = None


# ----- helpers -------------------------------------------------------------

def current_user(request: Request) -> Optional[Dict[str, Any]]:
    return request.session.get("user")


def render(request: Request, template: str, ctx: Dict[str, Any]) -> Response:
    base = {
        "request": request,
        "user": current_user(request),
        "conf": getattr(request.app.state, "conf", None),
    }
    base.update(ctx)
    return request.app.state.templates.TemplateResponse(template, base)  # type: ignore[attr-defined]


def require_login(request: Request) -> Optional[RedirectResponse]:
    if not current_user(request):
        return RedirectResponse("/login", status_code=302)
    return None


# ----- pages ---------------------------------------------------------------

def home(request: Request):
    return RedirectResponse("/dashboard", status_code=302)


def dashboard(request: Request):
    # Allow public dashboard; comment the next 2 lines if you want it protected:
    # guard = require_login(request)
    # if guard: return guard

    db = SessionLocal()
    try:
        CouponRequest = getattr(models, "CouponRequest", None)
        counts = {"pending": 0, "approved": 0, "done": 0}
        latest = []

        if CouponRequest is not None:
            # status field might be Enum or str; use plain string values you already use in DB
            try:
                counts["pending"] = db.query(CouponRequest).filter(CouponRequest.status == "requested").count()  # type: ignore[attr-defined]
                counts["approved"] = db.query(CouponRequest).filter(CouponRequest.status == "approved").count()   # type: ignore[attr-defined]
                counts["done"] = db.query(CouponRequest).filter(CouponRequest.status == "completed").count()      # type: ignore[attr-defined]
            except Exception:
                pass
            try:
                latest = (
                    db.query(CouponRequest)
                    .order_by(CouponRequest.created_at.desc())  # type: ignore[attr-defined]
                    .limit(10)
                    .all()
                )
            except Exception:
                latest = []

        return render(request, "dashboard.html", {"counts": counts, "latest_requests": latest})
    finally:
        db.close()


def contacts(request: Request):
    # guard = require_login(request)
    # if guard: return guard

    db = SessionLocal()
    try:
        rows = []
        if models_contact is not None and hasattr(models_contact, "Contact"):
            Contact = getattr(models_contact, "Contact")
            try:
                rows = db.query(Contact).order_by(Contact.id.desc()).all()  # type: ignore[attr-defined]
            except Exception:
                rows = []
        return render(request, "contacts.html", {"rows": rows})
    finally:
        db.close()


def enlist(request: Request):
    guard = require_login(request)
    if guard:
        return guard

    db = SessionLocal()
    try:
        DiscountGroup = getattr(models, "DiscountGroup", None)
        Coupon = getattr(models, "Coupon", None)

        groups, coupons = [], []
        if DiscountGroup is not None:
            try:
                groups = db.query(DiscountGroup).order_by(DiscountGroup.created_at.desc()).all()  # type: ignore[attr-defined]
            except Exception:
                groups = []
        if Coupon is not None:
            try:
                coupons = db.query(Coupon).order_by(Coupon.created_at.desc()).all()  # type: ignore[attr-defined]
            except Exception:
                coupons = []

        return render(request, "enlist.html", {"groups": groups, "coupons": coupons})
    finally:
        db.close()


def users(request: Request):
    guard = require_login(request)
    if guard:
        return guard

    db = SessionLocal()
    try:
        User = getattr(models, "User", None)
        rows = []
        if User is not None:
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
        CouponRequest = getattr(models, "CouponRequest", None)
        rows = []
        if CouponRequest is not None:
            try:
                rows = (
                    db.query(CouponRequest)
                    .order_by(CouponRequest.created_at.desc())  # type: ignore[attr-defined]
                    .limit(10)
                    .all()
                )
            except Exception:
                rows = []
        return render(request, "requests.html", {"rows": rows})
    finally:
        db.close()


def request_new(request: Request):
    guard = require_login(request)
    if guard:
        return guard

    db = SessionLocal()
    try:
        # preload simple dropdowns if you need (cashiers, references)
        User = getattr(models, "User", None)
        refs = []
        if User is not None:
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

    return render(request, "settings.html", {})


def pwa(request: Request):
    return render(request, "pwa.html", {})


# ----- register routes -----------------------------------------------------

def register_routes(app):
    app.add_api_route("/", home, methods=["GET"], name="home")
    app.add_api_route("/dashboard", dashboard, methods=["GET"], name="dashboard")

    app.add_api_route("/contacts", contacts, methods=["GET"], name="contacts")
    app.add_api_route("/enlist", enlist, methods=["GET"], name="enlist")

    app.add_api_route("/users", users, methods=["GET"], name="users")

    app.add_api_route("/requests", requests_list, methods=["GET"], name="requests")
    app.add_api_route("/request/create", request_new, methods=["GET"], name="request_create")

    app.add_api_route("/settings", settings, methods=["GET"], name="settings")
    app.add_api_route("/pwa", pwa, methods=["GET"], name="pwa")
