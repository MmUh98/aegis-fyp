// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract AegisRegistryV2 {
    struct Record {
        address creator;
        string falconKeyHash;
        string manifestHash;
        string pHash;
        uint256 timestamp;
        bool exists;
    }

    mapping(bytes32 => Record) private recordsByPHash;
    mapping(bytes32 => Record) private recordsByManifestHash;

    event ContentRegistered(
        address indexed creator,
        string falconKeyHash,
        string manifestHash,
        string pHash,
        uint256 timestamp
    );

    function registerContent(
        string calldata falconKeyHash,
        string calldata manifestHash,
        string calldata pHash
    ) external {
        Record memory record = Record({
            creator: msg.sender,
            falconKeyHash: falconKeyHash,
            manifestHash: manifestHash,
            pHash: pHash,
            timestamp: block.timestamp,
            exists: true
        });

        recordsByPHash[keccak256(abi.encodePacked(pHash))] = record;
        recordsByManifestHash[keccak256(abi.encodePacked(manifestHash))] = record;
        emit ContentRegistered(msg.sender, falconKeyHash, manifestHash, pHash, block.timestamp);
    }

    function getRecordByManifestHash(string calldata manifestHash)
        external
        view
        returns (address creator, string memory falconKeyHash, string memory pHash, uint256 timestamp, bool exists)
    {
        Record memory record = recordsByManifestHash[keccak256(abi.encodePacked(manifestHash))];
        return (record.creator, record.falconKeyHash, record.pHash, record.timestamp, record.exists);
    }

    function getRecordByPHash(string calldata pHash)
        external
        view
        returns (address creator, string memory falconKeyHash, string memory manifestHash, uint256 timestamp, bool exists)
    {
        Record memory record = recordsByPHash[keccak256(abi.encodePacked(pHash))];
        return (record.creator, record.falconKeyHash, record.manifestHash, record.timestamp, record.exists);
    }
}
