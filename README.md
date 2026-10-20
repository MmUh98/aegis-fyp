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
- `ffmpeg` and `ffprobe` (required for video analysis)
- A Polygon Amoy RPC endpoint for contract deployment
- A funded deployment wallet, if deploying to Amoy
- CUDA-compatible hardware is optional; Spike C falls back to CPU

## Frontend Setup

From the repository root, run the Vite app from the `frontend/` directory:

```bash
cd ~/aegis-fyp/frontend
npm install
npm run dev -- --host 127.0.0.1 --port 5173
```

Open `http://127.0.0.1:5173/`. The dashboard uses the backend at `http://127.0.0.1:8000` by default. To override it, create `frontend/.env` from [frontend/.env.example](frontend/.env.example) and set `VITE_API_URL`.

Other frontend commands:

```bash
npm run build
npm run lint
npm run preview
```

## Smart Contracts Setup

```bash
cd ~/aegis-fyp/contracts
npm install
npx hardhat compile
```

Deploy the optimized V2 registry to Polygon Amoy with:

```bash
npx hardhat run scripts/deploy_v2.js --network amoy
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
cd ~/aegis-fyp/backend
python -m venv .venv
source .venv/bin/activate
```

The production verification API uses the aggregate backend requirements file:

```bash
pip install -r requirements.txt
pip install -r requirements-ai.txt
PYTHONPATH=. uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

The API is available at `http://127.0.0.1:8000/`, with interactive documentation at `http://127.0.0.1:8000/docs`.

Set `AEGIS_REGISTRY_V2_ADDRESS` and `AMOY_RPC_URL` for read-only registry lookups. Set `PRIVATE_KEY` as well to enable `POST /api/v1/register`; the backend wallet signs and broadcasts registration transactions, so a frontend wallet connection is optional.

The API exposes:

- `POST /api/v1/verify` for image and video verification
- `POST /api/v1/register` for JPEG signing and Polygon Amoy anchoring

Verification accepts images up to 15 MB and `.mp4`, `.mov`, and `.webm` videos up to 50 MB and 120 seconds. Video analysis samples visual frames and analyzes extracted speech when an audio track is present. Temporary media and analysis files are cleaned up after processing.

The AI dependencies are separate because PyTorch is large:

```bash
pip install -r requirements-ai.txt
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

### Spike C: Multimodal AI Verification

The production Layer 3 detector loads the fine-tuned `google/siglip2-base-patch16-224` visual model and the verified `Hemgg/Deepfake-audio-detection` speech model at API startup. Missing or mismatched visual weights fail startup; missing or invalid audio metadata disables only the audio modality and is logged.

The required audio label mapping is recorded in `backend/spike_c/models/wav2vec2-audio/audio_meta.json`. The supplied mapping was empirically verified against `real.wav` and `fake.wav`; model weights remain ignored and must be provisioned separately.

The multimodal API accepts images up to 15 MB and videos (`.mp4`, `.mov`, `.webm`) up to 50 MB and 120 seconds. Audio analysis detects synthetic speech only; it does not detect lip-sync or face-swap manipulation.

Install ffmpeg on Ubuntu if it is unavailable:

```bash
sudo apt-get update
sudo apt-get install -y ffmpeg
```

Run the legacy Spike C benchmark with:

```bash
cd backend/spike_c
python spike_c_siglip2.py
```

The module can:

- Score a PIL image with `calculate_deepfake_score()`
- Extract a frame from an MP4 with `extract_frame_from_video()`
- Use CUDA when available, or CPU otherwise

The first inference run downloads and caches the model locally. Detector scores are uncalibrated evidence, not proof of manipulation.

The audio detector identifies synthetic speech such as TTS or voice cloning. It does not detect lip-sync or face-swap manipulation. When both detectors run, a `LIKELY_FAKE` result from either modality flags the file; detector failures never produce `LIKELY_REAL`.

For a deployment smoke test, run the detector memory utility with a local video:

```bash
python scripts/check_vram.py /path/to/video.mp4
```

## Repository Structure

```text
Aegis/
├── backend/
│   ├── app/
│   ├── scripts/
│   ├── tests/
│   ├── spike_a/
│   ├── spike_b/
│   ├── spike_c/
│   └── third_party/falcon_py/
├── contracts/
│   ├── contracts/AegisRegistry.sol
│   ├── contracts/AegisRegistryV2.sol
│   └── scripts/deploy_v2.js
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
