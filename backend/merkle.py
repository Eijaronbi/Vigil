import hashlib
from typing import Any


def hash_message(source: str, sender: str, text: str, timestamp: int) -> bytes:
    data = f"{source}|{sender}|{text}|{timestamp}".encode()
    return hashlib.sha256(data).digest()


def hash_pair(a: bytes, b: bytes) -> bytes:
    return hashlib.sha256(a + b).digest() if a < b else hashlib.sha256(b + a).digest()


def build_merkle_tree(leaves: list[bytes]) -> list[list[bytes]]:
    if not leaves:
        return []
    tree = [leaves]
    while len(tree[-1]) > 1:
        level = tree[-1]
        next_level = []
        for i in range(0, len(level), 2):
            if i + 1 < len(level):
                next_level.append(hash_pair(level[i], level[i + 1]))
            else:
                next_level.append(level[i])
        tree.append(next_level)
    return tree


def get_merkle_root(leaves: list[bytes]) -> bytes:
    tree = build_merkle_tree(leaves)
    return tree[-1][0] if tree else b""


def get_merkle_proof(tree: list[list[bytes]], leaf_index: int) -> list[bytes]:
    proof = []
    idx = leaf_index
    for level in tree[:-1]:
        sibling_idx = idx ^ 1
        if sibling_idx < len(level):
            proof.append(level[sibling_idx])
        idx //= 2
    return proof
