MEMORY_VAULT_ABI = [
    {
        "inputs": [
            {"name": "merkleRoot", "type": "bytes32"},
            {"name": "messageCount", "type": "uint256"},
            {"name": "metadataHash", "type": "bytes32"},
        ],
        "name": "commitBatch",
        "outputs": [{"name": "batchId", "type": "uint256"}],
        "stateMutability": "nonpayable",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "merkleRoot", "type": "bytes32"},
            {"name": "leaf", "type": "bytes32"},
            {"name": "proof", "type": "bytes32[]"},
        ],
        "name": "verifyMessage",
        "outputs": [{"name": "", "type": "bool"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [{"name": "batchId", "type": "uint256"}],
        "name": "getBatch",
        "outputs": [
            {
                "components": [
                    {"name": "merkleRoot", "type": "bytes32"},
                    {"name": "timestamp", "type": "uint256"},
                    {"name": "messageCount", "type": "uint256"},
                    {"name": "metadataHash", "type": "bytes32"},
                    {"name": "committer", "type": "address"},
                ],
                "name": "", "type": "tuple",
            }
        ],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [],
        "name": "getBatchCount",
        "outputs": [{"name": "", "type": "uint256"}],
        "stateMutability": "view",
        "type": "function",
    },
    {
        "inputs": [
            {"name": "source", "type": "string"},
            {"name": "sender", "type": "string"},
            {"name": "text", "type": "string"},
            {"name": "timestamp", "type": "uint256"},
        ],
        "name": "hashMessage",
        "outputs": [{"name": "", "type": "bytes32"}],
        "stateMutability": "pure",
        "type": "function",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "batchId", "type": "uint256"},
            {"indexed": True, "name": "merkleRoot", "type": "bytes32"},
            {"indexed": False, "name": "timestamp", "type": "uint256"},
            {"indexed": False, "name": "messageCount", "type": "uint256"},
            {"indexed": True, "name": "committer", "type": "address"},
        ],
        "name": "BatchCommitted",
        "type": "event",
    },
    {
        "anonymous": False,
        "inputs": [
            {"indexed": True, "name": "batchId", "type": "uint256"},
            {"indexed": True, "name": "leaf", "type": "bytes32"},
            {"indexed": False, "name": "valid", "type": "bool"},
        ],
        "name": "BatchVerified",
        "type": "event",
    },
]
