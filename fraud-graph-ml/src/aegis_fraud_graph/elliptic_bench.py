"""Elliptic++ full-feature benchmark.

The induced-subgraph run (data.py:load_elliptic) proves OUR feature pipeline
transfers to real data. This module answers a different question — "how good
is the classifier on the *published benchmark* features?" — using the official
55 per-wallet behavioural features (computed by the dataset authors on the
FULL 823k-wallet graph, so nothing is lost to subsampling).

Two claims for the deck, each with its dataset:
  - pipeline works end-to-end on real data  -> induced-subgraph run (AUC 0.945)
  - approach is benchmark-competitive       -> this run (official features)
"""

from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
from sklearn.metrics import average_precision_score, precision_score, recall_score, roc_auc_score
from sklearn.model_selection import train_test_split
from xgboost import XGBClassifier

from .config import DATA_DIR, MODELS_DIR, ModelConfig
from .model import _pick_threshold

COMBINED = DATA_DIR / "elliptic_raw" / "wallets_features_classes_combined.csv"
NON_FEATURES = {"address", "class", "Time step"}


def run_benchmark(csv: Path = COMBINED, cfg: ModelConfig | None = None) -> dict:
    cfg = cfg or ModelConfig()

    df = pd.read_csv(csv)
    # Wallets appear once per active time step; keep the latest snapshot per
    # wallet so each account is one instance (no leakage across split).
    df = df.sort_values("Time step").drop_duplicates("address", keep="last")
    df = df[df["class"].isin([1, 2])]  # 1 = illicit, 2 = licit; drop unknown

    y = (df["class"] == 1).astype(int)
    x = df.drop(columns=[c for c in NON_FEATURES if c in df.columns])
    x = x.apply(pd.to_numeric, errors="coerce").fillna(0.0)

    x_tr, x_te, y_tr, y_te = train_test_split(
        x, y, test_size=cfg.test_size, random_state=cfg.seed, stratify=y
    )
    spw = float((y_tr == 0).sum() / max((y_tr == 1).sum(), 1))
    clf = XGBClassifier(
        n_estimators=cfg.n_estimators,
        max_depth=cfg.max_depth,
        learning_rate=cfg.learning_rate,
        scale_pos_weight=spw,
        eval_metric="aucpr",
        random_state=cfg.seed,
        n_jobs=-1,
    )
    clf.fit(x_tr, y_tr)

    prob = clf.predict_proba(x_te)[:, 1]
    thr = _pick_threshold(y_te.to_numpy(), prob)
    pred = (prob >= thr).astype(int)

    importances = sorted(
        zip(x.columns.tolist(), clf.feature_importances_.tolist()),
        key=lambda kv: kv[1],
        reverse=True,
    )
    report = {
        "dataset": "elliptic++ wallets (official 55 features, dedup latest snapshot)",
        "n_wallets": int(len(df)),
        "n_illicit": int(y.sum()),
        "roc_auc": round(float(roc_auc_score(y_te, prob)), 4),
        "avg_precision": round(float(average_precision_score(y_te, prob)), 4),
        "precision_at_threshold": round(float(precision_score(y_te, pred, zero_division=0)), 4),
        "recall_at_threshold": round(float(recall_score(y_te, pred, zero_division=0)), 4),
        "chosen_threshold": round(thr, 4),
        "top_features": {k: round(v, 4) for k, v in importances[:10]},
    }
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    (MODELS_DIR / "elliptic_benchmark_report.json").write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    r = run_benchmark()
    print(json.dumps(r, indent=2))
