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
from backend.routers import auth, dashboard, groups, messages, rules, sources, vault
from backend.tts import TTSEngine

tts_engine: TTSEngine | None = None

START_TIME = time.time()

HERE = Path(__file__).resolve().parent.parent


@asynccontextmanager
async def lifespan(app):
    global tts_engine
    tts_engine = TTSEngine()
    init_db()
    await sources.init_telegram_bot()
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
app.include_router(vault.router)


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
