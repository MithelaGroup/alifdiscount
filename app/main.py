# app/main.py
from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

from app.database import Base, engine  # ensure models can create tables if needed
from app.views import register_routes

# Create tables if not already present (safe if they exist)
Base.metadata.create_all(bind=engine)

app = FastAPI(title="ALIF Discount")

# Static files
app.mount("/static", StaticFiles(directory="static"), name="static")

# Jinja templates + a handy global
templates = Jinja2Templates(directory="templates")
def _now():
    import datetime as _dt
    return _dt.datetime.utcnow()

templates.env.globals["now"] = _now
app.state.templates = templates  # type: ignore[attr-defined]

# Page routes
register_routes(app)
