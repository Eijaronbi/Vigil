from contextlib import asynccontextmanager

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response

from backend.database import init_db
from backend.routers import dashboard, groups, messages, rules
from backend.tts import TTSEngine


tts_engine: TTSEngine | None = None


@asynccontextmanager
async def lifespan(app):
    global tts_engine
    tts_engine = TTSEngine()
    init_db()
    yield


app = FastAPI(title="Message Monitor", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"]
)

app.include_router(messages.router)
app.include_router(groups.router)
app.include_router(rules.router)
app.include_router(dashboard.router)


@app.get("/api/tts")
async def text_to_speech(
    text: str = Query(..., min_length=1, max_length=1000),
    voice: str = Query("en-US-JennyNeural"),
):
    if tts_engine is None:
        return Response(status_code=503, content="TTS not ready")

    audio = await tts_engine.synthesize(text)
    if audio is None:
        return Response(status_code=503, content="TTS unavailable (edge-tts not installed?)")

    return Response(content=audio, media_type="audio/mp3")


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
