import os
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import SessionLocal, get_db
from backend.models import User
from backend.routers.auth import get_current_user as auth_get_current_user

get_current_user = auth_get_current_user

router = APIRouter(prefix="/api/sources", tags=["sources"])

TELEGRAM_BOT_INFO: dict | None = None
_TG_WATCHER = None
_DISCORD_WATCHER = None
_DISCORD_BOT_INFO: dict | None = None
_JINA_WATCHER = None
_PROFILE_HANDLES: dict = {}

user_telegram_watchers: dict[int, dict] = {}


class TelegramConnectRequest(BaseModel):
    token: str


class TelegramUserConnectRequest(BaseModel):
    token: str


class DiscordConnectRequest(BaseModel):
    token: str


class JinaConnectRequest(BaseModel):
    platform: str
    handle: str


class JinaDisconnectRequest(BaseModel):
    platform: str
    handle: str


def _save_and_broadcast(msg: dict, user_id: int = 1):
    db = SessionLocal()
    try:
        from backend.models import Group, Message
        ext_id = str(msg.get("group_external_id", "")) or msg.get("group_name", "unknown")
        uid = msg.get("user_id", user_id)
        group = (
            db.query(Group)
            .filter(Group.source == msg["source"], Group.external_id == ext_id)
            .first()
        )
        if not group:
            group = Group(
                source=msg["source"],
                name=msg.get("group_name", "Unknown"),
                external_id=ext_id,
                user_id=uid,
            )
            db.add(group)
            db.commit()
            db.refresh(group)
        db_msg = Message(
            group_id=group.id,
            source=msg["source"],
            sender=msg.get("sender", "Unknown"),
            text=msg.get("text", ""),
            timestamp=msg.get("timestamp"),
        )
        db.add(db_msg)
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
    import asyncio
    try:
        from backend.websocket_manager import ws_manager
        loop = asyncio.new_event_loop()
        loop.run_until_complete(ws_manager.broadcast({
            "type": "alert",
            "source": msg.get("source"),
            "sender": msg.get("sender"),
            "group_name": msg.get("group_name"),
            "text": msg.get("text"),
        }))
        loop.close()
    except Exception:
        pass


def _tg_callback(msg: dict):
    _save_and_broadcast(msg)


def _discord_callback(msg: dict):
    _save_and_broadcast(msg)


def _jina_callback(msg: dict):
    _save_and_broadcast(msg)


@router.get("")
def list_sources():
    from backend.models import Group

    db = SessionLocal()
    try:
        telegram_groups = db.query(Group).filter(Group.source == "telegram").count()
        discord_groups = db.query(Group).filter(Group.source == "discord").count()
        twitter_profiles = db.query(Group).filter(Group.source == "twitter").count()
        facebook_profiles = db.query(Group).filter(Group.source == "facebook").count()
    finally:
        db.close()

    return {
        "sources": [
            {
                "id": "telegram",
                "name": "Telegram",
                "connected": TELEGRAM_BOT_INFO is not None,
                "bot_username": TELEGRAM_BOT_INFO.get("username") if TELEGRAM_BOT_INFO else None,
                "group_count": telegram_groups,
            },
            {
                "id": "discord",
                "name": "Discord",
                "connected": _DISCORD_BOT_INFO is not None,
                "bot_username": _DISCORD_BOT_INFO.get("username") if _DISCORD_BOT_INFO else None,
                "group_count": discord_groups,
            },
            {
                "id": "twitter",
                "name": "Twitter / X",
                "connected": len(_PROFILE_HANDLES.get("twitter", [])) > 0,
                "profile_count": len(_PROFILE_HANDLES.get("twitter", [])),
            },
            {
                "id": "facebook",
                "name": "Facebook",
                "connected": len(_PROFILE_HANDLES.get("facebook", [])) > 0,
                "profile_count": len(_PROFILE_HANDLES.get("facebook", [])),
            },
            {
                "id": "gmail",
                "name": "Gmail",
                "connected": bool(settings.gmail_oauth_refresh_token),
            },
            {
                "id": "whatsapp",
                "name": "WhatsApp",
                "connected": _WHATSAPP_CONNECTED,
            },
        ]
    }


