# Moving Aegis to a GPU Laptop

Copy these deployment artifacts:

- `backend/spike_c/models/siglip2_base/vision_finetuned_tensors.pt`
- `backend/spike_c/models/siglip2_base/head.pt`
- `backend/spike_c/models/siglip2_base/aegis_meta.json`
- `backend/spike_c/models/wav2vec2-audio/audio_meta.json`
- `backend/sample_data/` only when rerunning the local evaluation data

The model weight files are intentionally ignored by Git. Install `ffmpeg` and `ffprobe`, then install the backend and AI requirements.

Check the machine before starting the API:

```bash
nvidia-smi
python -c 'import torch; print(torch.cuda.is_available(), torch.version.cuda)'
```

The device selector defaults to `AEGIS_DEVICE=auto`. Use `AEGIS_DEVICE=cpu` for reproducible CPU testing or `AEGIS_DEVICE=cuda` to fail loudly when CUDA is unavailable.

Measure memory with a local video:

```bash
python scripts/check_vram.py /path/to/video.mp4
```

The first model load downloads the pinned Hugging Face models. Re-run the audio evaluation on the GPU machine before changing thresholds:

```bash
python scripts/eval_audio.py \
  --model-id Hemgg/Deepfake-audio-detection \
  --revision 0d75271368ef2c7efd14831dc503c431f6aab0eb \
  --data-dir sample_data/audio --window 4 --hop 2 --out reports
```

Thresholds and label mappings should be confirmed on the demo machine. CPU video analysis is substantially slower than GPU analysis.
