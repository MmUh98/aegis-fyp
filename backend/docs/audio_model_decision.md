# Audio Model Decision

## Data and evaluation

The local sanity-check set contains 5 real and 5 fake audio clips, producing 25 real/fake score pairs. It is too small for accuracy, calibration, or a 5% false-positive claim.

All clips are mono 44.1 kHz PCM WAV files. The class sample rates and channel counts match, but fake clips have a higher mean RMS loudness (`0.0881` versus `0.0676` for real clips). Loudness/source confounding is therefore a risk.

The videos are approximately 10 seconds long, H.264 with mono AAC audio. The supplied manifest records that the fake video contains AI-generated facial visuals and no speech; the real video is a no-speech control.

## Current baseline

- Model: `Hemgg/Deepfake-audio-detection`
- Architecture: Wav2Vec2 audio-classification fine-tune
- Revision: `0d75271368ef2c7efd14831dc503c431f6aab0eb`
- License: Apache-2.0
- Weights: safetensors
- Empirical fake label index: `0`
- Runtime: 4-second windows with 2-second overlap
- Aggregation: `top_k_mean(k=2)` in production
- Calibration status: `none`

The baseline harness compared 16 kHz lossless PCM with AAC-remuxed audio. Best observed AUC was `0.60` on 25 real/fake pairs. The classes overlap substantially, so the heuristic threshold was not promoted into `audio_meta.json` and no calibration claim is made.

## WavLM/AASIST investigation

Candidate: `eliya/forensics_0.3B_base_deepfake_classifier`

- Revision: `cfd11365b02167214dc3b392378809fef6ca3cfa`
- Architecture: WavLM-large + custom AASIST graph-attention pooling
- Weight format: safetensors available; legacy pickle also present
- License: CC-BY-NC-4.0
- Inference contract: 5-second mono 16 kHz center crop
- Loading: custom PyTorch `model.py`; not a Transformers-native `AutoModelForAudioClassification` checkpoint
- Reported metrics: model-card claims across external benchmarks; these are not results on the Aegis 5+5 set

The candidate was investigated but not adopted. It requires reviewing and maintaining custom architecture code, uses a much larger approximately 0.3B-parameter checkpoint, and has a non-commercial license. Adoption requires an explicit follow-up decision and a dedicated adapter/evaluation path.

`microsoft/wavlm-base-plus` was rejected as a candidate detector because it is a self-supervised base model without a trained spoofing head. AASIST-family custom checkpoints were not adopted without an explicit architecture and license review.

## FE-1 and FE-2 deviation

FE-1 names WavLM/AASIST and 4-second windows. The current deployed baseline now meets the 4-second window requirement but remains a Wav2Vec2 classifier, not WavLM/AASIST. FE-2 is implemented as an optional `diagnosis` field:

- `Authentic`
- `Audio Substitution`
- `AI Visual`
- `Full Deepfake`

`diagnosis` is null whenever either required modality is unknown, uncertain, failed, or disabled. The graded `verdict` remains the source of truth.

## Limitations

- Five real and five fake clips are a sanity check, not a performance evaluation.
- Recording loudness and source may confound the audio result.
- Language, music, noise, compression, and domain shift can change detector behavior.
- Thresholds need confirmation on the GPU/demo machine and on a larger held-out set.
- The audio detector targets synthetic speech only; it cannot detect a real person dubbed over a video, lip-sync mismatch, or face swaps that retain original audio.
- OR fusion increases the chance of false positives when either modality is uncertain.
