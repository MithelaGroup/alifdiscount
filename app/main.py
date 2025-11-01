from __future__ import annotations

import os
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

# Routers
from app import auth
from app import views

APP_DIR = Path(__file__).resolve().parent
ROOT_DIR = APP_DIR.parent
TEMPLATES_DIR = ROOT_DIR / "templates"
STATIC_DIR = ROOT_DIR / "static"

def create_app() -> FastAPI:
    app = FastAPI(title="ALIF Discount")

    # CORS (relaxed; tighten if you want)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_methods=["*"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    # Sessions
    session_secret = os.getenv("SESSION_SECRET", "dev-secret-change-me")
    app.add_middleware(SessionMiddleware, secret_key=session_secret)

    # Templates
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

    # jinja helpers (fixes: jinja2.exceptions.UndefinedError: 'now' is undefined)
    def _now():
        return datetime.now(timezone.utc)

    templates.env.globals.update({
        "now": _now,
    })

    app.state.templates = templates  # for request.app.state.templates

    # Static files
    if STATIC_DIR.exists():
        app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Routers
    app.include_router(auth.router)
    app.include_router(views.router)

    # Health
    @app.get("/healthz")
    def healthz():
        return {"ok": True, "ts": datetime.utcnow().isoformat()}

    return app


app = create_app()
