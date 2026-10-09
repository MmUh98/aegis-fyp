const hre = require("hardhat");

async function main() {
  console.log("Deploying AegisRegistryV2 to Polygon Amoy...");

  const Registry = await hre.ethers.getContractFactory("AegisRegistryV2");
  const registry = await Registry.deploy();

  await registry.waitForDeployment();
  const address = await registry.getAddress();

  console.log(`AegisRegistryV2 successfully deployed to: ${address}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});