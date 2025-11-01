from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.responses import RedirectResponse
from starlette.templating import Jinja2Templates

# local modules
from app.config import settings  # expects object with secret_key, app_name, etc.
from app import auth
from app.views import register_routes  # we’ll call this to add all page routes


BASE_DIR = Path(__file__).resolve().parent.parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"


def create_app() -> FastAPI:
    app = FastAPI(title=getattr(settings, "app_name", "ALIF Discount"))

    # Sessions (for login state)
    app.add_middleware(SessionMiddleware, secret_key=settings.secret_key, https_only=False)

    # CORS (relaxed; adjust for your origin)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Static
    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    # Templates
    templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
    # make a `now()` helper available to Jinja (fixes the UndefinedError in your log)
    templates.env.globals["now"] = lambda: datetime.now(timezone.utc)
    templates.env.globals["app_name"] = getattr(settings, "app_name", "ALIF Discount")
    app.state.templates = templates  # store for easy access

    # Routers / routes
    auth.register_routes(app)       # /login, /logout etc.
    register_routes(app)            # dashboard, contacts, users, requests, enlist, …

    @app.get("/", include_in_schema=False)
    def index(_: Request):
        # send anonymous users to /login, others to /dashboard (auth.login_required already guards /dashboard)
        return RedirectResponse(url="/dashboard")

    # simple health check
    @app.get("/healthz", include_in_schema=False)
    def healthz():
        return {"ok": True, "ts": datetime.utcnow().isoformat()}

    return app


app = create_app()
