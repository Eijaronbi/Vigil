# Message Monitor Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build personal automation that monitors WhatsApp groups, Telegram groups, Twitter/X accounts, and Gmail for important messages and alerts via Telegram Bot, email, and TTS.

**Architecture:** Python monolith (FastAPI + Celery + SQLite) with Chrome extension sidecar. WhatsApp via Chrome extension hook, Telegram via Bot API, Twitter/X via Jina Reader polling (no login), Gmail via OAuth. Messages classified by hybrid AI keyword + LLM pipeline.

**Tech Stack:** Python 3.11+, FastAPI, SQLite, Celery, python-telegram-bot, google-auth-oauthlib, openai (OpenRouter), HTMX + Jinja2, Chrome Extension MV3

## Global Constraints

- Python 3.11+ required
- SQLite for storage (no external DB)
- All API keys/secrets in `.env` file (not hardcoded)
- Chrome Extension must be Manifest V3
- LLM calls through OpenRouter (configurable endpoint)
- Tests use pytest
- No message replies ever (read-only monitoring)

---

## File Structure

```
message-monitor/
├── backend/
│   ├── main.py                  # FastAPI entry point, lifespan, CORS
│   ├── config.py                # Env vars, settings
│   ├── database.py              # SQLite connection, session management
│   ├── models.py                # SQLAlchemy models (User, Group, Rule, Message, etc.)
│   ├── schemas.py               # Pydantic schemas (MessageIn, MessageOut, Rule, etc.)
│   ├── watchers/
│   │   ├── __init__.py
│   │   ├── telegram_watcher.py  # Telegram Bot API listener
│   │   ├── gmail_watcher.py     # Gmail OAuth poller
│   │   └── twitter_watcher.py   # Twitter/X via Jina Reader
│   ├── classifier/
│   │   ├── __init__.py
│   │   ├── rules.py             # KeywordRule, SenderRule, TopicRule
│   │   └── llm_scorer.py        # LLM importance scoring
│   ├── dispatcher/
│   │   ├── __init__.py
│   │   ├── telegram.py          # Send notifications via Telegram Bot
│   │   └── email.py             # Send digests via Gmail API
│   ├── routers/
│   │   ├── __init__.py
│   │   ├── messages.py          # POST /api/messages, GET /api/messages
│   │   ├── groups.py            # CRUD for groups
│   │   ├── rules.py             # CRUD for rules
│   │   └── dashboard.py         # HTML page routes
│   ├── websocket_manager.py     # WebSocket connections for TTS pushes
│   ├── tasks.py                 # Celery tasks (poll gmail, daily report, digest)
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── groups.html
│   │   ├── rules.html
│   │   └── messages.html
│   └── requirements.txt
├── extension/
│   ├── manifest.json
│   ├── background.js            # Service worker: WebSocket, TTS, alarms
│   ├── content.js               # WhatsApp Web DOM observer
│   ├── popup.html
│   ├── popup.js
│   └── icon.png
├── tests/
│   ├── test_database.py
│   ├── test_rules.py
│   ├── test_llm_scorer.py
│   ├── test_gmail_watcher.py
│   ├── test_twitter_watcher.py
│   ├── test_telegram_watcher.py
│   ├── test_dispatcher.py
│   └── test_api.py
├── .env.example
└── README.md
```

---

### Task 1: Project Scaffold and Database Layer

**Files:**
- Create: `message-monitor/backend/config.py`
- Create: `message-monitor/backend/database.py`
- Create: `message-monitor/backend/models.py`
- Create: `message-monitor/backend/schemas.py`
- Create: `message-monitor/backend/requirements.txt`
- Create: `message-monitor/.env.example`
- Create: `message-monitor/tests/test_database.py`

**Interfaces:**
- Consumes: nothing
- Produces: `database.SessionLocal()`, `models.User`, `models.Group`, `models.Rule`, `models.Message`, `models.DigestQueue`, `models.DailyReport`, `schemas.MessageIn`, `schemas.MessageOut`, `schemas.RuleIn`

- [ ] **Step 1: Create directory structure and requirements.txt**

```bash
New-Item -ItemType Directory -Path "message-monitor/backend/watchers", "message-monitor/backend/classifier", "message-monitor/backend/dispatcher", "message-monitor/backend/routers", "message-monitor/backend/templates", "message-monitor/extension", "message-monitor/tests" -Force
```

- [ ] **Step 2: Write `backend/requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.0
sqlalchemy==2.0.35
python-telegram-bot==21.6
google-auth-oauthlib==1.2.1
google-api-python-client==2.149.0
celery==5.4.0
redis==5.1.1
httpx==0.27.2
python-dotenv==1.0.1
pydantic==2.9.2
pydantic-settings==2.5.2
jinja2==3.1.4
aiofiles==24.1.0
websockets==13.1
pytest==8.3.3
pytest-asyncio==0.24.0
```

- [ ] **Step 3: Write `backend/config.py`**

```python
from pydantic_settings import BaseSettings
from typing import Optional


class Settings(BaseSettings):
    database_url: str = "sqlite:///./message_monitor.db"
    telegram_bot_token: str = ""
    telegram_api_id: Optional[str] = None
    telegram_api_hash: Optional[str] = None
    gmail_oauth_client_id: str = ""
    gmail_oauth_client_secret: str = ""
    gmail_oauth_refresh_token: str = ""
    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-4o-mini"
    importance_threshold: int = 6
    digest_interval_minutes: int = 30
    daily_report_time: str = "08:00"
    ws_port: int = 8765

    class Config:
        env_file = ".env"


settings = Settings()
```

- [ ] **Step 4: Write `backend/database.py`**

```python
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import settings

engine = create_engine(settings.database_url, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
```

- [ ] **Step 5: Write `backend/models.py`**

```python
import datetime
from sqlalchemy import Column, Integer, String, Text, Float, DateTime, Boolean, ForeignKey, JSON
from database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True)
    name = Column(String(255))
    email = Column(String(255))
    telegram_chat_id = Column(String(255))
    created_at = Column(DateTime, default=datetime.datetime.utcnow)


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    source = Column(String(50))  # "whatsapp", "telegram", "twitter", "gmail"
    name = Column(String(255))
    external_id = Column(String(255))
    enabled = Column(Boolean, default=True)


class Rule(Base):
    __tablename__ = "rules"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    rule_type = Column(String(50))  # "keyword", "sender", "topic"
    value = Column(Text)
    priority = Column(Integer, default=0)


class Message(Base):
    __tablename__ = "messages"

    id = Column(Integer, primary_key=True)
    group_id = Column(Integer, ForeignKey("groups.id"))
    source = Column(String(50))
    sender = Column(String(255))
    text = Column(Text)
    timestamp = Column(DateTime)
    importance_score = Column(Float, default=0.0)
    summary = Column(Text)
    is_read = Column(Boolean, default=False)
    notified = Column(Boolean, default=False)


class DigestQueue(Base):
    __tablename__ = "digest_queue"

    id = Column(Integer, primary_key=True)
    message_id = Column(Integer, ForeignKey("messages.id"))
    channel = Column(String(50))
    sent_at = Column(DateTime, nullable=True)


class DailyReport(Base):
    __tablename__ = "daily_reports"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    date = Column(DateTime)
    generated_at = Column(DateTime, default=datetime.datetime.utcnow)
    summary_json = Column(JSON)
```

- [ ] **Step 6: Write `backend/schemas.py`**

```python
import datetime
from typing import Optional
from pydantic import BaseModel


class MessageIn(BaseModel):
    source: str
    group_id: Optional[int] = None
    group_name: str
    sender: str
    text: str
    timestamp: Optional[datetime.datetime] = None


class MessageOut(BaseModel):
    id: int
    source: str
    group_name: str
    sender: str
    text: str
    timestamp: datetime.datetime
    importance_score: float
    summary: Optional[str] = None

    class Config:
        from_attributes = True


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

    class Config:
        from_attributes = True
```

- [ ] **Step 7: Write test `tests/test_database.py`**

```python
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from backend.database import Base
from backend.models import User, Group, Rule, Message


@pytest.fixture
def session():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})
    Base.metadata.create_all(bind=engine)
    TestSession = sessionmaker(bind=engine)
    db = TestSession()
    yield db
    db.close()


def test_create_user(session):
    user = User(name="Test User", email="test@example.com", telegram_chat_id="12345")
    session.add(user)
    session.commit()
    assert user.id is not None
    assert user.name == "Test User"


def test_create_group(session):
    group = Group(source="telegram", name="Test Group", external_id="-100123")
    session.add(group)
    session.commit()
    assert group.id is not None
    assert group.source == "telegram"


def test_create_rule(session):
    rule = Rule(group_id=1, rule_type="keyword", value="urgent", priority=1)
    session.add(rule)
    session.commit()
    assert rule.id is not None
    assert rule.rule_type == "keyword"


def test_create_message(session):
    msg = Message(
        group_id=1, source="whatsapp", sender="John",
        text="Hello world", importance_score=7.5, summary="Test summary"
    )
    session.add(msg)
    session.commit()
    assert msg.id is not None
    assert msg.importance_score == 7.5
```

- [ ] **Step 8: Run tests**

```bash
cd message-monitor && pip install -r backend/requirements.txt && pytest tests/test_database.py -v
```

Expected: 4 passed

- [ ] **Step 9: Commit**

```bash
git add message-monitor/ && git commit -m "feat: scaffold project with database layer"
```

---

### Task 2: Gmail Watcher with OAuth

**Files:**
- Create: `message-monitor/backend/watchers/__init__.py`
- Create: `message-monitor/backend/watchers/gmail_watcher.py`
- Create: `message-monitor/tests/test_gmail_watcher.py`

**Interfaces:**
- Consumes: `config.settings`, `database.SessionLocal`, `models.Message`
- Produces: `gmail_watcher.poll_gmail(db)` → list of new Message dicts

- [ ] **Step 1: Write `backend/watchers/__init__.py`** (empty)

