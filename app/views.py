from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import func, or_
from sqlalchemy.orm import joinedload, Session

from app.database import get_session  # must return a SQLAlchemy Session
from app.config import settings
from app.models import (
    User,
    Contact,
    Coupon,
    CouponGroup,        # your repo has groups for percentages
    CouponRequest,      # requests table
)

# ----------------------------
# Helpers
# ----------------------------

def render(request: Request, template_name: str, context: Dict[str, Any]):
    """
    Centralized renderer so we always pass the same baseline context to Jinja.
    """
    tmpl = request.app.state.templates  # set in main.py
    base_ctx = {
        "request": request,
        "conf": settings,                     # your templates use {{ conf.* }}
        "user": current_user(request),        # your templates often reference {{ user }}
    }
    base_ctx.update(context)
    return tmpl.TemplateResponse(template_name, base_ctx)


def current_user(request: Request) -> Optional[User]:
    """
    Pulls the logged-in user from the session.
    """
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    with get_session() as db:
        return db.query(User).get(user_id)


def login_required(request: Request) -> User:
    user = current_user(request)
    if not user:
        # send to login if not authenticated
        raise HTTPException(status_code=307, detail="redirect", headers={"Location": "/login"})
    return user


def safe(obj: Any, *candidates: str, default: Any = None):
    """
    Try several attribute names and return the first existing non-empty one.
    """
    for name in candidates:
        val = getattr(obj, name, None)
        if val not in (None, ""):
            return val
    return default


# ----------------------------
# Dashboard + Requests
# ----------------------------

def _query_latest_requests(db: Session, limit: int = 10) -> List[CouponRequest]:
    """
    Load latest coupon requests with relations (without assuming exact relationship names).
    """
    q = (
        db.query(CouponRequest)
        .options(
            joinedload(getattr(CouponRequest, "contact", None)),
            joinedload(getattr(CouponRequest, "assigned_coupon", None)),
            joinedload(getattr(CouponRequest, "created_by", None)),
            joinedload(getattr(CouponRequest, "reference_user", None)),
            joinedload(getattr(CouponRequest, "approved_by", None)),
        )
        .order_by(CouponRequest.created_at.desc())
        .limit(limit)
    )
    return list(q)


@dataclass
class RequestRow:
    id: int
    code: str
    status: str
    created_at: datetime
    customer_name: str
    customer_mobile: str
    cashier_name: str
    reference_name: str
    approved_by_name: str
    discount_percent: Optional[int]
    invoice_number: Optional[str]
    assigned_coupon_code: Optional[str]


def _row_from_request(r: CouponRequest) -> RequestRow:
    contact = safe(r, "contact")
    created_by = safe(r, "created_by", "cashier", "creator")
    approved_by = safe(r, "approved_by", "approver")
    reference_user = safe(r, "reference_user", "reference_by", "ref_user")
    assigned_coupon = safe(r, "assigned_coupon", "coupon")

    return RequestRow(
        id=int(safe(r, "id", default=0)),
        code=str(safe(r, "request_code", "code", default="")).strip(),
        status=str(safe(r, "status", default="PENDING")),
        created_at=safe(r, "created_at", default=datetime.utcnow()),
        customer_name=str(
            safe(r, "customer_name", default="")
            or safe(contact, "full_name", "name", default="")
        ),
        customer_mobile=str(
            safe(r, "customer_mobile", default="")
            or safe(contact, "mobile", "mobile_bd", default="")
        ),
        cashier_name=str(safe(created_by, "username", "name", default="")).strip(),
        reference_name=str(safe(reference_user, "username", "name", default="")).strip(),
        approved_by_name=str(safe(approved_by, "username", "name", default="")).strip(),
        discount_percent=safe(r, "discount_percent", default=None),
        invoice_number=safe(r, "invoice_number", default=None),
        assigned_coupon_code=safe(assigned_coupon, "code", default=None),
    )


def _status_counts(db: Session) -> Tuple[int, int, int]:
    """
    Return counts for PENDING, APPROVED, DONE without assuming an enum type.
    """
    rows = (
        db.query(CouponRequest.status, func.count(CouponRequest.id))
        .group_by(CouponRequest.status)
        .all()
    )
    by_status = {str(k): int(v) for k, v in rows}
    return (
        by_status.get("PENDING", 0),
        by_status.get("APPROVED", 0),
        by_status.get("DONE", 0),
    )


# ----------------------------
# Route registration
# ----------------------------

