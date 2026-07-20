from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.config import settings
from backend.database import get_db
from backend.models import Group, Rule
from backend.routers.auth import verify_token

router = APIRouter(prefix="/api/config", tags=["config"], dependencies=[Depends(verify_token)])


class ThresholdUpdate(BaseModel):
    importance_threshold: int


class RuleCreate(BaseModel):
    rule_type: str
    value: str
    group_id: int = 0
    priority: int = 1


class GroupPriorityUpdate(BaseModel):
    group_id: int
    is_priority: bool


@router.get("")
def get_config():
    return {
        "importance_threshold": settings.importance_threshold,
        "groq_connected": bool(settings.groq_api_key),
    }


@router.post("/threshold")
def set_threshold(body: ThresholdUpdate):
    if body.importance_threshold < 0 or body.importance_threshold > 10:
        return {"error": "threshold must be 0-10"}
    settings.importance_threshold = body.importance_threshold
    return {"ok": True, "importance_threshold": settings.importance_threshold}


@router.get("/groups")
def list_groups_with_priority(db: Session = Depends(get_db)):
    groups = db.query(Group).order_by(Group.source, Group.name).all()
    return {
        "groups": [
            {
                "id": g.id,
                "source": g.source,
                "name": g.name,
                "is_priority": g.is_priority,
                "enabled": g.enabled,
            }
            for g in groups
        ]
    }


@router.post("/groups/priority")
def set_group_priority(body: GroupPriorityUpdate, db: Session = Depends(get_db)):
    group = db.query(Group).filter(Group.id == body.group_id).first()
    if not group:
        return {"error": "group not found"}
    group.is_priority = body.is_priority
    db.commit()
    return {"ok": True, "group_id": body.group_id, "is_priority": body.is_priority}


@router.get("/rules")
def list_all_rules(db: Session = Depends(get_db)):
    rules = db.query(Rule).order_by(Rule.priority.desc()).all()
    return {
        "rules": [
            {
                "id": r.id,
                "rule_type": r.rule_type,
                "value": r.value,
                "group_id": r.group_id,
                "priority": r.priority,
            }
            for r in rules
        ]
    }


@router.post("/rules")
def create_rule(body: RuleCreate, db: Session = Depends(get_db)):
    rule = Rule(
        group_id=body.group_id,
        rule_type=body.rule_type,
        value=body.value,
        priority=body.priority,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return {"ok": True, "id": rule.id}


@router.delete("/rules/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        return {"error": "rule not found"}
    db.delete(rule)
    db.commit()
    return {"ok": True}
