from __future__ import annotations

import math
import os
import re
from datetime import datetime
from types import SimpleNamespace
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, Form, Request
from starlette.responses import RedirectResponse, Response

# --- DB / Models ---
# IMPORTANT: use the single existing models module to avoid duplicate tables.
# Do NOT import app.models_contact (it defines another 'contacts' table).
try:
    from app.database import SessionLocal  # typical FastAPI/SQLAlchemy pattern
except Exception:  # pragma: no cover
    SessionLocal = None  # we'll error loudly if this is None

try:
    # Your repo’s models (names inferred from your logs)
    from app.models import Contact, Request as DiscountRequest, RequestStatus, User
except Exception:
    # if some model name differs, we handle later by falling back safely
    Contact = None
    DiscountRequest = None
    RequestStatus = None
    User = None

# -------------------------
# helpers & infrastructure
# -------------------------

def _get_user_from_session(request: Request) -> Optional[dict]:
    """
    We keep whatever you put in session["user"] (dict).
    """
    u = request.session.get("user")
    return u if isinstance(u, dict) else None


def _app_conf() -> SimpleNamespace:
    return SimpleNamespace(
        APP_BASE_URL=os.getenv("APP_BASE_URL", ""),
        ENV=os.getenv("ENV", "prod"),
    )


def render(request: Request, template_name: str, context: Optional[Dict[str, Any]] = None) -> Response:
    """
    Centralized renderer that injects common variables so templates don’t fail:
      - request
      - user
      - now
      - conf (for settings.html)
    """
    base: Dict[str, Any] = {
        "request": request,
        "user": _get_user_from_session(request),
        "now": datetime.utcnow(),
        "conf": _app_conf(),
    }
    if context:
        base.update(context)
    return request.app.state.templates.TemplateResponse(template_name, base)  # type: ignore[attr-defined]


def _login_required_redirect(request: Request) -> Optional[RedirectResponse]:
    """
    If user not logged in, redirect to /login?next=<current>.
    """
    if not _get_user_from_session(request):
        next_path = request.url.path or "/dashboard"
        return RedirectResponse(f"/login?next={next_path}", status_code=303)
    return None


# ---------------
# Phone helpers
# ---------------
BD_MOBILE_RE = re.compile(r"^\+8801[3-9]\d{8}$")

def normalize_bd_mobile(mobile: str) -> Optional[str]:
    """
    Normalize/validate to E.164 BD format: +8801XXXXXXXXX.
    - Accepts '+088...' and normalizes to '+880...'.
    - Accepts '880...' and normalizes to '+880...'.
    - Rejects anything not matching BD mobile ranges (013–019).
    """
    if not mobile:
        return None
    m = mobile.strip().replace(" ", "")
    # normalize a couple of common prefixes users type
    if m.startswith("+088"):
        m = "+880" + m[4:]
    if m.startswith("088"):
        m = "880" + m[3:]
    if m.startswith("880"):
        m = "+" + m
    if not m.startswith("+880"):
        # if they typed 01xxxxxxxxx
        if m.startswith("01") and len(m) == 11:
            m = "+88" + m
        else:
            # fall back: ensure we at least stick + if they gave 880..........
            if m.startswith("88"):
                m = "+" + m
    return m if BD_MOBILE_RE.match(m) else None


# ---------------
# Queries
# ---------------
def _db():
    if SessionLocal is None:
        raise RuntimeError("SessionLocal not available; please check app.database")
    return SessionLocal()


def _count_by_status(status) -> int:
    if DiscountRequest is None or RequestStatus is None:
        return 0
    with _db() as s:
        return s.query(DiscountRequest).filter(DiscountRequest.status == status).count()


def _latest_requests(limit: int = 10) -> List[Dict[str, Any]]:
    if DiscountRequest is None:
        return []
    with _db() as s:
        q = (
            s.query(DiscountRequest)
            .order_by(DiscountRequest.id.desc())  # type: ignore[attr-defined]
            .limit(limit)
        )
        rows: List[Dict[str, Any]] = []
        for r in q:
            # Be defensive: some fields may differ in your model; use getattr()
            rows.append(
                {
                    "id": getattr(r, "id", None),
                    "code": getattr(r, "id", None),
                    "customer": getattr(r, "customer_name", "") or "",
                    "mobile": getattr(r, "customer_mobile", "") or "",
                    "cashier": getattr(r, "cashier_name", "") or "",
                    "reference": getattr(r, "reference_no", "") or "",
                    "approved_by": getattr(r, "approved_by", "") or "",
                    "status": getattr(r, "status", None),
                }
            )
        return rows


