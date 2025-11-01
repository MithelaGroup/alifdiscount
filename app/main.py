# app/main.py
import os
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
from fastapi.templating import Jinja2Templates

from .db import Base, engine
from .views import register_routes
from .routes_contacts import router as contacts_api_router

def create_app() -> FastAPI:
    app = FastAPI(title="ALIF Discount")

    # Static & Templates
    os.makedirs("static", exist_ok=True)
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="templates")
    app.state.templates = templates  # so views.py can use it

    # Sessions (adjust your secret)
    app.add_middleware(SessionMiddleware, secret_key=os.getenv("SESSION_SECRET", "alifdiscount-secret"))

    # DB tables
    Base.metadata.create_all(bind=engine)

    # Routers
    register_routes(app)                 # HTML pages (/dashboard, /contacts, /login, etc.)
    app.include_router(contacts_api_router)  # JSON API (/api/contacts)

    return app


app = create_app()
