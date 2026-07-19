import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import desc

from backend.config import settings
from backend.database import SessionLocal
from backend.merkle import get_merkle_root, hash_message
from backend.models import Message
from backend.routers.auth import verify_token

router = APIRouter(prefix="/api/vault", tags=["vault"])


def _get_contract():
    if not settings.contract_address or not settings.wallet_private_key:
        return None
    from eth_account import Account
    from web3 import Web3
    from web3.middleware import SignAndSendRawMiddlewareBuilder
    from backend.abi import MEMORY_VAULT_ABI
    w3 = Web3(Web3.HTTPProvider(settings.monad_rpc_url))
    if not w3.is_connected():
        return None
    account = Account.from_key(settings.wallet_private_key)
    w3.middleware_onion.add(SignAndSendRawMiddlewareBuilder.build(account))
    w3.eth.default_account = account.address
    contract = w3.eth.contract(address=Web3.to_checksum_address(settings.contract_address), abi=MEMORY_VAULT_ABI)
    return w3, contract, account


def _explorer_url(tx_hash: str | None = None) -> str:
    base = settings.monad_explorer_url
    if tx_hash:
        return f"{base}/tx/{tx_hash}"
    return base


class CommitResponse(BaseModel):
    batch_id: int
    tx_hash: str
    merkle_root: str
    message_count: int
    explorer_url: str


class BatchInfo(BaseModel):
    batch_id: int
    merkle_root: str
    timestamp: int
    message_count: int
    metadata_hash: str
    committer: str
    tx_hash: str | None = None
    explorer_url: str | None = None


class VerifyRequest(BaseModel):
    merkle_root: str
    source: str
    sender: str
    text: str
    timestamp: int
    proof: list[str]


class VerifyResponse(BaseModel):
    valid: bool
    message_hash: str


@router.post("/commit")
def commit_batch(token_data: dict = Depends(verify_token)):
    result = _get_contract()
    if not result:
        raise HTTPException(status_code=503, detail="Monad not configured")
    w3, contract, account = result

    db = SessionLocal()
    try:
        messages = (
            db.query(Message)
            .filter(Message.importance_score >= settings.importance_threshold)
            .order_by(desc(Message.timestamp))
            .limit(50)
            .all()
        )
        if not messages:
            raise HTTPException(status_code=400, detail="No important messages to commit")
        leaves = []
        for m in messages:
            ts = int(m.timestamp.timestamp()) if m.timestamp else int(time.time())
            leaves.append(hash_message(m.source or "", m.sender or "", m.text or "", ts))
        root = get_merkle_root(leaves)
        metadata_hash = w3.keccak(text=f"vigil-batch-{int(time.time())}")
        tx_hash = contract.functions.commitBatch(root, len(leaves), metadata_hash).transact()
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
        logs = contract.events.BatchCommitted().process_receipt(receipt)
        batch_id = logs[0]["args"]["batchId"] if logs else 0
        return CommitResponse(
            batch_id=batch_id,
            tx_hash=receipt["transactionHash"].hex(),
            merkle_root=root.hex(),
            message_count=len(leaves),
            explorer_url=_explorer_url(receipt["transactionHash"].hex()),
        )
    finally:
        db.close()


@router.get("/batches")
def list_batches(token_data: dict = Depends(verify_token)):
    result = _get_contract()
    if not result:
        raise HTTPException(status_code=503, detail="Monad not configured")
    w3, contract, account = result
    count = contract.functions.getBatchCount().call()
    batches = []
    for i in range(count):
        b = contract.functions.getBatch(i).call()
        batches.append(BatchInfo(
            batch_id=i,
            merkle_root=b[0].hex(),
            timestamp=b[1],
            message_count=b[2],
            metadata_hash=b[3].hex(),
            committer=b[4],
            explorer_url=f"{_explorer_url()}/address/{settings.contract_address}?batch={i}",
        ))
    network_name = "monad-mainnet" if settings.monad_chain_id == 143 else "monad-testnet"
    return {"batches": batches, "count": count, "network": network_name, "contract_address": settings.contract_address}


@router.get("/batches/{batch_id}")
def get_batch(batch_id: int, token_data: dict = Depends(verify_token)):
    result = _get_contract()
    if not result:
        raise HTTPException(status_code=503, detail="Monad not configured")
    w3, contract, account = result
    try:
        b = contract.functions.getBatch(batch_id).call()
    except Exception:
        raise HTTPException(status_code=404, detail="Batch not found")
    return BatchInfo(
        batch_id=batch_id,
        merkle_root=b[0].hex(),
        timestamp=b[1],
        message_count=b[2],
        metadata_hash=b[3].hex(),
        committer=b[4],
        explorer_url=f"{_explorer_url()}/address/{settings.contract_address}",
    )


@router.post("/verify")
def verify_message(body: VerifyRequest, token_data: dict = Depends(verify_token)):
    result = _get_contract()
    if not result:
        raise HTTPException(status_code=503, detail="Monad not configured")
    w3, contract, account = result
    leaf = hash_message(body.source, body.sender, body.text, body.timestamp)
    proof = [bytes.fromhex(p[2:] if p.startswith("0x") else p) for p in body.proof]
    root_bytes = bytes.fromhex(body.merkle_root[2:] if body.merkle_root.startswith("0x") else body.merkle_root)
    valid = contract.functions.verifyMessage(root_bytes, leaf, proof).call()
    return VerifyResponse(valid=valid, message_hash="0x" + leaf.hex())
