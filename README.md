# 🛡️ Aegis AI — Digital Public Safety Intelligence Platform

> **ET AI Hackathon 2026 · Problem Statement #6** — *AI for Digital Public Safety: Defeating
> Counterfeiting, Fraud & Digital Arrest Scams* (Theme: Smart Cities / Public Safety / Digital
> Trust / Geospatial Law Enforcement)

One unified command centre that fuses **three independent AI systems** into a single correlated
intelligence layer — exactly what the problem statement calls *"Agentic AI for multi-source
intelligence fusion."*

## The problem
India logged **1.14M cybercrime complaints in 2023** (up 60% YoY). "Digital arrest" scams
(fraudsters posing as CBI/ED/Customs on video calls) stole **₹1,776 crore in just 9 months of
2024**. Counterfeit ₹500 notes now beat manual bank checks. The core gap: **no intelligence
before mass victimization, and no system connects scam detection + counterfeit detection +
fraud networks together.**

## The solution — 4 modules, 1 command centre

| Module | What it does | AI type | Lead | Status |
|---|---|---|---|---|
| **Fraud Shield** (`:8001`) | Real-time scam / digital-arrest call & message classifier | Supervised NLP | Sudarsan | ✅ **v1 done** — ROC-AUC 0.984, scam-verdict precision 0.97 |
| **Counterfeit Vision** (`:8002`) | CNN + OpenCV spotting fake notes via missing security features | CNN / CV | Adharshan | ✅ **v1 done** — ROC-AUC 0.980, fake-verdict precision 1.0 (synthetic; Kaggle retrain hook ready) |
| **Fraud Graph** (`:8003`) | Graph ML clustering accounts into fraud rings | Graph ML | Prayag | ✅ **v1 done** — AUC 0.998 synth / **0.945 on real Elliptic++**, 12/12 rings |
| **Command Centre** (`:8000` + `:3000`) | Dashboard + crime map + **Gen AI fusion** tying all 3 together | Gen AI / agentic | Pushkar (+ Prayag) | ✅ backend, fusion, geospatial, frontend built — integration wiring in progress |

## 🎯 The three wow moments (all live-demoable)
1. **Scam call** read out loud → flagged instantly, with the digital-arrest markers that triggered it.
2. **Note** held to camera → the *missing security feature* (thread / watermark / microprint) named live.
3. **Fusion moment** → dashboard auto-writes: *"This scam call is linked to a fraud ring active
   in this district, and a counterfeit note was seized nearby."*

## 🚀 Run the whole stack

Each service is self-contained; start any subset (the dashboard degrades gracefully):

```bash
# 1. Fraud Shield (NLP) — train once, then serve       -> http://127.0.0.1:8001
cd fraud-shield-nlp
python -m aegis_fraud_shield.cli train
uvicorn aegis_fraud_shield.api:app --app-dir src --port 8001

# 2. Counterfeit Vision (CV) — generate + train once   -> http://127.0.0.1:8002
cd counterfeit-vision
python -m aegis_counterfeit.cli generate && python -m aegis_counterfeit.cli train
uvicorn aegis_counterfeit.api:app --app-dir src --port 8002

# 3. Fraud Graph (Graph ML)                            -> http://127.0.0.1:8003
cd fraud-graph-ml
fraud-graph serve            # (pip install -e . first; `fraud-graph demo` for CLI run)

# 4. Command-centre backend (aggregator + fusion)      -> http://127.0.0.1:8000
cd command-centre/backend && uvicorn aegis_command.api:app --app-dir src --port 8000

# 5. Dashboard frontend (Next.js + Leaflet crime map)  -> http://localhost:3000
cd command-centre/frontend && npm install && npm run dev
```

Ports 8001/8002 also serve their own **live demo UIs** (chat UI / camera scanner) at `/`.
For the live Gen AI narrator, put `ANTHROPIC_API_KEY=...` in `command-centre/fusion/.env`
(a deterministic template fallback keeps the demo alive without it).

