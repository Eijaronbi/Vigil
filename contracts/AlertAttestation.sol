// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract AlertAttestation {
    address public owner;
    uint256 public totalAttestations;

    struct Attestation {
        bytes32 messageHash;
        string groupName;
        uint256 timestamp;
        uint8 importanceScore;
    }

    event AttestationCreated(uint256 indexed id, bytes32 indexed messageHash, string groupName, uint256 timestamp, uint8 importanceScore);
    mapping(uint256 => Attestation) public attestations;
    mapping(bytes32 => bool) public messageHashSeen;

    error OnlyOwner();
    error MessageAlreadyAttested();

    modifier onlyOwner() { if (msg.sender != owner) revert OnlyOwner(); _; }

    constructor() { owner = msg.sender; }

    function attest(bytes32 _messageHash, string calldata _groupName, uint8 _importanceScore) external onlyOwner returns (uint256) {
        if (messageHashSeen[_messageHash]) revert MessageAlreadyAttested();
        uint256 id = totalAttestations;
        attestations[id] = Attestation(_messageHash, _groupName, block.timestamp, _importanceScore);
        messageHashSeen[_messageHash] = true;
        totalAttestations++;
        emit AttestationCreated(id, _messageHash, _groupName, block.timestamp, _importanceScore);
        return id;
    }

    function getAttestation(uint256 _id) external view returns (Attestation memory) { return attestations[_id]; }
    function verify(bytes32 _messageHash) external view returns (bool) { return messageHashSeen[_messageHash]; }
}
