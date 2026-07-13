from datetime import datetime

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.models import Base, Group, Message, Rule, User


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


def test_create_user(session: Session):
    user = User(name="Alice", email="alice@example.com", telegram_chat_id="12345")
    session.add(user)
    session.commit()
    assert user.id is not None
    assert user.name == "Alice"
    assert user.email == "alice@example.com"


def test_create_group(session: Session):
    user = User(name="Bob", email="bob@example.com")
    session.add(user)
    session.commit()

    group = Group(
        user_id=user.id,
        source="telegram",
        name="Test Group",
        external_id="ext_001",
    )
    session.add(group)
    session.commit()
    assert group.id is not None
    assert group.enabled is True


def test_create_rule(session: Session):
    user = User(name="Charlie", email="charlie@example.com")
    session.add(user)
    session.commit()

    group = Group(
        user_id=user.id,
        source="twitter",
        name="Twitter Feed",
        external_id="ext_002",
    )
    session.add(group)
    session.commit()

    rule = Rule(group_id=group.id, rule_type="keyword", value="urgent", priority=5)
    session.add(rule)
    session.commit()
    assert rule.id is not None
    assert rule.priority == 5


def test_create_message(session: Session):
    user = User(name="Diana", email="diana@example.com")
    session.add(user)
    session.commit()

    group = Group(
        user_id=user.id,
        source="gmail",
        name="Inbox",
        external_id="ext_003",
    )
    session.add(group)
    session.commit()

    msg = Message(
        group_id=group.id,
        source="gmail",
        sender="boss@example.com",
        text="Important meeting tomorrow",
        timestamp=datetime.now(),
        importance_score=8,
        summary="Meeting reminder",
    )
    session.add(msg)
    session.commit()
    assert msg.id is not None
    assert msg.is_read is False
    assert msg.notified is False
    assert msg.importance_score == 8
