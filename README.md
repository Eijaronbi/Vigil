# Vigil — Never Miss What Matters

Multi-platform message monitor with AI classification, voice alerts, and on-chain Memory Vault on Monad.

## Current Status

**Built for Spark Hackathon on Monad.** Working prototype running at `localhost:8002`.

### ✅ Completed

- **Telegram watcher** — Bot `@Vigil_watch_bot` polling, verified and live
- **Jina Reader watcher** — Twitter/X + Facebook public profile polling via `r.jina.ai` (no auth needed)
- **Discord watcher** — Code written (`discord.py` client), needs bot token from discord.com/developers
- **Gmail watcher** — Code written, needs Google Cloud OAuth credentials
- **WhatsApp** — Chrome extension (Manifest V3), load unpacked to use
- **AI classification** — Keyword rules + LLM urgency scoring via OpenRouter
- **Voice alerts (TTS)** — 322 edge-tts voices, live selector in dashboard
- **Wallet auth** — EIP-4361 sign-in with MetaMask + password fallback
- **Memory Vault** — Smart contract deployed on Monad Testnet at `0x819b869951dEa78C2BeEf5dD79691CbbB861bfFc`
- **Memory Vault UI** — Commit batches, view on-chain, explorer links, network badge
- **WebSocket** — Real-time message push to dashboard
- **Dashboard** — Source cards, message feed, voice panel, vault panel
- **Chrome extension** — WhatsApp DOM monitoring with TTS (MV3, no build needed)

### 🟡 Working (needs action from you)

| Feature | How to enable |
|---------|---------------|
| **Discord** | Create bot at discord.com/developers, enable Message Content Intent, paste token in dashboard |
| **Gmail** | Create OAuth credentials at console.cloud.google.com, add redirect URI, set `.env` |
| **WhatsApp** | Load `extension/` unpacked in chrome://extensions, scan QR on web.whatsapp.com |
| **GitHub push** | `gh auth login -w` then `git push origin master` |
| **Android app** | Install Flutter SDK, then `cd android-app && flutter build apk --debug` |

### 🔴 Not Done / Needs Work

| Issue | Details |
|-------|---------|
| **Mainnet deploy** | Contract only on testnet. Needs real MON in deployer wallet (`0x49e9...f945cc`). Deploy: `python contracts/scripts/deploy.py mainnet` |
| **Network switching** | Backend hardcoded to testnet. Need to add runtime network selector in `.env` or settings |
| **Android app TTS** | No `TTSService.dispose()`, permission stub only, hardcoded localhost WS URL |
| **Extension TTS (MV3)** | `window.speechSynthesis` doesn't work in service workers. Needs alternative (Web Speech API in offscreen doc or TTS via host) |
| **Extension WS URL** | Hardcoded to `ws://localhost:8002` — needs config page in popup |
| **WhatsApp selectors** | DOM `data-testid` values may be stale — verify against live web.whatsapp.com |
| **Gmail OAuth** | No Google Cloud project set up yet |
| **npm install for contracts** | Timed out here — run manually if needed |
| **Flutter SDK** | Not installed on build machine — install and run `flutter build apk --debug` |

## To Run on a Website (Production)

Currently runs on `localhost:8002`. To deploy publicly:

```
1. Host backend on a VPS (DigitalOcean, Railway, Render, etc.)
   - Run: uvicorn backend.main:app --host 0.0.0.0 --port 8002
   - Use a reverse proxy (nginx/Caddy) for TLS

2. Set these env vars:
   - TELEGRAM_BOT_TOKEN=<your token>
   - WALLET_PRIVATE_KEY=<deployer key for vault>
   - CONTRACT_ADDRESS=0x819b869951dEa78C2BeEf5dD79691CbbB861bfFc
   - AUTH_PASSWORD=<change from default "vigil">

3. Update the WebSocket URL in index.html
   - Change ws://localhost:8002 to wss://your-domain.com

4. Update extension/background.js WS_URL
   - Change localhost:8002 to your domain

5. Set up HTTPS (required for MetaMask)
   - Use Caddy for automatic TLS certs

6. For Gmail: set redirect URI to https://your-domain.com/api/auth/gmail/callback
```

## Architecture

```
MetaMask Wallet ──signs auth──> Backend ──session token──> Frontend
                                                                    │
Messages (TG/Gmail/Discord/Twitter/FB/WhatsApp) ──> AI Classifier ──> SQLite
                                                                    │
                                    ┌─ Important? ──> TTS Voice Alert + WebSocket
                                    │
                                    └─ Commit Batch ──> MemoryVault Contract (Monad)
```

## Memory Vault (Monad Testnet)

- **Contract**: `0x819b869951dEa78C2BeEf5dD79691CbbB861bfFc`
- **Explorer**: https://testnet.monadexplorer.com/address/0x819b869951dEa78C2BeEf5dD79691CbbB861bfFc
- **Chain**: Monad Testnet (ID: 10143)
- **How it works**: Important messages → SHA-256 Merkle tree → root hash committed to contract. Messages stay off-chain, anyone can verify inclusion with proof.

## Quick Start (Local)

```bash
pip install fastapi uvicorn pydantic sqlalchemy web3 eth_account httpx python-telegram-bot discord.py celery
python -m backend.main
# Open http://localhost:8002
# Login with password: "vigil" or connect MetaMask
```

## Project Structure

```
hackathon/
├── index.html              # Dashboard UI
├── backend/
│   ├── main.py             # FastAPI app
│   ├── config.py           # Settings from .env
│   ├── merkle.py           # Merkle tree
│   ├── abi.py              # Contract ABI
│   ├── routers/
│   │   ├── auth.py         # Wallet + password auth
│   │   ├── vault.py        # Memory Vault endpoints
│   │   ├── sources.py      # Source connections
│   │   └── ...
│   └── watchers/
│       ├── telegram_watcher.py
│       ├── discord_watcher.py
│       └── jina_watcher.py   # Twitter/X + Facebook
├── contracts/
│   ├── MemoryVault.sol
│   ├── deploy-testnet.json
│   └── scripts/deploy.py
├── extension/              # Chrome extension (WhatsApp)
└── android-app/            # Flutter app
```
