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


@router.get("/api/dashboard/brief")
def dashboard_brief(db: Session = Depends(get_db), _=Depends(verify_token)):
    from datetime import datetime, timedelta
    from backend.models import Message, Group

    today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    total = db.query(Message).count()
    today_count = db.query(Message).filter(Message.timestamp >= today).count()
    yesterday_count = db.query(Message).filter(
        Message.timestamp >= yesterday, Message.timestamp < today
    ).count()

    groups = db.query(Group).all()
    sources = {}
    for g in groups:
        sources[g.source] = sources.get(g.source, 0) + 1

    priority_groups = [g for g in groups if g.is_priority]

    latest_msgs = (
        db.query(Message).order_by(Message.timestamp.desc()).limit(3).all()
    )

    return {
        "total_messages": total,
        "today": today_count,
        "yesterday": yesterday_count,
        "sources": sources,
        "group_count": len(groups),
        "priority_group_count": len(priority_groups),
        "latest": [
            {
                "source": m.source,
                "sender": m.sender,
                "text": m.text[:80] if m.text else "",
                "score": getattr(m, "importance_score", None),
            }
            for m in latest_msgs
        ],
    }