- [ ] **Step 2: Write failing test `tests/test_gmail_watcher.py`**

```python
import pytest
from unittest.mock import patch, MagicMock
from backend.watchers.gmail_watcher import GmailWatcher


@pytest.fixture
def watcher():
    return GmailWatcher(
        client_id="test-id",
        client_secret="test-secret",
        refresh_token="test-token"
    )


def test_watcher_initializes_with_credentials(watcher):
    assert watcher.client_id == "test-id"
    assert watcher.client_secret == "test-secret"


@pytest.mark.asyncio
async def test_poll_returns_messages(watcher):
    mock_service = MagicMock()
    mock_service.users().messages().list().execute.return_value = {
        "messages": [{"id": "abc123"}]
    }
    mock_service.users().messages().get().execute.return_value = {
        "id": "abc123",
        "payload": {
            "headers": [
                {"name": "From", "value": "sender@example.com"},
                {"name": "Subject", "value": "Test Subject"}
            ]
        },
        "snippet": "Hello this is a test"
    }

    with patch.object(watcher, "_get_service", return_value=mock_service):
        messages = await watcher.poll()

    assert len(messages) == 1
    assert messages[0]["sender"] == "sender@example.com"
    assert messages[0]["text"] == "Hello this is a test"
```

- [ ] **Step 3: Run test to verify it fails**

```bash
cd message-monitor && pytest tests/test_gmail_watcher.py -v
```

Expected: FAIL with "cannot import 'GmailWatcher'"

- [ ] **Step 4: Write `backend/watchers/gmail_watcher.py`**

```python
import datetime
from typing import Optional
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build


class GmailWatcher:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._service = None
        self._last_check = None

    def _get_credentials(self) -> Credentials:
        return Credentials(
            None,
            refresh_token=self.refresh_token,
            client_id=self.client_id,
            client_secret=self.client_secret,
            token_uri="https://oauth2.googleapis.com/token"
        )

    def _get_service(self):
        if self._service is None:
            creds = self._get_credentials()
            self._service = build("gmail", "v1", credentials=creds)
        return self._service

    async def poll(self) -> list[dict]:
        service = self._get_service()
        query = "in:inbox is:unread"
        if self._last_check:
            query += f" after:{int(self._last_check.timestamp())}"

        result = service.users().messages().list(userId="me", q=query, maxResults=20).execute()
        messages = result.get("messages", [])

        parsed = []
        for msg in messages:
            details = service.users().messages().get(userId="me", id=msg["id"]).execute()
            headers = {h["name"]: h["value"] for h in details["payload"]["headers"]}
            parsed.append({
                "source": "gmail",
                "sender": headers.get("From", "unknown"),
                "group_name": "Inbox",
                "text": details.get("snippet", ""),
                "timestamp": datetime.datetime.utcnow(),
            })

        self._last_check = datetime.datetime.utcnow()
        return parsed
```

- [ ] **Step 5: Run test to verify it passes**

```bash
cd message-monitor && pytest tests/test_gmail_watcher.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add message-monitor/backend/watchers/ message-monitor/tests/test_gmail_watcher.py && git commit -m "feat: add Gmail watcher with OAuth"
```

---

### Task 2.5: Twitter/X Watcher (Jina Reader Polling)

**Files:**
- Create: `message-monitor/backend/watchers/twitter_watcher.py`
- Create: `message-monitor/tests/test_twitter_watcher.py`

**Interfaces:**
- Consumes: none (no API key needed)
- Produces: `twitter_watcher.TwitterWatcher.poll(username)` → list of post dicts with `{source, sender, group_name, text, timestamp, post_id}`

- [ ] **Step 1: Write failing test `tests/test_twitter_watcher.py`**

```python
import pytest
from unittest.mock import patch, AsyncMock
from backend.watchers.twitter_watcher import TwitterWatcher


@pytest.mark.asyncio
async def test_poll_returns_posts():
    watcher = TwitterWatcher()

    mock_markdown = """# @elonmusk on X

> Tesla Q2 deliveries just came in. Record numbers.

Jul 2, 2026 · 1.2K views

> Starship flight test 5 scheduled for next week.

Jul 1, 2026 · 3.4K views
"""

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = mock_markdown
        posts = await watcher.poll("elonmusk")

    assert len(posts) == 2
    assert posts[0]["source"] == "twitter"
    assert "Tesla" in posts[0]["text"]


@pytest.mark.asyncio
async def test_poll_handles_empty_profile():
    watcher = TwitterWatcher()

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 404
        posts = await watcher.poll("nonexistentaccount")

    assert posts == []


@pytest.mark.asyncio
async def test_poll_filters_seen_posts():
    watcher = TwitterWatcher()
    watcher.last_seen_ids["elonmusk"] = {"post_2"}

    mock_markdown = """# @elonmusk on X

> New post content.

Jul 3, 2026 · 100 views
"""

    with patch("httpx.AsyncClient.get", new_callable=AsyncMock) as mock_get:
        mock_get.return_value.status_code = 200
        mock_get.return_value.text = mock_markdown
        posts = await watcher.poll("elonmusk")

    assert len(posts) == 1
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd message-monitor && pytest tests/test_twitter_watcher.py -v
```

Expected: FAIL

- [ ] **Step 3: Write `backend/watchers/twitter_watcher.py`**

```python
import re
import hashlib
import datetime
from typing import Optional
import httpx


class TwitterWatcher:
    def __init__(self):
        self.last_seen_ids: dict[str, set[str]] = {}
        self.jina_url = "https://r.jina.ai"

    async def poll(self, username: str) -> list[dict]:
        url = f"{self.jina_url}/https://x.com/{username}"
        seen = self.last_seen_ids.get(username, set())
        new_posts = []

        async with httpx.AsyncClient(timeout=30, follow_redirects=True) as client:
            try:
                response = await client.get(url, headers={"X-Return-Format": "markdown"})
                if response.status_code != 200:
                    return []
                content = response.text
            except Exception:
                return []

        blocks = re.split(r'\n>\s', content)
        for block in blocks:
            if not block.strip():
                continue
            lines = block.strip().split("\n")
            text_lines = [l for l in lines if not l.startswith("#") and not re.match(r"^\w+ \d+, \d{4}", l) and not re.match(r"^\d+[KMB]? views", l) and l.strip()]
            text = " ".join(t.strip() for t in text_lines if t.strip())
            if not text or len(text) < 10:
                continue

            post_id = hashlib.md5(text.encode()).hexdigest()[:12]
            if post_id in seen:
                continue

            new_posts.append({
                "source": "twitter",
                "sender": f"@{username}",
                "group_name": f"Twitter/{username}",
                "text": text.strip(),
                "timestamp": datetime.datetime.utcnow(),
                "post_id": post_id,
            })

        self.last_seen_ids.setdefault(username, set()).update(p["post_id"] for p in new_posts)
        return new_posts
```

- [ ] **Step 4: Run tests**

```bash
cd message-monitor && pytest tests/test_twitter_watcher.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add message-monitor/backend/watchers/twitter_watcher.py message-monitor/tests/test_twitter_watcher.py && git commit -m "feat: add Twitter/X watcher via Jina Reader"
```

---

### Task 3: Telegram Watcher (Bot API Listener)

**Files:**
- Create: `message-monitor/backend/watchers/telegram_watcher.py`
- Create: `message-monitor/tests/test_telegram_watcher.py`

**Interfaces:**
- Consumes: `config.settings.telegram_bot_token`
- Produces: `telegram_watcher.TelegramWatcher` — runs as a polling bot, returns messages for groups it's in

- [ ] **Step 1: Write failing test `tests/test_telegram_watcher.py`**

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from backend.watchers.telegram_watcher import TelegramWatcher


@pytest.mark.asyncio
async def test_start_bot_initializes():
    watcher = TelegramWatcher(token="test-token")
    assert watcher.token == "test-token"


@pytest.mark.asyncio
async def test_on_message_queues_important():
    mock_update = MagicMock()
    mock_update.effective_chat.id = -100123
    mock_update.effective_chat.title = "Test Group"
    mock_update.effective_message.sender_chat.title = "Test Group"
    mock_update.effective_message.from_user.username = "testuser"
    mock_update.effective_message.text = "This is urgent"

    watcher = TelegramWatcher(token="test-token")
    messages = []

    async def fake_callback(msg):
        messages.append(msg)

    watcher.set_message_callback(fake_callback)
    await watcher._handle_message(mock_update, MagicMock())

    assert len(messages) == 1
    assert messages[0]["text"] == "This is urgent"
    assert messages[0]["source"] == "telegram"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd message-monitor && pytest tests/test_telegram_watcher.py -v
```

Expected: FAIL

- [ ] **Step 3: Write `backend/watchers/telegram_watcher.py`**

```python
from typing import Callable, Optional
from telegram import Update
from telegram.ext import Application, MessageHandler, filters, ContextTypes


class TelegramWatcher:
    def __init__(self, token: str):
        self.token = token
        self._app: Optional[Application] = None
        self._message_callback: Optional[Callable] = None
        self._group_ids: list[int] = []

    def set_message_callback(self, callback: Callable):
        self._message_callback = callback

    def set_monitored_groups(self, group_ids: list[int]):
        self._group_ids = group_ids

    async def _handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not update.effective_message or not update.effective_chat:
            return

        chat_id = update.effective_chat.id
        if self._group_ids and chat_id not in self._group_ids:
            return

        msg = {
            "source": "telegram",
            "sender": update.effective_message.from_user.username if update.effective_message.from_user else "unknown",
            "group_name": update.effective_chat.title or str(chat_id),
            "text": update.effective_message.text or "",
            "timestamp": update.effective_message.date,
            "group_external_id": str(chat_id),
        }

        if self._message_callback:
            await self._message_callback(msg)

    async def start(self):
        self._app = Application.builder().token(self.token).build()
        self._app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, self._handle_message))
        await self._app.initialize()
        await self._app.start()
        await self._app.updater.start_polling()

    async def stop(self):
        if self._app:
            await self._app.updater.stop()
            await self._app.stop()
            await self._app.shutdown()
