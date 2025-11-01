# app/main.py
from __future__ import annotations

import os
from datetime import datetime, timezone
from types import SimpleNamespace

from fastapi import FastAPI, Request
from fastapi.responses import RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

# local imports
from app.auth import register_auth_routes, get_current_user
from app.routes_contacts import router as contacts_router  # your API router for contacts
from app.views import register_routes  # your page routes that call render()

# -----------------------------------------------------------------------------
# App factory
# -----------------------------------------------------------------------------
def create_app() -> FastAPI:
    app = FastAPI(title="ALIF Discount")

    # --- Sessions (required for login) ---------------------------------------
    secret = os.getenv("SECRET_KEY", "please-change-me")
    app.add_middleware(SessionMiddleware, secret_key=secret, same_site="lax")

    # --- Templates ------------------------------------------------------------
    templates = Jinja2Templates(directory="templates")

    # A tiny "now()" helper and conf object used by templates like settings.html
    templates.env.globals["now"] = lambda: datetime.now(timezone.utc)
    app_base_url = os.getenv("APP_BASE_URL", "")
    templates.env.globals["conf"] = SimpleNamespace(APP_BASE_URL=app_base_url)

    # Always pass 'user' unless a route overrides it. Our app.render() already
    # does this too, but this guard helps if someone forgets.
    def render_with_user(request: Request, name: str, ctx: dict):
        ctx = dict(ctx or {})
        ctx.setdefault("user", get_current_user(request))
        ctx.setdefault("request", request)
        return templates.TemplateResponse(name, ctx)

    # stash for our render() helper in views.py
    app.state.templates = templates
    app.state.render_with_user = render_with_user

    # --- Static files (if you use /static) -----------------------------------
    if os.path.isdir("static"):
        app.mount("/static", StaticFiles(directory="static"), name="static")

    # --- Routes ---------------------------------------------------------------
    register_auth_routes(app)    # <-- fixes AttributeError from your logs
    register_routes(app)         # page routes (dashboard, requests, etc.)
    app.include_router(contacts_router, prefix="/api/contacts", tags=["contacts"])

    # Root redirects to dashboard
    @app.get("/")
    async def root(request: Request):
        if get_current_user(request):
            return RedirectResponse("/dashboard")
        return RedirectResponse("/login")

    return app


# Uvicorn entrypoint expects "app"
app = create_app()