def _paginate_contacts(page: int, per_page: int) -> Dict[str, Any]:
    """
    Returns dict with keys: items(list), total(int), page, per_page, pages
    """
    if Contact is None:
        return {"items": [], "total": 0, "page": page, "per_page": per_page, "pages": 0}

    with _db() as s:
        total = s.query(Contact).count()
        pages = math.ceil(total / per_page) if per_page > 0 else 1
        page = max(1, min(page, pages or 1))
        offset = (page - 1) * per_page
        q = (
            s.query(Contact)
            .order_by(getattr(Contact, "id").desc())
            .offset(offset)
            .limit(per_page)
        )
        items = []
        # build rows for the template (keep both 'rows' and 'contacts' for safety)
        for idx, c in enumerate(q, start=offset + 1):
            items.append(
                {
                    "sl": idx,
                    "id": getattr(c, "id", None),
                    "full_name": getattr(c, "full_name", "") or getattr(c, "name", ""),
                    "mobile": getattr(c, "mobile", ""),
                    "remarks": getattr(c, "remarks", ""),
                    "created_at": getattr(c, "created_at", None),
                }
            )
        return {"items": items, "total": total, "page": page, "per_page": per_page, "pages": pages}


# ---------------
# Routes
# ---------------
def register_routes(app: FastAPI) -> None:
    # --------- Auth convenience (keep your existing login page intact) ---------
    @app.get("/login")
    def login_page(request: Request):
        if _get_user_from_session(request):
            return RedirectResponse("/dashboard", status_code=303)
        # Keep your own login.html; we just pass context.
        return render(request, "login.html", {})

    @app.get("/logout")
    def logout(request: Request):
        request.session.pop("user", None)
        return RedirectResponse("/login", status_code=303)

    # ----------------- Dashboard -----------------
    @app.get("/dashboard")
    def dashboard(request: Request):
        redir = _login_required_redirect(request)
        if redir:
            return redir

        # Gather counts if model present; otherwise zeros.
        if RequestStatus is not None:
            try:
                pending = _count_by_status(RequestStatus.PENDING)
                approved = _count_by_status(RequestStatus.APPROVED)
                done = _count_by_status(RequestStatus.DONE)
            except Exception:
                pending = approved = done = 0
        else:
            pending = approved = done = 0

        latest = _latest_requests(limit=10)

        return render(
            request,
            "dashboard.html",
            {
                "pending_count": pending,
                "approved_count": approved,
                "done_count": done,
                "latest_rows": latest,
            },
        )

    # ----------------- Contacts (list + create) -----------------
    @app.get("/contacts")
    def contacts(request: Request, page: int = 1, per_page: int = 10):
        redir = _login_required_redirect(request)
        if redir:
            return redir

        try:
            data = _paginate_contacts(page=page, per_page=per_page)
        except Exception:
            data = {"items": [], "total": 0, "page": page, "per_page": per_page, "pages": 0}

        rows = data["items"]
        total = data["total"]
        pages = data["pages"]
        # NOTE: your contacts.html expects: page, per_page, total AND either rows or contacts.
        return render(
            request,
            "contacts.html",
            {
                "rows": rows,
                "contacts": rows,  # alias for safety
                "total": total,
                "page": data["page"],
                "per_page": data["per_page"],
                "pages": pages,
            },
        )

    @app.post("/contacts/create")
    def contacts_create(
        request: Request,
        full_name: str = Form(...),
        mobile: str = Form(...),
        remarks: str = Form(""),
    ):
        redir = _login_required_redirect(request)
        if redir:
            return redir

        normalized = normalize_bd_mobile(mobile)
        if not normalized:
            # invalid number -> flash-like pattern via query param
            return RedirectResponse("/contacts?error=invalid_mobile", status_code=303)

        if Contact is None:
            return RedirectResponse("/contacts?error=model_missing", status_code=303)

        try:
            with _db() as s:
                c = Contact(full_name=full_name.strip(), mobile=normalized, remarks=remarks.strip())
                s.add(c)
                s.commit()
        except Exception:
            # avoid breaking UX
            return RedirectResponse("/contacts?error=save_failed", status_code=303)

        return RedirectResponse("/contacts?ok=1", status_code=303)

    # ----------------- Users (kept simple; avoid 'user is undefined') -----------------
    @app.get("/users")
    def users(request: Request):
        redir = _login_required_redirect(request)
        if redir:
            return redir

        # Make sure `user` exists in context via render(); template should now be safe
        # If you have a list of users, you can load them here similarly to contacts.
        return render(request, "users.html", {"rows": []})

    # ----------------- Requests (list-only skeleton; your existing template) -----------------
    @app.get("/requests")
    def requests_list(request: Request):
        redir = _login_required_redirect(request)
        if redir:
            return redir

        latest = _latest_requests(limit=10)
        return render(request, "requests.html", {"rows": latest})

    # ----------------- Settings (fix 'conf is undefined') -----------------
    @app.get("/settings")
    def settings(request: Request):
        redir = _login_required_redirect(request)
        if redir:
            return redir

        return render(request, "settings.html", {})

    # ----------------- PWA -----------------
    @app.get("/pwa")
    def pwa(request: Request):
        return render(request, "pwa.html", {})
