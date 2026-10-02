const hre = require("hardhat");

async function main() {
  console.log("Deploying AegisRegistry to Polygon Amoy...");

  const Registry = await hre.ethers.getContractFactory("AegisRegistry");
  const registry = await Registry.deploy();

  await registry.waitForDeployment();
  const address = await registry.getAddress();

  console.log(`AegisRegistry successfully deployed to: ${address}`);
}

main().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});