from __future__ import annotations

import os
from datetime import datetime
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from app import auth  # your existing auth module
from app.routes_contacts import router as contacts_router  # NEW

APP_DIR = os.path.dirname(__file__)
TEMPLATES_DIR = os.path.join(APP_DIR, "..", "templates")
STATIC_DIR = os.path.join(APP_DIR, "..", "static")

def now():
    return datetime.now()

def create_app() -> FastAPI:
    app = FastAPI(title="ALIF Discount")

    # Static
    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")

    # Templates
    templates = Jinja2Templates(directory=TEMPLATES_DIR)
    app.state.templates = templates
    app.state.now = now  # expose to templates as callable

    # Sessions & CORS
    app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "change-me"))
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Routers ---
    # keep your existing routes registration (auth/views/etc.)
    # Example: app.include_router(auth.router)   # if you use APIRouter for auth
    app.include_router(contacts_router)  # NEW: Contacts pages

    # Health
    @app.get("/healthz")
    def healthz():
        return {"ok": True, "time": now().isoformat()}

    # Root -> dashboard or login
    @app.get("/")
    async def root(request: Request):
        user = request.session.get("user")
        return auth.redirect_to("/dashboard" if user else "/login")

    return app

app = create_app()
