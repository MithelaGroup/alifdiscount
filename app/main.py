# app/main.py
from __future__ import annotations

import os
from datetime import datetime
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.cors import CORSMiddleware
from starlette.responses import RedirectResponse
from starlette.templating import Jinja2Templates

# ---- App & Config ---------------------------------------------------------

app = FastAPI(title="ALIF Discount")

# Sessions (keep your existing SECRET_KEY env or .env)
SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-env")
app.add_middleware(SessionMiddleware, secret_key=SECRET_KEY)

# CORS (safe defaults; tweak if you need)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files
if not os.path.exists("static"):
    os.makedirs("static", exist_ok=True)
app.mount("/static", StaticFiles(directory="static"), name="static")

# Jinja
templates = Jinja2Templates(directory="templates")
templates.env.globals["now"] = lambda: datetime.now()  # {{ now() }} in templates
app.state.templates = templates

# Keep a small config object handy for templates (conf.APP_BASE_URL, etc.)
try:
    # your existing config.py
    from app.config import Config as _Cfg  # type: ignore
    app.state.conf = _Cfg()
except Exception:
    # very small fallback so templates work
    class _FallbackConf:
        APP_BASE_URL = os.getenv("APP_BASE_URL", "")
        APP_NAME = "ALIF Discount"
    app.state.conf = _FallbackConf()

# ---- Routers / Routes -----------------------------------------------------

# Auth (don’t fail app startup if file differs)
try:
    from app import auth  # type: ignore
    # Some projects expose register_routes(app) instead of APIRouter
    if hasattr(auth, "router"):
        app.include_router(auth.router)  # type: ignore[attr-defined]
    elif hasattr(auth, "register_routes"):
        auth.register_routes(app)  # type: ignore[attr-defined]
except Exception:
    pass

# Page routes (dashboard, contacts, users, requests, enlist, settings, pwa…)
from app.views import register_routes  # noqa: E402

register_routes(app)

# Root -> dashboard
@app.get("/", include_in_schema=False)
def root():
    return RedirectResponse("/dashboard", status_code=303)

# Small healthcheck for your systemd service
@app.get("/healthz", include_in_schema=False)
def healthz():
    return {"ok": True}
