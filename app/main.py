from datetime import datetime
import os
from types import SimpleNamespace

from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

# Routers / pages
from app.auth import router as auth_router  # you already have this
from app.views import register_routes       # defined in views.py below


def _build_conf():
    """
    Very small 'conf' object that is always available in templates as 'conf'.
    This avoids 'conf is undefined' errors.
    If you already have a richer config class, keep using it, this is safe.
    """
    return SimpleNamespace(
        APP_NAME=os.getenv("APP_NAME", "ALIF Discount"),
        APP_BASE_URL=os.getenv("APP_BASE_URL", ""),
    )


def create_app() -> FastAPI:
    app = FastAPI(title="ALIF Discount")

    # Sessions (needed for login/user in templates)
    secret = os.getenv("APP_SECRET", "change-me")
    app.add_middleware(SessionMiddleware, secret_key=secret)

    # Static files (already used by your templates)
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Jinja templates
    templates = Jinja2Templates(directory="templates")
    # Add a global 'now()' so `{% now() %}` works everywhere
    templates.env.globals["now"] = lambda: datetime.utcnow()

    app.state.templates = templates
    app.state.conf = _build_conf()

    # Auth endpoints (login/logout)
    app.include_router(auth_router)

    # All page routes
    register_routes(app)

    return app


app = create_app()

# If you ever run locally: `uvicorn app.main:app --reload --port 8011`
