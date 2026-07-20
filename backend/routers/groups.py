from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Group, User
from backend.schemas import GroupIn, GroupOut
from backend.routers.auth import verify_token

router = APIRouter(prefix="/api/groups", tags=["groups"], dependencies=[Depends(verify_token)])


class GroupPatch(BaseModel):
    is_priority: bool | None = None
    enabled: bool | None = None


def _default_user(db: Session) -> User:
    user = db.query(User).first()
    if user is None:
        user = User(name="Default", email="default@example.com")
        db.add(user)
        db.commit()
        db.refresh(user)
    return user


@router.post("", response_model=GroupOut)
def create_group(payload: GroupIn, db: Session = Depends(get_db)):
    user = _default_user(db)
    group = Group(
        user_id=user.id,
        source=payload.source,
        name=payload.name,
        external_id=payload.external_id,
    )
    db.add(group)
    db.commit()
    db.refresh(group)
    return group


@router.get("", response_model=list[GroupOut])
def list_groups(db: Session = Depends(get_db)):
    return db.query(Group).all()


@router.patch("/{group_id}", response_model=GroupOut)
def patch_group(group_id: int, payload: GroupPatch, db: Session = Depends(get_db)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    if payload.is_priority is not None:
        group.is_priority = payload.is_priority
    if payload.enabled is not None:
        group.enabled = payload.enabled
    db.commit()
    db.refresh(group)
    return group


@router.delete("/{group_id}", status_code=204)
def delete_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    db.delete(group)
    db.commit()
