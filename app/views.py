from __future__ import annotations

from typing import Optional
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import or_

# -------------------------
# DB session
# -------------------------
from .database import get_db

# -------------------------
# Robust imports for models
# (works even if your code calls the group
#  model CouponGroup instead of DiscountGroup,
#  or puts Contact in models_contact.py)
# -------------------------
try:
    from .models import User, Coupon, CouponRequest
except Exception as e:
    raise

# Contact may live in models.py or models_contact.py
try:
    from .models import Contact  # type: ignore
except Exception:
    try:
        from .models_contact import Contact  # type: ignore
    except Exception:
        Contact = None  # type: ignore

# Discount group may be named DiscountGroup or CouponGroup
DiscountGroup = None  # type: ignore
try:
    from .models import DiscountGroup as _DG  # type: ignore
    DiscountGroup = _DG  # type: ignore
except Exception:
    try:
        from .models import CouponGroup as _DG  # type: ignore
        DiscountGroup = _DG  # type: ignore
    except Exception:
        DiscountGroup = None  # type: ignore

router = APIRouter()

# -------------------------
# Helpers
# -------------------------
def render(request: Request, template_name: str, context: dict):
    context = {**context, "request": request}
    return request.app.state.templates.TemplateResponse(template_name, context)  # type: ignore[attr-defined]

def current_user(request: Request, db: Session) -> Optional[User]:
    uid = request.session.get("user_id") or request.session.get("uid")
    if not uid:
        return None
    return db.get(User, uid)

def login_required(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if not user:
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, detail="/login")
    return user

def is_superadmin(user: User) -> bool:
    r = (getattr(user, "role", None) or "").upper()
    return r == "SUPERADMIN"

def is_admin_or_super(user: User) -> bool:
    r = (getattr(user, "role", None) or "").upper()
    return r in ("ADMIN", "SUPERADMIN")

def approve_allowed_for(user: User, req: CouponRequest) -> bool:
    if is_superadmin(user):
        return True
    return getattr(req, "reference_user_id", None) == getattr(user, "id", None)

def pick_available_coupon(db: Session, group_id: int) -> Optional[Coupon]:
    q = (
        db.query(Coupon)
        .filter(
            Coupon.group_id == group_id,
            or_(
                getattr(Coupon, "assigned_request_id", None) == None,  # noqa: E711
                getattr(Coupon, "request_id", None) == None,          # noqa: E711
                getattr(Coupon, "is_used", None) == False,            # noqa: E712
            ),
        )
        .order_by(Coupon.id.asc())
    )
    return q.first()

# -------------------------
# Route Inspector
# -------------------------
@router.get("/routes")
def list_routes(request: Request):
    """Return all mounted routes & methods as JSON (no auth to make triage easy)."""
    entries = []
    for r in request.app.routes:
        path = getattr(r, "path", str(r))
        methods = sorted(list(getattr(r, "methods", set()))) if hasattr(r, "methods") else []
        entries.append({"path": path, "methods": methods})
    entries.sort(key=lambda e: e["path"])
    return JSONResponse(entries)

# -------------------------
# Dashboard
# -------------------------
@router.get("/")
@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    pending = db.query(CouponRequest).filter(CouponRequest.status == "PENDING").order_by(CouponRequest.created_at.desc()).all()
    approved = db.query(CouponRequest).filter(CouponRequest.status == "APPROVED").order_by(CouponRequest.created_at.desc()).all()
    done = db.query(CouponRequest).filter(or_(CouponRequest.status == "DONE", CouponRequest.status == "COMPLETED")).order_by(CouponRequest.created_at.desc()).all()

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

    groups = []
    if DiscountGroup is not None:
        groups = db.query(DiscountGroup).order_by(
            getattr(DiscountGroup, "percent", getattr(DiscountGroup, "percentage", None)).asc()
            if hasattr(DiscountGroup, "percent") or hasattr(DiscountGroup, "percentage")
            else DiscountGroup.id.asc()
        ).all()

    return render(
        request,
        "dashboard.html",
        {
            "user": user,
            "pending": pending,
            "approved": approved,
            "done": done,
            "items": items,
            "page": page,
            "page_size": page_size,
            "total": total,
            "groups": groups,
        },
    )

# -------------------------
# Requests page
# -------------------------
@router.get("/requests")
def requests_list(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    status_filter = request.query_params.get("status")
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

    groups = []
    if DiscountGroup is not None:
        groups = db.query(DiscountGroup).order_by(
            getattr(DiscountGroup, "percent", getattr(DiscountGroup, "percentage", None)).asc()
            if hasattr(DiscountGroup, "percent") or hasattr(DiscountGroup, "percentage")
            else DiscountGroup.id.asc()
        ).all()

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

# -------------------------
# Actions
# -------------------------
@router.post("/requests/{rid}/approve")
def request_approve(request: Request, rid: int, group_id: int = Form(...), db: Session = Depends(get_db)):
    user = login_required(request, db)

    req = (
        db.query(CouponRequest)
        .options(joinedload(CouponRequest.reference_user), joinedload(CouponRequest.assigned_coupon))
        .get(rid)
    )
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if not approve_allowed_for(user, req):
        raise HTTPException(status_code=403, detail="You are not allowed to approve this request")

    if req.status in ("APPROVED", "DONE", "COMPLETED", "REJECTED"):
        raise HTTPException(status_code=400, detail=f"Request already {req.status}")

    if DiscountGroup is None:
        raise HTTPException(status_code=500, detail="Discount groups are not configured in models")

    group = db.get(DiscountGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Discount group not found")

    coupon = pick_available_coupon(db, group_id)
    if not coupon:
        raise HTTPException(status_code=409, detail="No free coupons in this group")

    if hasattr(coupon, "assigned_request_id"):
        coupon.assigned_request_id = req.id
    if hasattr(coupon, "is_used"):
        coupon.is_used = True

    req.status = "APPROVED"
    req.discount_percent = getattr(group, "percent", getattr(group, "percentage", None))
    req.approved_by_id = getattr(user, "id", None)
    req.assigned_coupon_id = getattr(coupon, "id", None)

    db.add_all([coupon, req])
    db.commit()

    # Optional: WhatsApp notify; ignore failures silently
    try:
        from .whatsapp import send_coupon_to_customer
        send_coupon_to_customer(
            name=getattr(req, "customer_name", "") or "",
            mobile=getattr(req, "customer_mobile", "") or "",
            code=getattr(coupon, "code", "") or "",
            percent=getattr(req, "discount_percent", None),
        )
    except Exception:
        pass

    return RedirectResponse(url=request.headers.get("referer", "/dashboard"), status_code=status.HTTP_303_SEE_OTHER)

@router.post("/requests/{rid}/reject")
def request_reject(request: Request, rid: int, reason: str = Form(""), db: Session = Depends(get_db)):
    user = login_required(request, db)
    req = db.get(CouponRequest, rid)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
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

    req = db.query(CouponRequest).options(joinedload(CouponRequest.cashier)).get(rid)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Request must be APPROVED before finalizing")

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

@router.post("/requests/{rid}/delete")
def request_delete(request: Request, rid: int, db: Session = Depends(get_db)):
    user = login_required(request, db)
    if not is_superadmin(user):
        raise HTTPException(status_code=403, detail="Only superadmin can delete requests")

    req = db.get(CouponRequest, rid)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

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
