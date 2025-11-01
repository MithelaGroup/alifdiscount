from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import APIRouter, Depends, Form, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import asc, desc, func, select
from sqlalchemy.orm import Session

# --- database session dependency ------------------------------------------------
try:
    # your project has app.database with SessionLocal/get_db in the repo
    from app.database import get_db  # type: ignore
except Exception:  # pragma: no cover
    def get_db():  # very small fallback; you should never hit this
        raise RuntimeError("get_db not found; please keep app/database.py as in repo")

# --- models (import defensively, names sometimes moved across files) ------------
# Users
try:
    from app.models import User  # type: ignore
except Exception:
    User = None  # type: ignore

# Contacts
try:
    from app.models_contact import Contact  # type: ignore
except Exception:
    try:
        from app.models import Contact  # type: ignore
    except Exception:
        Contact = None  # type: ignore

# Coupons, groups, requests
DiscountGroup = None
Coupon = None
CouponRequest = None
RequestStatus = None

try:
    from app.models import DiscountGroup as _DG  # type: ignore
    DiscountGroup = _DG
except Exception:
    try:
        from app.models import CouponGroup as _DG  # type: ignore
        DiscountGroup = _DG
    except Exception:
        pass

try:
    from app.models import Coupon as _CP  # type: ignore
    Coupon = _CP
except Exception:
    pass

try:
    from app.models import CouponRequest as _CR  # type: ignore
    CouponRequest = _CR
except Exception:
    pass

try:
    from app.models import RequestStatus as _RS  # type: ignore
    RequestStatus = _RS
except Exception:
    # final fallback
    class _RSF:  # pragma: no cover
        PENDING = "PENDING"
        APPROVED = "APPROVED"
        DONE = "DONE"
        REJECTED = "REJECTED"
    RequestStatus = _RSF  # type: ignore


router = APIRouter()


# ------------------------------------------------------------------------------
# helpers
# ------------------------------------------------------------------------------

def render(request: Request, template_name: str, context: Dict[str, Any]):
    ctx = {"request": request, **context}
    return request.app.state.templates.TemplateResponse(template_name, ctx)  # type: ignore[attr-defined]


def safe(obj: Any, attr: str, default: Any = None):
    try:
        return getattr(obj, attr)
    except Exception:
        return default


def safe_name(user: Any) -> str:
    if not user:
        return ""
    return safe(user, "full_name", None) or safe(user, "username", None) or safe(user, "email", "") or ""


def as_request_row(r: Any) -> Dict[str, Any]:
    """Flatten a CouponRequest to a dict the templates can use safely."""
    ref_user = safe(r, "reference_user")
    cashier = safe(r, "cashier")
    approver = safe(r, "approved_by") or safe(r, "approver") or safe(r, "approved_by_user")
    coupon = safe(r, "assigned_coupon")

    return {
        "id": safe(r, "id"),
        "request_code": safe(r, "request_code") or safe(r, "code"),
        "customer_name": safe(r, "customer_name") or safe(r, "customer_full_name") or "",
        "customer_mobile": safe(r, "customer_mobile") or safe(r, "mobile") or "",
        "status": safe(r, "status"),
        "discount_percent": safe(r, "discount_percent"),
        "invoice_number": safe(r, "invoice_number"),
        "discount_amount": safe(r, "discount_amount"),
        "reference_name": safe_name(ref_user),
        "cashier_name": safe_name(cashier),
        "approved_by_name": safe_name(approver),
        "coupon_code": safe(coupon, "code"),
        "created_at": safe(r, "created_at"),
    }


def paginate_query(query, page: int, per_page: int):
    return query.limit(per_page).offset((page - 1) * per_page)


# ------------------------------------------------------------------------------
# routes
# ------------------------------------------------------------------------------

@router.get("/")
def home() -> RedirectResponse:
    return RedirectResponse(url="/dashboard", status_code=307)


@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """
    Renders the 3 tiles (pending/approved/done) and the table of latest 10 requests.
    Works even if some relationships are missing – we won't eager load attributes
    that error'd in your logs (e.g. `CouponRequest.approved_by`).
    """
    if not CouponRequest:
        return render(request, "message.html", {"title": "Setup error", "message": "CouponRequest model not found."})

    # counts + small lists for the tiles
    def qstatus(status_value):
        return select(CouponRequest).where(CouponRequest.status == status_value).order_by(desc(CouponRequest.created_at))  # type: ignore

    pending = [as_request_row(r) for r in db.execute(paginate_query(qstatus(RequestStatus.PENDING), 1, 5)).scalars().all()]  # type: ignore
    approved = [as_request_row(r) for r in db.execute(paginate_query(qstatus(RequestStatus.APPROVED), 1, 5)).scalars().all()]  # type: ignore
    done = [as_request_row(r) for r in db.execute(paginate_query(qstatus(RequestStatus.DONE), 1, 5)).scalars().all()]  # type: ignore

    def count(status_value) -> int:
        return db.scalar(select(func.count()).select_from(CouponRequest).where(CouponRequest.status == status_value)) or 0  # type: ignore

    # latest 10 for table
    latest = [as_request_row(r) for r in db.execute(
        select(CouponRequest).order_by(desc(CouponRequest.created_at)).limit(10)  # type: ignore
    ).scalars().all()]

    ctx = {
        "pending": pending,
        "approved": approved,
        "done": done,
        "count_pending": count(RequestStatus.PENDING),
        "count_approved": count(RequestStatus.APPROVED),
        "count_done": count(RequestStatus.DONE),
        "latest": latest,
    }
    return render(request, "dashboard.html", ctx)


