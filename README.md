# Message Monitor

Real-time message monitoring system with importance classification, Telegram alerts, and on-chain attestation.

## Features
- Import messages from Telegram and Gmail sources
- Rule-based and LLM-powered importance classification
- Telegram alert dispatching for high-importance messages
- WebSocket real-time dashboard
- On-chain attestation on Monad testnet

## Setup

```bash
pip install -r requirements.txt
```

Copy `.env.example` to `.env` and configure:

| Variable | Description |
|---|---|
| `telegram_bot_token` | Telegram bot token for alerts |
| `openrouter_api_key` | OpenRouter API key for LLM scoring |
| `openrouter_model` | Model name (default: openai/gpt-4o-mini) |
| `monad_rpc_url` | Monad testnet RPC URL |
| `contract_address` | On-chain attestation contract |
| `wallet_private_key` | Wallet key for on-chain transactions |

## Run

```bash
uvicorn backend.main:app --reload
```

Open `http://localhost:8000` for the dashboard.

## Chrome Extension

Load the `extension/` directory as an unpacked extension in Chrome.
