import json
import requests
from app.config import settings

GRAPH_URL = "https://graph.facebook.com/v20.0"

def send_whatsapp_text(to_e164: str, message: str) -> bool:
    token = settings.WHATSAPP_TOKEN
    phone_id = settings.WHATSAPP_PHONE_NUMBER_ID
    if not token or not phone_id:
        print("WhatsApp not configured; skipping send.")
        return False
    url = f"{GRAPH_URL}/{phone_id}/messages"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    payload = {
        "messaging_product": "whatsapp",
        "to": to_e164.replace("+", ""),  # WA expects country code without '+'
        "type": "text",
        "text": {"body": message},
    }
    try:
        resp = requests.post(url, headers=headers, data=json.dumps(payload), timeout=15)
        print("WA response:", resp.status_code, resp.text[:300])
        return 200 <= resp.status_code < 300
    except Exception as e:
        print("WhatsApp send error:", e)
        return False

def render_coupon_message(name: str, discount: int, coupon_code: str, request_code: str) -> str:
    tpl = settings.WHATSAPP_TEMPLATE_TEXT
    return tpl.format(name=name, discount=discount, coupon=coupon_code, request_code=request_code)
