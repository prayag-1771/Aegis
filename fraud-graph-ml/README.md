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

## Folder layout (self-contained)
```
data/        # Elliptic++ / Kaggle datasets (gitignored if large)
notebooks/   # graph EDA, feature engineering, model training
src/         # graph builder (NetworkX), feature extraction, XGBoost model, ring clustering,
             # exporter that writes fraud_graph JSON
models/      # saved XGBoost model
tests/       # unit tests + contract validation
```

## Tech
NetworkX / PyTorch Geometric (stretch) · XGBoost · pandas · scikit-learn

## Definition of done
- [ ] Dataset loads and a transaction graph is built
- [ ] Graph features + XGBoost flag illicit accounts with decent precision
- [ ] Accounts clustered into rings with `risk_score`
- [ ] Emits valid `fraud_graph` JSON (accounts + rings + top-N edges)
- [ ] Handed off to the command centre early (Phase 3)

## ⚠️ Note: Prayag also co-owns the command-centre Gen AI fusion layer
See [`../command-centre/README.md`](../command-centre/README.md). Hand this module's output off
early so there's time to focus on the fusion layer.
