# app/auth.py
from __future__ import annotations

import os
from typing import Optional, Dict

from fastapi import FastAPI, Request, Form
from fastapi.responses import RedirectResponse
from starlette import status

# --- Simple, swappable credential check -------------------------------------
# You can switch this to DB auth later if you want. For now it reads env vars.
ADMIN_USER = os.getenv("ADMIN_USER", "admin")
ADMIN_PASS = os.getenv("ADMIN_PASS", "admin")
DEFAULT_ROLE = os.getenv("ADMIN_ROLE", "admin")


def _validate_credentials(username: str, password: str) -> bool:
    return username == ADMIN_USER and password == ADMIN_PASS


def get_current_user(request: Request) -> Optional[Dict]:
    """Return the current user dict from the session, or None."""
    return request.session.get("user")


def login_required(request: Request) -> Optional[RedirectResponse]:
    """
    Small helper you can call at the top of any view function:

        if (resp := login_required(request)): return resp

    Redirects anonymous users to /login. Returns None if authenticated.
    """
    if get_current_user(request) is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
    return None


# --- Public API used by main.py ----------------------------------------------
def register_auth_routes(app: FastAPI) -> None:
    """
    Mount /login and /logout and make sure templates always
    get a 'user' variable in the context through a tiny wrapper.
    """

    templates = app.state.templates  # Jinja2Templates set in main.py

    # Make 'user' always available in Jinja as a global (in addition to our render())
    # so {% if user %} works everywhere even if a view forgets to pass it.
    def _jinja_current_user(request: Request) -> Optional[Dict]:
        return get_current_user(request)

    templates.env.globals["current_user"] = _jinja_current_user  # optional helper

    @app.get("/login")
    async def login_form(request: Request):
        # Already logged in? Go to dashboard.
        if get_current_user(request):
            return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)
        return templates.TemplateResponse(
            "login.html",
            {"request": request, "title": "Login", "user": None},
        )

    @app.post("/login")
    async def login_submit(
        request: Request,
        username: str = Form(...),
        password: str = Form(...),
    ):
        if not _validate_credentials(username, password):
            return templates.TemplateResponse(
                "login.html",
                {
                    "request": request,
                    "title": "Login",
                    "error": "Invalid username or password.",
                    "user": None,
                },
                status_code=status.HTTP_401_UNAUTHORIZED,
            )

        # Save a very small, non-sensitive session record
        request.session["user"] = {
            "username": username,
            "role": DEFAULT_ROLE,
        }
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_303_SEE_OTHER)

    @app.get("/logout")
    async def logout(request: Request):
        request.session.clear()
        return RedirectResponse(url="/login", status_code=status.HTTP_303_SEE_OTHER)
