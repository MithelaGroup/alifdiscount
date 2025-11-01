import os
from fastapi import FastAPI
from starlette.middleware.sessions import SessionMiddleware
from starlette.staticfiles import StaticFiles
from starlette.responses import RedirectResponse
from starlette.templating import Jinja2Templates

# --- App bootstrap ---
app = FastAPI(title="ALIF Discount")

# Sessions
SESSION_SECRET = os.getenv("SESSION_SECRET", "change-me-in-prod")
app.add_middleware(
    SessionMiddleware,
    secret_key=SESSION_SECRET,
    same_site="lax",
    https_only=False,  # set True if you force HTTPS
    session_cookie="alif_session",
)

# Static & templates
static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
templates_dir = os.path.join(os.path.dirname(__file__), "..", "templates")
app.mount("/static", StaticFiles(directory=static_dir), name="static")

templates = Jinja2Templates(directory=templates_dir)
app.state.templates = templates  # used by render() in views.py

# Root redirect
@app.get("/")
def root():
    return RedirectResponse("/dashboard", status_code=303)

# Register app routes
from app import views  # noqa: E402

views.register_routes(app)
