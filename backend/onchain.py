import hashlib
from web3 import Web3
from typing import Optional
from backend.config import settings

CONTRACT_ABI = [
    {
        "inputs": [],
        "stateMutability": "nonpayable",
        "type": "constructor",
    },
    {
        "inputs": [],
        "name": "OnlyOwner",
        "type": "error",
    },
    {
        "inputs": [],
        "name": "MessageAlreadyAttested",
        "type": "error",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "internalType": "uint256", "name": "id", "type": "uint256"},
            {"indexed": True, "internalType": "bytes32", "name": "messageHash", "type": "bytes32"},
            {"indexed": False, "internalType": "string", "name": "groupName", "type": "string"},
            {"indexed": False, "internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"indexed": False, "internalType": "uint8", "name": "importanceScore", "type": "uint8"},
        ],
        "name": "AttestationCreated",
        "type": "event",
    },
    {
        "inputs": [
            {"internalType": "bytes32", "name": "_messageHash", "type": "bytes32"},
            {"internalType": "string", "name": "_groupName", "type": "string"},
            {"internalType": "uint8", "name": "_importanceScore", "type": "uint8"},
        ],
        "name": "attest",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "_id", "type": "uint256"}],
        "name": "getAttestation",
        "outputs": [
            {"internalType": "bytes32", "name": "messageHash", "type": "bytes32"},
            {"internalType": "string", "name": "groupName", "type": "string"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "uint8", "name": "importanceScore", "type": "uint8"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "owner",
        "outputs": [{"internalType": "address", "name": "", "type": "address"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "totalAttestations",
        "outputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "", "type": "bytes32"}],
        "name": "messageHashSeen",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "uint256", "name": "", "type": "uint256"}],
        "name": "attestations",
        "outputs": [
            {"internalType": "bytes32", "name": "messageHash", "type": "bytes32"},
            {"internalType": "string", "name": "groupName", "type": "string"},
            {"internalType": "uint256", "name": "timestamp", "type": "uint256"},
            {"internalType": "uint8", "name": "importanceScore", "type": "uint8"},
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"internalType": "bytes32", "name": "_messageHash", "type": "bytes32"}],
        "name": "verify",
        "outputs": [{"internalType": "bool", "name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
]


class OnChainClient:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.monad_rpc_url))
        self.contract = (
            self.w3.eth.contract(
                address=Web3.to_checksum_address(settings.contract_address),
                abi=CONTRACT_ABI,
            )
            if settings.contract_address
            else None
        )
        self.account = (
            self.w3.eth.account.from_key(settings.wallet_private_key)
            if settings.wallet_private_key
            else None
        )

    def is_available(self) -> bool:
        return (
            self.contract is not None
            and self.account is not None
            and self.w3.is_connected()
        )

    def hash_message(self, text: str, group: str, timestamp: int) -> bytes:
        raw = f"{text}|{group}|{timestamp}".encode("utf-8")
        return Web3.keccak(raw)

    def attest_alert(
        self, text: str, group: str, timestamp: int, score: int
    ) -> Optional[str]:
        if not self.is_available():
            return None
        message_hash = self.hash_message(text, group, timestamp)
        tx = self.contract.functions.attest(
            message_hash, group, score
        ).build_transaction({
            "from": self.account.address,
            "nonce": self.w3.eth.get_transaction_count(self.account.address),
            "gas": 200000,
            "gasPrice": self.w3.eth.gas_price,
        })
        signed = self.account.sign_transaction(tx)
        tx_hash = self.w3.eth.send_raw_transaction(signed.raw_transaction)
        receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        return receipt.transactionHash.hex()

    def verify_alert(self, text: str, group: str, timestamp: int) -> Optional[bool]:
        if not self.is_available():
            return None
        message_hash = self.hash_message(text, group, timestamp)
        return self.contract.functions.verify(message_hash).call()


onchain_client = OnChainClient()
