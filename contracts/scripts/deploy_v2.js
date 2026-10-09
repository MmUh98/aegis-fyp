const { ethers } = require("hardhat");

async function main() {
  const [deployer] = await ethers.getSigners();
  console.log("🚀 Starting deployment with account:", deployer.address);

  const balance = await ethers.provider.getBalance(deployer.address);
  console.log("💰 Current wallet balance:", ethers.formatEther(balance), "POL");

  const factory = await ethers.getContractFactory("AegisRegistryV2");

  const deployTx = await factory.getDeployTransaction();
  const gas = await deployer.estimateGas(deployTx);
  const limit = (gas * 11n) / 10n;

  const fee = await ethers.provider.getFeeData();
  const maxFee = fee.maxFeePerGas ?? fee.gasPrice;
  if (maxFee === null) {
    throw new Error("Provider did not return maxFeePerGas or gasPrice");
  }

  console.log("--------------------------------------------------");
  console.log("⛽ Estimated gas units:", gas.toString());
  console.log("⛽ Gas limit (10% buffer):", limit.toString());
  if (fee.maxFeePerGas) {
    console.log("📊 Max fee per gas:", ethers.formatUnits(fee.maxFeePerGas, "gwei"), "gwei");
  }
  console.log("💵 Worst-case reservation cost:", ethers.formatEther(limit * maxFee), "POL");
  console.log("--------------------------------------------------");

  if (balance < limit * maxFee) {
    console.warn("⚠️ Warning: Balance is lower than the worst-case max reservation.");
  }

  console.log("⏳ Broadcasting transaction to Polygon Amoy...");
  const contract = await factory.deploy({ gasLimit: limit });

  await contract.waitForDeployment();
  const deployedAddress = await contract.getAddress();

  console.log("--------------------------------------------------");
  console.log("✅ AegisRegistryV2 deployed successfully to:", deployedAddress);
  console.log("--------------------------------------------------");
  console.log("Action required: Update your backend environment file with:");
  console.log(`AEGIS_REGISTRY_V2_ADDRESS=${deployedAddress}`);
}

main().catch((error) => {
  console.error("❌ Deployment failed:", error);
  process.exitCode = 1;
});