@router.get("/requests")
def requests_list(request: Request, page: int = 1, per: int = 10, db: Session = Depends(get_db)):
    if not CouponRequest:
        return render(request, "message.html", {"title": "Setup error", "message": "CouponRequest model not found."})

    page = max(1, page)
    per = max(1, min(per, 50))

    base_q = select(CouponRequest).order_by(desc(CouponRequest.created_at))  # type: ignore
    rows = [as_request_row(r) for r in db.execute(paginate_query(base_q, page, per)).scalars().all()]
    total = db.scalar(select(func.count()).select_from(CouponRequest)) or 0  # type: ignore
    has_next = (page * per) < total
    has_prev = page > 1

    return render(
        request,
        "requests.html",
        {"rows": rows, "page": page, "per": per, "has_next": has_next, "has_prev": has_prev, "total": total},
    )


@router.post("/requests/{rid}/approve")
def request_approve(
    request: Request,
    rid: int,
    group_id: int = Form(...),
    db: Session = Depends(get_db),
):
    """
    Approve: choose a discount group, auto-pick one available coupon,
    mark request APPROVED, set discount_percent from group, set 'approved_by' if such field exists.
    """
    if not (CouponRequest and Coupon and DiscountGroup):
        return render(request, "message.html", {"title": "Setup error", "message": "Models missing in server."})

    req = db.get(CouponRequest, rid)  # type: ignore
    if not req:
        return render(request, "message.html", {"title": "Not found", "message": "Request not found."})

    group = db.get(DiscountGroup, group_id)  # type: ignore
    if not group:
        return render(request, "message.html", {"title": "Not found", "message": "Discount group not found."})

    # pick one unassigned coupon in this group
    coupon = db.execute(
        select(Coupon).where((Coupon.group_id == group.id) & (Coupon.request_id.is_(None)))  # type: ignore
        .order_by(asc(Coupon.id))  # type: ignore
        .limit(1)
    ).scalars().first()

    if not coupon:
        return render(
            request, "message.html",
            {"title": "No stock", "message": f"No available coupon in '{getattr(group, 'name', 'group')}'."},
        )

    # attach coupon and mark approved
    setattr(req, "status", RequestStatus.APPROVED)
    setattr(req, "discount_percent", getattr(group, "percent", None) or getattr(group, "percentage", None))
    setattr(req, "assigned_coupon", coupon)
    setattr(coupon, "request_id", getattr(req, "id", None))  # be robust if backref missing

    # set approved_by if field exists on model/session
    session_user = request.session.get("user") if hasattr(request, "session") else None
    approver_id = (session_user or {}).get("id") if isinstance(session_user, dict) else None
    for field in ("approved_by_id", "approver_id"):
        if hasattr(req, field) and approver_id:
            setattr(req, field, approver_id)

    db.commit()
    return RedirectResponse(url="/requests", status_code=303)


@router.post("/requests/{rid}/reject")
def request_reject(request: Request, rid: int, db: Session = Depends(get_db)):
    if not CouponRequest:
        return render(request, "message.html", {"title": "Setup error", "message": "CouponRequest model not found."})

    req = db.get(CouponRequest, rid)  # type: ignore
    if not req:
        return render(request, "message.html", {"title": "Not found", "message": "Request not found."})

    setattr(req, "status", RequestStatus.REJECTED)
    db.commit()
    return RedirectResponse(url="/requests", status_code=303)


@router.post("/requests/{rid}/done")
def request_done(
    request: Request,
    rid: int,
    invoice_number: str = Form(...),
    discount_amount: Optional[float] = Form(None),
    db: Session = Depends(get_db),
):
    if not CouponRequest:
        return render(request, "message.html", {"title": "Setup error", "message": "CouponRequest model not found."})

    req = db.get(CouponRequest, rid)  # type: ignore
    if not req:
        return render(request, "message.html", {"title": "Not found", "message": "Request not found."})

    setattr(req, "invoice_number", invoice_number)
    if discount_amount is not None:
        try:
            setattr(req, "discount_amount", float(discount_amount))
        except Exception:
            pass
    setattr(req, "status", RequestStatus.DONE)
    db.commit()
    return RedirectResponse(url="/requests", status_code=303)


# --- simple pages so routes exist and render -----------------------------------

@router.get("/contacts")
def contacts_page(request: Request, db: Session = Depends(get_db)):
    rows = []
    if Contact:
        rows = db.execute(select(Contact).order_by(asc(Contact.full_name))).scalars().all()  # type: ignore
    return render(request, "contacts.html", {"contacts": rows})


@router.get("/enlist")
def coupons_page(request: Request, db: Session = Depends(get_db)):
    groups, coupons = [], []
    if DiscountGroup:
        groups = db.execute(select(DiscountGroup).order_by(asc(DiscountGroup.name))).scalars().all()  # type: ignore
    if Coupon:
        coupons = db.execute(select(Coupon).order_by(asc(Coupon.id))).scalars().all()  # type: ignore
    return render(request, "coupons.html", {"groups": groups, "coupons": coupons})


@router.get("/users")
def users_page(request: Request, db: Session = Depends(get_db)):
    users = []
    if User:
        users = db.execute(select(User).order_by(asc(User.id))).scalars().all()  # type: ignore
    return render(request, "users.html", {"users": users})


@router.get("/settings")
def settings_page(request: Request):
    return render(request, "settings.html", {})


# Optional: simple PWA helper page (your static SW still handles most)
@router.get("/pwa")
def pwa_page(request: Request):
    return render(request, "placeholder.html", {"title": "PWA", "message": "PWA is enabled."})
