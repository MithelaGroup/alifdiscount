from __future__ import annotations

from typing import Optional, List, Any, Dict
from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy.orm import Session, joinedload

from .database import get_db

# --- core models that exist in your repo ---
from .models import User, Coupon, CouponRequest

# Contact may live in models.py or models_contact.py
try:
    from .models import Contact  # type: ignore
except Exception:
    try:
        from .models_contact import Contact  # type: ignore
    except Exception:
        Contact = None  # type: ignore

# Discount group can be called DiscountGroup or CouponGroup
DiscountGroup = None  # type: ignore
try:
    from .models import DiscountGroup as _DG  # type: ignore
    DiscountGroup = _DG
except Exception:
    try:
        from .models import CouponGroup as _DG  # type: ignore
        DiscountGroup = _DG
    except Exception:
        DiscountGroup = None  # type: ignore


router = APIRouter()


# -------------------------
# small helpers
# -------------------------
def render(request: Request, template_name: str, context: dict):
    context = {**context, "request": request}
    return request.app.state.templates.TemplateResponse(template_name, context)  # type: ignore[attr-defined]


def current_user(request: Request, db: Session) -> Optional[User]:
    uid = request.session.get("user_id") or request.session.get("uid")
    return db.get(User, uid) if uid else None


def login_required(request: Request, db: Session) -> User:
    user = current_user(request, db)
    if not user:
        # FastAPI RedirectResponse with 307 to /login
        raise HTTPException(status_code=status.HTTP_307_TEMPORARY_REDIRECT, detail="/login")
    return user


def is_superadmin(user: User) -> bool:
    return (getattr(user, "role", "") or "").upper() == "SUPERADMIN"


def is_admin_or_super(user: User) -> bool:
    return (getattr(user, "role", "") or "").upper() in ("ADMIN", "SUPERADMIN")


def approve_allowed_for(user: User, req: CouponRequest) -> bool:
    if is_superadmin(user):
        return True
    # allowed only if selected as reference person
    return getattr(req, "reference_user_id", None) == getattr(user, "id", None)


def pick_available_coupon(db: Session, group_id: int) -> Optional[Coupon]:
    q = (
        db.query(Coupon)
        .filter(
            Coupon.group_id == group_id,
            # be tolerant to different field names
            (getattr(Coupon, "assigned_request_id", None) == None)  # noqa: E711
            if hasattr(Coupon, "assigned_request_id")
            else True,
        )
        .order_by(Coupon.id.asc())
    )
    # if there is an is_used flag, prefer unused ones
    if hasattr(Coupon, "is_used"):
        q = q.filter(getattr(Coupon, "is_used") == False)  # noqa: E712
    return q.first()


def joinedload_options_for_request() -> List[Any]:
    """Only joinedload relations that actually exist on CouponRequest."""
    opts: List[Any] = []
    if hasattr(CouponRequest, "reference_user"):
        opts.append(joinedload(CouponRequest.reference_user))
    if hasattr(CouponRequest, "approved_by"):
        opts.append(joinedload(CouponRequest.approved_by))
    elif hasattr(CouponRequest, "approver"):
        opts.append(joinedload(CouponRequest.approver))
    if hasattr(CouponRequest, "assigned_coupon"):
        opts.append(joinedload(CouponRequest.assigned_coupon))
    if hasattr(CouponRequest, "cashier"):
        opts.append(joinedload(CouponRequest.cashier))
    elif hasattr(CouponRequest, "created_by"):
        opts.append(joinedload(CouponRequest.created_by))
    return opts


def normalize_request_aliases(req: CouponRequest) -> None:
    """Add standard attribute aliases so templates can always use:
       reference_user / approved_by / assigned_coupon / cashier / discount_percent
    """
    alias_map: Dict[str, List[str]] = {
        "reference_user": ["reference", "ref_user", "referrer"],
        "approved_by": ["approver", "approved_user", "approver_user"],
        "assigned_coupon": ["coupon", "coupon_assigned", "assigned"],
        "cashier": ["created_by", "creator", "created_by_user"],
    }
    for std_name, candidates in alias_map.items():
        if not hasattr(req, std_name):
            for cand in candidates:
                if hasattr(req, cand):
                    setattr(req, std_name, getattr(req, cand))
                    break
    # discount percent naming tolerance
    if not hasattr(req, "discount_percent"):
        if hasattr(req, "discount_percentage"):
            setattr(req, "discount_percent", getattr(req, "discount_percentage"))
        elif hasattr(req, "percent"):
            setattr(req, "discount_percent", getattr(req, "percent"))


# -------------------------
# Route Inspector
# -------------------------
@router.get("/routes")
def list_routes(request: Request):
    entries = []
    for r in request.app.routes:
        path = getattr(r, "path", str(r))
        methods = sorted(list(getattr(r, "methods", set()))) if hasattr(r, "methods") else []
        entries.append({"path": path, "methods": methods})
    return JSONResponse(sorted(entries, key=lambda x: x["path"]))