```

- [ ] **Step 4: Run tests**

```bash
cd message-monitor && pytest tests/test_telegram_watcher.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add message-monitor/backend/watchers/telegram_watcher.py message-monitor/tests/test_telegram_watcher.py && git commit -m "feat: add Telegram watcher (Bot API listener)"
```

---

### Task 4: AI Classifier — Rules Engine

**Files:**
- Create: `message-monitor/backend/classifier/__init__.py`
- Create: `message-monitor/backend/classifier/rules.py`
- Create: `message-monitor/tests/test_rules.py`

**Interfaces:**
- Consumes: `models.Rule` (from DB)
- Produces: `rules.KeywordRule`, `rules.SenderRule`, `rules.HybridClassifier` — `classify(message_text, sender, group_name)` → `(score, matched_rules)`

- [ ] **Step 1: Write failing test `tests/test_rules.py`**

```python
import pytest
from backend.classifier.rules import KeywordRule, SenderRule, HybridClassifier
from backend.schemas import MessageIn


def test_keyword_rule_matches():
    rule = KeywordRule(keywords=["urgent", "price", "deal"])
    msg = MessageIn(source="telegram", group_name="Deals", sender="john", text="Check the price now")

    score, matched = rule.evaluate(msg)
    assert score > 0
    assert "price" in matched


def test_keyword_rule_no_match():
    rule = KeywordRule(keywords=["urgent", "price"])
    msg = MessageIn(source="telegram", group_name="General", sender="john", text="Hello everyone")

    score, matched = rule.evaluate(msg)
    assert score == 0
    assert matched == []


def test_sender_rule_matches():
    rule = SenderRule(priority_senders=["@john", "@admin"])
    msg = MessageIn(source="telegram", group_name="General", sender="@admin", text="Meeting at 3pm")

    score, matched = rule.evaluate(msg)
    assert score == 10
    assert "@admin" in matched


def test_hybrid_classifier_combines_rules():
    rules = [
        KeywordRule(keywords=["urgent"], priority=2),
        SenderRule(priority_senders=["@john"], priority=1),
    ]
    classifier = HybridClassifier(rules=rules)

    msg = MessageIn(source="telegram", group_name="General", sender="@john", text="This is urgent")
    result = classifier.classify(msg)

    assert result["score"] > 0
    assert len(result["matched_rules"]) == 2
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
cd message-monitor && pytest tests/test_rules.py -v
```

Expected: FAIL

- [ ] **Step 3: Write `backend/classifier/__init__.py`** (empty)

- [ ] **Step 4: Write `backend/classifier/rules.py`**

```python
import re
from typing import List
from backend.schemas import MessageIn


class KeywordRule:
    def __init__(self, keywords: list[str], priority: int = 1):
        self.keywords = [k.lower() for k in keywords]
        self.priority = priority

    def evaluate(self, message: MessageIn) -> tuple[float, list[str]]:
        text = message.text.lower()
        matched = [k for k in self.keywords if k in text]
        if matched:
            return 7.0 * self.priority, matched
        return 0, []


class SenderRule:
    def __init__(self, priority_senders: list[str], priority: int = 1):
        self.priority_senders = [s.lower() for s in priority_senders]
        self.priority = priority

    def evaluate(self, message: MessageIn) -> tuple[float, list[str]]:
        sender = message.sender.lower()
        matched = [s for s in self.priority_senders if s == sender or s.replace("@", "") == sender]
        if matched:
            return 10.0 * self.priority, matched
        return 0, []


class TopicRule:
    def __init__(self, topic_descriptions: list[str], priority: int = 1):
        self.topics = [t.lower() for t in topic_descriptions]
        self.priority = priority

    def evaluate(self, message: MessageIn) -> tuple[float, list[str]]:
        text = message.text.lower()
        matched = []
        for topic in self.topics:
            topic_words = topic.split()
            matches = sum(1 for w in topic_words if w in text)
            if matches >= len(topic_words) * 0.5:
                matched.append(topic)
        if matched:
            return 5.0 * self.priority, matched
        return 0, []


class HybridClassifier:
    def __init__(self, rules: list | None = None):
        self.rules = rules or []

    def set_rules(self, rules: list):
        self.rules = rules

    def classify(self, message: MessageIn) -> dict:
        total_score = 0.0
        all_matched = []

        for rule in self.rules:
            score, matched = rule.evaluate(message)
            total_score += score
            all_matched.extend(matched)

        return {
            "score": min(total_score, 10.0),
            "matched_rules": all_matched,
        }
```

- [ ] **Step 5: Run tests**

```bash
cd message-monitor && pytest tests/test_rules.py -v
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add message-monitor/backend/classifier/ message-monitor/tests/test_rules.py && git commit -m "feat: add keyword, sender, and topic rule classifiers"
```

---

### Task 5: AI Classifier — LLM Scorer

**Files:**
- Create: `message-monitor/backend/classifier/llm_scorer.py`
- Create: `message-monitor/tests/test_llm_scorer.py`

**Interfaces:**
- Consumes: `config.settings.openrouter_api_key`, `config.settings.openrouter_model`, `schemas.MessageIn`
- Produces: `llm_scorer.LLMScorer.score(message, context)` → `{"score": float, "summary": str}`

- [ ] **Step 1: Write failing test `tests/test_llm_scorer.py`**

```python
import pytest
from unittest.mock import patch, AsyncMock
from backend.classifier.llm_scorer import LLMScorer


@pytest.mark.asyncio
async def test_score_returns_valid_response():
    scorer = LLMScorer(api_key="test-key", model="openai/gpt-4o-mini")

    mock_response = {
        "choices": [{
            "message": {
                "content": '{"importance": 8, "summary": "Urgent deal update", "reason": "Contains price drop info"}'
            }
        }]
    }

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = mock_response

        result = await scorer.score(
            text="The price just dropped to $50!",
            sender="@john",
            group_name="Deals Group",
            sender_rules=["@john"],
            keyword_matches=["price"]
        )

    assert result["score"] == 8
    assert result["summary"] == "Urgent deal update"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd message-monitor && pytest tests/test_llm_scorer.py -v
```

Expected: FAIL

- [ ] **Step 3: Write `backend/classifier/llm_scorer.py`**

```python
import json
import httpx
from typing import Optional


LLM_PROMPT = """You are a message importance classifier. Given a message from a group chat, rate its importance from 0-10 and provide a one-sentence summary.

Consider:
- Does it contain time-sensitive information?
- Does it mention deals, prices, or opportunities?
- Is it from a priority sender?
- Does it match monitored topics?
- Is it urgent or requires action?

Respond with JSON: {"importance": <0-10>, "summary": "<one sentence>", "reason": "<brief reason>"}
"""


class LLMScorer:
    def __init__(self, api_key: str, model: str = "openai/gpt-4o-mini"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://openrouter.ai/api/v1/chat/completions"

    async def score(
        self,
        text: str,
        sender: str,
        group_name: str,
        sender_rules: Optional[list] = None,
        keyword_matches: Optional[list] = None,
    ) -> dict:
        context = f"Group: {group_name}\nSender: {sender}\nMessage: {text}\n"
        if keyword_matches:
            context += f"Keyword matches: {', '.join(keyword_matches)}\n"
        if sender_rules:
            context += f"Priority sender: {', '.join(sender_rules)}\n"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                self.api_url,
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": [
                        {"role": "system", "content": LLM_PROMPT},
                        {"role": "user", "content": context},
                    ],
                    "temperature": 0.1,
                },
            )

        if response.status_code != 200:
            return {"score": 0, "summary": text[:100], "error": str(response.status_code)}

        try:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            parsed = json.loads(content)
            return {
                "score": max(0, min(10, parsed.get("importance", 0))),
                "summary": parsed.get("summary", text[:100]),
                "reason": parsed.get("reason", ""),
            }
        except (json.JSONDecodeError, KeyError, IndexError):
            return {"score": 0, "summary": text[:100], "error": "parse_failed"}
```

- [ ] **Step 4: Run tests**

```bash
cd message-monitor && pytest tests/test_llm_scorer.py -v
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add message-monitor/backend/classifier/llm_scorer.py message-monitor/tests/test_llm_scorer.py && git commit -m "feat: add LLM importance scorer via OpenRouter"
```

---

### Task 6: Notification Dispatcher

**Files:**
- Create: `message-monitor/backend/dispatcher/__init__.py`
- Create: `message-monitor/backend/dispatcher/telegram.py`
- Create: `message-monitor/backend/dispatcher/email.py`
- Create: `message-monitor/tests/test_dispatcher.py`

**Interfaces:**
- Consumes: `config.settings`, `models.Message`
- Produces: `telegram.TelegramDispatcher.send_alert(message)` and `email.EmailDispatcher.send_digest(messages)`

- [ ] **Step 1: Write failing test `tests/test_dispatcher.py`**

```python
import pytest
from unittest.mock import AsyncMock, patch
from backend.dispatcher.telegram import TelegramDispatcher
from backend.dispatcher.email import EmailDispatcher


@pytest.mark.asyncio
async def test_telegram_dispatcher_sends_alert():
    dispatcher = TelegramDispatcher(bot_token="test-token", chat_id="12345")

    with patch("httpx.AsyncClient.post", new_callable=AsyncMock) as mock_post:
        mock_post.return_value.status_code = 200
        mock_post.return_value.json.return_value = {"ok": True}

        result = await dispatcher.send_alert(
            group_name="Deals",
            sender="john",
            text="Price dropped!",
            summary="Urgent price drop",
            score=9,
        )

    assert result is True
    call_kwargs = mock_post.call_args.kwargs
    assert "Price dropped!" in call_kwargs["json"]["text"]


