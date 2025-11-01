# app/main.py
from __future__ import annotations

from fastapi import FastAPI
from starlette.templating import Jinja2Templates
from starlette.staticfiles import StaticFiles

from app import views, auth

# NEW: contacts router (safe import, no duplicate models)
from app.routes_contacts import router as contacts_router


def create_app() -> FastAPI:
    app = FastAPI(title="ALIF Discount")

    # Templates & static
    templates = Jinja2Templates(directory="templates")
    # handy "now" in Jinja
    import datetime as _dt

    templates.env.globals["now"] = lambda: _dt.datetime.now()
    app.state.templates = templates

    app.mount("/static", StaticFiles(directory="static"), name="static")

    # Existing routes
    views.register_routes(app)
    auth.register_auth_routes(app)

    # Contacts router
    app.include_router(contacts_router)

    return app


app = create_app()
