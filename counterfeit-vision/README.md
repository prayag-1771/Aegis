# Counterfeit Vision — Fake Currency Detection (Computer Vision)

**Lead:** Adharshan
**AI type:** classical CV classification (not Gen AI)

## Goal
A CNN image classifier that decides **fake vs. genuine** ₹500/₹2000 notes from a photo —
ideally **feature-level** (flag the *missing* security thread / microprint), not just a
whole-note verdict.

## Deliverable / output
Every scan emits JSON matching
[`../contracts/counterfeit.schema.json`](../contracts/counterfeit.schema.json).
Study [`../contracts/samples/counterfeit.sample.json`](../contracts/samples/counterfeit.sample.json).

## Plan (per PROJECT_PLAN.md)
1. **Transfer learning CNN** (ResNet / EfficientNet) on the Kaggle Fake Currency dataset +
   GitHub starter repo.
2. Attempt **feature-level detection** — populate `missing_features` (security thread,
   microprint, watermark…).
3. **Fallback locked early:** if behind, scope to a **single denomination** (₹500). Decide
   early, don't wait.
4. Demo-able on a **laptop camera** (hold note to camera → live verdict).

## Folder layout (self-contained — no other module edits this)
```
data/        # note image datasets (gitignored if large)
notebooks/   # training & augmentation
src/         # model, OpenCV preprocessing, inference, FastAPI endpoint
models/      # saved weights
tests/       # unit tests + contract validation
```

## Tech
PyTorch / TensorFlow · ResNet / EfficientNet · OpenCV

## Quick start
```bash
cd counterfeit-vision
pip install -e .[dev]      # or: pip install torch torchvision opencv-python pillow fastapi uvicorn python-multipart jsonschema

python -m aegis_counterfeit.cli generate   # render the synthetic training set (data/synth)
python -m aegis_counterfeit.cli train      # EfficientNet-B0 transfer learning, saves weights + report
python -m aegis_counterfeit.cli demo       # scan freshly rendered genuine + fake notes
python -m aegis_counterfeit.cli analyze path/to/note.jpg

# live camera demo + the /analyze endpoint the command centre calls:
uvicorn aegis_counterfeit.api:app --app-dir src --port 8002
# then open http://127.0.0.1:8002/

python -m pytest -q                        # tests (offline, tiny backbone)
```

## How it works (two layers fused)
1. **CNN verdict** ([model.py](src/aegis_counterfeit/model.py)) — EfficientNet-B0, ImageNet
   weights, head-only fine-tuning. Mid-probability scans return **`uncertain`** (manual check)
   instead of a coin-flip — and a note is *never* certified genuine while any security check
   fails.
2. **Feature-level checks** ([features.py](src/aegis_counterfeit/features.py)) — OpenCV
   inspections of the *regions where real security features live*: security-thread darkness
   contrast, watermark brightness lift, microprint sharpness (Laplacian). These populate the
   contract's `missing_features` — the "why fake", auditable answer.

## Dataset status (fallback locked early, per plan)
No Kaggle API credentials on the build machine, so v1 trains on a **synthetic note renderer**
([synth.py](src/aegis_counterfeit/synth.py)) that draws ₹500/₹2000 notes with controllable
security features — giving **per-feature ground truth** no public dataset has (feature checks
validated 40/40 genuine clean, 40/40 fakes caught with the right feature named).
[data.py](src/aegis_counterfeit/data.py) keeps the Kaggle hook ready: drop `kaggle.json` in
`~/.kaggle/`, run `download_kaggle()` + `prepare_real_dataset()`, retrain with
`--data data/real` — zero pipeline changes.

## Definition of done
- [x] Classifies fake vs genuine ₹500 reliably (synthetic v1; real-data retrain pending Kaggle creds)
- [x] Emits valid `counterfeit` JSON (validated in tests + `shared/validate_contract.py`)
- [x] Live laptop-camera demo works (`/` on port 8002 — webcam capture + upload)
- [ ] Handed off to the command centre with a working endpoint or JSON file (endpoint ready on
      port 8002 — integration pending dashboard wiring)
