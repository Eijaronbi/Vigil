# Message Monitor — Design Document

## Overview

A personal automation system that monitors WhatsApp groups, Telegram groups, and Gmail for important messages, then alerts the user via Telegram Bot, email, and voice (TTS through a Chrome extension). Built as a Python monolith with a Chrome extension sidecar.

## Sources

| Source | Method | Risk Level |
|--------|--------|------------|
| WhatsApp | Chrome extension injects into user's WhatsApp Web session | Low |
| Telegram | Bot API (official, read-only) | None |
| Gmail | Gmail API OAuth 2.0 (official) | None |
| Twitter/X | Jina Reader polling (no login, no API key) | None |

## Outputs

| Channel | Mechanism | When |
|---------|-----------|------|
| Telegram Bot | Official Bot API push | Immediately on important message |
| Email | Gmail API OAuth (send via same auth) | Configurable digest + daily report |
| TTS | Chrome extension receives WebSocket event, uses Web Speech API | Immediately + voice-command triggered |
| On-Chain | AlertAttestation contract (Monad testnet) | On every important alert |

## Architecture

```
┌──────────────────────────────────────────────────────────────┐
│                   Python Backend (FastAPI)                    │
│                                                              │
│  ┌──────────┐   ┌───────────┐   ┌──────────┐  ┌────────┐   │
│  │ Telegram │   │ Gmail     │   │ Twitter  │  │ Web    │   │
│  │ Watcher  │   │ Watcher   │   │ Watcher  │  │Dashboard│   │
│  │ (Bot API)│   │ (OAuth)   │   │(JinaReader│  │ (HTMX) │   │
│  └─────┬────┘   └─────┬─────┘   └────┬─────┘  └────────┘   │
│        │              │              │                      │
│  ┌─────▼──────────────▼──────────────▼──────┐               │
│  │   Message Queue          │                               │
│  │   (in-memory + SQLite)   │                               │
│  └─────┬─────────────────────┘                               │
│        │                                                     │
│  ┌─────▼──────────────────────┐                              │
│  │   AI Classifier + Rules    │                              │
│  │   - Keyword pass           │                              │
│  │   - Sender filter          │                              │
│  │   - Topic filter           │                              │
│  │   - LLM pass (OpenRouter)  │                              │
│  └─────┬──────────────────────┘                              │
│        │                                                     │
│  ┌─────▼──────────────────────┐                              │
│  │   Notification Dispatcher  │                              │
│  │   ┌──────┐ ┌─────┐ ┌────┐ │                              │
│  │   │TG Bot│ │Email│ │TTS │ │                              │
│  │   └──────┘ └─────┘ └──┬─┘ │                              │
│  └───────────────────────────┘                              │
└──────────────────────────────┘                              │
                               │ WebSocket                    │
┌──────────────────────────────▼──────────────────────────────┐
│                Chrome Extension                               │
│  - Hooks into WhatsApp Web tab, reads new messages           │
│  - Receives WebSocket pushes → reads aloud (Web Speech API)  │
│  - Microphone trigger: voice command to check messages       │
│  - Keeps WA session alive                                    │
│  - Minimal popup UI (status, recent alerts)                  │
└──────────────────────────────────────────────────────────────┘

┌──────────────────────────────┐
│   On-Chain (Monad Testnet)   │
│   AlertAttestation Contract  │
│   - attests hashes on alert  │
│   - public verify() function │
│   - tamper-proof record      │
└──────────────────────────────┘
```

## Data Flow

1. **WhatsApp:** Chrome extension detects new messages → sends to backend via HTTP/WebSocket
2. **Telegram:** Bot API polls/listens for new messages in joined groups
3. **Gmail:** OAuth API polls inbox periodically (every 1-5 min)
4. **Twitter/X:** Jina Reader polls monitored accounts periodically (every 5 min) → extracts latest posts → tracks last-seen post ID per account
5. All messages enter the queue → classified for importance
6. Classification pipeline:
   - **Keyword match** (immediate flag, configurable per-group/account)
   - **Sender filter** (flag if specific person posts)
   - **Topic filter** (flag if message matches a topic description)
   - **LLM scoring** (async, batch) → importance 0-10 + summary
7. Score ≥ threshold (default: 6) → Notification Dispatcher
8. Dispatcher:
   - Sends Telegram message with sender, group/account, summary
   - Queues for email digest (configurable interval)
   - Pushes to Chrome extension via WebSocket → TTS
   - Writes attestation to AlertAttestation contract (Monad testnet)
9. All messages stored in SQLite with importance scores
10. Daily report: formatted email with top messages from all sources

## Components

### Backend (Python)

**Stack:** FastAPI, SQLite, Celery (for scheduled tasks), HTMX + Jinja2 templates

