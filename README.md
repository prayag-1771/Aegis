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

| Module | What it does | AI type | Lead |
|---|---|---|---|
| **Fraud Shield** | Real-time scam / digital-arrest call & message classifier | Supervised NLP | Sudarsan |
| **Counterfeit Vision** | CV model spotting fake notes via missing security features | CNN / CV | Adharshan |
| **Fraud Graph** | Graph ML clustering accounts into fraud rings | Graph ML | Prayag |
| **Command Centre** | Dashboard + crime map + **Gen AI fusion** tying all 3 together | Gen AI / agentic | Pushkar (+ Prayag) |

## 🎯 The three wow moments (all live-demoable)
1. **Scam call** read out loud → system flags it instantly.
2. **Note** held to camera → system flags the missing security feature live.
3. **Fusion moment** → dashboard auto-writes: *"This scam call is linked to a fraud ring active
   in this district, and a counterfeit note was seized nearby."*

## 🚀 Why we win
- **Innovation + Business Impact = 50% of judging** — the fusion layer + geospatial overlap
  hits both.
- **Auditability for legal admissibility** is a named metric — we build court-submittable
  intelligence packages, not just alerts.
- **Low false-positive rate** is a stated requirement — designed in from day 1.
- Matches **4 of 6 suggested tech areas** across our 4-person split — zero wasted effort.

## 🧠 The 3 defensible innovations
1. **The fusion itself** — no product combines scam + counterfeit + fraud graph.
2. **Self-improving classifier** — an LLM generates new scam-script variants to retrain the NLP
   model ahead of real-world scam evolution (before/after accuracy demo).
3. **Cross-domain crime map** — counterfeit seizures + scam origins on one map; overlapping
   clusters signal a coordinated crime hub.

## 📁 Repository layout
```
Aegis/
├── contracts/            # 📜 THE data contract — JSON the modules hand to the command centre
│   ├── *.schema.json     #    one schema per module (lock Day 1–2)
│   └── samples/          #    example payloads everyone codes against
├── fraud-shield-nlp/     # Sudarsan  — NLP scam detection
├── counterfeit-vision/   # Adharshan — CV counterfeit detection
├── fraud-graph-ml/       # Prayag    — Graph ML fraud rings  ⭐
├── command-centre/       # Pushkar + Prayag — dashboard + geospatial + Gen AI fusion
├── shared/               # 🔧 contract validator + shared mock data
├── docs/                 # 📐 architecture diagram, deck, demo script
├── PROJECT_PLAN.md       # 📋 living plan + progress log (read this)
└── README.md
```

## 🔀 How we avoid git conflicts
**Each person owns exactly one module folder and never edits another's.** The three detection
modules don't import each other's code — they only emit JSON matching [`contracts/`](contracts/).
The command centre consumes that JSON. So four people work in parallel with zero overlapping
changes. The **only** shared files are the contract schemas (locked early) and `PROJECT_PLAN.md`.
See [`PROJECT_PLAN.md`](PROJECT_PLAN.md) → *Git workflow* for branch/commit rules.

## ⚙️ Tech stack
- **Fraud Shield (NLP):** Python · scikit-learn / DistilBERT · FastAPI
- **Counterfeit Vision (CV):** PyTorch / TensorFlow · ResNet / EfficientNet · OpenCV
- **Fraud Graph (Graph ML):** NetworkX / PyTorch Geometric · XGBoost
- **Command Centre:** React / Next.js · FastAPI / Node · PostgreSQL · Mapbox · Claude / GPT API
- **Shared:** Docker · GitHub

## 🚦 Getting started (each person)
1. Read this README, then [`PROJECT_PLAN.md`](PROJECT_PLAN.md), then your `person_*/README.md`.
2. Read [`contracts/README.md`](contracts/README.md) — the JSON you produce/consume.
3. Work **only inside your own folder.** Branch per person (see plan).
4. Validate output before hand-off: `python shared/validate_contract.py <kind> <file>`.

---
*Forked from Sudarsan's repo → final merge upstreams to Sudarsan. Fork:
[github.com/prayag-1771/Aegis](https://github.com/prayag-1771/Aegis)*
