import asyncio
import time
from datetime import datetime, timezone

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import MonitorTarget, SavedUrl

router = APIRouter(prefix="/api/targets", tags=["targets"])


class AddTargetRequest(BaseModel):
    source: str
    target_type: str
    target_id: str
    label: str = ""


class SaveUrlRequest(BaseModel):
    url: str
    title: str = ""
    note: str = ""


class UpdateTargetRequest(BaseModel):
    enabled: bool | None = None
    label: str | None = None


@router.get("")
def list_targets(db: Session = Depends(get_db)):
    targets = db.query(MonitorTarget).filter(MonitorTarget.user_id == 1).order_by(MonitorTarget.created_at.desc()).all()
    return {
        "targets": [
            {
                "id": t.id,
                "source": t.source,
                "target_type": t.target_type,
                "target_id": t.target_id,
                "label": t.label,
                "enabled": t.enabled,
                "last_checked": t.last_checked.isoformat() if t.last_checked else None,
                "last_post_text": t.last_post_text[:200] if t.last_post_text else None,
                "saved_url_count": len(t.saved_urls),
                "created_at": t.created_at.isoformat(),
            }
            for t in targets
        ]
    }


@router.post("")
def add_target(body: AddTargetRequest, db: Session = Depends(get_db)):
    source = body.source.lower()
    if source not in ("telegram", "facebook", "twitter", "x", "whatsapp", "discord"):
        raise HTTPException(status_code=400, detail="Invalid source")
    if body.target_type not in ("profile", "group", "url"):
        raise HTTPException(status_code=400, detail="Invalid target_type")

    clean_source = "twitter" if source == "x" else source
    clean_id = body.target_id.strip()
    if clean_source == "twitter":
        clean_id = clean_id.replace("https://x.com/", "").replace("https://twitter.com/", "").split("?")[0].split("/")[0]
    elif clean_source == "facebook":
        clean_id = clean_id.replace("https://facebook.com/", "").replace("https://www.facebook.com/", "").split("?")[0].split("/")[0]

    existing = db.query(MonitorTarget).filter(
        MonitorTarget.user_id == 1,
        MonitorTarget.source == clean_source,
        MonitorTarget.target_id == clean_id,
    ).first()
    if existing:
        raise HTTPException(status_code=409, detail="Target already exists")

    label = body.label or clean_id
    target = MonitorTarget(
        user_id=1,
        source=clean_source,
        target_type=body.target_type,
        target_id=clean_id,
        label=label,
    )
    db.add(target)
    db.commit()
    db.refresh(target)
    return {
        "id": target.id,
        "source": target.source,
        "target_type": target.target_type,
        "target_id": target.target_id,
        "label": target.label,
        "enabled": target.enabled,
    }


@router.delete("/{target_id}")
def delete_target(target_id: int, db: Session = Depends(get_db)):
    target = db.query(MonitorTarget).filter(MonitorTarget.id == target_id, MonitorTarget.user_id == 1).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    db.delete(target)
    db.commit()
    return {"ok": True}


@router.put("/{target_id}")
def update_target(target_id: int, body: UpdateTargetRequest, db: Session = Depends(get_db)):
    target = db.query(MonitorTarget).filter(MonitorTarget.id == target_id, MonitorTarget.user_id == 1).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    if body.enabled is not None:
        target.enabled = body.enabled
    if body.label is not None:
        target.label = body.label
    db.commit()
    return {"ok": True}


@router.get("/{target_id}/saved-urls")
def list_saved_urls(target_id: int, db: Session = Depends(get_db)):
    target = db.query(MonitorTarget).filter(MonitorTarget.id == target_id, MonitorTarget.user_id == 1).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    return {
        "urls": [
            {
                "id": u.id,
                "url": u.url,
                "title": u.title,
                "note": u.note,
                "created_at": u.created_at.isoformat(),
            }
            for u in target.saved_urls
        ]
    }


@router.post("/{target_id}/saved-urls")
def save_url(target_id: int, body: SaveUrlRequest, db: Session = Depends(get_db)):
    target = db.query(MonitorTarget).filter(MonitorTarget.id == target_id, MonitorTarget.user_id == 1).first()
    if not target:
        raise HTTPException(status_code=404, detail="Target not found")
    saved = SavedUrl(target_id=target.id, url=body.url, title=body.title, note=body.note)
    db.add(saved)
    db.commit()
    return {"ok": True, "id": saved.id}


@router.delete("/saved-urls/{url_id}")
def delete_saved_url(url_id: int, db: Session = Depends(get_db)):
    saved = db.query(SavedUrl).filter(SavedUrl.id == url_id).first()
    if not saved:
        raise HTTPException(status_code=404, detail="Saved URL not found")
    db.delete(saved)
    db.commit()
    return {"ok": True}


@router.get("/poll")
async def poll_targets(db: Session = Depends(get_db)):
    targets = db.query(MonitorTarget).filter(MonitorTarget.user_id == 1, MonitorTarget.enabled == True).all()
    new_posts = []
    for target in targets:
        try:
            posts = await _fetch_target_posts(target)
            for post in posts:
                new_posts.append(post)
                from backend.websocket_manager import ws_manager
                asyncio.create_task(ws_manager.broadcast({
                    "type": "target_alert",
                    "source": post["source"],
                    "sender": post["sender"],
                    "target_label": target.label,
                    "text": post["text"][:500],
                    "url": post.get("url", ""),
                    "target_id": target.id,
                }))
            target.last_checked = datetime.now(timezone.utc)
        except Exception:
            pass
    db.commit()
    return {"new_posts": len(new_posts)}


async def _fetch_target_posts(target: MonitorTarget) -> list[dict]:
    if target.source == "twitter":
        url = f"https://r.jina.ai/https://x.com/{target.target_id}"
    elif target.source == "facebook":
        url = f"https://r.jina.ai/https://facebook.com/{target.target_id}"
    else:
        return []

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.get(url, headers={"Accept": "text/plain", "X-Return-Format": "markdown"})
        if resp.status_code != 200:
            return []
        content = resp.text

    if target.last_post_text and target.last_post_text in content:
        return []

    posts = _parse_content(target, content)
    if posts:
        target.last_post_text = posts[0]["text"]
    return posts


def _parse_content(target: MonitorTarget, content: str) -> list[dict]:
    import re
    posts = []
    lines = content.split("\n")
    for line in lines:
        line = line.strip()
        if not line or len(line) < 20:
            continue
        if target.source == "twitter":
            match = re.match(r"^\d{1,2}:\d{2}\s*(AM|PM)?\s*·\s*", line)
            if not match:
                match = re.match(r"^[A-Z][a-z]+ \d{1,2},?\s*\d{4}", line)
            if match:
                text = line[match.end():].strip()
                if text and (not target.last_post_text or line not in target.last_post_text):
                    posts.append({
                        "source": "twitter",
                        "sender": f"@{target.target_id}",
                        "group_name": f"Twitter/{target.target_id}",
                        "text": text[:500],
                        "url": f"https://x.com/{target.target_id}",
                        "timestamp": time.time(),
                    })
        elif target.source == "facebook":
            if "shared" in line.lower() or "posted" in line.lower() or len(line) > 60:
                if not target.last_post_text or line not in target.last_post_text:
                    posts.append({
                        "source": "facebook",
                        "sender": target.target_id,
                        "group_name": f"Facebook/{target.target_id}",
                        "text": line[:500],
                        "url": f"https://facebook.com/{target.target_id}",
                        "timestamp": time.time(),
                    })
    return posts[:3]