@pytest.mark.asyncio
async def test_email_dispatcher_sends_digest():
    dispatcher = EmailDispatcher(
        client_id="test-id",
        client_secret="test-secret",
        refresh_token="test-token",
        to_email="user@example.com",
    )

    messages = [
        {"group_name": "Deals", "sender": "john", "text": "Price drop", "summary": "Deal alert", "importance_score": 8},
        {"group_name": "Church", "sender": "pastor", "text": "Meeting tomorrow", "summary": "Church meeting", "importance_score": 7},
    ]

    with patch.object(dispatcher, "_send_via_gmail", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = True
        result = await dispatcher.send_digest(messages, digest_type="daily")

    assert result is True
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd message-monitor && pytest tests/test_dispatcher.py -v
```

Expected: FAIL

- [ ] **Step 3: Write `backend/dispatcher/__init__.py`** (empty)

- [ ] **Step 4: Write `backend/dispatcher/telegram.py`**

```python
import httpx


class TelegramDispatcher:
    def __init__(self, bot_token: str, chat_id: str):
        self.api_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        self.chat_id = chat_id

    async def send_alert(self, group_name: str, sender: str, text: str, summary: str, score: float) -> bool:
        icon = "🔴" if score >= 8 else "🟡" if score >= 5 else "🔵"
        message = (
            f"{icon} *{group_name}*\n"
            f"👤 {sender}\n"
            f"📝 {summary}\n\n"
            f"_{text[:200]}_"
        )

        async with httpx.AsyncClient() as client:
            response = await client.post(self.api_url, json={
                "chat_id": self.chat_id,
                "text": message,
                "parse_mode": "Markdown",
                "disable_web_page_preview": True,
            })

        return response.status_code == 200 and response.json().get("ok")
```

- [ ] **Step 5: Write `backend/dispatcher/email.py`**

```python
import datetime
from email.mime.text import MIMEText
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
import base64


class EmailDispatcher:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str, to_email: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self.to_email = to_email

    def _get_service(self):
        creds = Credentials(
            None,
            refresh_token=self.refresh_token,
            client_id=self.client_id,
            client_secret=self.client_secret,
            token_uri="https://oauth2.googleapis.com/token"
        )
        return build("gmail", "v1", credentials=creds)

    async def _send_via_gmail(self, subject: str, body_html: str) -> bool:
        service = self._get_service()
        message = MIMEText(body_html, "html")
        message["To"] = self.to_email
        message["Subject"] = subject
        raw = base64.urlsafe_b64encode(message.as_bytes()).decode()

        try:
            service.users().messages().send(userId="me", body={"raw": raw}).execute()
            return True
        except Exception:
            return False

    async def send_digest(self, messages: list[dict], digest_type: str = "digest") -> bool:
        if not messages:
            return False

        if digest_type == "daily":
            subject = f"Daily Report — {datetime.date.today().isoformat()}"
        else:
            subject = f"Message Digest — {datetime.datetime.now().strftime('%b %d %I:%M %p')}"

        rows = "".join(
            f"<tr><td>{m['group_name']}</td><td>{m['sender']}</td>"
            f"<td>{m.get('summary', m['text'][:80])}</td>"
            f"<td>{'⭐' * int(m.get('importance_score', 0) // 2)}</td></tr>"
            for m in messages
        )

        body = f"""
        <html><body>
        <h2>{subject}</h2>
        <table border="1" cellpadding="8" cellspacing="0" style="border-collapse:collapse">
        <tr><th>Group</th><th>Sender</th><th>Message</th><th>Importance</th></tr>
        {rows}
        </table>
        </body></html>
        """

        return await self._send_via_gmail(subject, body)
```

- [ ] **Step 6: Run tests**

```bash
cd message-monitor && pytest tests/test_dispatcher.py -v
```

Expected: PASS

- [ ] **Step 7: Commit**

```bash
git add message-monitor/backend/dispatcher/ message-monitor/tests/test_dispatcher.py && git commit -m "feat: add Telegram and email notification dispatcher"
```

---

### Task 7: FastAPI Backend Core + API Routes

**Files:**
- Create: `message-monitor/backend/main.py`
- Create: `message-monitor/backend/websocket_manager.py`
- Create: `message-monitor/backend/routers/__init__.py`
- Create: `message-monitor/backend/routers/messages.py`
- Create: `message-monitor/backend/routers/groups.py`
- Create: `message-monitor/backend/routers/rules.py`
- Create: `message-monitor/tests/test_api.py`

**Interfaces:**
- Consumes: all previous tasks
- Produces: FastAPI app with routes, WebSocket endpoint

- [ ] **Step 1: Write failing test `tests/test_api.py`**

```python
import pytest
from httpx import AsyncClient, ASGITransport
from backend.main import app
from backend.database import Base, SessionLocal, engine
from backend.models import Group, Rule, Message


@pytest.fixture
def db():
    Base.metadata.create_all(bind=engine)
    session = SessionLocal()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.mark.asyncio
async def test_post_message():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post("/api/messages", json={
            "source": "telegram",
            "group_name": "Test Group",
            "sender": "john",
            "text": "This is a test message",
        })
    assert response.status_code == 200
    data = response.json()
    assert data["sender"] == "john"
    assert data["source"] == "telegram"


@pytest.mark.asyncio
async def test_get_messages_empty():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/messages")
    assert response.status_code == 200
    assert response.json() == []


@pytest.mark.asyncio
async def test_get_messages_with_filter():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        await client.post("/api/messages", json={
            "source": "telegram", "group_name": "Deals", "sender": "john", "text": "Price drop!"
        })
        await client.post("/api/messages", json={
            "source": "whatsapp", "group_name": "Family", "sender": "mom", "text": "Dinner ready"
        })
        response = await client.get("/api/messages?source=telegram")
    data = response.json()
    assert len(data) == 1
    assert data[0]["source"] == "telegram"
```

- [ ] **Step 2: Run test to verify it fails**

```bash
cd message-monitor && pytest tests/test_api.py -v
```

Expected: FAIL (cannot import app from main)

- [ ] **Step 3: Write `backend/websocket_manager.py`**

```python
from typing import Set
from fastapi import WebSocket


class WebSocketManager:
    def __init__(self):
        self.connections: Set[WebSocket] = set()

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.connections.add(websocket)

    def disconnect(self, websocket: WebSocket):
        self.connections.discard(websocket)

    async def broadcast(self, message: dict):
        dead = set()
        for ws in self.connections:
            try:
                await ws.send_json(message)
            except Exception:
                dead.add(ws)
        for ws in dead:
            self.connections.discard(ws)


ws_manager = WebSocketManager()
```

- [ ] **Step 4: Write `backend/routers/__init__.py`** (empty)

- [ ] **Step 5: Write `backend/routers/messages.py`**

```python
import datetime
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Message
from backend.schemas import MessageIn, MessageOut

router = APIRouter(prefix="/api/messages", tags=["messages"])


@router.post("", response_model=MessageOut)
async def create_message(msg: MessageIn, db: Session = Depends(get_db)):
    db_msg = Message(
        source=msg.source,
        sender=msg.sender,
        text=msg.text,
        group_id=msg.group_id,
        timestamp=msg.timestamp or datetime.datetime.utcnow(),
    )
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)
    return db_msg


@router.get("", response_model=list[MessageOut])
async def get_messages(
    source: str = Query(None),
    group_name: str = Query(None),
    important: bool = Query(None),
    limit: int = Query(50),
    db: Session = Depends(get_db),
):
    query = db.query(Message)
    if source:
        query = query.filter(Message.source == source)
    if important:
        query = query.filter(Message.importance_score >= 6)
    return query.order_by(Message.timestamp.desc()).limit(limit).all()
```

- [ ] **Step 6: Write `backend/routers/groups.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Group
from backend.schemas import GroupIn, GroupOut

router = APIRouter(prefix="/api/groups", tags=["groups"])


@router.post("", response_model=GroupOut)
def create_group(group: GroupIn, db: Session = Depends(get_db)):
    db_group = Group(source=group.source, name=group.name, external_id=group.external_id)
    db.add(db_group)
    db.commit()
    db.refresh(db_group)
    return db_group


@router.get("", response_model=list[GroupOut])
def get_groups(db: Session = Depends(get_db)):
    return db.query(Group).all()


@router.delete("/{group_id}")
def delete_group(group_id: int, db: Session = Depends(get_db)):
    group = db.query(Group).filter(Group.id == group_id).first()
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    db.delete(group)
    db.commit()
    return {"ok": True}
```

- [ ] **Step 7: Write `backend/routers/rules.py`**

```python
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from backend.database import get_db
from backend.models import Rule
from backend.schemas import RuleIn

router = APIRouter(prefix="/api/rules", tags=["rules"])


@router.post("")
def create_rule(rule: RuleIn, db: Session = Depends(get_db)):
    db_rule = Rule(group_id=rule.group_id, rule_type=rule.rule_type, value=rule.value, priority=rule.priority)
    db.add(db_rule)
    db.commit()
    db.refresh(db_rule)
    return db_rule


@router.get("")
def get_rules(group_id: int = None, db: Session = Depends(get_db)):
    query = db.query(Rule)
    if group_id:
        query = query.filter(Rule.group_id == group_id)
    return query.all()


@router.delete("/{rule_id}")
def delete_rule(rule_id: int, db: Session = Depends(get_db)):
    rule = db.query(Rule).filter(Rule.id == rule_id).first()
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    db.delete(rule)
    db.commit()
    return {"ok": True}
```

- [ ] **Step 8: Write `backend/routers/dashboard.py`**

```python
from fastapi import APIRouter, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.orm import Session
from fastapi import Depends

from backend.database import get_db
from backend.models import Message, Group

router = APIRouter(tags=["dashboard"])
templates = Jinja2Templates(directory="backend/templates")


@router.get("/", response_class=HTMLResponse)
def dashboard(request: Request, db: Session = Depends(get_db)):
    recent = db.query(Message).order_by(Message.timestamp.desc()).limit(20).all()
    groups = db.query(Group).all()
    return templates.TemplateResponse("dashboard.html", {
        "request": request,
        "messages": recent,
        "groups": groups,
    })
