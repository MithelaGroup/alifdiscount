from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from jinja2 import Environment, FileSystemLoader, select_autoescape
from starlette.templating import Jinja2Templates
import os

# Routers / views
from app.views import register_page_routes
from app.auth import auth_router

# --------- App factory ----------
def create_app() -> FastAPI:
    app = FastAPI(title="ALIF Discount")

    # Secret for server-side cookie session
    secret = os.getenv("SECRET_KEY", "change-me-please")
    app.add_middleware(SessionMiddleware, secret_key=secret, same_site="lax")

    # Static + templates
    if os.path.isdir("static"):
        app.mount("/static", StaticFiles(directory="static"), name="static")

    templates = Jinja2Templates(directory="templates")
    app.state.templates = templates

    # Routers
    app.include_router(auth_router)             # /login, /logout
    register_page_routes(app)                   # /dashboard, /contacts, /requests, etc.

    return app


# Uvicorn entrypoint expects `app`
app = create_app()
