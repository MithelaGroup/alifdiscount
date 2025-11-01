# app/auth.py
from __future__ import annotations

from typing import Optional

from fastapi import APIRouter, Depends, Form, HTTPException, Request
from fastapi.responses import RedirectResponse
from sqlalchemy import select, or_
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import User
from app.utils import verify_password, login_user, logout_user

router = APIRouter()

def _render(request: Request, template_name: str, context: dict):
    tmpl = request.app.state.templates
    return tmpl.TemplateResponse(template_name, context)

@router.get("/login")
def login_get(request: Request, next: Optional[str] = None):
    return _render(
        request,
        "login.html",
        {
            "request": request,
            "next": next or "/",
            "error": None,
        },
    )

@router.post("/login")
def login_post(
    request: Request,
    db: Session = Depends(get_db),
    login: str = Form(...),
    password: str = Form(...),
    next: Optional[str] = Form(None),
):
    # Find by username or email
    stmt = select(User).where(or_(User.username == login, User.email == login))
    user = db.execute(stmt).scalar_one_or_none()
    if not user or not verify_password(password, user.password_hash):
        # Do NOT leak which part failed
        return _render(
            request,
            "login.html",
            {
                "request": request,
                "next": next or "/",
                "error": "Invalid username/email or password.",
            },
        )

    # Ok – create session
    login_user(request, user)
    # Respect next if it is a local path
    target = next if (next and next.startswith("/")) else "/"
    return RedirectResponse(url=target, status_code=303)

@router.get("/logout")
def logout(request: Request):
    logout_user(request)
    return RedirectResponse(url="/login", status_code=303)
