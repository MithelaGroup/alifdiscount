import json
from sqlalchemy.orm import Session
from pywebpush import webpush, WebPushException
from app.config import settings
from app.models import PushSubscription, User, Role


def _push(sub: PushSubscription, title: str, body: str, url: str | None = None):
    payload = {"title": title, "body": body}
    if url:
        payload["url"] = url

    webpush(
        subscription_info={
            "endpoint": sub.endpoint,
            "keys": {"p256dh": sub.p256dh, "auth": sub.auth},
        },
        data=json.dumps(payload),
        vapid_private_key=settings.VAPID_PRIVATE_KEY,
        vapid_claims={"sub": settings.VAPID_EMAIL},
        timeout=10,
    )


def send_push_to_user(db: Session, user_id: int, title: str, body: str, url: str | None = None):
    subs = db.query(PushSubscription).filter(PushSubscription.user_id == user_id).all()
    for s in subs:
        try:
            _push(s, title, body, url=url)
        except WebPushException:
            # If expired/invalid, ignore for now
            pass


def send_push_to_role(db: Session, role: Role, title: str, body: str, url: str | None = None):
    users = db.query(User).filter(User.role == role, User.is_active == True).all()
    for u in users:
        send_push_to_user(db, u.id, title, body, url=url)
