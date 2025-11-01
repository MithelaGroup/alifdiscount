# app/views.py
from datetime import datetime
from typing import Dict, Any

from fastapi import FastAPI, Request, Form, Depends
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRouter
from sqlalchemy.orm import Session
import re

from .db import SessionLocal
from .models import Contact

router = APIRouter()

BD_REGEX = re.compile(r"^\+8801\d{9}$")  # 10 digits after +880

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def render(request: Request, template_name: str, ctx: Dict[str, Any]) -> Any:
    base = {
        "request": request,
        "current_year": datetime.utcnow().year,
        "user": request.session.get("user"),
    }
    base.update(ctx or {})
    return request.app.state.templates.TemplateResponse(template_name, base)  # type: ignore[attr-defined]


# ------------------ Auth ------------------

@router.get("/login")
def login_page(request: Request, next: str = "/dashboard"):
    return render(request, "login.html", {"next": next})


@router.post("/login")
def login_submit(request: Request, username: str = Form(...), password: str = Form(...), next: str = Form("/dashboard")):
    """
    Minimal demo login:
    - In your real app, replace with proper authentication against your Users table.
    """
    # TODO: replace this stub with your real user/password check
    if username and password:
        request.session["user"] = username
        return RedirectResponse(url=next or "/dashboard", status_code=303)

    # Fallback: reload form
    return render(request, "login.html", {"next": next, "error": "Invalid credentials"})


@router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)


# ------------------ Pages ------------------

@router.get("/")
def root():
    return RedirectResponse(url="/dashboard", status_code=303)


@router.get("/dashboard")
def dashboard(request: Request):
    # Keep this lightweight; cards will show zero if there’s no data.
    return render(request, "dashboard.html", {})


@router.get("/contacts")
def contacts_page(request: Request, page: int = 1, per_page: int = 10, db: Session = Depends(get_db)):
    if page < 1:
        page = 1
    if per_page < 1:
        per_page = 10

    q = db.query(Contact)
    total = q.count()
    rows = (
        q.order_by(Contact.id.desc())
        .offset((page - 1) * per_page)
        .limit(per_page)
        .all()
    )

    return render(
        request,
        "contacts.html",
        {
            "rows": rows,
            "page": page,
            "per_page": per_page,
            "total": total,
        },
    )


@router.post("/contacts/create")
def contacts_create(
    request: Request,
    full_name: str = Form(...),
    mobile: str = Form(...),
    remarks: str = Form(""),
    db: Session = Depends(get_db),
):
    mobile = mobile.strip()
    if not BD_REGEX.match(mobile):
        # Reload the page with a message; your page JS already blocks bad inputs too
        return render(
            request,
            "contacts.html",
            {
                "page": 1,
                "per_page": 10,
                "total": db.query(Contact).count(),
                "rows": [],
                "error": "Please enter a valid BD number: +8801XXXXXXXXX (10 digits after +880).",
            },
        )

    exists = db.query(Contact).filter(Contact.mobile == mobile).first()
    if exists:
        return render(
            request,
            "contacts.html",
            {
                "page": 1,
                "per_page": 10,
                "total": db.query(Contact).count(),
                "rows": [],
                "error": "This mobile already exists.",
            },
        )

    item = Contact(full_name=full_name.strip(), mobile=mobile, remarks=remarks.strip() or None)
    db.add(item)
    db.commit()

    return RedirectResponse(url="/contacts", status_code=303)


def register_routes(app: FastAPI) -> None:
    app.include_router(router)
