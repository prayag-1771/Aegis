"""End-to-end pipeline tests. The contract test is the one that protects
integration week — if it passes, the command centre can consume our output."""

import json

import pytest

from aegis_fraud_graph.config import CONTRACT_SCHEMA, SynthConfig
from aegis_fraud_graph.data import Dataset
from aegis_fraud_graph.graph import FEATURE_COLUMNS, compute_features
from aegis_fraud_graph.model import train
from aegis_fraud_graph.rings import detect_rings
from aegis_fraud_graph.export import build_output
from aegis_fraud_graph.demo import inject_demo_ring
from aegis_fraud_graph.synth import generate


@pytest.fixture(scope="module")
def small_world():
    cfg = SynthConfig(n_legit_accounts=400, n_rings=4, n_background_tx=2500, seed=7)
    result = generate(cfg)
    return Dataset(accounts=result.accounts, transactions=result.transactions, name="test")


@pytest.fixture(scope="module")
def features(small_world):
    return compute_features(small_world)


def test_generator_shapes(small_world):
    assert small_world.accounts["account_id"].is_unique
    assert small_world.accounts["is_illicit"].sum() >= 4 * 4  # >= n_rings * min size
    tx = small_world.transactions
    assert (tx["amount"] > 0).all()
    assert set(tx["source"]).issubset(set(small_world.accounts["account_id"]))


def test_features_complete(features, small_world):
    assert list(features.columns) == FEATURE_COLUMNS
    assert len(features) == len(small_world.accounts)
    assert not features.isna().any().any(), "features must be NaN-free for XGBoost"


def test_model_learns(features, small_world):
    labels = small_world.accounts.set_index("account_id")["is_illicit"]
    _, report = train(features, labels)
    assert report.roc_auc > 0.9, f"model should beat 0.9 AUC on synthetic, got {report.roc_auc}"
    assert report.precision_at_threshold >= 0.8, "precision-first thresholding failed"


def test_end_to_end_contract_compliance(features, small_world):
    """The output JSON must validate against the shared contract schema."""
    from jsonschema import validate

    labels = small_world.accounts.set_index("account_id")["is_illicit"]
    clf, _ = train(features, labels)

    from aegis_fraud_graph.model import score_all

    scores = score_all(clf, features)
    rings, accounts = detect_rings(small_world, scores)
    out = build_output(small_world, rings, accounts, features)

    payload = json.loads(out.model_dump_json())
    schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
    validate(instance=payload, schema=schema)  # raises on violation

    assert payload["schema_version"] == "1.0"
    assert len(payload["rings"]) >= 1
    # every ringed account must reference an existing ring
    ring_ids = {r["ring_id"] for r in payload["rings"]}
    for acc in payload["accounts"]:
        assert acc["ring_id"] in ring_ids


def test_demo_ring_injection_detects_a_fresh_ring(small_world):
    injected = inject_demo_ring(small_world, district="Alwar")
    features = compute_features(injected)
    labels = injected.accounts.set_index("account_id")["is_illicit"]
    clf, _ = train(features, labels)

    from aegis_fraud_graph.model import score_all

    scores = score_all(clf, features)
    rings, accounts = detect_rings(injected, scores)
    payload = json.loads(build_output(injected, rings, accounts, features).model_dump_json())

    assert any(r["district"] == "Alwar" and r["size"] == 6 for r in payload["rings"])
