from datetime import datetime
import os
from types import SimpleNamespace

from fastapi import FastAPI, Request
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from app.auth import router as auth_router  # your existing auth router
from app.views import register_routes       # defined in views.py


def _build_conf():
    return SimpleNamespace(
        APP_NAME=os.getenv("APP_NAME", "ALIF Discount"),
        APP_BASE_URL=os.getenv("APP_BASE_URL", ""),
    )


def create_app() -> FastAPI:
    app = FastAPI(title="ALIF Discount")

    # Sessions (for login state in templates)
    app.add_middleware(SessionMiddleware, secret_key=os.getenv("APP_SECRET", "change-me"))

    # Static folder
    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Templates
    templates = Jinja2Templates(directory="templates")
    # global helpers for Jinja
    templates.env.globals["now"] = lambda: datetime.utcnow()
    app.state.templates = templates
    app.state.conf = _build_conf()

    # auth endpoints (login/logout)
    app.include_router(auth_router)

    # page routes
    register_routes(app)
    return app


app = create_app()
