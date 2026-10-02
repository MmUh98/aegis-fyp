// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

contract AegisRegistry {
    event ContentRegistered(
        address indexed creator,
        string ipfsCID,
        string c2paHash,
        string pHash,
        uint256 timestamp
    );

    function registerContent(
        string calldata cid,
        string calldata _c2paHash,
        string calldata _pHash
    ) external {
        emit ContentRegistered(msg.sender, cid, _c2paHash, _pHash, block.timestamp);
    }
}