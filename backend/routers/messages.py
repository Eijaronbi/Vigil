from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import Group, Message
from backend.schemas import MessageIn, MessageOut

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.post("", response_model=MessageOut)
def create_message(payload: MessageIn, db: Session = Depends(get_db)):
    group_id = payload.group_id
    if group_id is None:
        group = db.query(Group).filter(
            Group.source == payload.source,
            Group.name == payload.group_name,
        ).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        group_id = group.id

    message = Message(
        group_id=group_id,
        source=payload.source,
        sender=payload.sender,
        text=payload.text,
        timestamp=payload.timestamp or datetime.now(),
    )
    db.add(message)
    db.commit()
    db.refresh(message)
    return message


@router.get("", response_model=list[MessageOut])
def list_messages(
    source: str | None = Query(None),
    group_name: str | None = Query(None),
    important: bool | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    db: Session = Depends(get_db),
):
    q = db.query(Message)

    if source:
        q = q.filter(Message.source == source)

    if group_name:
        q = q.join(Group).filter(Group.name == group_name)

    if important:
        q = q.filter(Message.importance_score >= settings.importance_threshold)

    return q.order_by(desc(Message.timestamp)).limit(limit).all()