@router.post("/telegram/connect")
async def connect_telegram(body: TelegramConnectRequest):
    result = await _verify_token(body.token)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid token or bot not found")
    global TELEGRAM_BOT_INFO
    TELEGRAM_BOT_INFO = result
    settings.telegram_bot_token = body.token
    await _start_watcher(body.token)
    return {"connected": True, "bot_username": result["username"]}


@router.post("/telegram/disconnect")
async def disconnect_telegram():
    global TELEGRAM_BOT_INFO
    TELEGRAM_BOT_INFO = None
    settings.telegram_bot_token = ""
    await _stop_watcher()
    return {"connected": False}


@router.get("/telegram/info")
def telegram_info():
    if not TELEGRAM_BOT_INFO:
        return {"connected": False}
    return {
        "connected": True,
        "bot_username": TELEGRAM_BOT_INFO.get("username"),
        "bot_name": TELEGRAM_BOT_INFO.get("first_name"),
    }


@router.get("/telegram/groups")
def telegram_groups():
    from backend.models import Group

    db = SessionLocal()
    try:
        groups = (
            db.query(Group)
            .filter(Group.source == "telegram")
            .order_by(Group.name)
            .all()
        )
        return [
            {"id": g.id, "name": g.name, "external_id": g.external_id, "enabled": g.enabled}
            for g in groups
        ]
    finally:
        db.close()


