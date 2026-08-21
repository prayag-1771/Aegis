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

## How it works (who is allowed to say what)

Every layer has an explicit authority, and the payload records which ones actually ran.
**Nothing acquits** — no layer can turn a `fake` into a `genuine`.

0. **Pre-flight triage** ([prescreen.py](src/aegis_counterfeit/prescreen.py)) — deterministic
   OpenCV checks run *before* the CNN: a quality gate (blur / resolution / exposure →
   `uncertain` + rescan advice) and four obvious-fake tells (photocopy saturation collapse,
   flat print, impossible geometry, unknown colour). Each tell reports at **two levels**: an
   *advisory* threshold that records evidence, and a much stricter *convicts* threshold a
   genuine note cannot reach under any lighting. Only the strict level counts toward a
   verdict, and only on a **located** note. One conclusive tell, or two strict ones, convict
   as `fake` without consulting the model; an agentic narrator (Claude → Groq → Gemini →
   template) writes the "why" over the measurements into the payload's `triage` block.
   `COUNTERFEIT_TRIAGE_CONVICTS=0` restores advisory-only triage.
1. **CNN verdict** ([model.py](src/aegis_counterfeit/model.py)) — EfficientNet-B0, ImageNet
   weights, head-only fine-tuning. Owns the print-physics fake/genuine call. Mid-probability
   scans return **`uncertain`** (manual check) instead of a coin flip; `MIN_UNCERTAIN_BAND`
   guarantees that review band is at least 0.20 wide, enforced at load so shipped weights
   get it without a retrain.
2. **Feature-level checks** ([features.py](src/aegis_counterfeit/features.py)) — OpenCV
   inspections of the *regions where real security features live*: security-thread darkness
   contrast, watermark brightness lift, microprint sharpness (Laplacian). They may **block a
   certification** (`genuine` → `uncertain`) but never convict. Thread and watermark are
   structural, so one clean failure is enough; microprint is a sharpness measure, so it needs
   a second. These populate the contract's `missing_features` — reported on every verdict,
   including `genuine`, rather than hidden.
3. **Semantic review** ([vision_agent.py](src/aegis_counterfeit/vision_agent.py), key-gated) —
   the **only layer that reads what is printed on the note** rather than measuring its print
   physics. Portrait-is-Gandhi, header text, printed denomination, SPECIMEN overprint, serial.
   A wrong portrait or header **convicts**: a note whose portrait is not Gandhi is not a
   genuine Indian banknote, and that is a fact about content, not a fragile surface
   measurement. SPECIMEN or a denomination mismatch caps to `uncertain` (genuine RBI specimen
   notes exist). Set `ANTHROPIC_API_KEY`, `GEMINI_API_KEY` or `GROQ_API_KEY` in
   `counterfeit-vision/.env` — the chain tries them in that order.
   Groq serves multimodal Qwen (`qwen/qwen3.6-27b`, override with
   `COUNTERFEIT_GROQ_VISION_MODEL`); note its free tier meters **tokens per minute**,
   so that leg sends a 512px image and runs with `reasoning_effort: none` — without
   that the model spends its whole completion budget inside `<think>` and never emits
   an answer. A quota refusal degrades to `status: unavailable_rate_limited`, which
   caps confidence rather than convicting.
   **Without a key the layer reports itself unavailable** and any `genuine` is capped to 0.80
   confidence with a `caveats` entry — a note nothing read the content of is not fully vetted.
4. **Serial layer** ([serials.py](src/aegis_counterfeit/serials.py)) — RBI-format validation
   (nonsense/prop patterns flagged) and a sighting registry: the same serial on two scans
   means a printing run. Uses the typed-in serial, falling back to the one the semantic layer
   read off the note. Caps a certification; never convicts.

### Trust boundaries the payload makes explicit
`analysis.note_located` — false means no note outline was found and the whole frame was
resized instead, so every fixed-geometry measurement was reading background; none of them
were allowed to affect the verdict, and the denomination is reported `unknown`.
`analysis.feature_checks_applied` — whether the feature checks were trusted enough to count.
`analysis.heatmap_method` — `grad_cam` (class-specific, "what drove FAKE") or `eigen_cam`
(class-agnostic, "where the model looked", substituted on low-memory hosts). Different
explanations, so the payload names which one produced `heatmap_ref`.

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
