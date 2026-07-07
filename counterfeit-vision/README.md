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

## Definition of done
- [ ] Classifies fake vs genuine ₹500 reliably
- [ ] Emits valid `counterfeit` JSON
- [ ] Live laptop-camera demo works
- [ ] Handed off to the command centre with a working endpoint or JSON file