@router.post("/telegram/sync-groups")
async def telegram_sync_groups():
    global _TG_WATCHER
    if not _TG_WATCHER:
        return {"ok": False, "error": "Telegram bot not connected"}
    try:
        updates = await _TG_WATCHER.fetch_updates()
        new_count = 0
        from backend.models import Group
        from backend.database import SessionLocal

        db = SessionLocal()
        try:
            for update in updates:
                msg = update.get("message", {})
                chat = msg.get("chat", {})
                chat_id = str(chat.get("id"))
                title = chat.get("title") or chat.get("first_name", "Unknown")
                existing = db.query(Group).filter(
                    Group.source == "telegram", Group.external_id == chat_id
                ).first()
                if not existing:
                    group = Group(
                        source="telegram",
                        name=title,
                        external_id=chat_id,
                        user_id=1,
                    )
                    db.add(group)
                    new_count += 1
            db.commit()
        finally:
            db.close()
        return {"ok": True, "new_groups": new_count, "total": len(updates)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.post("/telegram/connect-user")
async def connect_telegram_user(
    body: TelegramUserConnectRequest,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await _verify_token(body.token)
    if not result:
        raise HTTPException(status_code=400, detail="Invalid token or bot not found")

    current_user.telegram_bot_token = body.token
    db.commit()

    global user_telegram_watchers
    existing = user_telegram_watchers.get(current_user.id)
    if existing and existing.get("watcher"):
        try:
            await existing["watcher"].stop()
        except Exception:
            pass

    from backend.watchers.telegram_watcher import TelegramWatcher
    async def _user_cb(uid: int):
        def cb(msg: dict):
            msg["user_id"] = uid
            _save_and_broadcast(msg, uid)
        return cb

    global _TG_WATCHER, TELEGRAM_BOT_INFO
    watcher = TelegramWatcher(body.token)
    watcher.set_message_callback(await _user_cb(current_user.id))
    user_telegram_watchers[current_user.id] = {
        "watcher": watcher,
        "running": True,
        "username": result.get("username"),
    }
    if not _TG_WATCHER:
        _TG_WATCHER = watcher
        TELEGRAM_BOT_INFO = result
    await watcher.start()
    return {"connected": True, "bot_username": result["username"]}


@router.post("/telegram/disconnect-user")
async def disconnect_telegram_user(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    global user_telegram_watchers
    entry = user_telegram_watchers.pop(current_user.id, None)
    if entry and entry.get("watcher"):
        try:
            await entry["watcher"].stop()
        except Exception:
            pass
    current_user.telegram_bot_token = None
    db.commit()
    return {"connected": False}


@router.post("/telegram/sync-groups-user")
async def telegram_sync_groups_user(
    current_user: User = Depends(get_current_user),
):
    entry = user_telegram_watchers.get(current_user.id)
    if not entry or not entry.get("running"):
        return {"ok": False, "error": "Telegram bot not connected for this user"}
    watcher = entry["watcher"]
    try:
        updates = await watcher.fetch_updates() if hasattr(watcher, 'fetch_updates') else []
        new_count = 0
        from backend.models import Group
        from backend.database import SessionLocal
        db = SessionLocal()
        try:
            for update in updates:
                msg = update.get("message", {})
                chat = msg.get("chat", {})
                chat_id = str(chat.get("id"))
                title = chat.get("title") or chat.get("first_name", "Unknown")
                existing = db.query(Group).filter(
                    Group.source == "telegram", Group.external_id == chat_id
                ).first()
                if not existing:
                    group = Group(
                        source="telegram",
                        name=title,
                        external_id=chat_id,
                        user_id=current_user.id,
                    )
                    db.add(group)
                    new_count += 1
            db.commit()
        finally:
            db.close()
        return {"ok": True, "new_groups": new_count}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@router.get("/telegram/status-user")
def telegram_status_user(current_user: User = Depends(get_current_user)):
    entry = user_telegram_watchers.get(current_user.id)
    if entry and entry.get("running"):
        return {"connected": True, "bot_username": entry.get("username")}
    if current_user.telegram_bot_token:
        return {"connected": False, "token_stored": True}
    return {"connected": False, "token_stored": False}


DISCORD_BOT_TOKEN_STORED: str = ""


@router.post("/discord/connect")
async def connect_discord(body: DiscordConnectRequest):
    global _DISCORD_BOT_INFO, _DISCORD_WATCHER, DISCORD_BOT_TOKEN_STORED
    from backend.watchers.discord_watcher import DiscordWatcher
    watcher = DiscordWatcher(body.token)
    watcher.set_callback(_discord_callback)
    try:
        await watcher.start()
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Discord connection failed: {e}")
    _DISCORD_WATCHER = watcher
    _DISCORD_BOT_INFO = {"username": "connected"}
    DISCORD_BOT_TOKEN_STORED = body.token
    return {"connected": True}


@router.post("/discord/disconnect")
async def disconnect_discord():
    global _DISCORD_BOT_INFO, _DISCORD_WATCHER, DISCORD_BOT_TOKEN_STORED
    if _DISCORD_WATCHER:
        await _DISCORD_WATCHER.stop()
    _DISCORD_WATCHER = None
    _DISCORD_BOT_INFO = None
    DISCORD_BOT_TOKEN_STORED = ""
    return {"connected": False}


@router.get("/discord/info")
def discord_info():
    if not _DISCORD_BOT_INFO:
        return {"connected": False}
    servers = _DISCORD_WATCHER._servers if _DISCORD_WATCHER else []
    return {"connected": True, "servers": servers}


@router.post("/jina/connect")
async def connect_jina(body: JinaConnectRequest):
    global _JINA_WATCHER
    from backend.watchers.jina_watcher import JinaWatcher
    if not _JINA_WATCHER:
        _JINA_WATCHER = JinaWatcher()
        _JINA_WATCHER.set_callback(_jina_callback)
        await _JINA_WATCHER.start()
    _JINA_WATCHER.add_profile(body.platform, body.handle)
    if body.platform not in _PROFILE_HANDLES:
        _PROFILE_HANDLES[body.platform] = []
    if body.handle not in _PROFILE_HANDLES[body.platform]:
        _PROFILE_HANDLES[body.platform].append(body.handle)
    return {"connected": True, "platform": body.platform, "handle": body.handle}


@router.post("/jina/disconnect")
async def disconnect_jina(body: JinaDisconnectRequest):
    if _JINA_WATCHER:
        _JINA_WATCHER.remove_profile(body.platform, body.handle)
    if body.platform in _PROFILE_HANDLES:
        _PROFILE_HANDLES[body.platform] = [h for h in _PROFILE_HANDLES[body.platform] if h != body.handle]
    return {"connected": False, "platform": body.platform, "handle": body.handle}


@router.get("/jina/profiles")
def jina_profiles():
    return {"profiles": _PROFILE_HANDLES}


async def _verify_token(token: str) -> dict | None:
    try:
        from telegram import Bot
        bot = Bot(token=token)
        me = await bot.get_me()
        return {"id": me.id, "username": me.username, "first_name": me.first_name}
    except Exception:
        return None


async def _tg_callback_async(msg: dict):
    _save_and_broadcast(msg)


async def _start_watcher(token: str):
    global _TG_WATCHER
    await _stop_watcher()
    from backend.watchers.telegram_watcher import TelegramWatcher
    watcher = TelegramWatcher(token)
    watcher.set_message_callback(_tg_callback_async)
    _TG_WATCHER = watcher
    await watcher.start()


async def _stop_watcher():
    global _TG_WATCHER
    if _TG_WATCHER:
        try:
            await _TG_WATCHER.stop()
        except Exception:
            pass
        _TG_WATCHER = None


async def init_telegram_bot():
    if settings.telegram_bot_token:
        result = await _verify_token(settings.telegram_bot_token)
        if result:
            global TELEGRAM_BOT_INFO
            TELEGRAM_BOT_INFO = result
            await _start_watcher(settings.telegram_bot_token)


_WHATSAPP_CONNECTED = False


@router.post("/whatsapp/message")
async def whatsapp_message(body: dict):
    global _WHATSAPP_CONNECTED
    _WHATSAPP_CONNECTED = True
    from backend.models import Group, Message
    from backend.classifier.classification_service import classify_message
    from backend.schemas import MessageIn

    group_name = body.get("group_name", "WhatsApp")
    sender = body.get("sender", "Unknown")
    text = body.get("text", "")
    if not text:
        return {"ok": False, "error": "empty text"}

    db = SessionLocal()
    try:
        group = db.query(Group).filter(Group.source == "whatsapp", Group.name == group_name).first()
        if not group:
            group = Group(source="whatsapp", name=group_name, external_id=group_name, user_id=1)
            db.add(group)
            db.commit()
            db.refresh(group)

        msg_body = MessageIn(source="whatsapp", group_name=group_name, sender=sender, text=text)
        db_msg = Message(group_id=group.id, source="whatsapp", sender=sender, text=text, timestamp=datetime.now())
        db.add(db_msg)
        db.commit()
        db.refresh(db_msg)

        await classify_message(db, db_msg, msg_body)
        db.refresh(db_msg)

        import asyncio
        try:
            from backend.websocket_manager import ws_manager
            asyncio.create_task(ws_manager.broadcast({
                "type": "alert",
                "source": "whatsapp",
                "sender": sender,
                "group_name": group_name,
                "text": text[:500],
            }))
        except Exception:
            pass

        return {"ok": True, "message_id": db_msg.id, "score": db_msg.importance_score}
    finally:
        db.close()


@router.get("/whatsapp/status")
def whatsapp_status():
    return {"connected": _WHATSAPP_CONNECTED}


_WHATSAPP_AUTH_TOKEN: str = ""


class WhatsAppAuthRequest(BaseModel):
    token: str


@router.post("/whatsapp/auth")
async def whatsapp_auth(body: WhatsAppAuthRequest):
    global _WHATSAPP_AUTH_TOKEN
    _WHATSAPP_AUTH_TOKEN = body.token
    return {"ok": True, "authenticated": True}


@router.get("/whatsapp/auth-token")
def whatsapp_get_auth_token():
    if not _WHATSAPP_AUTH_TOKEN:
        _WHATSAPP_AUTH_TOKEN = os.urandom(16).hex()
    return {"token": _WHATSAPP_AUTH_TOKEN}