**API Endpoints:**
- `POST /api/messages` — receives message from Chrome extension
- `POST /api/classify` — forces re-classification
- `GET /api/messages?group=X&important=true` — query messages
- `GET /api/report/daily` — generate daily report
- `WS /ws/alerts` — WebSocket for TTS pushes to extension
- Dashboard routes for group/rule management

**Watchers:**
- `TelegramWatcher` — uses python-telegram-bot, listens in joined groups, forwards to queue
- `GmailWatcher` — uses google-auth + Gmail API, polls for new messages, forwards to queue
- `TwitterWatcher` — uses httpx to poll Jina Reader (`https://r.jina.ai/https://x.com/{username}`), parses markdown for posts, tracks last-seen post ID, forwards new posts to queue

**Classifier:**
- `KeywordRule` — regex/word-list match per group
- `SenderRule` — match by sender name/phone
- `TopicRule` — LLM classification against topic descriptions
- `LLMClassifier` — calls OpenRouter/OpenAI API, returns score + summary
- `HybridClassifier` — runs all rules, combines scores

**Dispatcher:**
- `TelegramDispatcher` — sends formatted alerts to user's bot
- `EmailDispatcher` — sends digests + daily reports via Gmail API
- `TTSDispatcher` — pushes to extension via WebSocket

**On-Chain:**
- `AlertAttestation.sol` — Solidity contract deployed on Monad testnet that stores `(messageHash, groupName, timestamp, importanceScore)` per alert
- `onchain.py` — `OnChainClient` using web3.py, called after every important alert to create an immutable attestation
- Users can verify any alert on-chain: `contract.verify(keccak256(message + group + timestamp))` → bool

**Scheduler (Celery beats):**
- Gmail poll (every 1 min)
- Twitter/X poll (every 5 min per account)
- Daily report generation (daily at 8 AM)
- Email digest (every 30 min configurable)
- Old message cleanup (optional)

### Chrome Extension

**Manifest V3**

**Permissions:** `storage`, `alarms`, `tts`, `activeTab`, script injection on `web.whatsapp.com`

**Content Script:** Injects into WhatsApp Web, observes DOM for new messages (MutationObserver), extracts text/sender/group, sends to backend

**Background Service Worker:** Manages WebSocket connection to backend, receives TTS events, triggers speech synthesis

**Popup UI:** Connection status, recent alerts, pause/resume, settings link

**Voice trigger:** Uses Web Speech API (SpeechRecognition) — listens for wake word ("check messages") → requests backend for recent important messages → reads them aloud

### Web Dashboard

**Pages:**
- Login / setup wizard (OAuth connection guides)
- Groups page (add/remove WhatsApp groups, Telegram groups, Twitter accounts)
- Rules page (per-group keywords, priority senders, topics)
- Message history (searchable, filterable by source/group/importance/date)
- Daily report preview
- Cross-account Twitter report (weekly summary of all monitored accounts)
- Settings (digest interval, TTS preferences, threshold sliders)

### Database Schema (SQLite)

```
users (id, name, email, telegram_chat_id, created_at)
groups (id, user_id, source, name, external_id, enabled)
rules (id, group_id, rule_type, value, priority)
messages (id, group_id, source, sender, text, timestamp, importance_score, summary, is_read, notified)
digest_queue (id, message_id, channel, sent_at)
daily_reports (id, user_id, date, generated_at, summary_json)
```

## Classification Rules

Each rule is configured per-group:

```
Group: "Deals"
  Keywords: ["price", "discount", "code", "link", "urgent"]
  Priority Senders: ["@john", "@admin"]
  Topics: ["new product launches", "limited time offers"]
  Importance Threshold: 6
```

```
Group: "Church"
  Keywords: ["meeting", "prayer", "emergency", "urgent"]
  Priority Senders: ["@pastor", "@moderator"]
  Topics: ["service changes", "events this week"]
  Importance Threshold: 5
```

```
Twitter: "@elonmusk"
  Keywords: ["tesla", "spacex", "launch", "stock"]
  Topics: ["new product announcements", "company earnings"]
  Importance Threshold: 7
```

## Voice Interface

Activation: Wake word "check messages" via Chrome extension microphone
Flow:
1. Speech captured → sent to backend
2. Backend returns top N recent important messages (within configurable time window)
3. Extension reads them aloud via Web Speech API (TTS)
4. Optional: ask follow-ups like "what about the deals group" → triggers keyword-filtered query

## Future Considerations (Not MVP)

- Mobile companion app (iOS/Android) for TTS on phone
- Multi-user support (shared server, individual sessions)
- WhatsApp Business API integration (if scaling to production)
- Message summarization (LLM summary of all missed messages)
- Export/analytics dashboard
- Instagram / LinkedIn / Reddit monitoring (same Jina Reader approach)

## Non-Goals (V1)

- Replying to messages (explicitly avoided to prevent flagging)
- Media processing (image/voice transcription)
- Anomaly detection or trend analysis
- Integration with Slack, Discord, or other platforms
