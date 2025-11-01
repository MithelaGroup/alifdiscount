from fastapi import APIRouter, Depends, Request, Form
from fastapi.responses import PlainTextResponse, JSONResponse, HTMLResponse
from sqlalchemy.orm import Session
from app.config import settings
from app.database import get_db
from app.auth import require_login
from app.models import PushSubscription

router = APIRouter()


@router.get("/vapid_public_key", response_class=PlainTextResponse)
def vapid_public_key() -> str:
    return settings.vapid_public_key or ""


@router.get("/push/enable", response_class=HTMLResponse)
def push_enable_page():
    return """
<!doctype html><meta charset=utf-8>
<title>Enable Push</title>
<link rel="stylesheet" href="/static/theme.css">
<div class="container" style="padding:28px">
  <h2>Enable Push Notifications</h2>
  <p>Click the button to register your browser for push notifications.</p>
  <button class="btn btn-primary" id="btn">Enable Push</button>
</div>
<script src="/static/app.js"></script>
<script>window.enablePushFromPage&&window.enablePushFromPage()</script>
"""


@router.post("/push/subscribe")
def push_subscribe(
    db: Session = Depends(get_db),
    user=Depends(require_login),
    endpoint: str = Form(...),
    p256dh: str = Form(...),
    auth: str = Form(...),
):
    # upsert per user+endpoint
    row = db.query(PushSubscription).filter(PushSubscription.endpoint == endpoint).first()
    if not row:
        row = PushSubscription(user_id=user.id, endpoint=endpoint, p256dh=p256dh, auth=auth)
        db.add(row)
    else:
        row.user_id = user.id
        row.p256dh = p256dh
        row.auth = auth
    db.commit()
    return {"ok": True}


@router.get("/push/test")
def push_test():
    # placeholder (you can wire pywebpush here if you want server-side test)
    return {"ok": True}