# -------------------------
# Dashboard
# -------------------------
@router.get("/")
@router.get("/dashboard")
def dashboard(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    pending = (
        db.query(CouponRequest)
        .filter(CouponRequest.status == "PENDING")
        .order_by(CouponRequest.created_at.desc())
        .all()
    )
    approved = (
        db.query(CouponRequest)
        .filter(CouponRequest.status == "APPROVED")
        .order_by(CouponRequest.created_at.desc())
        .all()
    )
    done = (
        db.query(CouponRequest)
        .filter(CouponRequest.status.in_(["DONE", "COMPLETED"]))
        .order_by(CouponRequest.created_at.desc())
        .all()
    )

    page = max(int(request.query_params.get("page", "1") or 1), 1)
    page_size = 10

    q = db.query(CouponRequest).options(*joinedload_options_for_request()).order_by(
        CouponRequest.created_at.desc(), CouponRequest.id.desc()
    )
    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    for r in items + pending + approved + done:
        normalize_request_aliases(r)

    groups = []
    if DiscountGroup is not None:
        # order by percent/percentage when available
        if hasattr(DiscountGroup, "percent"):
            groups = db.query(DiscountGroup).order_by(DiscountGroup.percent.asc()).all()
        elif hasattr(DiscountGroup, "percentage"):
            groups = db.query(DiscountGroup).order_by(DiscountGroup.percentage.asc()).all()
        else:
            groups = db.query(DiscountGroup).order_by(DiscountGroup.id.asc()).all()

    return render(
        request,
        "dashboard.html",
        dict(
            user=user,
            pending=pending,
            approved=approved,
            done=done,
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            groups=groups,
        ),
    )


# -------------------------
# Requests list page
# -------------------------
@router.get("/requests")
def requests_list(request: Request, db: Session = Depends(get_db)):
    user = current_user(request, db)
    if not user:
        return RedirectResponse(url="/login", status_code=status.HTTP_307_TEMPORARY_REDIRECT)

    status_filter = (request.query_params.get("status") or "").upper() or None
    page = max(int(request.query_params.get("page", "1") or 1), 1)
    page_size = 20

    q = db.query(CouponRequest).options(*joinedload_options_for_request()).order_by(
        CouponRequest.created_at.desc(), CouponRequest.id.desc()
    )
    if status_filter:
        q = q.filter(CouponRequest.status == status_filter)

    total = q.count()
    items = q.offset((page - 1) * page_size).limit(page_size).all()

    for r in items:
        normalize_request_aliases(r)

    groups = []
    if DiscountGroup is not None:
        if hasattr(DiscountGroup, "percent"):
            groups = db.query(DiscountGroup).order_by(DiscountGroup.percent.asc()).all()
        elif hasattr(DiscountGroup, "percentage"):
            groups = db.query(DiscountGroup).order_by(DiscountGroup.percentage.asc()).all()
        else:
            groups = db.query(DiscountGroup).order_by(DiscountGroup.id.asc()).all()

    return render(
        request,
        "requests.html",
        dict(
            user=user,
            items=items,
            page=page,
            page_size=page_size,
            total=total,
            status_filter=status_filter,
            groups=groups,
        ),
    )


# -------------------------
# Actions
# -------------------------
@router.post("/requests/{rid}/approve")
def request_approve(request: Request, rid: int, group_id: int = Form(...), db: Session = Depends(get_db)):
    user = login_required(request, db)

    req = db.query(CouponRequest).get(rid)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")

    if not approve_allowed_for(user, req):
        raise HTTPException(status_code=403, detail="You are not allowed to approve this request")

    if req.status in ("APPROVED", "DONE", "COMPLETED", "REJECTED"):
        raise HTTPException(status_code=400, detail=f"Request already {req.status}")

    if DiscountGroup is None:
        raise HTTPException(status_code=500, detail="Discount groups are not configured")

    group = db.get(DiscountGroup, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Discount group not found")

    coupon = pick_available_coupon(db, group_id)
    if not coupon:
        raise HTTPException(status_code=409, detail="No free coupons in this group")

    # link coupon to request
    if hasattr(coupon, "assigned_request_id"):
        coupon.assigned_request_id = req.id
    if hasattr(coupon, "is_used"):
        coupon.is_used = True

    # set approval details
    req.status = "APPROVED"
    percent = getattr(group, "percent", getattr(group, "percentage", None))
    if hasattr(req, "discount_percent"):
        req.discount_percent = percent
    elif hasattr(req, "discount_percentage"):
        req.discount_percentage = percent
    elif hasattr(req, "percent"):
        req.percent = percent

    if hasattr(req, "approved_by_id"):
        req.approved_by_id = getattr(user, "id", None)
    elif hasattr(req, "approver_id"):
        req.approver_id = getattr(user, "id", None)

    if hasattr(req, "assigned_coupon_id"):
        req.assigned_coupon_id = getattr(coupon, "id", None)

    db.add_all([coupon, req])
    db.commit()

    # Optional WhatsApp notify (best-effort)
    try:
        from .whatsapp import send_coupon_to_customer
        send_coupon_to_customer(
            name=getattr(req, "customer_name", "") or "",
            mobile=getattr(req, "customer_mobile", "") or "",
            code=getattr(coupon, "code", "") or "",
            percent=percent,
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

    req = db.query(CouponRequest).get(rid)
    if not req:
        raise HTTPException(status_code=404, detail="Request not found")
    if req.status != "APPROVED":
        raise HTTPException(status_code=400, detail="Request must be APPROVED before finalizing")

    is_owner_cashier = getattr(req, "cashier_id", None) == getattr(user, "id", None)
    is_creator = getattr(req, "created_by_id", None) == getattr(user, "id", None)
    if not (is_owner_cashier or is_creator or is_admin_or_super(user)):
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

    # free coupon if any
    if hasattr(req, "assigned_coupon_id") and req.assigned_coupon_id:
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
