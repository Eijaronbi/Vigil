from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import desc
from sqlalchemy.orm import Session

from backend.classifier.classification_service import classify_message
from backend.config import settings
from backend.database import get_db
from backend.models import Group, Message
from backend.schemas import MessageIn, MessageOut

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.post("", response_model=MessageOut)
async def create_message(msg: MessageIn, db: Session = Depends(get_db)):
    group_id = msg.group_id
    if group_id is None:
        group = db.query(Group).filter(
            Group.source == msg.source,
            Group.name == msg.group_name,
        ).first()
        if not group:
            raise HTTPException(status_code=404, detail="Group not found")
        group_id = group.id

    db_msg = Message(
        group_id=group_id,
        source=msg.source,
        sender=msg.sender,
        text=msg.text,
        timestamp=msg.timestamp or datetime.now(),
    )
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)

    await classify_message(db, db_msg, msg)

    db.refresh(db_msg)
    return db_msg


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
