"""End-to-end orchestration: data -> features -> model -> rings -> contract JSON."""

from __future__ import annotations

import json
from pathlib import Path

from .config import OUTPUT_DIR, ModelConfig, RingConfig
from .data import Dataset, load
from .export import FraudGraphOut, build_output
from .graph import compute_features
from .model import TrainReport, load_model, save_model, score_all, train


def run_training(source: str = "synthetic") -> TrainReport:
    """Train the classifier from scratch and persist it."""
    ds = load(source)
    features = compute_features(ds)
    labels = ds.accounts.set_index("account_id")["is_illicit"]
    clf, report = train(features, labels, ModelConfig())
    save_model(clf, report)
    return report


def run_detection(
    source: str = "synthetic",
    out_path: Path | None = None,
    ds: Dataset | None = None,
) -> FraudGraphOut:
    """Score all accounts with the persisted model and emit contract JSON."""
    from .rings import detect_rings

    ds = ds or load(source)
    features = compute_features(ds)
    clf = load_model()
    scores = score_all(clf, features)
    rings, accounts = detect_rings(ds, scores, RingConfig())
    output = build_output(ds, rings, accounts, features)

    out_path = out_path or (OUTPUT_DIR / "fraud_graph.json")
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(output.model_dump_json(indent=2), encoding="utf-8")
    return output


def run_all(source: str = "synthetic") -> tuple[TrainReport, FraudGraphOut]:
    """Full demo pipeline: train + detect + export."""
    report = run_training(source)
    output = run_detection(source)
    return report, output


def validate_against_contract(payload: dict | None = None) -> None:
    """Assert the emitted JSON matches the shared contract schema."""
    from jsonschema import validate

    from .config import CONTRACT_SCHEMA, OUTPUT_DIR

    schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
    if payload is None:
        payload = json.loads((OUTPUT_DIR / "fraud_graph.json").read_text(encoding="utf-8"))
    validate(instance=payload, schema=schema)