## 🧠 The 3 defensible innovations
1. **The fusion itself** — no product combines scam + counterfeit + fraud graph. The correlation
   engine is deterministic (shared district / ≤30 km / ≤96 h evidence) and **auditable**; the LLM
   only narrates established facts (`audit_trail.inputs_hash` makes packages reproducible).
2. **Self-improving classifier** — an LLM generates new scam-script variants to retrain Fraud
   Shield ahead of real-world scam evolution (before/after accuracy demo).
3. **Cross-domain crime map** — counterfeit seizures + scam origins on one map (DBSCAN hotspots);
   overlapping clusters signal a coordinated crime hub.

## 🏆 Why we win
- **Innovation + Business Impact = 50% of judging** — the fusion layer + geospatial overlap hits both.
- **Auditability for legal admissibility** is a named metric — every verdict carries its evidence:
  marker spans (NLP), per-feature check scores (CV), feature importances (graph), correlation basis (fusion).
- **Low false-positive rate** is a stated requirement — every module thresholds precision-first
  (scam band ≥0.97 precision; a note is never certified genuine while a security check fails;
  fraud threshold picked from the PR curve at 0.94 precision).

## 📁 Repository layout
```
Aegis/
├── contracts/            # 📜 THE data contract — schemas + samples all modules code against
├── fraud-shield-nlp/     # Sudarsan  — marker rules, TF-IDF⊕marker LogReg, chat UI, :8001
├── counterfeit-vision/   # Adharshan — synth renderer, OpenCV feature checks, EfficientNet-B0, :8002
├── fraud-graph-ml/       # Prayag    — 18 graph features, XGBoost, Louvain rings, :8003 ⭐
├── command-centre/
│   ├── backend/          # aggregator API the dashboard talks to, :8000
│   ├── fusion/           # Gen AI layer: deterministic correlator + Claude narrator
│   ├── geospatial/       # DBSCAN hotspot clustering, cross-domain hubs
│   └── frontend/         # Next.js dashboard: signal cards, crime map, fusion reveal, :3000
├── shared/               # 🔧 contract validator (validate before every hand-off!)
├── docs/                 # 📐 architecture diagram, deck, demo script
├── PROJECT_PLAN.md       # 📋 living plan + progress log (read this)
└── README.md
```

## 🔀 How we avoid git conflicts
**Each person owns exactly one module folder.** The detection modules never import each other —
they only emit JSON matching [`contracts/`](contracts/), which the command centre consumes. The
only shared files are the contracts (locked Day 1) and `PROJECT_PLAN.md`. Validate every
hand-off: `python shared/validate_contract.py <scam|counterfeit|graph|fusion> <file>`.

## ⚙️ Tech stack
- **Fraud Shield (NLP):** Python · scikit-learn (TF-IDF ⊕ marker features → LogReg) · FastAPI
- **Counterfeit Vision (CV):** PyTorch · EfficientNet-B0 transfer learning · OpenCV feature checks
- **Fraud Graph (Graph ML):** NetworkX · XGBoost · Louvain communities · Elliptic++ (real-data validated)
- **Command Centre:** Next.js 16 / React 19 · Tailwind · Leaflet · FastAPI · Claude (`claude-opus-4-8`) fusion
- **Shared:** JSON-Schema contracts · pytest (40 tests across modules) · GitHub

## 🚦 Getting started (each person)
1. Read this README, then [`PROJECT_PLAN.md`](PROJECT_PLAN.md) (plan + progress log), then your
   module's `README.md` — each has a Quick start.
2. Read [`contracts/README.md`](contracts/README.md) — the JSON you produce/consume.
3. Work **only inside your own folder**; commit small, push often, pull `main` before starting.
4. Validate output before hand-off: `python shared/validate_contract.py <kind> <file>`.

---
*Repo: [github.com/sudarsan2507-hue/Aegis](https://github.com/sudarsan2507-hue/Aegis) ·
development also flows through the [prayag-1771/Aegis](https://github.com/prayag-1771/Aegis) fork.*
