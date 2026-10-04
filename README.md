# Aegis

Aegis is a research prototype for verifying digital media authenticity. It combines content credentials, perceptual hashing, AI-based manipulation scoring, and on-chain registration into one project.

## Project Components

| Directory | Purpose | Main tools |
| --- | --- | --- |
| `frontend/` | React web interface | React, Vite |
| `contracts/` | On-chain content registry | Solidity, Hardhat, Polygon Amoy |
| `backend/spike_a/` | C2PA and Falcon verification experiments | Python, `c2pa-python`, Falcon |
| `backend/spike_b/` | Web3 integration experiment | Python, Web3.py |
| `backend/spike_c/` | AI verification with image and video inputs | PyTorch, Hugging Face Transformers, OpenCV |
| `backend/third_party/falcon_py/` | Vendored Falcon implementation | Python |
| `ml/` | Machine-learning workspace | Reserved for ML assets and experiments |
| `docs/` | Project documentation | Markdown |

## Requirements

- Python 3.12 or newer
- Node.js and npm
- A Polygon Amoy RPC endpoint for contract deployment
- A funded deployment wallet, if deploying to Amoy
- CUDA-compatible hardware is optional; Spike C falls back to CPU

## Frontend Setup

```bash
cd frontend
npm install
npm run dev
```

Other frontend commands:

```bash
npm run build
npm run lint
npm run preview
```

## Smart Contracts Setup

```bash
cd contracts
npm install
npx hardhat compile
```

The `AegisRegistry` contract emits a `ContentRegistered` event containing:

- Creator address
- IPFS CID
- C2PA hash
- Perceptual hash
- Registration timestamp

Create a `.env` file in `contracts/` before deploying to Polygon Amoy:

```env
AMOY_RPC_URL=https://your-amoy-rpc-endpoint
PRIVATE_KEY=your_deployment_wallet_private_key
```

Never commit `.env` files, private keys, or other secrets.

## Backend Setup

Create or activate the shared virtual environment:

```bash
cd backend
python -m venv .venv
source .venv/bin/activate
```

Install each spike's dependencies from its own directory:

```bash
cd spike_a
pip install -r requirements.txt

cd ../spike_b
pip install -r requirements.txt

cd ../spike_c
pip install -r requirements.txt
```

### Spike C: AI Verification

Spike C uses `google/siglip2-base-patch16-224` through Hugging Face Transformers.

```bash
cd backend/spike_c
python spike_c_siglip2.py
```

The module can:

- Score a PIL image with `calculate_deepfake_score()`
- Extract a frame from an MP4 with `extract_frame_from_video()`
- Use CUDA when available, or CPU otherwise

The first inference run downloads and caches the model locally. The score is a zero-shot research signal, not a production forensic determination.

## Repository Structure

```text
Aegis/
├── backend/
│   ├── spike_a/
│   ├── spike_b/
│   ├── spike_c/
│   └── third_party/falcon_py/
├── contracts/
│   ├── contracts/AegisRegistry.sol
│   └── scripts/deploy.js
├── docs/
├── frontend/
├── ml/
├── package-lock.json
├── pyrightconfig.json
└── README.md
```

## Development Notes

This repository contains experimental spikes rather than a single production service. Interfaces between the frontend, Python verification layers, and blockchain registry may change as the prototype evolves.

Generated directories such as Python virtual environments, Node dependencies, Hardhat artifacts, model caches, and local environment files should not be committed.
