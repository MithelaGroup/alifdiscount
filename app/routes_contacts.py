# app/routes_contacts.py
from __future__ import annotations
import re
from typing import Dict, Any, List, Optional

from fastapi import APIRouter, Request, Form
from fastapi.responses import RedirectResponse
from sqlalchemy import select, func
from sqlalchemy.orm import Session

# --- DB session helper (compatible with your codebase) -----------------------
# Try SessionLocal; if not present, try a get_session() factory.
SessionLocal = None
_get_session = None
try:
    from .database import SessionLocal as _SL  # most common in repo
    SessionLocal = _SL
except Exception:
    try:
        from .database import get_session as _GS  # fallback
        _get_session = _GS
    except Exception:
        pass


def open_db() -> Session:
    """
    Return a SQLAlchemy Session regardless of whether the repo exposes
    SessionLocal() or a get_session() helper.
    """
    if SessionLocal is not None:
        return SessionLocal()
    if _get_session is not None:
        # Some projects provide a ready-made Session (not a context manager)
        return _get_session()
    raise RuntimeError("No Session factory found (database.py).")

# --- Models ------------------------------------------------------------------
# IMPORTANT: import the *existing* Contact model from models.py
from .models import Contact  # <- DO NOT import from models_contact.py

# --- Router ------------------------------------------------------------------
router = APIRouter()

# --- Utilities ---------------------------------------------------------------

BD_MOBILE_RE = re.compile(r"^\+8801[3-9]\d{8}$")  # +8801XXXXXXXXX


def normalize_mobile(mobile_raw: str) -> str:
    """
    Normalize many inputs to BD format: +8801XXXXXXXXX
    Accepts:
      - +8801XXXXXXXXX
      - 8801XXXXXXXXX
      - 01XXXXXXXXX
      - 1XXXXXXXXX  (we'll treat as 01XXXXXXXXX if length==9 or 10)
    """
    s = re.sub(r"[^\d+]", "", mobile_raw.strip())  # remove spaces, hyphens, etc.

    # Already +880?
    if s.startswith("+880"):
        normalized = s
    elif s.startswith("880"):
        normalized = "+" + s
    elif s.startswith("01"):
        normalized = "+880" + s[1:]
    elif s.startswith("1") and len(s) in (9, 10):  # be tolerant: 1XXXXXXXXX
        normalized = "+880" + s
    else:
        # Last fallback: if someone typed 11 digits starting with 0
        if len(s) == 11 and s[0] == "0":
            normalized = "+880" + s[1:]
        else:
            normalized = s  # let validator raise
    if not BD_MOBILE_RE.match(normalized):
        raise ValueError("Invalid Bangladesh mobile number. Use +8801XXXXXXXXX.")
    return normalized


def _contact_columns() -> List[str]:
    return list(Contact.__table__.columns.keys())


def _build_contact_kwargs(full_name: str, mobile: str, remark: str) -> Dict[str, Any]:
    """
    Build kwargs for Contact(**kwargs) that adapt to your actual column names.
    We prefer these canonical names but fall back to common alternatives.
    """
    cols = _contact_columns()
    data: Dict[str, Any] = {}
    # name
    if "full_name" in cols:
        data["full_name"] = full_name
    elif "name" in cols:
        data["name"] = full_name
    elif "customer_name" in cols:
        data["customer_name"] = full_name
    else:
        data["full_name"] = full_name  # default (SQLAlchemy will ignore if not a col)

    # mobile
    if "mobile" in cols:
        data["mobile"] = mobile
    elif "mobile_number" in cols:
        data["mobile_number"] = mobile
    elif "phone" in cols:
        data["phone"] = mobile
    else:
        data["mobile"] = mobile

    # remark
    if "remark" in cols:
        data["remark"] = remark
    elif "remarks" in cols:
        data["remarks"] = remark
    elif "note" in cols:
        data["note"] = remark
    else:
        data["remark"] = remark

    return data


def _row_view(c: Contact) -> Dict[str, Any]:
    """
    Convert a Contact ORM row to a display-friendly dict so the template doesn't
    care about exact column names.
    """
    return {
        "id": getattr(c, "id", None),
        "full_name": (
            getattr(c, "full_name", None)
            or getattr(c, "name", None)
            or getattr(c, "customer_name", "")
        ),
        "mobile": (
            getattr(c, "mobile", None)
            or getattr(c, "mobile_number", None)
            or getattr(c, "phone", "")
        ),
        "remark": (
            getattr(c, "remark", None)
            or getattr(c, "remarks", None)
            or getattr(c, "note", "")
        ),
    }

# --- Routes ------------------------------------------------------------------


@router.get("/contacts")
def contacts_page(request: Request, page: int = 1, per_page: int = 10):
    """
    Render the Contacts page with pagination.
    """
    db = open_db()
    try:
        page = max(1, int(page))
        per_page = min(50, max(5, int(per_page)))

        total = db.execute(select(func.count()).select_from(Contact)).scalar_one()
        pages = max(1, (total + per_page - 1) // per_page)
        page = min(page, pages)

        q = db.execute(
            select(Contact).order_by(Contact.id.desc()).offset((page - 1) * per_page).limit(per_page)
        )
        rows = [_row_view(r[0]) for r in q.all()]

        return request.app.state.templates.TemplateResponse(
            "contacts.html",
            {
                "request": request,
                "rows": rows,
                "page": page,
                "pages": pages,
                "per_page": per_page,
                "total": total,
            },
        )
    finally:
        try:
            db.close()
        except Exception:
            pass


@router.post("/contacts")
def contacts_create(
    request: Request,
    full_name: str = Form(...),
    mobile_input: str = Form(...),
    remark: str = Form(""),
):
    """
    Handle the modal form submit to create a contact.
    """
    db = open_db()
    try:
        mobile = normalize_mobile(mobile_input)
        kwargs = _build_contact_kwargs(full_name.strip(), mobile, remark.strip())
        obj = Contact(**kwargs)
        db.add(obj)
        db.commit()
        return RedirectResponse(url="/contacts", status_code=303)
    except ValueError:
        # bad phone format; bounce back with query flag
        return RedirectResponse(url="/contacts?err=mobile", status_code=303)
    finally:
        try:
            db.close()
        except Exception:
            pass
