from __future__ import annotations

from datetime import datetime
from typing import Optional, List

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import func, select, and_, or_
from sqlalchemy.orm import Session, joinedload

# --- Project imports (adjust only if your module names differ) ---
from .database import get_db
from .models import (
    User,
    Contact,
    Coupon,
    DiscountGroup,
    CouponRequest,
)
# If you have an Enum for statuses, keep using strings to avoid mismatch.
# PENDING, APPROVED, DONE, REJECTED are used throughout.

router = APIRouter()

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

def render(request: Request, template_name: str, context: dict):
    """
    Always use the app's configured Jinja2 environment (so custom filters/globals like `now` work).
    """
    context = {**context, "request": request}
    return request.app.state.templates.TemplateResponse(template_name, context)  # type: ignore[attr-defined]


def current_user(request: Request, db: Session) -> Optional[User]:
    """
    Reads user id from session and returns a User row. Works with either `user_id` or `uid` keys.
    """
    uid = request.session.get("user_id") or request.session.get("uid")
    if not uid:
        return None
    return db.get(User, uid)


def login_required(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if not user:
        # redirect to login
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, detail="/login")
    return user


def is_superadmin(user: User) -> bool:
    # Compatible with role strings like: "SUPERADMIN" / "ADMIN" / "CASHIER"
    r = (getattr(user, "role", None) or "").upper()
    return r == "SUPERADMIN"


def is_admin_or_super(user: User) -> bool:
    r = (getattr(user, "role", None) or "").upper()
    return r in ("ADMIN", "SUPERADMIN")


def pick_available_coupon(db: Session, group_id: int) -> Optional[Coupon]:
    """
    Returns one free coupon from the given group. Compatible with either:
    - `Coupon.assigned_request_id is NULL`, or
    - `Coupon.is_used == False`
    """
    q = (
        db.query(Coupon)
        .filter(
            Coupon.group_id == group_id,
            # Try a few common "free coupon" conditions to avoid schema mismatch
            or_(
                getattr(Coupon, "assigned_request_id", None) == None,  # noqa: E711
                getattr(Coupon, "request_id", None) == None,          # noqa: E711
                getattr(Coupon, "is_used", None) == False,            # noqa: E712
            ),
        )
        .order_by(Coupon.id.asc())
    )
    return q.first()


def approve_allowed_for(user: User, req: CouponRequest) -> bool:
    """
    Superadmin can approve any.
    Admin can approve if they are the selected reference person.
    """
    if is_superadmin(user):
        return True
    # reference_user_id on request:
    ref_id = getattr(req, "reference_user_id", None)
    return ref_id == getattr(user, "id", None)


# ------------------------------------------------------------------
# Dashboard
# ------------------------------------------------------------------

@router.get("/")
@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    """
    - Shows three tiles (Pending, Approved, Done)
    - Below, shows the latest requests table (paginated)
    """
    user = current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    # Counts for tiles
    pending = db.query(CouponRequest).filter(CouponRequest.status == "PENDING").order_by(CouponRequest.created_at.desc()).all()
    approved = db.query(CouponRequest).filter(CouponRequest.status == "APPROVED").order_by(CouponRequest.created_at.desc()).all()
    done = db.query(CouponRequest).filter(or_(CouponRequest.status == "DONE", CouponRequest.status == "COMPLETED")).order_by(CouponRequest.created_at.desc()).all()

    # Table: page=1..N (10 per page)
    page = max(int(request.query_params.get("page", "1") or 1), 1)
    page_size = 10

    base_q = (
        db.query(CouponRequest)
        .options(
            joinedload(CouponRequest.reference_user),
            joinedload(CouponRequest.approved_by),
            joinedload(CouponRequest.assigned_coupon),
            joinedload(CouponRequest.cashier),
        )
        .order_by(CouponRequest.created_at.desc(), CouponRequest.id.desc())
    )

    total = base_q.count()
    items = base_q.offset((page - 1) * page_size).limit(page_size).all()

    # Discount groups for the Approve modal:
    groups = (
        db.query(DiscountGroup)
        .order_by(DiscountGroup.percent.asc(), DiscountGroup.name.asc())
        .all()
    )

    ctx = {
        "user": user,
        "pending": pending,
        "approved": approved,
        "done": done,
        "items": items,
        "page": page,
        "page_size": page_size,
        "total": total,
        "groups": groups,
    }
    return render(request, "dashboard.html", ctx)


# ------------------------------------------------------------------
# Requests list page (same table as dashboard, just its own page)
# ------------------------------------------------------------------

