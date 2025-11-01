import os
from datetime import datetime
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.templating import Jinja2Templates

# our routes live in views.py
from .views import register_routes


def create_app() -> FastAPI:
    app = FastAPI(title="ALIF Discount")

    # Sessions (for login)
    secret = os.getenv("SESSION_SECRET", "change-me-please")
    app.add_middleware(SessionMiddleware, secret_key=secret, same_site="lax")

    # Static & Templates
    app.mount("/static", StaticFiles(directory="static"), name="static")
    templates = Jinja2Templates(directory="templates")

    # make {{ now() }} available in all templates
    templates.env.globals["now"] = datetime.utcnow
    app.state.templates = templates

    # register all page routes
    register_routes(app)
    return app


app = create_app()
