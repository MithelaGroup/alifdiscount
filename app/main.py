# app/main.py
from __future__ import annotations

from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from app.config import settings

# Routers
from app import auth, views

BASE_DIR = Path(__file__).resolve().parents[1]
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"

app = FastAPI(title="ALIF Discount")

# --- Sessions ---
secret = (getattr(settings, "SECRET_KEY", None) or "change-this-secret")
app.add_middleware(SessionMiddleware, secret_key=secret, same_site="lax")

# --- CORS (liberal; tighten if needed) ---
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Static files ---
if STATIC_DIR.exists():
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# --- Templates and Jinja globals ---
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
# make "now()" available in all templates
templates.env.globals.update(now=datetime.utcnow, app_name="ALIF Discount")
app.state.templates = templates  # so views/auth can always access

# --- Routers ---
app.include_router(auth.router)
app.include_router(views.router)
