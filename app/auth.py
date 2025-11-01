from fastapi import APIRouter, Request, Form
from starlette.responses import RedirectResponse
from datetime import datetime

auth_router = APIRouter()

# ---- helpers -------------------------------------------------
def current_user(request: Request):
    """Return user dict from session or None."""
    return request.session.get("user")

def login_required(request: Request, next_path: str):
    if not current_user(request):
        return RedirectResponse(url=f"/login?next={next_path}", status_code=303)
    return None

def verify_credentials(username_or_email: str, password: str):
    """
    Replace this with your real DB check if desired.
    For now, accept 'admin' with any non-empty password so the UI works.
    """
    if username_or_email and password:
        # role used by templates like users.html that check for 'superadmin'
        return {"username": username_or_email, "role": "superadmin"}
    return None

# ---- routes --------------------------------------------------
@auth_router.get("/login")
def login_page(request: Request, next: str = "/dashboard"):
    """
    Show login form unless already logged in, then send to 'next'.
    """
    if current_user(request):
        return RedirectResponse(url=next or "/dashboard", status_code=303)

    # Provide 'now' as a datetime OBJECT; use {{ now.year }} in base.html
    ctx = {"request": request, "user": None, "now": datetime.now(), "next": next}
    return request.app.state.templates.TemplateResponse("login.html", ctx)

@auth_router.post("/login")
def login_submit(
    request: Request,
    username: str = Form(..., alias="username"),
    password: str = Form(..., alias="password"),
    next: str = Form("/dashboard")
):
    """
    Handle POST from login form.
    """
    user = verify_credentials(username, password)
    if not user:
        # Simple reload; you could flash a message if you have messaging
        return RedirectResponse(url="/login?next=" + (next or "/dashboard"), status_code=303)

    request.session["user"] = user
    return RedirectResponse(url=next or "/dashboard", status_code=303)

@auth_router.get("/logout")
def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/login", status_code=303)
