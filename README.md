# Vigil — Never Miss What Matters

Multi-platform message monitor with AI classification, voice alerts, and on-chain Memory Vault on Monad.

## The Problem

You're in 20+ Web3 communities — Telegram groups, Discord servers, Twitter threads, WhatsApp chats. Important messages (grant opportunities, partnership offers, security alerts, alpha calls) get buried in noise. You can't read everything, but you can't afford to miss what matters.

## The Solution

Vigil listens across every channel, classifies messages by importance using AI, reads critical alerts aloud via TTS, and commits important moments to an immutable on-chain Memory Vault on Monad.

### Key Features

- **Multi-source listening**: Telegram, WhatsApp, Gmail, Twitter/X — one dashboard
- **AI classification**: Keyword rules + LLM urgency scoring
- **Voice alerts**: edge-tts neural voices — 322 voices across 100+ languages
- **On-chain Memory Vault**: Tamper-evident proof of important communications
- **Wallet auth**: Connect with MetaMask — no passwords needed

## Why Monad

Vigil's Memory Vault stores cryptographic commitments (Merkle roots) of important message batches on-chain. We chose Monad for three reasons:

### 1. Proof of Existence Without Bloat
Storing full messages on-chain is expensive and unnecessary. Instead, each batch of important messages is hashed into a Merkle tree, and only the 32-byte root is committed to the Memory Vault contract. The actual messages stay in your local database — but anyone can cryptographically verify that a message was part of a committed batch using the Merkle proof. Monad's low gas fees make this practical even for frequent commits.

### 2. Parallel Execution for Scale
Monad's parallel EVM enables us to commit multiple batches concurrently without contention. As Vigil scales to thousands of users, each committing daily batches, Monad's pipelined execution keeps costs predictable and throughput high — unlike sequential EVM chains where batch commits would compete for block space.

### 3. Asynchronous Deferred State
Vigil's alert pipeline generates bursts of important messages (e.g., during a security incident or a grant deadline). Monad's asynchronous execution model means our commit transactions don't stall while waiting for prior state reads — critical for time-sensitive attestations.

> **Memory Vault** is not a chain of custody or a legal framework. It is a cryptographic proof-of-existence mechanism — tamper-evident timestamps for communication memories, stored on a public ledger where they cannot be altered or deleted.

## Architecture

```
User Wallet (MetaMask) ──signs auth message──> Backend ──issues session token──> Frontend
                                                                                        │
User's Messages (Telegram, Gmail, etc.) ──> Backend ──> AI Classifier ──> SQLite DB
                                                                                        │
                                                          ┌─> Voice Alert (edge-tts)
                                                ┌─ Important? ──> WebSocket Push
                                                │
                                                └─ Commit Batch ──> MemoryVault Contract (Monad)
                                                                         │
                                                                  Merkle Root (32 bytes)
                                                                         │
                                                                  Monad Block (immutable)
```

## Memory Vault Smart Contract

`contracts/contracts/MemoryVault.sol`

```solidity
function commitBatch(bytes32 merkleRoot, uint256 messageCount, bytes32 metadataHash)
    external returns (uint256 batchId);

function verifyMessage(bytes32 merkleRoot, bytes32 leaf, bytes32[] calldata proof)
    external view returns (bool);

function getBatch(uint256 batchId) external view returns (Batch memory);
function getBatchCount() external view returns (uint256);
```

- Each batch stores: Merkle root, timestamp, message count, metadata hash, committer address
- Messages are never stored on-chain — only the root hash
- Anyone can verify a message belonged to a batch by providing the Merkle proof
- Deployed on Monad Testnet (chain ID 10143)

### How Verification Works

1. User marks messages as "important"
2. Backend collects important messages into a batch
3. Backend builds a Merkle tree (SHA-256) of the messages
4. Backend commits the root hash to the Memory Vault contract on Monad
5. The transaction is permanently recorded on Monad's ledger
6. To prove a message was in the batch: provide the message data + Merkle proof
7. Anyone can call `verifyMessage()` with the proof to confirm inclusion

## Getting Started

### Prerequisites

