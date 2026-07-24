import hashlib
import hmac
import logging
from datetime import datetime, timezone

import httpx

logger = logging.getLogger("vigil.whatsapp")

WHATSAPP_API_BASE = "https://graph.facebook.com/v21.0"

_ACCESS_TOKEN = ""
_PHONE_NUMBER_ID = ""
_VERIFY_TOKEN = ""
_CALLBACK = None
_WEBHOOK_SECRET = ""


def configure(access_token: str, phone_number_id: str, verify_token: str):
    global _ACCESS_TOKEN, _PHONE_NUMBER_ID, _VERIFY_TOKEN
    _ACCESS_TOKEN = access_token
    _PHONE_NUMBER_ID = phone_number_id
    _VERIFY_TOKEN = verify_token


def set_callback(callback):
    global _CALLBACK
    _CALLBACK = callback


def verify_webhook(mode: str, token: str, challenge: str):
    if mode == "subscribe" and token == _VERIFY_TOKEN and challenge:
        return int(challenge)
    return None


def _headers() -> dict:
    return {
        "Authorization": f"Bearer {_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }


async def send_message(to: str, text: str) -> dict:
    if not _ACCESS_TOKEN or not _PHONE_NUMBER_ID:
        return {"ok": False, "error": "WhatsApp not configured"}
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": to,
        "type": "text",
        "text": {"preview_url": False, "body": text},
    }
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.post(
                f"{WHATSAPP_API_BASE}/{_PHONE_NUMBER_ID}/messages",
                headers=_headers(),
                json=payload,
            )
            data = resp.json()
            if resp.status_code == 200:
                return {"ok": True, "message_id": data.get("messages", [{}])[0].get("id")}
            return {"ok": False, "error": data}
    except Exception as e:
        return {"ok": False, "error": str(e)}


async def process_webhook(body: dict):
    changes = []
    for entry in body.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            for msg in value.get("messages", []):
                chat = _extract_chat(msg, value)
                if chat:
                    changes.append(chat)
                    if _CALLBACK:
                        await _CALLBACK(chat)
    return changes


def _extract_chat(msg: dict, value: dict) -> dict | None:
    msg_type = msg.get("type")
    text = ""
    if msg_type == "text":
        text = msg.get("text", {}).get("body", "")
    elif msg_type in ("image", "video", "audio", "document"):
        text = f"[{msg_type}] {msg.get(msg_type, {}).get('caption', '') or ''}"
    elif msg_type == "interactive":
        interactive = msg.get("interactive", {})
        if interactive.get("type") == "button_reply":
            text = interactive.get("button_reply", {}).get("title", "")
        elif interactive.get("type") == "list_reply":
            text = interactive.get("list_reply", {}).get("title", "")

    if not text:
        return None

    profile = value.get("contacts", [{}])[0] if value.get("contacts") else {}
    sender_name = profile.get("profile", {}).get("name", "Unknown")
    wa_id = msg.get("from", "")
    chat_name = value.get("metadata", {}).get("display_phone_number", "WhatsApp")

    return {
        "source": "whatsapp",
        "sender": sender_name,
        "sender_id": wa_id,
        "group_name": chat_name,
        "text": text,
        "timestamp": datetime.now(timezone.utc).replace(tzinfo=None),
        "group_external_id": wa_id,
        "message_id": msg.get("id", ""),
    }


def check_signature(body: bytes, signature_header: str | None) -> bool:
    if not _WEBHOOK_SECRET or not signature_header:
        return False
    expected = "sha256=" + hmac.new(
        _WEBHOOK_SECRET.encode(), body, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature_header)
