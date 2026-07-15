// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;
import "forge-std/Script.sol";
import "../AlertAttestation.sol";

contract DeployScript is Script {
    function run() external {
        uint256 deployerPrivateKey = vm.envUint("MONAD_PRIVATE_KEY");
        vm.startBroadcast(deployerPrivateKey);
        new AlertAttestation();
        vm.stopBroadcast();
    }
}
