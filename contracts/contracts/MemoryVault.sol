// SPDX-License-Identifier: MIT
pragma solidity ^0.8.27;

contract MemoryVault {
    struct Batch {
        bytes32 merkleRoot;
        uint256 timestamp;
        uint256 messageCount;
        bytes32 metadataHash;
        address committer;
    }

    Batch[] public batches;
    mapping(bytes32 => bool) public committedRoots;

    event BatchCommitted(
        uint256 indexed batchId,
        bytes32 indexed merkleRoot,
        uint256 timestamp,
        uint256 messageCount,
        address indexed committer
    );

    event BatchVerified(
        uint256 indexed batchId,
        bytes32 indexed leaf,
        bool valid
    );

    function commitBatch(
        bytes32 merkleRoot,
        uint256 messageCount,
        bytes32 metadataHash
    ) external returns (uint256 batchId) {
        require(merkleRoot != bytes32(0), "empty root");
        require(!committedRoots[merkleRoot], "duplicate root");
        require(messageCount > 0, "no messages");

        batchId = batches.length;
        batches.push(Batch({
            merkleRoot: merkleRoot,
            timestamp: block.timestamp,
            messageCount: messageCount,
            metadataHash: metadataHash,
            committer: msg.sender
        }));
        committedRoots[merkleRoot] = true;

        emit BatchCommitted(batchId, merkleRoot, block.timestamp, messageCount, msg.sender);
    }

    function verifyMessage(
        bytes32 merkleRoot,
        bytes32 leaf,
        bytes32[] calldata proof
    ) external view returns (bool) {
        require(committedRoots[merkleRoot], "root not found");
        bytes32 computedHash = leaf;
        for (uint256 i = 0; i < proof.length; i++) {
            computedHash = _hashPair(computedHash, proof[i]);
        }
        return computedHash == merkleRoot;
    }

    function getBatch(uint256 batchId) external view returns (Batch memory) {
        require(batchId < batches.length, "invalid batch");
        return batches[batchId];
    }

    function getBatchCount() external view returns (uint256) {
        return batches.length;
    }

    function hashMessage(
        string calldata source,
        string calldata sender,
        string calldata text,
        uint256 timestamp
    ) external pure returns (bytes32) {
        return keccak256(abi.encodePacked(source, sender, text, timestamp));
    }

    function _hashPair(bytes32 a, bytes32 b) private pure returns (bytes32) {
        return a < b ? keccak256(abi.encodePacked(a, b)) : keccak256(abi.encodePacked(b, a));
    }
}
