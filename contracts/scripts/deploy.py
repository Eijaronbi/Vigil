"""
Deploy MemoryVault contract to Monad.

Usage:
    python scripts/deploy.py testnet          # Deploy to testnet
    python scripts/deploy.py mainnet          # Deploy to mainnet
    python scripts/deploy.py testnet --verify # Deploy + verify

Requires:
    - PRIVATE_KEY environment variable or --private-key flag
    - eth_account, web3 packages
"""

import argparse
import json
import os
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent.parent
CONTRACT_PATH = HERE / "contracts" / "MemoryVault.sol"

CHAINS = {
    "testnet": {
        "rpc": "https://testnet-rpc.monad.xyz",
        "chain_id": 10143,
        "explorer": "https://testnet.monadexplorer.com",
        "explorer_api": "https://api.etherscan.io/v2/api?chainid=10143",
    },
    "mainnet": {
        "rpc": "https://rpc.monad.xyz",
        "chain_id": 143,
        "explorer": "https://monadscan.com",
        "explorer_api": "https://api.etherscan.io/v2/api?chainid=143",
    },
}


def deploy(chain_key: str, private_key: str, verify: bool = False):
    chain = CHAINS[chain_key]
    print(f"Deploying to Monad {chain_key} ({chain['chain_id']})...")

    from eth_account import Account
    from web3 import Web3
    from web3.middleware import SignAndSendRawMiddlewareBuilder

    account = Account.from_key(private_key)
    w3 = Web3(Web3.HTTPProvider(chain["rpc"]))
    w3.middleware_onion.add(SignAndSendRawMiddlewareBuilder.build(account))
    w3.eth.default_account = account.address

    balance = w3.eth.get_balance(account.address)
    print(f"  Deployer: {account.address}")
    print(f"  Balance:  {w3.from_wei(balance, 'ether')} MON")

    if balance == 0:
        raise RuntimeError("Deployer has no MON — use faucet at https://faucet.monad.xyz")

    # Compile with solc (or use cached artifacts)
    import subprocess
    out_dir = HERE / "artifacts"
    out_dir.mkdir(exist_ok=True)
    
    bin_path = out_dir / "MemoryVault.bin"
    abi_path = out_dir / "MemoryVault.abi"
    
    if bin_path.exists() and abi_path.exists():
        print("  Using cached artifacts")
    else:
        result = subprocess.run(
            ["solc", "--evm-version", "prague", "--optimize", "--optimize-runs", "200",
             "--bin", "--abi", "--overwrite", "-o", str(out_dir),
             str(CONTRACT_PATH)],
            capture_output=True, text=True
        )
        if result.returncode != 0:
            raise RuntimeError(f"solc failed:\n{result.stderr}")

    with open(out_dir / "MemoryVault.bin") as f:
        bytecode = f.read().strip()
    with open(out_dir / "MemoryVault.abi") as f:
        abi = json.load(f)

    contract = w3.eth.contract(abi=abi, bytecode=bytecode)
    tx_hash = contract.constructor().transact()
    print(f"  Deploy tx: {tx_hash.hex()}")

    receipt = w3.eth.wait_for_transaction_receipt(tx_hash, timeout=180)
    address = receipt["contractAddress"]
    print(f"  Contract:  {address}")
    print(f"  Explorer:  {chain['explorer']}/address/{address}")
    print(f"  Gas used:  {receipt['gasUsed']}")

    # Save deployment info
    info = {
        "network": chain_key,
        "chain_id": chain["chain_id"],
        "address": address,
        "deployer": account.address,
        "tx_hash": tx_hash.hex(),
        "block_number": receipt["blockNumber"],
        "timestamp": int(time.time()),
    }
    info_path = HERE / f"deploy-{chain_key}.json"
    with open(info_path, "w") as f:
        json.dump(info, f, indent=2)
    print(f"  Saved to {info_path}")

    if verify:
        _verify(address, chain, abi)

    return address


def _verify(address: str, chain: dict, abi: list):
    """Submit source code to explorer for verification."""
    import requests

    source = CONTRACT_PATH.read_text()
    metadata = {
        "apikey": "empty",
        "module": "contract",
        "action": "verifysourcecode",
        "contractaddress": address,
        "sourceCode": source,
        "codeformat": "solidity-single-file",
        "contractname": "MemoryVault",
        "compilerversion": "v0.8.27",
        "optimizationUsed": 1,
        "runs": 200,
        "evmversion": "prague",
        "licenseType": 3,  # MIT
    }
    resp = requests.post(chain["explorer_api"], data=metadata, timeout=30)
    print(f"  Verification: {resp.text}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Deploy MemoryVault to Monad")
    parser.add_argument("network", choices=["testnet", "mainnet"])
    parser.add_argument("--private-key", help="Wallet private key (or PRIVATE_KEY env var)")
    parser.add_argument("--verify", action="store_true", help="Verify on explorer")
    args = parser.parse_args()

    pk = args.private_key or os.environ.get("PRIVATE_KEY")
    if not pk:
        raise SystemExit("ERROR: Provide --private-key or set PRIVATE_KEY env var")

    deploy(args.network, pk, verify=args.verify)
