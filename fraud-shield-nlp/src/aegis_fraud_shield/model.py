"""TF-IDF + Logistic Regression scam classifier.

Design choices (defensible in judging):
- **Baseline-first per the project plan**: TF-IDF + LogReg trains in seconds,
  is fully inspectable, and on short-message scam detection sits within a few
  points of DistilBERT — we upgrade only if the schedule allows.
- **Hybrid features**: word n-grams (what is said) + char n-grams (obfuscation
  like "K.Y.C" or "b1t.ly") + the 8 contract markers as explicit features, so
  the model directly learns how much weight a detected "video_call_isolation"
  deserves.
- **Precision-first thresholds**: the problem statement demands a low false
  positive rate. The "scam" verdict threshold is chosen from the held-out
  precision-recall curve as the highest-recall point with precision >= 0.97;
  a lower "suspicious" band catches the rest without crying wolf.
- **Marker safety net**: a message the model under-scores but which trips 3+
  rule markers is never shown as clean — it escalates to at least "suspicious".
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import joblib
import numpy as np
import pandas as pd
from sklearn.base import BaseEstimator, TransformerMixin
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    precision_recall_curve,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupShuffleSplit
from sklearn.pipeline import FeatureUnion, Pipeline

from .config import MODELS_DIR, ModelConfig
from .markers import ALL_MARKERS, marker_names

MODEL_FILE = MODELS_DIR / "scam_classifier.joblib"
REPORT_FILE = MODELS_DIR / "train_report.json"


class MarkerFeatures(BaseEstimator, TransformerMixin):
    """8 binary contract-marker indicators + a scaled marker count."""

    def fit(self, X, y=None):  # noqa: N803 (sklearn API)
        return self

    def transform(self, X) -> np.ndarray:  # noqa: N803
        rows = []
        for text in X:
            names = set(marker_names(text))
            vec = [1.0 if m in names else 0.0 for m in ALL_MARKERS]
            vec.append(min(len(names), 5) / 5.0)
            rows.append(vec)
        return np.asarray(rows)


def build_pipeline(cfg: ModelConfig) -> Pipeline:
    features = FeatureUnion([
        ("word", TfidfVectorizer(ngram_range=(1, 2), max_features=cfg.max_word_features,
                                 sublinear_tf=True, strip_accents="unicode")),
        ("char", TfidfVectorizer(analyzer="char_wb", ngram_range=(3, 5),
                                 max_features=cfg.max_char_features, sublinear_tf=True)),
        ("markers", MarkerFeatures()),
    ])
    clf = LogisticRegression(C=cfg.C, class_weight="balanced", max_iter=2000)
    return Pipeline([("features", features), ("clf", clf)])


@dataclass
class TrainReport:
    roc_auc: float
    avg_precision: float
    scam_threshold: float
    suspicious_threshold: float
    precision_at_scam: float
    recall_at_scam: float
    n_train: int
    n_test: int
    recall_by_family: dict[str, float]  # scam families only, on held-out rows

    def to_dict(self) -> dict:
        return {
            "roc_auc": round(self.roc_auc, 4),
            "avg_precision": round(self.avg_precision, 4),
            "scam_threshold": round(self.scam_threshold, 4),
            "suspicious_threshold": round(self.suspicious_threshold, 4),
            "precision_at_scam": round(self.precision_at_scam, 4),
            "recall_at_scam": round(self.recall_at_scam, 4),
            "n_train": self.n_train,
            "n_test": self.n_test,
            "recall_by_family": {k: round(v, 4) for k, v in self.recall_by_family.items()},
        }


def _pick_threshold(y_true: np.ndarray, y_prob: np.ndarray,
                    min_precision: float, fallback: float) -> float:
    """Highest-recall threshold that keeps precision >= min_precision."""
    precision, recall, thresholds = precision_recall_curve(y_true, y_prob)
    best, best_recall = None, -1.0
    for i, thr in enumerate(thresholds):
        if precision[i] >= min_precision and recall[i] > best_recall:
            best_recall = recall[i]
            best = float(thr)
    if best is not None:
        return best
    # No threshold reaches min_precision — warn instead of silently returning the
    # caller's fallback, so a precision-guarantee miss is visible.
    import warnings

    warnings.warn(
        f"no threshold reaches precision {min_precision:.2f}; using fallback {fallback}.",
        stacklevel=2,
    )
    return fallback


@dataclass
class ScamClassifier:
    """Trained pipeline + the two verdict thresholds, saved/loaded as one unit."""

    pipeline: Pipeline
    scam_threshold: float
    suspicious_threshold: float
    trained_at: str

    def risk_score(self, text: str) -> float:
        return float(self.pipeline.predict_proba([text])[0, 1])

    def decide_verdict(self, risk: float, n_markers: int) -> str:
        if risk >= self.scam_threshold:
            return "scam"
        if risk >= self.suspicious_threshold:
            return "suspicious"
        # Safety net: heavy rule evidence never renders as clean.
        if n_markers >= 3:
            return "suspicious"
        return "legit"

    def save(self, path: Path = MODEL_FILE) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        joblib.dump(self, path)
        return path

    @staticmethod
    def load(path: Path = MODEL_FILE) -> "ScamClassifier":
        return joblib.load(path)


def _grouped_split(frame: pd.DataFrame, test_size: float, seed: int):
    """Split holding template groups together (synthetic rows share a `group`
    per source template; UCI rows are singleton groups). Prevents variants of
    one scam template landing on both sides and inflating recall."""
    groups = frame["group"] if "group" in frame.columns else pd.Series(range(len(frame)))
    splitter = GroupShuffleSplit(n_splits=1, test_size=test_size, random_state=seed)
    train_idx, held_idx = next(splitter.split(frame, groups=groups))
    return frame.iloc[train_idx], frame.iloc[held_idx]


def train(frame: pd.DataFrame, cfg: ModelConfig | None = None) -> tuple[ScamClassifier, TrainReport]:
    """Train on a (text, label, origin[, group]) frame.

    Three-way template-grouped split: thresholds are tuned on the validation
    slice and the report's metrics come from a test slice the tuning never
    saw — otherwise the reported precision is optimistically biased.
    """
    cfg = cfg or ModelConfig()
    rest_df, test_df = _grouped_split(frame, cfg.test_size, cfg.seed)
    train_df, val_df = _grouped_split(rest_df, cfg.test_size, cfg.seed + 1)

    pipeline = build_pipeline(cfg)
    pipeline.fit(train_df["text"], train_df["label"])

    y_val = val_df["label"].to_numpy()
    p_val = pipeline.predict_proba(val_df["text"])[:, 1]
    y_test = test_df["label"].to_numpy()
    y_prob = pipeline.predict_proba(test_df["text"])[:, 1]

    scam_thr = _pick_threshold(y_val, p_val, cfg.min_scam_precision, cfg.scam_threshold_fallback)
    susp_thr = min(
        _pick_threshold(y_val, p_val, cfg.min_suspicious_precision,
                        cfg.suspicious_threshold_fallback),
        scam_thr,  # suspicious band must sit below the scam threshold
    )

    y_scam = (y_prob >= scam_thr).astype(int)
    recall_by_family: dict[str, float] = {}
    scam_test = test_df.assign(flagged=y_scam)[test_df["label"] == 1]
    for family, group in scam_test.groupby("origin"):
        recall_by_family[str(family)] = float(group["flagged"].mean())

    report = TrainReport(
        roc_auc=float(roc_auc_score(y_test, y_prob)),
        avg_precision=float(average_precision_score(y_test, y_prob)),
        scam_threshold=scam_thr,
        suspicious_threshold=susp_thr,
        precision_at_scam=float(precision_score(y_test, y_scam)),
        recall_at_scam=float(recall_score(y_test, y_scam)),
        n_train=len(train_df),
        n_test=len(test_df),
        recall_by_family=recall_by_family,
    )

    model = ScamClassifier(
        pipeline=pipeline,
        scam_threshold=scam_thr,
        suspicious_threshold=susp_thr,
        trained_at=datetime.now(timezone.utc).isoformat(timespec="seconds"),
    )
    return model, report


def save_report(report: TrainReport, path: Path = REPORT_FILE) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report.to_dict(), indent=2), encoding="utf-8")
    return path