def register_routes(app: FastAPI):
    # Dashboard
    @app.get("/dashboard", response_class=HTMLResponse)
    def dashboard(request: Request):
        user = login_required(request)  # will 307 to /login if not authenticated

        with get_session() as db:
            pending, approved, done = _status_counts(db)
            latest = [_row_from_request(r) for r in _query_latest_requests(db, limit=10)]

        return render(
            request,
            "dashboard.html",
            {
                "title": "Dashboard",
                "pending_count": pending,
                "approved_count": approved,
                "done_count": done,
                "latest": [asdict(x) for x in latest],
            },
        )

    # Requests list (paginated; page query param optional)
    @app.get("/requests", response_class=HTMLResponse)
    def requests_list(request: Request, page: int = 1, per_page: int = 10):
        user = login_required(request)
        page = max(1, page)
        offset = (page - 1) * per_page

        with get_session() as db:
            q = (
                db.query(CouponRequest)
                .options(
                    joinedload(getattr(CouponRequest, "contact", None)),
                    joinedload(getattr(CouponRequest, "assigned_coupon", None)),
                    joinedload(getattr(CouponRequest, "created_by", None)),
                    joinedload(getattr(CouponRequest, "reference_user", None)),
                    joinedload(getattr(CouponRequest, "approved_by", None)),
                )
                .order_by(CouponRequest.created_at.desc())
            )
            total = q.count()
            items = [_row_from_request(r) for r in q.offset(offset).limit(per_page)]
            has_prev = page > 1
            has_next = offset + per_page < total

        return render(
            request,
            "requests.html",
            {
                "title": "Requests",
                "rows": [asdict(x) for x in items],
                "page": page,
                "has_prev": has_prev,
                "has_next": has_next,
                "total": total,
            },
        )

    # Approve/reject/done actions — keep endpoints so buttons don’t 404.
    @app.post("/requests/{rid}/approve")
    def approve_request(request: Request, rid: int, group_id: int):
        user = login_required(request)
        with get_session() as db:
            req = db.query(CouponRequest).get(rid)
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")

            group = db.query(CouponGroup).get(group_id)
            if not group:
                raise HTTPException(status_code=400, detail="Invalid group")

            # assign an unused coupon from this group
            coupon = (
                db.query(Coupon)
                .filter(
                    Coupon.group_id == group.id,
                    or_(Coupon.is_assigned == False, Coupon.is_assigned.is_(None)),  # noqa
                )
                .order_by(Coupon.id.asc())
                .first()
            )
            if not coupon:
                raise HTTPException(status_code=400, detail="No coupon available in this group")

            # update request
            setattr(req, "status", "APPROVED")
            setattr(req, "discount_percent", getattr(group, "percent", None))
            setattr(req, "assigned_coupon_id", getattr(coupon, "id", None))
            setattr(req, "approved_by_id", getattr(user, "id", None))
            setattr(coupon, "is_assigned", True)

            db.commit()

        return RedirectResponse(url="/requests", status_code=303)

    @app.post("/requests/{rid}/reject")
    def reject_request(request: Request, rid: int):
        user = login_required(request)
        with get_session() as db:
            req = db.query(CouponRequest).get(rid)
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")
            setattr(req, "status", "REJECTED")
            setattr(req, "approved_by_id", getattr(user, "id", None))
            db.commit()
        return RedirectResponse(url="/requests", status_code=303)

    @app.post("/requests/{rid}/done")
    def finalize_request(request: Request, rid: int, invoice: str, discount_amount: Optional[int] = None):
        user = login_required(request)
        with get_session() as db:
            req = db.query(CouponRequest).get(rid)
            if not req:
                raise HTTPException(status_code=404, detail="Request not found")
            setattr(req, "invoice_number", invoice)
            setattr(req, "status", "DONE")
            if discount_amount is not None:
                setattr(req, "discount_amount", discount_amount)
            db.commit()
        return RedirectResponse(url="/requests", status_code=303)

    # Contacts
    @app.get("/contacts", response_class=HTMLResponse)
    def contacts_page(request: Request):
        user = login_required(request)
        with get_session() as db:
            contacts = (
                db.query(Contact).order_by(func.lower(Contact.full_name).asc(), Contact.id.asc()).all()
            )
        return render(
            request,
            "contacts.html",
            {"title": "Contacts", "contacts": contacts},
        )

    # Users
    @app.get("/users", response_class=HTMLResponse)
    def users_page(request: Request):
        user = login_required(request)
        with get_session() as db:
            users = db.query(User).order_by(func.lower(User.username).asc()).all()
        return render(
            request,
            "users.html",
            {"title": "Users", "users": users},
        )

    # Enlist coupons (groups + codes)
    @app.get("/enlist", response_class=HTMLResponse)
    def enlist_page(request: Request):
        user = login_required(request)
        with get_session() as db:
            groups = db.query(CouponGroup).order_by(CouponGroup.percent.asc()).all()
            coupons = (
                db.query(Coupon)
                .options(joinedload(Coupon.group), joinedload(getattr(Coupon, "assigned_to", None)))
                .order_by(Coupon.id.asc())
                .all()
            )
        return render(
            request,
            "coupon_enlist.html",  # use your existing template name
            {"title": "Enlist Coupon", "groups": groups, "coupons": coupons},
        )
