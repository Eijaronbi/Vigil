import json
import time
from pathlib import Path
from typing import Optional

from web3 import Web3
from web3.middleware import SignAndSendRawMiddlewareBuilder

from backend.abi import MEMORY_VAULT_ABI
from backend.config import settings
from backend.merkle import get_merkle_root, hash_message


class OnChainClient:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.monad_rpc_url))
        self.contract = (
            self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.contract_address),
                abi=MEMORY_VAULT_ABI,
            )
            if settings.contract_address
            else None
        )
        self.account = (
            self.w3.eth.account.from_key(settings.wallet_private_key)
            if settings.wallet_private_key
            else None
        )
        if self.account:
            self.w3.middleware_onion.add(SignAndSendRawMiddlewareBuilder.build(self.account))
            self.w3.eth.default_account = self.account.address

    def is_available(self) -> bool:
        return (
            self.contract is not None
            and self.account is not None
            and self.w3.is_connected()
        )

    def commit_batch(
        self, messages: list[dict]
    ) -> Optional[dict]:
        if not self.is_available() or not messages:
            return None

        leaves = []
        for m in messages:
            h = hash_message(
                m.get("source", ""),
                m.get("sender", ""),
                m.get("text", ""),
                int(m.get("timestamp", 0)),
            )
            leaves.append(h)

        merkle_root = get_merkle_root(leaves)
        message_count = len(messages)
        metadata_hash = Web3.keccak(
            json.dumps(
                [{"source": m["source"], "sender": m["sender"], "text": m["text"][:200]}
                 for m in messages],
                sort_keys=True,
            ).encode()
        )

        try:
            tx_hash = self.contract.functions.commitBatch(
                merkle_root, message_count, metadata_hash
            ).transact({"from": self.account.address})
            receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=120)
            if receipt["status"] == 1:
                return {
                    "tx_hash": receipt.transactionHash.hex(),
                    "block_number": receipt["blockNumber"],
                    "merkle_root": merkle_root.hex(),
                    "message_count": message_count,
                    "batch_id": None,
                }
        except Exception as e:
            print(f"commit_batch failed: {e}")
        return None

    def get_batch_count(self) -> int:
        if not self.is_available():
            return 0
        return self.contract.functions.getBatchCount().call()

    def get_batch(self, batch_id: int) -> Optional[dict]:
        if not self.is_available():
            return None
        try:
            b = self.contract.functions.getBatch(batch_id).call()
            return {
                "merkle_root": b[0].hex(),
                "timestamp": b[1],
                "message_count": b[2],
                "metadata_hash": b[3].hex(),
                "committer": b[4],
            }
        except Exception:
            return None


onchain_client = OnChainClient()
