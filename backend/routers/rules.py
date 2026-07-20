from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Rule
from backend.schemas import RuleIn
from backend.routers.auth import verify_token

router = APIRouter(prefix="/api/rules", tags=["rules"], dependencies=[Depends(verify_token)])


@router.post("")
def create_rule(payload: RuleIn, db: Session = Depends(get_db)):
    rule = Rule(
        group_id=payload.group_id,
        rule_type=payload.rule_type,
        value=payload.value,
        priority=payload.priority,
    )
    db.add(rule)
    db.commit()
    db.refresh(rule)
    return rule


@router.get("")
def list_rules(
    group_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    q = db.query(Rule)
    if group_id is not None:
        q = q.filter(Rule.group_id == group_id)
    return q.all()


@router.delete("/{rule_id}", status_code=204)
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
