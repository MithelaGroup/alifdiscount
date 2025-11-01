# app/views.py
from __future__ import annotations

from typing import Any, Dict, Optional
from fastapi import FastAPI, Request
from starlette.responses import RedirectResponse

# --- DB session helper (works with your current database.py) ---------------

def _new_session():
    """
    Try common patterns: SessionLocal(), get_session(), get_db().
    Returns a session or None (never raises at import-time).
    """
    try:
        from app.database import SessionLocal  # type: ignore
        return SessionLocal()
    except Exception:
        pass
    try:
        from app.database import get_session  # type: ignore
        return get_session()
    except Exception:
        pass
    try:
        # Some projects expose a generator get_db()
        from app.database import get_db  # type: ignore

        try:
            return next(get_db())
        except Exception:
            pass
    except Exception:
        pass
    return None

# --- Model aliases (tolerant to different names) ---------------------------

def _models():
    import importlib

    m = importlib.import_module("app.models")  # your models.py
    # Table aliases (whichever exists in your models)
    User = getattr(m, "User", None)
    Coupon = getattr(m, "Coupon", None)
    Group = (
        getattr(m, "DiscountGroup", None)
        or getattr(m, "CouponGroup", None)
        or getattr(m, "Group", None)
    )
    RequestModel = getattr(m, "CouponRequest", None) or getattr(m, "Request", None)
    RequestStatus = getattr(m, "RequestStatus", None)
    return User, Coupon, Group, RequestModel, RequestStatus


# --- User / auth helpers ---------------------------------------------------

def _current_user(request: Request):
    """
    Read the logged-in user from session. We support both (id) and (dict) forms.
    """
    uid = request.session.get("user_id")
    uname = request.session.get("username")
    if not uid and not uname:
        return None

    User, *_ = _models()
    if User is None:
        # we can still display the name if stored in session
        return {"username": uname, "id": uid}
    db = _new_session()
    if not db:
        return {"username": uname, "id": uid}
    try:
        if hasattr(User, "id") and uid:
            return db.query(User).filter(User.id == uid).first()
    except Exception:
        pass
    finally:
        try:
            db.close()
        except Exception:
            pass
    return {"username": uname, "id": uid}


def _require_login(request: Request) -> Optional[RedirectResponse]:
    """Redirect to /login if no user session."""
    if _current_user(request) is None:
        return RedirectResponse("/login", status_code=303)
    return None


# --- Rendering helper injects user + conf everywhere -----------------------

def render(request: Request, template_name: str, ctx: Dict[str, Any]):
    user = _current_user(request)
    base = {
        "request": request,
        "user": user,
        "conf": getattr(request.app.state, "conf", None),
    }
    base.update(ctx or {})
    return request.app.state.templates.TemplateResponse(template_name, base)  # type: ignore[attr-defined]


# --- Pages -----------------------------------------------------------------

def register_routes(app: FastAPI):

    @app.get("/dashboard")
    def dashboard(request: Request):
        if (redir := _require_login(request)) is not None:
            return redir

        User, Coupon, Group, RequestModel, RequestStatus = _models()

        # Three tiles: counts
        pending_cnt = approved_cnt = done_cnt = 0

        db = _new_session()
        rows = []
        if db and RequestModel is not None:
            # Figure out created_at / id for sorting
            created_col = getattr(RequestModel, "created_at", None) or getattr(RequestModel, "created", None) or getattr(RequestModel, "id", None)

            # best-effort status enum / string
            def _sv(name: str):
                return getattr(RequestStatus, name, name) if RequestStatus else name

            try:
                # counts
                if hasattr(RequestModel, "status"):
                    pending_cnt = db.query(RequestModel).filter(RequestModel.status == _sv("PENDING")).count()
                    approved_cnt = db.query(RequestModel).filter(RequestModel.status == _sv("APPROVED")).count()
                    done_cnt = db.query(RequestModel).filter(RequestModel.status == _sv("DONE")).count()

                # latest 10
                if created_col is not None:
                    rows = (
                        db.query(RequestModel)
                        .order_by(created_col.desc())
                        .limit(10)
                        .all()
                    )
                else:
                    rows = db.query(RequestModel).limit(10).all()
            except Exception:
                rows = []
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        return render(
            request,
            "dashboard.html",
            {
                "pending_cnt": pending_cnt,
                "approved_cnt": approved_cnt,
                "done_cnt": done_cnt,
                "rows": rows,
                "status_enum": RequestStatus,  # for template comparisons
            },
        )

    @app.get("/contacts")
    def contacts(request: Request):
        if (redir := _require_login(request)) is not None:
            return redir

        # Optional contacts module
        try:
            from app.models_contact import Contact  # type: ignore
        except Exception:
            Contact = None

        db = _new_session()
        items = []
        if db and Contact is not None:
            try:
                items = db.query(Contact).all()
            except Exception:
                items = []
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        return render(request, "contacts.html", {"contacts": items})

    @app.get("/users")
    def users(request: Request):
        if (redir := _require_login(request)) is not None:
            return redir

        User, *_ = _models()
        db = _new_session()
        rows = []
        if db and User is not None:
            try:
                rows = db.query(User).all()
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        return render(request, "users.html", {"rows": rows})

    @app.get("/requests")
    def requests_list(request: Request):
        if (redir := _require_login(request)) is not None:
            return redir

        _, _, _, RequestModel, RequestStatus = _models()
        db = _new_session()
        rows = []
        if db and RequestModel is not None:
            created_col = getattr(RequestModel, "created_at", None) or getattr(RequestModel, "created", None) or getattr(RequestModel, "id", None)
            try:
                if created_col is not None:
                    rows = (
                        db.query(RequestModel)
                        .order_by(created_col.desc())
                        .limit(10)
                        .all()
                    )
                else:
                    rows = db.query(RequestModel).limit(10).all()
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        return render(
            request,
            "requests.html",
            {"rows": rows, "status_enum": RequestStatus},
        )

    @app.get("/request/create")
    def request_create(request: Request):
        if (redir := _require_login(request)) is not None:
            return redir
        # Your existing create form lives in templates/request_create.html
        return render(request, "request_create.html", {})

    @app.get("/enlist")
    def enlist(request: Request):
        if (redir := _require_login(request)) is not None:
            return redir

        _, Coupon, Group, *_ = _models()
        db = _new_session()
        groups, coupons = [], []
        if db:
            try:
                if Group is not None:
                    # order by name/percent if available
                    order_col = getattr(Group, "percent", None) or getattr(Group, "name", None) or getattr(Group, "id", None)
                    q = db.query(Group)
                    if order_col is not None:
                        q = q.order_by(order_col.desc())
                    groups = q.all()
                if Coupon is not None:
                    order_col = getattr(Coupon, "created_at", None) or getattr(Coupon, "enlisted_at", None) or getattr(Coupon, "id", None)
                    q = db.query(Coupon)
                    if order_col is not None:
                        q = q.order_by(order_col.desc())
                    coupons = q.all()
            finally:
                try:
                    db.close()
                except Exception:
                    pass

        return render(request, "enlist.html", {"groups": groups, "coupons": coupons})

    @app.get("/settings")
    def settings(request: Request):
        if (redir := _require_login(request)) is not None:
            return redir

        return render(request, "settings.html", {})
    
    @app.get("/pwa")
    def pwa(request: Request):
        # PWA page can be public; no redirect here
        return render(request, "pwa.html", {})
