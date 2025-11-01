from __future__ import annotations

import re
from typing import Optional

from fastapi import FastAPI, Form, Request
from fastapi.responses import RedirectResponse, JSONResponse
from starlette.responses import Response

# --- DB / Models -------------------------------------------------------------

try:
    # single source of truth for contacts
    from .models_contact import Contact, SessionLocal, Base, engine  # type: ignore
except Exception as e:  # pragma: no cover
    # Fail loudly with a readable message if someone deletes models_contact.py
    raise RuntimeError("models_contact.py is required. Error: %r" % e)

# Ensure tables (only contacts here); other models live in their own modules
Base.metadata.create_all(bind=engine)

# --- helpers ----------------------------------------------------------------

def render(request: Request, template_name: str, ctx: dict) -> Response:
    """
    Central render that guarantees 'request' and a stable base context.
    """
    base = {
        "request": request,
        "active_path": request.url.path,
    }
    base.update(ctx or {})
    return request.app.state.templates.TemplateResponse(template_name, base)  # type: ignore[attr-defined]


def require_login(request: Request) -> Optional[RedirectResponse]:
    """
    Returns a RedirectResponse to /login if not logged in, else None.
    """
    user = request.session.get("user")
    if not user:
        dest = request.url.path
        return RedirectResponse(url=f"/login?next={dest}", status_code=302)
    return None


# Bangladesh mobile: exactly +8801#########  (10 digits after +880)
_MOBILE_RE = re.compile(r"^\+8801\d{9}$")


def _valid_bd_mobile(m: str) -> bool:
    return bool(_MOBILE_RE.match(m or ""))


# --- ROUTES -----------------------------------------------------------------

def register_routes(app: FastAPI) -> None:
    # ----------------------- Home -> Dashboard ------------------------------
    @app.get("/")
    def index() -> RedirectResponse:
        return RedirectResponse(url="/dashboard", status_code=302)

    # ---------------------------- Login ------------------------------------
    @app.get("/login")
    def login_page(request: Request, next: str = "/dashboard"):
        # If already logged in, go where they intended
        if request.session.get("user"):
            return RedirectResponse(url=next or "/dashboard", status_code=302)
        return render(request, "login.html", {"next": next})

    @app.post("/login")
    def login_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
        next: str = Form("/dashboard"),
    ):
        """
        Minimal session login.
        You can swap this for DB-based auth later; for now we accept any non-empty
        username/password pair, or you can lock with env ADMIN_USER/PASS.
        """
        env_user = (request.app.state.__dict__.get("ADMIN_USER")  # type: ignore
                    or None)
        env_pass = (request.app.state.__dict__.get("ADMIN_PASS")  # type: ignore
                    or None)

        if env_user is not None and env_pass is not None:
            ok = (username == env_user and password == env_pass)
        else:
            # fallback: simple non-empty check (replace with real auth later)
            ok = bool(username.strip()) and bool(password.strip())

        if not ok:
            # Redisplay login with a simple error (no 500s)
            return render(
                request,
                "login.html",
                {
                    "next": next,
                    "error": "Invalid credentials. Please try again.",
                },
            )

        # Store session
        request.session["user"] = {"username": username}
        return RedirectResponse(url=next or "/dashboard", status_code=302)

    @app.get("/logout")
    def logout(request: Request):
        request.session.clear()
        return RedirectResponse(url="/login", status_code=302)

    # -------------------------- Dashboard ----------------------------------
    @app.get("/dashboard")
    def dashboard(request: Request):
        redir = require_login(request)
        if redir:
            return redir
        # Keep dashboard simple & stable — page owns its own layout pieces
        return render(request, "dashboard.html", {})

    # --------------------------- Contacts -----------------------------------
    @app.get("/contacts")
    def contacts_page(
        request: Request,
        page: int = 1,
        per_page: int = 10,
    ):
        redir = require_login(request)
        if redir:
            return redir

        page = max(1, page)
        per_page = max(1, min(100, per_page))

        db = SessionLocal()
        try:
            total = db.query(Contact).count()
            offset = (page - 1) * per_page
            rows = (
                db.query(Contact)
                .order_by(Contact.id.desc())
                .offset(offset)
                .limit(per_page)
                .all()
            )
        finally:
            db.close()

        return render(
            request,
            "contacts.html",
            {
                # the template can read these to build its own UI
                "rows": rows,
                "total": total,
                "page": page,
                "per_page": per_page,
            },
        )

    @app.post("/contacts")
    def contacts_create(
        request: Request,
        full_name: str = Form(...),
        mobile: str = Form(...),
        remarks: str = Form(""),
    ):
        redir = require_login(request)
        if redir:
            return redir

        full_name = (full_name or "").strip()
        mobile = (mobile or "").strip()
        remarks = (remarks or "").strip()

        if not full_name:
            return JSONResponse({"ok": False, "error": "Full name is required."}, status_code=400)

        if not _valid_bd_mobile(mobile):
            return JSONResponse(
                {
                    "ok": False,
                    "error": "Please enter a valid BD mobile like +8801XXXXXXXXX (10 digits after +880).",
                },
                status_code=400,
            )

        db = SessionLocal()
        try:
            # prevent duplicates by mobile
            exists = db.query(Contact).filter(Contact.mobile == mobile).first()
            if exists:
                return JSONResponse(
                    {"ok": False, "error": "This mobile is already in contacts."},
                    status_code=400,
                )
            c = Contact(full_name=full_name, mobile=mobile, remarks=remarks)
            db.add(c)
            db.commit()
            return JSONResponse({"ok": True})
        finally:
            db.close()

    # A tiny API to help other pages (e.g., Request Create) pick contacts
    @app.get("/api/contacts")
    def contacts_api(q: str = "", limit: int = 10):
        q = (q or "").strip()
        db = SessionLocal()
        try:
            qry = db.query(Contact)
            if q:
                like = f"%{q}%"
                qry = qry.filter(
                    (Contact.full_name.ilike(like)) | (Contact.mobile.ilike(like))
                )
            items = (
                qry.order_by(Contact.id.desc())
                .limit(max(1, min(50, limit)))
                .all()
            )
            return [
                {"id": c.id, "name": c.full_name, "mobile": c.mobile, "remarks": c.remarks}
                for c in items
            ]
        finally:
            db.close()

    # --------------------------- Users (stub) -------------------------------
    @app.get("/users")
    def users_page(request: Request):
        redir = require_login(request)
        if redir:
            return redir
        # Keep existing template; wiring can be added later
        return render(request, "users.html", {})

    # --------------------------- Requests (stub) ----------------------------
    @app.get("/requests")
    def requests_page(request: Request):
        redir = require_login(request)
        if redir:
            return redir
        return render(request, "requests.html", {})
