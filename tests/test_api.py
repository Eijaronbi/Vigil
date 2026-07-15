from datetime import datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from backend.database import get_db
from backend.main import app
from backend.models import Base, Group, User

engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


def override_get_db():
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db
client = TestClient(app)


@pytest.fixture(autouse=True)
def setup_db():
    Base.metadata.create_all(bind=engine)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def db(setup_db):
    db = TestSessionLocal()
    try:
        yield db
    finally:
        db.close()


@pytest.fixture
def user(db: Session) -> User:
    u = User(name="Test", email="test@example.com")
    db.add(u)
    db.commit()
    db.refresh(u)
    return u


@pytest.fixture
def group(db: Session, user: User) -> Group:
    g = Group(user_id=user.id, source="telegram", name="Test Group", external_id="ext_001")
    db.add(g)
    db.commit()
    db.refresh(g)
    return g


class TestMessages:
    def test_post_message(self, group: Group):
        resp = client.post(
            "/api/messages",
            json={
                "source": "telegram",
                "group_id": group.id,
                "group_name": "Test Group",
                "sender": "@alice",
                "text": "Hello world",
                "timestamp": "2025-01-01T12:00:00",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["source"] == "telegram"
        assert data["sender"] == "@alice"
        assert data["text"] == "Hello world"
        assert data["id"] is not None

    def test_post_message_without_group_id(self, group: Group):
        resp = client.post(
            "/api/messages",
            json={
                "source": "telegram",
                "group_name": "Test Group",
                "sender": "@bob",
                "text": "No group_id",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["sender"] == "@bob"
        assert data["group_name"] == "Test Group"

    def test_post_message_group_not_found(self):
        resp = client.post(
            "/api/messages",
            json={
                "source": "telegram",
                "group_name": "Nonexistent",
                "sender": "@x",
                "text": "missing",
            },
        )
        assert resp.status_code == 404

    def test_list_messages(self, group: Group):
        client.post(
            "/api/messages",
            json={
                "source": "telegram",
                "group_id": group.id,
                "group_name": "Test Group",
                "sender": "@alice",
                "text": "First",
                "timestamp": "2025-01-01T12:00:00",
            },
        )
        client.post(
            "/api/messages",
            json={
                "source": "telegram",
                "group_id": group.id,
                "group_name": "Test Group",
                "sender": "@bob",
                "text": "Second",
                "timestamp": "2025-01-01T13:00:00",
            },
        )

        resp = client.get("/api/messages")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 2

    def test_list_messages_filter_source(self, group: Group):
        client.post(
            "/api/messages",
            json={
                "source": "telegram",
                "group_id": group.id,
                "group_name": "Test Group",
                "sender": "@a",
                "text": "msg",
            },
        )
        resp = client.get("/api/messages?source=telegram")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

        resp = client.get("/api/messages?source=slack")
        assert resp.status_code == 200
        assert len(resp.json()) == 0

    def test_list_messages_filter_group_name(self, group: Group):
        client.post(
            "/api/messages",
            json={
                "source": "telegram",
                "group_id": group.id,
                "group_name": "Test Group",
                "sender": "@a",
                "text": "msg",
            },
        )
        resp = client.get("/api/messages?group_name=Test Group")
        assert resp.status_code == 200
        assert len(resp.json()) == 1

    def test_list_messages_limit(self, group: Group):
        for i in range(5):
            client.post(
                "/api/messages",
                json={
                    "source": "telegram",
                    "group_id": group.id,
                    "group_name": "Test Group",
                    "sender": "@a",
                    "text": f"msg {i}",
                },
            )
        resp = client.get("/api/messages?limit=3")
        assert resp.status_code == 200
        assert len(resp.json()) == 3


class TestGroups:
    def test_create_group(self):
        resp = client.post(
            "/api/groups",
            json={"source": "telegram", "name": "New Group", "external_id": "ext_999"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["name"] == "New Group"
        assert data["source"] == "telegram"
        assert data["enabled"] is True

    def test_list_groups(self, group: Group):
        resp = client.get("/api/groups")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["name"] == "Test Group"

    def test_delete_group(self, group: Group):
        resp = client.delete(f"/api/groups/{group.id}")
        assert resp.status_code == 204

        resp = client.get("/api/groups")
        assert len(resp.json()) == 0

    def test_delete_group_not_found(self):
        resp = client.delete("/api/groups/999")
        assert resp.status_code == 404


class TestRules:
    def test_create_rule(self, group: Group):
        resp = client.post(
            "/api/rules",
            json={"group_id": group.id, "rule_type": "keyword", "value": "urgent", "priority": 5},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["rule_type"] == "keyword"
        assert data["value"] == "urgent"
        assert data["priority"] == 5

    def test_list_rules(self, group: Group):
        client.post(
            "/api/rules",
            json={"group_id": group.id, "rule_type": "keyword", "value": "alert", "priority": 1},
        )
        resp = client.get(f"/api/rules?group_id={group.id}")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["value"] == "alert"

    def test_delete_rule(self, group: Group):
        resp = client.post(
            "/api/rules",
            json={"group_id": group.id, "rule_type": "keyword", "value": "test", "priority": 0},
        )
        rule_id = resp.json()["id"]

        resp = client.delete(f"/api/rules/{rule_id}")
        assert resp.status_code == 204

        resp = client.get(f"/api/rules?group_id={group.id}")
        assert len(resp.json()) == 0

    def test_delete_rule_not_found(self):
        resp = client.delete("/api/rules/999")
        assert resp.status_code == 404


class TestDashboard:
    def test_dashboard_returns_html(self, group: Group):
        resp = client.get("/")
        assert resp.status_code == 200
        assert "text/html" in resp.headers["content-type"]
