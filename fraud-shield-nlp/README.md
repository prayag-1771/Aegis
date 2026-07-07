# Fraud Shield — Scam & Digital-Arrest Detection (NLP)

**Lead:** Sudarsan
**AI type:** classic supervised NLP (Gen AI only for the optional explanation stretch)

## Goal
A real-time scam / digital-arrest **call & message classifier**. Given a text (SMS,
WhatsApp, call transcript), decide `scam` / `suspicious` / `legit`, and surface the
digital-arrest markers that triggered it.

## Deliverable / output
Every analysis emits JSON matching
[`../contracts/scam_detection.schema.json`](../contracts/scam_detection.schema.json).
Study [`../contracts/samples/scam_detection.sample.json`](../contracts/samples/scam_detection.sample.json).

## Plan (per PROJECT_PLAN.md)
1. **Baseline first:** TF-IDF + Logistic Regression on SMS Spam Collection + a phishing dataset.
2. Add **digital-arrest markers**: authority impersonation (fake CBI/ED), fake FIR, crypto/
   gift-card pressure, video-call isolation, urgency.
3. Wrap in a **simple chat UI** for the live "watch it catch a scam" demo.
4. **Only if ahead of schedule:** upgrade to DistilBERT. **Stretch:** LLM-generated
   plain-language explanation (`explanation` field).

## Folder layout (self-contained — no other module edits this)
```
data/        # datasets (gitignored if large — see .gitignore)
notebooks/   # exploration & training
src/         # classifier, feature extraction, marker rules, FastAPI endpoint
models/      # saved model artifacts
tests/       # unit tests + contract validation
```

## Tech
Python · scikit-learn / HuggingFace DistilBERT · FastAPI

## Definition of done
- [ ] Classifies the sample scripts correctly
- [ ] Emits valid `scam_detection` JSON (validate against the schema)
- [ ] Chat UI can demo a live scam catch
- [ ] Handed off to the command centre with a working endpoint or JSON file
