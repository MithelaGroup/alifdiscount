from __future__ import annotations

from fastapi import APIRouter, Request, Depends, Form
from fastapi.responses import RedirectResponse, JSONResponse
from sqlalchemy import func
from sqlalchemy.orm import Session
import re
from typing import Optional

from .database import SessionLocal
from .models_contact import Contact  # already in repo
from .models import User  # only for typing; not required at runtime

router = APIRouter()

# --- infra helpers -----------------------------------------------------------

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

def current_user(request: Request) -> Optional[User]:
    # Your app stores the logged user in session as `user` dict.
    # We'll expose it to templates as `user`.
    return request.session.get("user")

def render(request: Request, template_name: str, context: dict):
    base = {
        "request": request,
        "user": current_user(request),
        "now": request.app.state.now,   # provided by main.py
    }
    base.update(context or {})
    return request.app.state.templates.TemplateResponse(template_name, base)

# --- phone normalizer / validator --------------------------------------------

_bd_digits = re.compile(r"\D+")

def normalize_bd_mobile(raw: str) -> str:
    """
    Normalize to E.164 for Bangladesh: +8801XXXXXXXXX
    Accepts inputs like:
        018XXXXXXXX, 01XXXXXXXXX, +88018XXXXXXX, 88018XXXXXXX, 0088018XXXXXXX
    """
    if not raw:
        return ""

    s = raw.strip()
    # quick exits for already well-formed
    if s.startswith("+880"):
        digits = _bd_digits.sub("", s[1:])  # strip + then non-digits
        return f"+{digits}"

    # strip all non-digits
    d = _bd_digits.sub("", s)

    # common variants -> +8801XXXXXXXXX
    if d.startswith("00880"):
        d = d[2:]  # -> 880...
    if d.startswith("880"):
        d = d[3:]  # -> local (possibly 1XXXXXXXXX)
    if d.startswith("0"):
        d = d[1:]  # drop local 0

    # at this point we expect 1XXXXXXXXX (11 digits incl. leading 1)
    if len(d) == 10 and d[0] != "1":
        # e.g. someone typed 9-10 digits; we’ll fail later
        pass

    return f"+880{d}"

def is_valid_bd_mobile(e164: str) -> bool:
    """
    Valid BD mobile in E.164 must be +8801XXXXXXXXX (13 chars including +).
    """
    if not e164.startswith("+880"):
        return False
    digits = _bd_digits.sub("", e164)
    return digits.startswith("8801") and len(digits) == 13

# --- routes ------------------------------------------------------------------

@router.get("/contacts", name="contacts")
def contacts_page(
    request: Request,
    page: int = 1,
    page_size: int = 10,
    db: Session = Depends(get_db),
):
    page = max(1, page)
    page_size = max(1, min(50, page_size))

    q = db.query(Contact).order_by(Contact.id.desc())
    total = q.count()
    rows = (
        q.offset((page - 1) * page_size)
         .limit(page_size)
         .all()
    )

    last_page = max(1, (total + page_size - 1) // page_size)
    return render(
        request,
        "contacts.html",
        {
            "rows": rows,
            "page": page,
            "page_size": page_size,
            "total": total,
            "last_page": last_page,
        },
    )

@router.post("/contacts/create", name="contacts_create")
def contacts_create(
    request: Request,
    full_name: str = Form(...),
    mobile: str = Form(...),
    remarks: str = Form(""),
    db: Session = Depends(get_db),
):
    full_name = (full_name or "").strip()
    mobile_norm = normalize_bd_mobile(mobile)

    if not full_name:
        return JSONResponse({"ok": False, "error": "Full name is required."}, status_code=400)
    if not is_valid_bd_mobile(mobile_norm):
        return JSONResponse({"ok": False, "error": "Invalid Bangladesh mobile number."}, status_code=400)

    exists = db.query(Contact).filter(func.lower(Contact.mobile) == mobile_norm.lower()).first()
    if exists:
        return JSONResponse({"ok": False, "error": "This mobile number already exists."}, status_code=409)

    contact = Contact(full_name=full_name, mobile=mobile_norm, remarks=(remarks or "").strip() or None)
    db.add(contact)
    db.commit()

    # after create, go back to list (page 1)
    return RedirectResponse("/contacts", status_code=303)