- Python 3.11+
- Node.js 20+ (for contract compilation)
- MetaMask (for wallet auth)
- MON testnet tokens (faucet: https://faucet.monad.xyz)

### Quick Start

```bash
# 1. Install Python deps
cd hackathon
pip install -r backend/requirements.txt

# 2. Set up .env
cp .env.example .env
# Add your Telegram bot token, wallet private key, etc.

# 3. Start the server
python -m backend.main
# -> http://localhost:8002

# 4. Open the dashboard
# -> http://localhost:8002
# Connect MetaMask or use password "vigil"
```

### Deploy the Memory Vault Contract

```bash
cd contracts

# Install deps
npm install

# Compile
npx hardhat compile

# Deploy to testnet (set PRIVATE_KEY env var first)
npx hardhat ignition deploy ./ignition/modules/MemoryVault.ts --network monadTestnet

# Or use Python script
python scripts/deploy.py testnet --private-key YOUR_KEY
```

After deployment, copy the contract address to your `.env`:
```
CONTRACT_ADDRESS=0x...
WALLET_PRIVATE_KEY=0x...
```

### Connect Wallet in Dashboard

1. Open http://localhost:8002
2. Click "Connect Wallet"
3. MetaMask prompts for Monad Testnet (add it if not present)
4. Sign the auth message
5. Dashboard unlocks — source cards, message feed, and Memory Vault panel appear

### Commit a Batch

1. Make sure some messages are classified as important (score >= 6)
2. In the Memory Vault panel, click "Commit Batch"
3. Backend builds Merkle tree, submits to Monad
4. Transaction appears with explorer link
5. Batch is listed in the vault panel

## Dashboard

- **Login**: Connect MetaMask wallet (EIP-4361 sign-in) or password fallback
- **Sources**: Connect Telegram (bot token), Gmail (OAuth), WhatsApp (Chrome extension)
- **Message Feed**: Real-time messages with importance scores, searchable by source/sender
- **Voice Settings**: Choose from 322 edge-tts voices grouped by region and gender
- **Memory Vault**: View on-chain batches, commit new batches, network switcher (testnet/mainnet)
- **Voice Demo**: Test TTS with custom text

## Supported Sources

| Source | Method | Status |
|--------|--------|--------|
| Telegram | Bot API (polling) | ✅ Ready |
| Gmail | OAuth 2.0 | ⚠️ Needs Google Cloud setup |
| WhatsApp | Chrome Extension (DOM) | ⚠️ Extension scaffold done |
| Twitter/X | Jina Reader (public only) | ⚠️ Needs implementation |
| Discord | Bot API | 📋 Planned |
| Slack | App | 📋 Planned |

## Project Structure

```
hackathon/
├── index.html              # Dashboard (wallet auth, vault UI, voice selector)
├── backend/
│   ├── main.py             # FastAPI app
│   ├── config.py           # Settings from .env
│   ├── models.py           # SQLAlchemy models
│   ├── merkle.py           # Merkle tree utilities
│   ├── abi.py              # MemoryVault contract ABI
│   ├── routers/
│   │   ├── auth.py         # Password + wallet auth
│   │   ├── vault.py        # Memory Vault API (commit, list, verify)
│   │   ├── sources.py      # Source connections
│   │   ├── messages.py     # Message CRUD
│   │   └── ...
│   └── watchers/
│       └── telegram_watcher.py
├── contracts/
│   ├── contracts/MemoryVault.sol
│   ├── ignition/modules/MemoryVault.ts
│   ├── scripts/deploy.py
│   └── hardhat.config.js
├── extension/              # Chrome extension
├── android-app/            # Flutter Android app
└── requirements.txt
```

## Roadmap

- **Memory Vault NFT**: Soulbound NFTs for milestones (first grant, 100 verified opportunities, community badges)
- **Discord integration**: Bot API for message monitoring
- **Priority digests**: Scheduled summaries of important missed messages
- **Multi-user**: Team workspaces with shared vaults
- **Monad Mainnet**: Deploy Memory Vault when mainnet launches

## License

MIT — built for Spark Hackathon on Monad Testnet
