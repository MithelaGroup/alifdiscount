from fastapi import Request
from starlette.responses import RedirectResponse
from datetime import datetime

# If you have models / DB, you can import and use them here.
# from app.models_contact import Contact
# from app.database import SessionLocal

# ---------- helpers ----------
def _user(request: Request):
    return request.session.get("user")

def _render(request: Request, template: str, extra: dict):
    """
    Central renderer that always injects:
    - request (required by Jinja2Templates)
    - user     (for navbar, role checks)
    - now      (use {{ now.year }}, not now())
    """
    base = {"request": request, "user": _user(request), "now": datetime.now()}
    base.update(extra or {})
    return request.app.state.templates.TemplateResponse(template, base)

def _require_login(request: Request, next_path: str):
    if not _user(request):
        return RedirectResponse(url=f"/login?next={next_path}", status_code=303)
    return None

# ---------- page routes ----------
def register_page_routes(app):
    @app.get("/")
    def root(request: Request):
        # Send logged-in users to dashboard, others to login
        if _user(request):
            return RedirectResponse(url="/dashboard", status_code=303)
        return RedirectResponse(url="/login?next=/dashboard", status_code=303)

    @app.get("/dashboard")
    def dashboard(request: Request):
        guard = _require_login(request, "/dashboard")
        if guard:
            return guard

        # If you have real stats, compute them here.
        stats = {"pending": 0, "approved": 0, "done": 0, "latest": []}
        return _render(request, "dashboard.html", {"stats": stats})

    @app.get("/contacts")
    def contacts_page(request: Request, page: int = 1, per_page: int = 10):
        guard = _require_login(request, "/contacts")
        if guard:
            return guard

        # If your updated contacts.html expects 'page', 'per_page', 'total' etc, provide them.
        # Keep items empty list; your template can render "No contacts yet."
        items = []
        total = 0
        return _render(
            request,
            "contacts.html",
            {"contacts": items, "page": page, "per_page": per_page, "total": total},
        )

    @app.get("/enlist")
    def enlist(request: Request):
        guard = _require_login(request, "/enlist")
        if guard:
            return guard
        return _render(request, "enlist.html", {})

    @app.get("/users")
    def users_page(request: Request):
        guard = _require_login(request, "/users")
        if guard:
            return guard
        return _render(request, "users.html", {"rows": []})

    @app.get("/requests")
    def requests_page(request: Request, page: int = 1, per_page: int = 10):
        guard = _require_login(request, "/requests")
        if guard:
            return guard
        rows = []
        total = 0
        return _render(
            request,
            "requests.html",
            {"rows": rows, "page": page, "per_page": per_page, "total": total},
        )

    @app.get("/settings")
    def settings_page(request: Request):
        guard = _require_login(request, "/settings")
        if guard:
            return guard
        # If your template used {{ conf.APP_BASE_URL }}, you can pass it here from env.
        conf = {"APP_BASE_URL": ""}
        return _render(request, "settings.html", {"conf": conf})

    @app.get("/pwa")
    def pwa_page(request: Request):
        return _render(request, "pwa.html", {})
