from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers import dashboard, groups, messages, rules


@asynccontextmanager
async def lifespan(app):
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


@app.websocket("/ws")
async def websocket_endpoint(websocket):
    from backend.websocket_manager import ws_manager

    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        ws_manager.disconnect(websocket)
