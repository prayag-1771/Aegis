# Fraud Graph — Fraud Network Detection (Graph ML) ⭐

**Lead:** Prayag
**AI type:** discriminative graph ML (not Gen AI) — highest technical ceiling of the four modules

## Goal
Cluster transaction / account data to **flag illicit fraud rings** — the "follow the money"
module. Output a set of rings (clusters of colluding accounts) + per-account risk, rendered
by the command centre as a graph where fraud rings light up red.

## Deliverable / output
Emits JSON matching
[`../contracts/fraud_graph.schema.json`](../contracts/fraud_graph.schema.json).
Study [`../contracts/samples/fraud_graph.sample.json`](../contracts/samples/fraud_graph.sample.json).

## Plan (per PROJECT_PLAN.md)
1. **Data first (Day 1–2):** confirm **Elliptic++** access *immediately*. If blocked, switch
   same-day to **IEEE-CIS Fraud** or **mlg-ulb** (Kaggle). Don't lose days to a dataset stall.
2. **Simple version (default):** graph features (degree/betweenness centrality, clustering
   coefficient, connected components) + **XGBoost / Random Forest** for illicit classification.
3. Cluster flagged accounts into **rings** (connected components / community detection over
   the high-risk subgraph) → emit `rings[]`.
4. **GNN is CUT for the 15-day plan** — graph-features + XGBoost only. (GraphSAGE/GCN only if
   the 20-day timeline is restored *and* the simple version is solid by ~day 10.)

## Quickstart
```bash
cd fraud-graph-ml
uv venv && uv pip install -e ".[dev]"      # one-time setup
.venv/Scripts/fraud-graph demo             # train + detect + contract-validate
.venv/Scripts/fraud-graph serve            # API on :8003 for the command centre
.venv/Scripts/python -m pytest             # test suite
```

API endpoints (port 8003 — convention: NLP=8001, CV=8002, graph=8003):
- `GET /health` — liveness
- `GET /fraud-graph` — latest contract JSON (runs pipeline on first call)
- `POST /detect` — force fresh detection

## Folder layout (self-contained)
```
data/        # generated synthetic data / Elliptic++ drop-in (gitignored)
notebooks/   # graph EDA (optional)
src/aegis_fraud_graph/
  synth.py     # synthetic world: mule chains, smurfing fan-in, cycles + legit
               # merchants/payroll/B2B so amounts alone can't separate fraud
  data.py      # swappable loaders (synthetic | elliptic)
  graph.py     # 18 behavioural features per account (NetworkX + pandas)
  model.py     # XGBoost + precision-first threshold from PR curve
  rings.py     # Louvain communities on high-risk subgraph + topology labels
  export.py    # pydantic models mirroring the contract -> fraud_graph.json
  pipeline.py  # orchestration; validate_against_contract()
  cli.py       # typer CLI (train/detect/demo/serve)
  api.py       # FastAPI service for the command centre
models/      # saved XGBoost model + train_report.json (gitignored)
output/      # fraud_graph.json (gitignored)
tests/       # incl. end-to-end contract-compliance test
```

## Current results (synthetic, seed 42)
- AUC **0.998**, avg precision **0.958**, precision **0.94** @ recall 0.76 (threshold 0.92)
- Ring recovery: **12/12 rings**, 78/83 illicit accounts (94%)
- Topology labels: layering chain / mule collection hub / round-tripping cycle

## Tech
NetworkX / PyTorch Geometric (stretch) · XGBoost · pandas · scikit-learn

## Definition of done
- [x] Dataset loads and a transaction graph is built
- [x] Graph features + XGBoost flag illicit accounts with decent precision
- [x] Accounts clustered into rings with `risk_score`
- [x] Emits valid `fraud_graph` JSON (accounts + rings + top-N edges)
- [x] FastAPI endpoint ready for the command centre (`fraud-graph serve`)
- [ ] Handed off to the command centre (Phase 3) — endpoint ready, integration pending
- [ ] (Optional) Re-validated on real Elliptic++ data once dataset access is sorted

## ⚠️ Note: Prayag also co-owns the command-centre Gen AI fusion layer
See [`../command-centre/README.md`](../command-centre/README.md). Hand this module's output off
early so there's time to focus on the fusion layer.
