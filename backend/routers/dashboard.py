from pathlib import Path

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.routers.auth import verify_token

router = APIRouter(tags=["dashboard"])

HERE = Path(__file__).resolve().parent.parent.parent

STATIC_FILES = {
    "/styles.css": "text/css",
    "/script.js": "application/javascript",
}


@router.get("/")
def serve_index():
    return FileResponse(HERE / "index.html")


@router.get("/index.html")
def serve_index_direct():
    return FileResponse(HERE / "index.html")


@router.get("/live-demo.html")
def serve_live_demo():
    return FileResponse(HERE / "live-demo.html")


@router.get("/styles.css")
def serve_css():
    return FileResponse(HERE / "styles.css", media_type="text/css")


@router.get("/script.js")
def serve_js():
    return FileResponse(HERE / "script.js", media_type="application/javascript")


@router.get("/api/dashboard/stats")
def dashboard_stats(db: Session = Depends(get_db), _=Depends(verify_token)):
    from backend.models import Message

    total = db.query(Message).count()
    latest = db.query(Message).order_by(Message.timestamp.desc()).first()
    return {
        "total_messages": total,
        "latest_timestamp": latest.timestamp.isoformat() if latest else None,
    }
