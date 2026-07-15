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

## Quick start
```bash
cd fraud-shield-nlp
pip install -e .[dev]          # or: pip install scikit-learn pandas fastapi uvicorn joblib jsonschema requests

python -m aegis_fraud_shield.cli train     # downloads UCI data, trains, saves model + report
python -m aegis_fraud_shield.cli demo      # sanity-check the bundled demo scripts
python -m aegis_fraud_shield.cli analyze "your message here" --source sms

# live demo chat UI + the /analyze endpoint the command centre calls:
uvicorn aegis_fraud_shield.api:app --app-dir src --port 8001
# then open http://127.0.0.1:8001/

python -m pytest -q                        # tests (offline, no download needed)
```

## How it works
1. **Data** ([src/aegis_fraud_shield/data.py](src/aegis_fraud_shield/data.py)) — UCI SMS Spam
   Collection (5.5k real SMS) + a template-generated Indian-scam corpus
   ([corpus.py](src/aegis_fraud_shield/corpus.py)): digital-arrest call scripts, KYC/lottery/
   loan/phishing messages, and *hard legit negatives* (genuine OTPs, real police verification)
   so the model can't cheat on surface words.
2. **Markers** ([markers.py](src/aegis_fraud_shield/markers.py)) — regex rule layer for the 8
   contract markers (authority impersonation, fake FIR, video-call isolation…). Returns matched
   evidence spans → powers the "why flagged" explanation and auditability.
3. **Model** ([model.py](src/aegis_fraud_shield/model.py)) — word + char TF-IDF ⊕ marker
   features → Logistic Regression. Verdict thresholds picked precision-first from the held-out
   PR curve (scam band ≥ 0.97 precision; suspicious band ≥ 0.90).
4. **Contract** ([analyze.py](src/aegis_fraud_shield/analyze.py)) — emits schema-valid
   `scam_detection` JSON with a deterministic evidence-based explanation.
5. **Agentic verification** ([verify/](src/aegis_fraud_shield/verify/)) — *additive, never
   overrides.* For a **flagged** message only, an LLM agent extracts the concrete entities a
   scammer relies on (shortlink, IFSC, UPI, phone) and runs real verification tools, then
   narrates only tool-confirmed evidence into a `verification` block.

**Held-out metrics (seed 42):** ROC-AUC 0.984 · scam-verdict precision 0.971 / recall 0.919 ·
100% recall on synthetic digital-arrest / KYC / lottery / loan / phishing families.

## Agentic verification layer (`verify/`)

The deterministic stack (markers + classifier + playbooks) decides the verdict — that verdict is
authoritative and court-defensible, and the agent **never** writes `verdict`, `risk_score`,
`scam_type`, or `markers`. What the agent adds is hard, external evidence a regex can't produce:

| Tool | What it checks | Key? |
|---|---|---|
| `resolve_url` | Follows a shortlink to its real host; flags typosquats + credential-harvest pages | ❌ (public HTTP; **SSRF-hardened** — http/https only, private/loopback/metadata IPs refused on every redirect hop) |
| `validate_ifsc` | Confirms an IFSC is a real bank + branch (Razorpay's free public API) | ❌ |
| `validate_upi` | Validates a `name@psp` handle against known PSPs | ❌ (offline) |
| `phone_reputation` | Flags spoofed / malformed numbers | ❌ (offline) |
| LLM synthesis | Narrates only tool-confirmed findings + claim cross-check | ✅ `ANTHROPIC_API_KEY` |

**Never dies, never hangs** (mirrors the fusion narrator's `narrate_safe`): live tools → offline
heuristics → deterministic synthesis → `None`. Each tool has a timeout and the whole pass has a
hard wall-clock budget (`VerifyConfig.total_budget_s`); on expiry it returns partial findings.
With **no key** the whole layer still runs and produces findings — you just lose the LLM
write-up. Runtime-flippable via `VerifyConfig.enabled` / the `verify=` arg to `analyze()`.

## Definition of done
- [x] Classifies the sample scripts correctly (`cli demo` + tests)
- [x] Emits valid `scam_detection` JSON (validated in tests and via `shared/validate_contract.py`)
- [x] Chat UI can demo a live scam catch (`/` on the API)
- [ ] Handed off to the command centre with a working endpoint or JSON file (endpoint ready on
      port 8001 — integration pending Pushkar's dashboard)