@router.get("/requests")
def requests_list(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    status_filter = request.query_params.get("status")  # PENDING/APPROVED/DONE/REJECTED or None
    page = max(int(request.query_params.get("page", "1") or 1), 1)
    page_size = 20

    q = (
        db.query(CouponRequest)
        .options(
            joinedload(CouponRequest.reference_user),
            joinedload(CouponRequest.approved_by),
            joinedload(CouponRequest.assigned_coupon),
            joinedload(CouponRequest.cashier),
        )
        .order_by(CouponRequest.created_at.desc(), CouponRequest.id.desc())
    )

    if status_filter:
        q = q.filter(CouponRequest.status == status_filter.upper())

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    groups = db.query(DiscountGroup).order_by(DiscountGroup.percent.asc(), DiscountGroup.name.asc()).all()

    return render(
        request,
        "requests.html",
        {
            "user": user,
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "status_filter": status_filter,
            "groups": groups,
        },
    )


# ------------------------------------------------------------------
# Actions: approve / reject / finalize (done)
# ------------------------------------------------------------------

@router.post("/requests/{rid}/approve")
def request_approve(
    request: Request,
    rid: int,
    group_id: int = Form(...),
    db: Session = Depends(get_db),
):
    user = login_required(request, db)

    req = (
        db.query(CouponRequest)
        .options(
            joinedload(CouponRequest.reference_user),
            joinedload(CouponRequest.assigned_coupon),
        )
        .get(rid)
    )
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if not approve_allowed_for(user, req):
        raise HTTPException(status_code=403, detail="You are not allowed to approve this request")

    if req.status in ("APPROVED", "DONE", "COMPLETED", "REJECTED"):
        raise HTTPException(status_code=400, detail=f"Request already {req.status}")

    group = db.get(DiscountGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Discount group not found")

    # pick & assign a free coupon
    coupon = pick_available_coupon(db, group_id)
    if not coupon:
        raise HTTPException(status_code=409, detail="No free coupons in this group")

    # Mark as assigned to this request
    if hasattr(coupon, "assigned_request_id"):
        coupon.assigned_request_id = req.id
    if hasattr(coupon, "is_used"):
        coupon.is_used = True

    # update request
    req.status = "APPROVED"
    req.discount_percent = getattr(group, "percent", None)
    req.approved_by_id = getattr(user, "id", None)
    req.assigned_coupon_id = getattr(coupon, "id", None)

    db.add_all([coupon, req])
    db.commit()

    # Optional: WhatsApp notify (best effort, won't break flow)
    try:
        from .whatsapp import send_coupon_to_customer  # your helper; implement as you like
        # expects: customer_name, customer_mobile, coupon_code, percent
        send_coupon_to_customer(
            name=getattr(req, "customer_name", "") or "",
            mobile=getattr(req, "customer_mobile", "") or "",
            code=getattr(coupon, "code", "") or "",
            percent=getattr(req, "discount_percent", None),
        )
    except Exception:
        pass  # keep silent if WA config not ready

    return RedirectResponse(url=request.headers.get("referer", "/dashboard"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/requests/{rid}/reject")
def request_reject(
    request: Request,
    rid: int,
    reason: str = Form(""),
    db: Session = Depends(get_db),
):
    user = login_required(request, db)
    req = db.get(CouponRequest, rid)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    # Allow superadmin always; Admin only if they are reference person
    if not approve_allowed_for(user, req):
        raise HTTPException(status_code=403, detail="You are not allowed to reject this request")

    if req.status in ("DONE", "COMPLETED"):
        raise HTTPException(status_code=400, detail="Already completed")

    req.status = "REJECTED"
    if hasattr(req, "rejection_reason"):
        req.rejection_reason = reason

    db.add(req)
    db.commit()
    return RedirectResponse(url=request.headers.get("referer", "/requests"), status_code=status.HTTP_303_SEE_OTHER)


@router.post("/requests/{rid}/done")
def request_done(
    request: Request,
    rid: int,
    invoice_number: str = Form(...),
    discount_amount_bdt: Optional[float] = Form(None),
    db: Session = Depends(get_db),
):
    user = login_required(request, db)

    # Cashier who created the request should be able to finalize it after approval.
    req = (
        db.query(CouponRequest)
        .options(joinedload(CouponRequest.cashier))
        .get(rid)
    )
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    # Must be approved first
    if req.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Request must be APPROVED before finalizing")

    # Only cashier who created OR any admin/superadmin may finalize
    is_owner_cashier = getattr(req, "cashier_id", None) == getattr(user, "id", None)
    if not (is_owner_cashier or is_admin_or_super(user)):
        raise HTTPException(status_code=403, detail="Not allowed to finalize this request")

    req.status = "DONE"
    if hasattr(req, "invoice_number"):
        req.invoice_number = invoice_number
    if hasattr(req, "discount_amount_bdt"):
        req.discount_amount_bdt = discount_amount_bdt

    db.add(req)
    db.commit()
    return RedirectResponse(url=request.headers.get("referer", "/requests"), status_code=status.HTTP_303_SEE_OTHER)


# Optional: only superadmin can delete at any stage
@router.post("/requests/{rid}/delete")
def request_delete(request: Request, rid: int, db: Session = Depends(get_db)):
    user = login_required(request, db)
    if not is_superadmin(user):
        raise HTTPException(status_code=403, detail="Only superadmin can delete requests")

    req = db.get(CouponRequest, rid)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    # Ideally, free back the coupon if already assigned
    if getattr(req, "assigned_coupon_id", None):
        coupon = db.get(Coupon, req.assigned_coupon_id)
        if coupon:
            if hasattr(coupon, "assigned_request_id"):
                coupon.assigned_request_id = None
            if hasattr(coupon, "is_used"):
                coupon.is_used = False
            db.add(coupon)

    db.delete(req)
    db.commit()
    return RedirectResponse(url=request.headers.get("referer", "/requests"), status_code=status.HTTP_303_SEE_OTHER)