```

- [ ] **Step 9: Write `backend/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.database import init_db
from backend.routers import messages, groups, rules, dashboard


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    yield


app = FastAPI(title="Message Monitor", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])
app.include_router(messages.router)
app.include_router(groups.router)
app.include_router(rules.router)
app.include_router(dashboard.router)


@app.websocket("/ws")
async def websocket_endpoint(websocket):
    from backend.websocket_manager import ws_manager
    await ws_manager.connect(websocket)
    try:
        while True:
            await websocket.receive_text()
    except Exception:
        ws_manager.disconnect(websocket)
```

- [ ] **Step 10: Run tests**

```bash
cd message-monitor && pytest tests/test_api.py -v
```

Expected: PASS

- [ ] **Step 11: Commit**

```bash
git add message-monitor/backend/main.py message-monitor/backend/websocket_manager.py message-monitor/backend/routers/ message-monitor/tests/test_api.py && git commit -m "feat: add FastAPI backend with REST API and WebSocket"
```

---

### Task 8: Web Dashboard HTML Templates

**Files:**
- Create: `message-monitor/backend/templates/base.html`
- Create: `message-monitor/backend/templates/dashboard.html`
- Create: `message-monitor/backend/templates/groups.html`
- Create: `message-monitor/backend/templates/rules.html`
- Create: `message-monitor/backend/templates/messages.html`

**Interfaces:**
- Consumes: `dashboard.py` routes
- Produces: Rendered HTML pages

- [ ] **Step 1: Write `backend/templates/base.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Message Monitor</title>
    <script src="https://unpkg.com/htmx.org@2.0.2"></script>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, sans-serif; margin: 0; padding: 20px; background: #f5f5f5; }
        .container { max-width: 1000px; margin: 0 auto; }
        nav { background: #1a1a2e; padding: 12px 20px; border-radius: 8px; margin-bottom: 20px; }
        nav a { color: white; text-decoration: none; margin-right: 20px; font-weight: 500; }
        nav a:hover { opacity: 0.8; }
        .card { background: white; padding: 20px; border-radius: 8px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); margin-bottom: 16px; }
        .badge { display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 12px; font-weight: bold; }
        .badge-telegram { background: #0088cc; color: white; }
        .badge-whatsapp { background: #25D366; color: white; }
        .badge-gmail { background: #EA4335; color: white; }
        table { width: 100%; border-collapse: collapse; }
        th, td { padding: 10px; text-align: left; border-bottom: 1px solid #eee; }
        th { background: #f8f8f8; font-weight: 600; }
        .btn { padding: 8px 16px; border: none; border-radius: 4px; cursor: pointer; font-size: 14px; }
        .btn-primary { background: #1a1a2e; color: white; }
        .btn-danger { background: #e74c3c; color: white; }
        input, select { padding: 8px; border: 1px solid #ddd; border-radius: 4px; font-size: 14px; width: 100%; box-sizing: border-box; }
        .msg-important { border-left: 4px solid #e74c3c; }
        .msg-normal { border-left: 4px solid #bdc3c7; }
        .stats { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 16px; }
        .stat-card { background: white; padding: 20px; border-radius: 8px; text-align: center; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
        .stat-number { font-size: 32px; font-weight: bold; color: #1a1a2e; }
        .stat-label { color: #666; font-size: 14px; }
    </style>
</head>
<body>
    <div class="container">
        <nav>
            <a href="/">Dashboard</a>
            <a href="/groups">Groups</a>
            <a href="/rules">Rules</a>
            <a href="/messages">Messages</a>
        </nav>
        {% block content %}{% endblock %}
    </div>
</body>
</html>
```

- [ ] **Step 2: Write `backend/templates/dashboard.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="stats">
    <div class="stat-card">
        <div class="stat-number">{{ messages|length }}</div>
        <div class="stat-label">Recent Messages</div>
    </div>
    <div class="stat-card">
        <div class="stat-number">{{ groups|length }}</div>
        <div class="stat-label">Monitored Groups</div>
    </div>
    <div class="stat-card">
        <div class="stat-number">{{ messages|selectattr('importance_score', 'gt', 5)|list|length }}</div>
        <div class="stat-label">Important (Score > 5)</div>
    </div>
</div>

<div class="card">
    <h2>Recent Messages</h2>
    <table>
        <tr><th>Time</th><th>Source</th><th>Group</th><th>Sender</th><th>Message</th><th>Score</th></tr>
        {% for msg in messages %}
        <tr class="msg-important" {% if msg.importance_score < 6 %}style="opacity:0.7"{% endif %}>
            <td>{{ msg.timestamp.strftime('%H:%M') }}</td>
            <td><span class="badge badge-{{ msg.source }}">{{ msg.source }}</span></td>
            <td>{{ msg.group.name if msg.group else 'N/A' }}</td>
            <td>{{ msg.sender }}</td>
            <td>{{ msg.text[:50] }}{% if msg.text|length > 50 %}...{% endif %}</td>
            <td>{{ "%.1f"|format(msg.importance_score) }}</td>
        </tr>
        {% endfor %}
    </table>
</div>
{% endblock %}
```

- [ ] **Step 3: Write `backend/templates/groups.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card">
    <h2>Monitored Groups</h2>
    <form hx-post="/api/groups" hx-target="#groups-list" hx-swap="afterbegin" hx-on="submit: this.reset()">
        <div style="display:flex; gap:8px; margin-bottom:16px;">
            <select name="source" required>
                <option value="telegram">Telegram</option>
                <option value="whatsapp">WhatsApp</option>
                <option value="gmail">Gmail</option>
            </select>
            <input type="text" name="name" placeholder="Group name" required>
            <input type="text" name="external_id" placeholder="Group ID / chat ID" required>
            <button type="submit" class="btn btn-primary">Add Group</button>
        </div>
    </form>
    <table id="groups-list">
        <tr><th>Source</th><th>Name</th><th>External ID</th><th>Enabled</th><th></th></tr>
        {% for group in groups %}
        <tr>
            <td><span class="badge badge-{{ group.source }}">{{ group.source }}</span></td>
            <td>{{ group.name }}</td>
            <td>{{ group.external_id }}</td>
            <td>{{ group.enabled }}</td>
            <td><button class="btn btn-danger" hx-delete="/api/groups/{{ group.id }}" hx-target="closest tr" hx-swap="outerHTML">Remove</button></td>
        </tr>
        {% endfor %}
    </table>
</div>
{% endblock %}
```

- [ ] **Step 4: Write `backend/templates/rules.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card">
    <h2>Importance Rules</h2>
    <form hx-post="/api/rules" hx-target="#rules-list" hx-swap="afterbegin" hx-on="submit: this.reset()">
        <div style="display:flex; gap:8px; margin-bottom:16px;">
            <select name="rule_type" required>
                <option value="keyword">Keyword</option>
                <option value="sender">Priority Sender</option>
                <option value="topic">Topic</option>
            </select>
            <input type="text" name="value" placeholder='e.g. "urgent, price" for keywords' required>
            <input type="number" name="group_id" placeholder="Group ID" required>
            <input type="number" name="priority" placeholder="Priority (1-5)" value="1" min="1" max="5">
            <button type="submit" class="btn btn-primary">Add Rule</button>
        </div>
    </form>
    <table id="rules-list">
        <tr><th>Group ID</th><th>Type</th><th>Value</th><th>Priority</th><th></th></tr>
        {% for rule in rules %}
        <tr>
            <td>{{ rule.group_id }}</td>
            <td>{{ rule.rule_type }}</td>
            <td>{{ rule.value }}</td>
            <td>{{ rule.priority }}</td>
            <td><button class="btn btn-danger" hx-delete="/api/rules/{{ rule.id }}" hx-target="closest tr" hx-swap="outerHTML">Delete</button></td>
        </tr>
        {% endfor %}
    </table>
</div>
{% endblock %}
```

- [ ] **Step 5: Write `backend/templates/messages.html`**

```html
{% extends "base.html" %}
{% block content %}
<div class="card">
    <h2>Message History</h2>
    <div style="margin-bottom:16px;">
        <input type="text" id="search" placeholder="Search messages..." style="width:300px;display:inline-block;">
        <select id="source-filter" style="width:auto;display:inline-block;">
            <option value="">All sources</option>
            <option value="telegram">Telegram</option>
            <option value="whatsapp">WhatsApp</option>
            <option value="gmail">Gmail</option>
        </select>
        <button class="btn btn-primary" hx-get="/api/messages" hx-target="#messages-table" hx-trigger="click">Refresh</button>
    </div>
    <table id="messages-table">
        <tr><th>Time</th><th>Source</th><th>Sender</th><th>Message</th><th>Score</th><th>Summary</th></tr>
        {% for msg in messages %}
        <tr class="{% if msg.importance_score >= 6 %}msg-important{% else %}msg-normal{% endif %}">
            <td>{{ msg.timestamp.strftime('%Y-%m-%d %H:%M') }}</td>
            <td><span class="badge badge-{{ msg.source }}">{{ msg.source }}</span></td>
            <td>{{ msg.sender }}</td>
            <td>{{ msg.text[:60] }}{% if msg.text|length > 60 %}...{% endif %}</td>
            <td>{{ "%.1f"|format(msg.importance_score) }}</td>
            <td>{{ msg.summary or '' }}</td>
        </tr>
        {% endfor %}
    </table>
</div>
{% endblock %}
```

- [ ] **Step 6: Wire dashboard routes**

Edit `backend/routers/dashboard.py` — add routes for groups, rules, messages pages:

```python
@router.get("/groups", response_class=HTMLResponse)
def groups_page(request: Request, db: Session = Depends(get_db)):
    groups = db.query(Group).all()
    return templates.TemplateResponse("groups.html", {"request": request, "groups": groups})


@router.get("/rules", response_class=HTMLResponse)
def rules_page(request: Request, db: Session = Depends(get_db)):
    rules = db.query(Rule).all()
    return templates.TemplateResponse("rules.html", {"request": request, "rules": rules})


@router.get("/messages", response_class=HTMLResponse)
def messages_page(request: Request, db: Session = Depends(get_db)):
    messages = db.query(Message).order_by(Message.timestamp.desc()).limit(100).all()
    return templates.TemplateResponse("messages.html", {"request": request, "messages": messages})
```

- [ ] **Step 7: Create `.env.example`**

```
TELEGRAM_BOT_TOKEN=your_bot_token
TELEGRAM_CHAT_ID=your_chat_id
GMAIL_OAUTH_CLIENT_ID=your_client_id
GMAIL_OAUTH_CLIENT_SECRET=your_client_secret
GMAIL_OAUTH_REFRESH_TOKEN=your_refresh_token
OPENROUTER_API_KEY=your_openrouter_key
OPENROUTER_MODEL=openai/gpt-4o-mini
IMPORTANCE_THRESHOLD=6
DIGEST_INTERVAL_MINUTES=30
DAILY_REPORT_TIME=08:00
```

- [ ] **Step 8: Run the server and verify dashboard loads**

```bash
cd message-monitor && uvicorn backend.main:app --reload
```

Open http://localhost:8000 in browser — should see dashboard with nav and stats.

- [ ] **Step 9: Commit**

```bash
git add message-monitor/backend/templates/ message-monitor/backend/routers/dashboard.py message-monitor/.env.example && git commit -m "feat: add web dashboard with HTMX templates"
```

---

### Task 9: Celery Task Scheduler

**Files:**
- Create: `message-monitor/backend/tasks.py`
- Create: `message-monitor/backend/celery_app.py`

**Interfaces:**
- Consumes: `gmail_watcher.poll()`, `classifier.classify()`, `dispatcher.send_digest()`
- Produces: Scheduled celery tasks for gmail polling, daily report, email digest

- [ ] **Step 1: Write `backend/celery_app.py`**

```python
from celery import Celery
from backend.config import settings

celery_app = Celery(
    "message_monitor",
    broker="redis://localhost:6379/0",
    backend="redis://localhost:6379/0",
)

celery_app.conf.beat_schedule = {
    "poll-gmail": {
        "task": "backend.tasks.poll_gmail",
        "schedule": 60.0,
    },
    "poll-twitter": {
        "task": "backend.tasks.poll_twitter",
        "schedule": 300.0,
    },
    "send-digest": {
        "task": "backend.tasks.send_digest",
        "schedule": settings.digest_interval_minutes * 60.0,
    },
    "generate-daily-report": {
        "task": "backend.tasks.generate_daily_report",
        "schedule": {"hour": 8, "minute": 0},
    },
}
```

- [ ] **Step 2: Write `backend/tasks.py`**

```python
import datetime
from celery import shared_task
from backend.database import SessionLocal
from backend.models import Message, DigestQueue, DailyReport
from backend.schemas import MessageIn
from backend.classifier.rules import KeywordRule, SenderRule, HybridClassifier
from backend.classifier.llm_scorer import LLMScorer
from backend.config import settings
from backend.dispatcher.telegram import TelegramDispatcher
from backend.dispatcher.email import EmailDispatcher
from backend.watchers.gmail_watcher import GmailWatcher


@shared_task
def poll_gmail():
    watcher = GmailWatcher(
        client_id=settings.gmail_oauth_client_id,
        client_secret=settings.gmail_oauth_client_secret,
        refresh_token=settings.gmail_oauth_refresh_token,
    )
    import asyncio
    messages = asyncio.run(watcher.poll())

    db = SessionLocal()
    for msg in messages:
        db_msg = Message(source="gmail", sender=msg["sender"], text=msg["text"], timestamp=datetime.datetime.utcnow())
        db.add(db_msg)
    db.commit()
    db.close()
    
    return len(messages)


@shared_task
def poll_twitter():
    from backend.watchers.twitter_watcher import TwitterWatcher
    from backend.models import Group

    watcher = TwitterWatcher()
    db = SessionLocal()
    twitter_accounts = db.query(Group).filter(Group.source == "twitter", Group.enabled == True).all()
    total = 0

    for account in twitter_accounts:
        import asyncio
        posts = asyncio.run(watcher.poll(account.external_id))
        for post in posts:
            db_msg = Message(
                source="twitter",
                sender=post["sender"],
                text=post["text"],
                group_id=account.id,
                timestamp=post["timestamp"],
            )
            db.add(db_msg)
        total += len(posts)

    db.commit()
    db.close()
    return total


@shared_task
def classify_and_notify(message_id: int):
    db = SessionLocal()
    msg = db.query(Message).filter(Message.id == message_id).first()
    if not msg:
        return

    rules = [
        KeywordRule(keywords=["urgent", "price", "deal", "deadline", "payment"]),
        SenderRule(priority_senders=["@admin", "@moderator", "@pastor"]),
    ]
    classifier = HybridClassifier(rules=rules)
    msg_in = MessageIn(source=msg.source, group_name="", sender=msg.sender, text=msg.text)
    result = classifier.classify(msg_in)

    if result["score"] < settings.importance_threshold:
        msg.importance_score = result["score"]
        db.commit()
        db.close()
        return

    scorer = LLMScorer(api_key=settings.openrouter_api_key, model=settings.openrouter_model)
    import asyncio
    llm_result = asyncio.run(scorer.score(
        text=msg.text, sender=msg.sender, group_name=msg.group.name if msg.group else "Unknown"
    ))
    final_score = max(result["score"], llm_result.get("score", 0))
    msg.importance_score = final_score
    msg.summary = llm_result.get("summary", "")
    db.commit()

    if final_score >= settings.importance_threshold:
        dispatcher = TelegramDispatcher(
            bot_token=settings.telegram_bot_token,
            chat_id="",  # fetched from user settings
        )
        asyncio.run(dispatcher.send_alert(
            group_name=msg.group.name if msg.group else "Unknown",
            sender=msg.sender,
            text=msg.text,
            summary=msg.summary,
            score=final_score,
        ))
        msg.notified = True
        db.commit()

    db.close()


@shared_task
def send_digest():
    db = SessionLocal()
    pending = db.query(Message).filter(Message.notified == False).order_by(Message.timestamp.desc()).limit(20).all()
    if not pending:
        db.close()
        return

    messages_data = [{
        "group_name": m.group.name if m.group else "Unknown",
        "sender": m.sender,
        "text": m.text,
        "summary": m.summary or m.text[:80],
        "importance_score": m.importance_score,
    } for m in pending]

    dispatcher = EmailDispatcher(
        client_id=settings.gmail_oauth_client_id,
        client_secret=settings.gmail_oauth_client_secret,
        refresh_token=settings.gmail_oauth_refresh_token,
        to_email="",
    )
    import asyncio
    asyncio.run(dispatcher.send_digest(messages_data, digest_type="digest"))

    for m in pending:
        dq = DigestQueue(message_id=m.id, channel="email")
        db.add(dq)
        m.notified = True
    db.commit()
    db.close()


@shared_task
def generate_daily_report():
    db = SessionLocal()
    yesterday = datetime.datetime.utcnow() - datetime.timedelta(days=1)
    important = db.query(Message).filter(
        Message.importance_score >= settings.importance_threshold,
        Message.timestamp >= yesterday,
    ).order_by(Message.importance_score.desc()).all()

    messages_data = [{
        "group_name": m.group.name if m.group else "Unknown",
        "sender": m.sender,
        "text": m.text,
        "summary": m.summary or m.text[:80],
        "importance_score": m.importance_score,
    } for m in important]

    dispatcher = EmailDispatcher(
        client_id=settings.gmail_oauth_client_id,
        client_secret=settings.gmail_oauth_client_secret,
        refresh_token=settings.gmail_oauth_refresh_token,
        to_email="",
    )
    import asyncio
    asyncio.run(dispatcher.send_digest(messages_data, digest_type="daily"))

    report = DailyReport(user_id=1, date=datetime.date.today(), summary_json=messages_data)
    db.add(report)
    db.commit()
    db.close()
```

- [ ] **Step 3: Commit**

```bash
git add message-monitor/backend/tasks.py message-monitor/backend/celery_app.py && git commit -m "feat: add Celery task scheduler for polling, digest, and daily report"
```

---

### Task 10: Chrome Extension — WhatsApp Hook + TTS + Voice

**Files:**
- Create: `message-monitor/extension/manifest.json`
- Create: `message-monitor/extension/content.js`
- Create: `message-monitor/extension/background.js`
- Create: `message-monitor/extension/popup.html`
- Create: `message-monitor/extension/popup.js`

- [ ] **Step 1: Write `extension/manifest.json`**

```json
{
  "manifest_version": 3,
  "name": "Message Monitor",
  "version": "1.0.0",
  "description": "Monitors WhatsApp Web, reads important messages aloud",
  "permissions": ["storage", "alarms", "tts", "activeTab"],
  "host_permissions": ["https://web.whatsapp.com/*", "http://localhost:8000/*"],
  "background": {
    "service_worker": "background.js"
  },
  "content_scripts": [
    {
      "matches": ["https://web.whatsapp.com/*"],
      "js": ["content.js"],
      "run_at": "document_idle"
    }
  ],
  "action": {
    "default_popup": "popup.html",
    "default_title": "Message Monitor"
  },
  "icons": {
    "128": "icon.png"
  }
}
```

- [ ] **Step 2: Write `extension/content.js`**

```javascript
const BACKEND_URL = 'http://localhost:8000';

let lastMessageCount = 0;

function extractMessages() {
  const messageElements = document.querySelectorAll('[data-testid="conversation-panel-messages"] [data-testid="conversation-panel-message-body"]');
  const currentCount = messageElements.length;

  if (currentCount <= lastMessageCount) return;
  lastMessageCount = currentCount;

  const groupName = document.querySelector('[data-testid="conversation-info-header"] h1')?.innerText || 'Unknown';

  const latestMsgs = [];
  for (const el of messageElements) {
    const text = el.innerText;
    if (!text) continue;

    const senderEl = el.closest('[data-testid="conversation-panel-message"]')?.querySelector('[data-testid="conversation-panel-message-sender"]');
    const sender = senderEl?.innerText || 'unknown';

    latestMsgs.push({ source: 'whatsapp', group_name: groupName, sender, text });
  }

  if (latestMsgs.length > 0) {
    chrome.runtime.sendMessage({ type: 'NEW_MESSAGES', messages: latestMsgs });
  }
}

const observer = new MutationObserver(() => extractMessages());
observer.observe(document.body, { childList: true, subtree: true });

extractMessages();
```

- [ ] **Step 3: Write `extension/background.js`**

```javascript
const BACKEND_URL = 'http://localhost:8000';
let ws = null;
let isSpeaking = false;

function connectWebSocket() {
  ws = new WebSocket('ws://localhost:8000/ws');
  ws.onmessage = (event) => {
    try {
      const data = JSON.parse(event.data);
      if (data.type === 'alert' && !isSpeaking) {
        isSpeaking = true;
        const text = `Important message from ${data.group}. ${data.summary}`;
        chrome.tts.speak(text, {
          rate: 0.9,
          onEvent: (event) => {
            if (event.type === 'end' || event.type === 'error') {
              isSpeaking = false;
            }
          }
        });
      }
    } catch (e) {
      console.error('WS parse error:', e);
    }
  };
  ws.onclose = () => setTimeout(connectWebSocket, 5000);
}

connectWebSocket();

chrome.runtime.onMessage.addListener((msg, sender, sendResponse) => {
  if (msg.type === 'NEW_MESSAGES') {
    for (const message of msg.messages) {
      fetch(`${BACKEND_URL}/api/messages`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(message),
      }).catch(e => console.error('Send failed:', e));
    }
  }

  if (msg.type === 'CHECK_MESSAGES') {
    fetch(`${BACKEND_URL}/api/messages?important=true&limit=5`)
      .then(r => r.json())
      .then(messages => {
        if (messages.length > 0 && !isSpeaking) {
          isSpeaking = true;
          let speech = `You have ${messages.length} important messages. `;
          messages.forEach(m => {
            speech += `${m.summary || m.text}. `;
          });
          chrome.tts.speak(speech, {
            rate: 0.9,
            onEvent: (event) => {
              if (event.type === 'end' || event.type === 'error') isSpeaking = false;
            }
          });
        }
        sendResponse({ messages });
      });
    return true;
  }
});
```

- [ ] **Step 4: Write `extension/popup.html`**

```html
<!DOCTYPE html>
<html>
<head><style>
  body { width: 300px; padding: 12px; font-family: -apple-system, sans-serif; }
  h2 { margin: 0 0 8px; font-size: 16px; }
  .status { display: flex; align-items: center; gap: 6px; margin-bottom: 12px; }
  .dot { width: 8px; height: 8px; border-radius: 50%; }
  .dot.online { background: #2ecc71; }
  .dot.offline { background: #e74c3c; }
  .alert { background: #f8f8f8; padding: 8px; border-radius: 4px; margin-bottom: 6px; font-size: 13px; }
  .btn { width: 100%; padding: 8px; background: #1a1a2e; color: white; border: none; border-radius: 4px; cursor: pointer; }
</style></head>
<body>
  <h2>Message Monitor</h2>
  <div class="status">
    <span class="dot offline" id="status-dot"></span>
    <span id="status-text">Disconnected</span>
  </div>
  <div id="alerts"><div class="alert" style="color:#999;">No recent alerts</div></div>
  <button class="btn" id="check-now">Check Messages</button>
  <script src="popup.js"></script>
</body>
</html>
```

- [ ] **Step 5: Write `extension/popup.js`**

```javascript
document.addEventListener('DOMContentLoaded', () => {
  const statusDot = document.getElementById('status-dot');
  const statusText = document.getElementById('status-text');

  fetch('http://localhost:8000/api/messages?limit=5')
    .then(r => r.json())
    .then(messages => {
      statusDot.className = 'dot online';
      statusText.textContent = 'Connected';

      const alertsDiv = document.getElementById('alerts');
      alertsDiv.innerHTML = '';
      if (messages.length === 0) {
        alertsDiv.innerHTML = '<div class="alert" style="color:#999;">No recent alerts</div>';
      } else {
        messages.forEach(m => {
          const div = document.createElement('div');
          div.className = 'alert';
          div.innerHTML = `<strong>${m.group_name || m.source}</strong>: ${(m.summary || m.text).substring(0, 80)}`;
          alertsDiv.appendChild(div);
        });
      }
    })
    .catch(() => {
      statusDot.className = 'dot offline';
      statusText.textContent = 'Disconnected';
    });

  document.getElementById('check-now').addEventListener('click', () => {
    chrome.runtime.sendMessage({ type: 'CHECK_MESSAGES' }, (response) => {
      if (response?.messages) {
        alert(`Found ${response.messages.length} important messages. Listening...`);
      }
    });
  });
});
```

- [ ] **Step 6: Commit**

```bash
git add message-monitor/extension/ && git commit -m "feat: add Chrome extension for WhatsApp monitoring and TTS"
```

---

### Task 11: Integration — Wire Everything Together

**Files:**
- Modify: `message-monitor/backend/main.py`
- Create: `message-monitor/backend/classifier/classification_service.py`
- Create: `message-monitor/README.md`

- [ ] **Step 1: Write `backend/classifier/classification_service.py`**

```python
from sqlalchemy.orm import Session
from backend.models import Group, Rule, Message
from backend.schemas import MessageIn
from backend.classifier.rules import KeywordRule, SenderRule, TopicRule, HybridClassifier
from backend.classifier.llm_scorer import LLMScorer
from backend.config import settings


def build_classifier_for_group(db: Session, group_id: int) -> HybridClassifier:
    rules = db.query(Rule).filter(Rule.group_id == group_id).all()
    classifier_rules = []
    for r in rules:
        if r.rule_type == "keyword":
            keywords = [k.strip() for k in r.value.split(",")]
            classifier_rules.append(KeywordRule(keywords=keywords, priority=r.priority))
        elif r.rule_type == "sender":
            senders = [s.strip() for s in r.value.split(",")]
            classifier_rules.append(SenderRule(priority_senders=senders, priority=r.priority))
        elif r.rule_type == "topic":
            topics = [t.strip() for t in r.value.split(",")]
            classifier_rules.append(TopicRule(topic_descriptions=topics, priority=r.priority))
    return HybridClassifier(rules=classifier_rules)


async def classify_message(db: Session, msg: Message, message_in: MessageIn):
    classifier = build_classifier_for_group(db, msg.group_id or 0)
    rule_result = classifier.classify(message_in)
    msg.importance_score = rule_result["score"]

    if rule_result["score"] >= settings.importance_threshold:
        scorer = LLMScorer(api_key=settings.openrouter_api_key, model=settings.openrouter_model)
        llm_result = await scorer.score(
            text=message_in.text,
            sender=message_in.sender,
            group_name=message_in.group_name,
        )
        msg.importance_score = max(msg.importance_score, llm_result.get("score", 0))
        msg.summary = llm_result.get("summary", "")

        if msg.importance_score >= settings.importance_threshold:
            from backend.dispatcher.telegram import TelegramDispatcher
            dispatcher = TelegramDispatcher(
                bot_token=settings.telegram_bot_token,
                chat_id="",  # fetched from user
            )
            await dispatcher.send_alert(
                group_name=message_in.group_name,
                sender=message_in.sender,
                text=message_in.text,
                summary=msg.summary,
                score=msg.importance_score,
            )
            msg.notified = True

            from backend.websocket_manager import ws_manager
            await ws_manager.broadcast({
                "type": "alert",
                "group": message_in.group_name,
                "sender": message_in.sender,
                "summary": msg.summary,
                "score": msg.importance_score,
            })

    db.commit()
```

- [ ] **Step 2: Update `backend/routers/messages.py` to run classification**

Replace the `create_message` function with:

```python
from backend.classifier.classification_service import classify_message


@router.post("", response_model=MessageOut)
async def create_message(msg: MessageIn, db: Session = Depends(get_db)):
    db_msg = Message(
        source=msg.source,
        sender=msg.sender,
        text=msg.text,
        group_id=msg.group_id,
        timestamp=msg.timestamp or datetime.datetime.utcnow(),
    )
    db.add(db_msg)
    db.commit()
    db.refresh(db_msg)

    await classify_message(db, db_msg, msg)

    db.refresh(db_msg)
    return db_msg
```

- [ ] **Step 3: Write `README.md`**

```markdown
# Message Monitor

Monitors WhatsApp groups, Telegram groups, and Gmail for important messages. Alerts you via Telegram Bot, email digests, and TTS through a Chrome extension.

## Setup

1. Install dependencies:
   ```bash
   pip install -r backend/requirements.txt
   ```

2. Copy `.env.example` to `.env` and fill in your credentials:
   - Telegram Bot Token (from @BotFather)
   - Gmail OAuth client ID/secret (Google Cloud Console)
   - OpenRouter API key

3. Start the backend:
   ```bash
   uvicorn backend.main:app --reload
   ```

4. Start Celery workers (optional, for scheduled tasks):
   ```bash
   celery -A backend.celery_app worker --beat -l info
   ```

5. Load the Chrome extension:
   - Go to `chrome://extensions`
   - Enable Developer mode
   - Load unpacked → select the `extension/` folder

## Usage

- Open WhatsApp Web → extension hooks in automatically
- Add Telegram bot to groups you want monitored
- Configure groups and rules on the dashboard (http://localhost:8000)
- Say "check messages" into your microphone → extension reads important messages aloud
```

- [ ] **Step 4: Verify everything runs**

```bash
cd message-monitor && uvicorn backend.main:app --reload &
```

Open http://localhost:8000 — confirm dashboard loads, API responds.

- [ ] **Step 5: Final commit**

```bash
git add message-monitor/ && git commit -m "feat: full integration — classification pipeline, README"
```

---

### Task 12: Smart Contract + On-Chain Integration

**Files:**
- Create: `message-monitor/contracts/AlertAttestation.sol`
- Create: `message-monitor/contracts/test/AlertAttestation.t.sol`
- Create: `message-monitor/contracts/foundry.toml`
- Create: `message-monitor/contracts/script/Deploy.s.sol`
- Create: `message-monitor/backend/onchain.py`
- Modify: `message-monitor/backend/config.py`
- Modify: `message-monitor/backend/classifier/classification_service.py`

**Interfaces:**
- Consumes: `config.settings.contract_address`, `config.settings.wallet_private_key`, `config.settings.rpc_url`
- Produces: Deployed contract on Monad testnet, `onchain.attest_alert(message_hash, group, timestamp)` → tx hash

- [ ] **Step 1: Create contract directory and install Foundry**

```bash
mkdir -p message-monitor/contracts/test message-monitor/contracts/script
```

```bash
# Install Foundry (if not already installed)
curl -L https://foundry.paradigm.xyz | bash
foundryup
```

- [ ] **Step 2: Write `contracts/foundry.toml`**

```toml
[profile.default]
src = "."
out = "out"
libs = ["lib"]

[profile.default.optimizer]
runs = 200

[rpc_endpoints]
monad_testnet = "https://testnet-rpc.monad.xyz"
```

- [ ] **Step 3: Write `contracts/AlertAttestation.sol`**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

/// @title AlertAttestation
/// @notice Records attestations of important message alerts on-chain.
///         Each attestation proves a user was alerted about a message
///         at a specific timestamp. Immutable once written.
contract AlertAttestation {
    address public owner;
    uint256 public totalAttestations;

    struct Attestation {
        bytes32 messageHash;
        string groupName;
        uint256 timestamp;
        uint8 importanceScore;
    }

    event AttestationCreated(
        uint256 indexed id,
        bytes32 indexed messageHash,
        string groupName,
        uint256 timestamp,
        uint8 importanceScore
    );

    mapping(uint256 => Attestation) public attestations;
    mapping(bytes32 => bool) public messageHashSeen;

    error OnlyOwner();
    error MessageAlreadyAttested();

    modifier onlyOwner() {
        if (msg.sender != owner) revert OnlyOwner();
        _;
    }

    constructor() {
        owner = msg.sender;
    }

    function attest(
        bytes32 _messageHash,
        string calldata _groupName,
        uint8 _importanceScore
    ) external onlyOwner returns (uint256) {
        if (messageHashSeen[_messageHash]) revert MessageAlreadyAttested();

        uint256 id = totalAttestations;
        attestations[id] = Attestation({
            messageHash: _messageHash,
            groupName: _groupName,
            timestamp: block.timestamp,
            importanceScore: _importanceScore
        });
        messageHashSeen[_messageHash] = true;
        totalAttestations++;

        emit AttestationCreated(id, _messageHash, _groupName, block.timestamp, _importanceScore);
        return id;
    }

    function getAttestation(uint256 _id) external view returns (Attestation memory) {
        return attestations[_id];
    }

    function verify(bytes32 _messageHash) external view returns (bool) {
        return messageHashSeen[_messageHash];
    }
}
```

- [ ] **Step 4: Write `contracts/test/AlertAttestation.t.sol`**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Test.sol";
import "../AlertAttestation.sol";

contract AlertAttestationTest is Test {
    AlertAttestation public alertContract;

    function setUp() public {
        alertContract = new AlertAttestation();
    }

    function test_OwnerSet() public view {
        assertEq(alertContract.owner(), address(this));
    }

    function test_Attest() public {
        bytes32 hash = keccak256("test message");
        uint256 id = alertContract.attest(hash, "Test Group", 8);
        assertEq(id, 0);
        assertEq(alertContract.totalAttestations(), 1);

        (bytes32 messageHash, string memory groupName, , uint8 score) = alertContract.getAttestation(0);
        assertEq(messageHash, hash);
        assertEq(groupName, "Test Group");
        assertEq(score, 8);
    }

    function test_CannotDuplicateMessage() public {
        bytes32 hash = keccak256("unique message");
        alertContract.attest(hash, "Group", 7);
        vm.expectRevert(AlertAttestation.MessageAlreadyAttested.selector);
        alertContract.attest(hash, "Group", 7);
    }

    function test_Verify() public {
        bytes32 hash = keccak256("important alert");
        alertContract.attest(hash, "Deals", 9);
        assertTrue(alertContract.verify(hash));
    }

    function test_NonOwnerCannotAttest() public {
        vm.prank(address(0x123));
        vm.expectRevert(AlertAttestation.OnlyOwner.selector);
        alertContract.attest(keccak256("hack"), "Hack Group", 10);
    }
}
```

- [ ] **Step 5: Write `contracts/script/Deploy.s.sol`**

```solidity
// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "forge-std/Script.sol";
import "../AlertAttestation.sol";

contract DeployScript is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("MONAD_PRIVATE_KEY");
        vm.startBroadcast(deployerPrivateKey);
        new AlertAttestation();
        vm.stopBroadcast();
    }
}
```

- [ ] **Step 6: Run Foundry tests**

```bash
cd message-monitor/contracts && forge test -vv
```

Expected: 5/5 tests passing

- [ ] **Step 7: Write `backend/onchain.py`**

```python
import hashlib
from web3 import Web3
from typing import Optional
from backend.config import settings


CONTRACT_ABI = [
    {
        "inputs": [{"internalType": "bytes32", "name": "_messageHash", "type": "bytes32"}, {"internalType": "string", "name": "_groupName", "type": "string"}, {"internalType": "uint8", "name": "_importanceScore", "type": "uint8"}],
        "name": "attest",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "_messageHash", "type": "bytes32"}],
        "name": "verify",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_id", "type": "uint256"}],
        "name": "getAttestation",
        "outputs": [{"internalType": "bytes32", "name": "messageHash", "type": "bytes32"}, {"internalType": "string", "name": "groupName", "type": "string"}, {"internalType": "uint256", "name": "timestamp", "type": "uint256"}, {"internalType": "uint8", "name": "importanceScore", "type": "uint8"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class OnChainClient:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.monad_rpc_url))
        self.contract = self.w3.eth.contract(
            address=Web3.to_checksum_address(settings.contract_address),
            abi=CONTRACT_ABI,
        ) if settings.contract_address else None
        self.account = self.w3.eth.account.from_key(settings.wallet_private_key) if settings.wallet_private_key else None

    def is_available(self) -> bool:
        return self.contract is not None and self.account is not None and self.w3.is_connected()

    def hash_message(self, text: str, group: str, timestamp: str) -> bytes:
        combined = f"{text}|{group}|{timestamp}"
        return Web3.keccak(text=combined)

    def attest_alert(self, text: str, group: str, timestamp: str, score: float) -> Optional[str]:
        if not self.is_available():
            return None

        msg_hash = self.hash_message(text, group, timestamp)
        tx = self.contract.functions.attest(
            msg_hash,
            group,
            min(int(score), 10),
        ).transact({"from": self.account.address})
        receipt = self.w3.eth.wait_for_transaction_receipt(tx)
        return receipt.transactionHash.hex()

    def verify_alert(self, text: str, group: str, timestamp: str) -> Optional[bool]:
        if not self.contract:
            return None
        msg_hash = self.hash_message(text, group, timestamp)
        return self.contract.functions.verify(msg_hash).call()


onchain_client = OnChainClient()
```

- [ ] **Step 8: Update `backend/config.py` — add Monad RPC fields**

Add to `Settings` class:
```python
monad_rpc_url: str = "https://testnet-rpc.monad.xyz"
contract_address: str = ""
wallet_private_key: str = ""
```

- [ ] **Step 9: Integrate attestation into classification service**

In `backend/classifier/classification_service.py`, at the end of `classify_message`, after sending Telegram alert and WebSocket push:

```python
from backend.onchain import onchain_client
try:
    tx_hash = onchain_client.attest_alert(
        text=message_in.text,
        group=message_in.group_name,
        timestamp=str(msg.timestamp),
        score=msg.importance_score,
    )
    if tx_hash:
        print(f"Attested on-chain: {tx_hash}")
except Exception as e:
    print(f"On-chain attestation failed (non-critical): {e}")
```

- [ ] **Step 10: Wire up and verify**

```bash
cd message-monitor && pip install web3
```

```bash
cd message-monitor/contracts && forge build
```

Expected: Contract compiles; attestation fires on important alerts (no-op if contract address not configured).

- [ ] **Step 11: Commit**

```bash
git add message-monitor/contracts/ message-monitor/backend/onchain.py && git commit -m "feat: add AlertAttestation contract + on-chain integration"
```

---

## Spec Coverage Check

| Spec Requirement | Task |
|-----------------|------|
| WhatsApp monitoring | Task 10 (Chrome extension) |
| Telegram monitoring | Task 3 (Telegram watcher) |
| Gmail monitoring | Task 2 (Gmail watcher) |
| Twitter/X monitoring | Task 2.5 (Twitter watcher) |
| Keyword rules | Task 4 (Rules engine) |
| Sender rules | Task 4 (Rules engine) |
| Topic rules | Task 4 (Rules engine) |
| LLM scoring | Task 5 (LLM scorer) |
| Telegram alerts | Task 6 (Dispatcher) |
| Email digests | Task 6 (Email dispatcher) |
| Daily reports | Task 9 (Celery tasks) |
| TTS / voice | Task 10 (Chrome extension) |
| Web dashboard | Task 7 + 8 (FastAPI + templates) |
| Group management | Task 7 (Groups API) |
| Rule management | Task 7 (Rules API) |
| No message replies | Global constraint (read-only) |
| Hybrid AI + keyword classification | Task 11 (Classification service) |
| Smart contract / on-chain component | Task 12 (AlertAttestation) |
