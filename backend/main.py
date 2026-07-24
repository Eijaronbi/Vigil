import asyncio
import os
import time
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from backend.database import init_db
from backend.middleware import RateLimitMiddleware, SecurityHeadersMiddleware
from backend.routers import auth, chat, config_api, dashboard, groups, messages, public, rules, sources, targets, vault
from backend.tts import TTSEngine

tts_engine: TTSEngine | None = None

START_TIME = time.time()

HERE = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app):
    global tts_engine
    tts_engine = TTSEngine()
    init_db()
    from backend.database import SessionLocal
    from backend.models import User
    db = SessionLocal()
    try:
        users_with_tokens = db.query(User).filter(
            User.telegram_bot_token.isnot(None),
            User.telegram_bot_token != ""
        ).all()
        for u in users_with_tokens:
            try:
                from backend.routers.sources import user_telegram_watchers
                watcher = user_telegram_watchers.get(u.id)
                if watcher and watcher.get("running"):
                    continue
                from backend.watchers.telegram_watcher import TelegramWatcher
                from backend.routers.sources import _save_and_broadcast, _tg_reply_handler
                async def _make_callback(uid=u.id):
                    def cb(msg: dict):
                        msg["user_id"] = uid
                        _save_and_broadcast(msg, uid)
                    return cb
                w = TelegramWatcher(u.telegram_bot_token)
                w.set_message_callback(await _make_callback())
                w.set_reply_handler(_tg_reply_handler)
                await w.start()
                user_telegram_watchers[u.id] = {"watcher": w, "running": True, "username": f"user_{u.id}"}
            except Exception as exc:
                logger = __import__("logging").getLogger("vigil.main")
                logger.warning("Failed to resume Telegram bot for user %s: %s", u.id, exc)

        users_with_wa = db.query(User).filter(
            User.whatsapp_access_token.isnot(None),
            User.whatsapp_access_token != "",
            User.whatsapp_phone_number_id.isnot(None),
        ).all()
        for u in users_with_wa:
            try:
                from backend.watchers.whatsapp_watcher import configure, set_callback
                from backend.routers.sources import _save_and_broadcast
                configure(u.whatsapp_access_token, u.whatsapp_phone_number_id, u.whatsapp_verify_token or "")
                async def _wa_cb(msg: dict):
                    msg["user_id"] = u.id
                    _save_and_broadcast(msg, u.id)
                set_callback(_wa_cb)
                from backend.routers.sources import _WHATSAPP_CONNECTED
                _WHATSAPP_CONNECTED = True
            except Exception as exc:
                logger = __import__("logging").getLogger("vigil.main")
                logger.warning("Failed to resume WhatsApp for user %s: %s", u.id, exc)
    finally:
        db.close()
    yield


app = FastAPI(title="Vigil", version="2.0.0", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(RateLimitMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
    allow_credentials=True,
)

app.include_router(auth.router)
app.include_router(messages.router)
app.include_router(groups.router)
app.include_router(rules.router)
app.include_router(dashboard.router)
app.include_router(sources.router)
app.include_router(targets.router)
app.include_router(chat.router)
app.include_router(config_api.router)
app.include_router(vault.router)
app.include_router(public.router)


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception):
    return JSONResponse(
        status_code=500,
        content={"error": "Internal server error", "request_id": str(id(request))},
    )


@app.get("/api/health")
async def health():
    return {
        "status": "healthy",
        "version": "2.0.0",
        "uptime_seconds": int(time.time() - START_TIME),
        "database": "sqlite",
    }


@app.get("/api/tts")
async def text_to_speech(
    text: str = Query(..., min_length=1, max_length=1000),
    voice: str = Query("en-US-JennyNeural"),
):
    if tts_engine is None:
        return Response(status_code=503, content="TTS not ready")
    audio = await tts_engine.synthesize(text)
    if audio is None:
        return Response(
            status_code=503, content="TTS unavailable (edge-tts not installed?)"
        )
    return Response(content=audio, media_type="audio/mp3")


class SetVoiceRequest(BaseModel):
    voice: str


@app.get("/api/tts/voices")
async def list_voices():
    if tts_engine is None:
        return JSONResponse(status_code=503, content={"error": "TTS not ready"})
    voices = await tts_engine.list_voices()
    grouped: dict[str, list[dict]] = {}
    for v in voices:
        key = v["locale"]
        if key not in grouped:
            grouped[key] = []
        grouped[key].append(v)
    return {"voices": voices, "grouped": grouped, "current": tts_engine.voice}


@app.post("/api/tts/voice")
async def set_voice(body: SetVoiceRequest):
    if tts_engine is None:
        return JSONResponse(status_code=503, content={"error": "TTS not ready"})
    tts_engine.set_voice(body.voice)
    return {"ok": True, "voice": body.voice}


@app.get("/api/tts/priority")
async def priority_tts(
    group: str = Query(""),
    sender: str = Query(""),
    text: str = Query(..., min_length=1, max_length=500),
    summary: str = Query(""),
):
    if tts_engine is None:
        return Response(status_code=503, content="TTS not ready")
    read_text = summary or f"Priority message from {sender} in {group}. {text[:200]}"
    audio = await tts_engine.synthesize(read_text[:500])
    if audio is None:
        return Response(status_code=503, content="TTS unavailable")
    return Response(content=audio, media_type="audio/mp3")


@app.websocket("/ws")
async def websocket_endpoint(websocket):
    from backend.websocket_manager import ws_manager

    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        ws_manager.disconnect(websocket)
