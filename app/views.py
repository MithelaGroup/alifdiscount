# app/views.py
from datetime import datetime
from typing import Any, Dict, Optional

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse, HTMLResponse, PlainTextResponse
from sqlalchemy import select, func, desc
from sqlalchemy.orm import Session

from .database import get_db
from .models import (
    User,
    Contact,
    Coupon,
    CouponGroup,          # <- use CouponGroup (not DiscountGroup)
    CouponRequest,
    RequestStatus,
)

router = APIRouter()

# ---------------------------------------------------------
# Templating helper (injects `now` so base.html won’t crash)
# ---------------------------------------------------------
def render(request: Request, template_name: str, context: Dict[str, Any]):
    tmpl = request.app.state.templates  # set in app startup
    base = {
        "request": request,
        "now": datetime.utcnow,         # jinja callable, fixes 'now is undefined'
    }
    base.update(context)
    return tmpl.TemplateResponse(template_name, base)  # type: ignore[attr-defined]


# Make sure templates don’t explode if a relationship is missing
def _normalize_request_row(r: "CouponRequest") -> "CouponRequest":
    # Some DBs use different attribute names — expose safe defaults used by templates
    if not hasattr(r, "approved_by"):
        setattr(r, "approved_by", getattr(r, "approved_by_user", None) or getattr(r, "approver", None))
    if not hasattr(r, "cashier"):
        setattr(r, "cashier", getattr(r, "created_by", None) or getattr(r, "created_by_user", None))
    if not hasattr(r, "reference_user"):
        setattr(r, "reference_user", getattr(r, "ref_user", None))
    if not hasattr(r, "assigned_coupon"):
        setattr(r, "assigned_coupon", getattr(r, "coupon", None))
    return r


# ----------------
# Public endpoints
# ----------------
@router.get("/", response_class=HTMLResponse)
def root():
    # Keep root simple; most setups redirect to dashboard via proxy/Nginx
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_307_TEMPORARY_REDIRECT)


@router.get("/dashboard", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    # 3 tiles
    pending = db.execute(
        select(CouponRequest)
        .where(CouponRequest.status == RequestStatus.PENDING)
        .order_by(desc(CouponRequest.created_at))
        .limit(20)
    ).scalars().all()

    approved = db.execute(
        select(CouponRequest)
        .where(CouponRequest.status == RequestStatus.APPROVED)
        .order_by(desc(CouponRequest.created_at))
        .limit(20)
    ).scalars().all()

    done = db.execute(
        select(CouponRequest)
        .where(CouponRequest.status == RequestStatus.DONE)
        .order_by(desc(CouponRequest.created_at))
        .limit(20)
    ).scalars().all()

    # last 10 for the table under tiles
    recent = db.execute(
        select(CouponRequest).order_by(desc(CouponRequest.created_at)).limit(10)
    ).scalars().all()

    # make templates resilient to absent attributes
    pending = [_normalize_request_row(r) for r in pending]
    approved = [_normalize_request_row(r) for r in approved]
    done = [_normalize_request_row(r) for r in done]
    recent = [_normalize_request_row(r) for r in recent]

    groups = db.execute(select(CouponGroup).order_by(CouponGroup.name.asc())).scalars().all()

    return render(
        request,
        "dashboard.html",
        {
            "active": "dashboard",
            "pending": pending,
            "approved": approved,
            "done": done,
            "items": recent,   # the table under the tiles expects `items`
            "groups": groups,  # for approve modal
        },
    )


@router.get("/contacts", response_class=HTMLResponse)
def contacts_page(request: Request, db: Session = Depends(get_db)):
    items = db.execute(
        select(Contact).order_by(func.lower(Contact.full_name).asc(), Contact.id.asc())
    ).scalars().all()
    return render(request, "contacts.html", {"active": "contacts", "items": items})


@router.get("/requests", response_class=HTMLResponse)
def requests_list(request: Request, db: Session = Depends(get_db), page: int = 1, size: int = 20):
    items = db.execute(
        select(CouponRequest)
        .order_by(desc(CouponRequest.created_at))
        .offset((page - 1) * size)
        .limit(size)
    ).scalars().all()
    items = [_normalize_request_row(r) for r in items]
    groups = db.execute(select(CouponGroup).order_by(CouponGroup.name.asc())).scalars().all()
    return render(request, "requests.html", {"active": "requests", "items": items, "groups": groups})


@router.get("/enlist", response_class=HTMLResponse)
def enlist_page(request: Request, db: Session = Depends(get_db)):
    groups = db.execute(select(CouponGroup).order_by(CouponGroup.name.asc())).scalars().all()
    coupons = db.execute(select(Coupon).order_by(desc(Coupon.created_at))).scalars().all()
    return render(request, "coupon_enlist.html", {"active": "enlist", "groups": groups, "coupons": coupons})


@router.get("/users", response_class=HTMLResponse)
def users_page(request: Request, db: Session = Depends(get_db)):
    items = db.execute(select(User).order_by(User.username.asc())).scalars().all()
    return render(request, "users.html", {"active": "users", "items": items})


# ---------------------------
# Handy debug: list all routes
# ---------------------------
@router.get("/routes", response_class=PlainTextResponse)
def routes(request: Request) -> str:
    out = []
    for r in request.app.router.routes:  # type: ignore[attr-defined]
        path = getattr(r, "path", "")
        methods = ",".join(sorted(getattr(r, "methods", set())))
        out.append(f"{path}  [{methods}]")
    return "\n".join(out)


# ------------------------
# Actions (basic skeletons)
# ------------------------
@router.post("/requests/{rid}/approve")
def approve_request(rid: int, request: Request, db: Session = Depends(get_db), group_id: Optional[int] = None):
    r = db.get(CouponRequest, rid)
    if not r:
        raise HTTPException(404, "Request not found")
    r.status = RequestStatus.APPROVED
    # NOTE: your existing business logic for assigning a coupon & WhatsApp message goes here.
    db.add(r)
    db.commit()
    return RedirectResponse(url=request.headers.get("referer", "/requests"), status_code=303)


@router.post("/requests/{rid}/reject")
def reject_request(rid: int, request: Request, db: Session = Depends(get_db)):
    r = db.get(CouponRequest, rid)
    if not r:
        raise HTTPException(404, "Request not found")
    r.status = RequestStatus.REJECTED
    db.add(r)
    db.commit()
    return RedirectResponse(url=request.headers.get("referer", "/requests"), status_code=303)


@router.post("/requests/{rid}/done")
def finalize_request(
    rid: int,
    request: Request,
    db: Session = Depends(get_db),
    invoice_number: Optional[str] = None,
    discount_amount: Optional[float] = None,
):
    r = db.get(CouponRequest, rid)
    if not r:
        raise HTTPException(404, "Request not found")
    r.status = RequestStatus.DONE
    if invoice_number:
        setattr(r, "invoice_number", invoice_number)
    if discount_amount is not None:
        setattr(r, "discount_amount", discount_amount)
    db.add(r)
    db.commit()
    return RedirectResponse(url=request.headers.get("referer", "/requests"), status_code=303)
