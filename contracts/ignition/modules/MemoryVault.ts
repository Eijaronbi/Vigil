import { buildModule } from "@nomicfoundation/hardhat-ignition/modules";

const MemoryVaultModule = buildModule("MemoryVault", (m) => {
  const vault = m.contract("MemoryVault");
  return { vault };
});

export default MemoryVaultModule;
