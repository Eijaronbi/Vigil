from datetime import datetime

from pydantic import BaseModel, Field


class MessageIn(BaseModel):
    source: str
    group_id: int | None = None
    group_name: str
    sender: str
    text: str
    timestamp: datetime | None = None


class MessageOut(BaseModel):
    id: int
    source: str
    group_name: str
    sender: str
    text: str
    timestamp: datetime
    importance_score: int | None = None
    summary: str | None = None

    model_config = {"from_attributes": True}


class RuleIn(BaseModel):
    group_id: int
    rule_type: str
    value: str
    priority: int = 0


class GroupIn(BaseModel):
    source: str
    name: str
    external_id: str


class GroupOut(BaseModel):
    id: int
    source: str
    name: str
    external_id: str
    enabled: bool
    is_priority: bool = False

    model_config = {"from_attributes": True}
