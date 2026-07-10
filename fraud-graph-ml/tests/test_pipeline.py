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
from aegis_fraud_graph.demo import build_custom_dataset, clean_account_names, inject_demo_ring
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


def test_export_includes_victim_inflow_edges(features, small_world):
    """Victim -> collector payments must reach the command centre so fusion can
    trace a scam's reported_payment into a ring account (the money trail)."""
    from aegis_fraud_graph.model import score_all

    labels = small_world.accounts.set_index("account_id")["is_illicit"]
    clf, _ = train(features, labels)
    scores = score_all(clf, features)
    rings, accounts = detect_rings(small_world, scores)
    payload = json.loads(build_output(small_world, rings, accounts, features).model_dump_json())

    ringed = {a["account_id"] for a in payload["accounts"]}
    inflows = [e for e in payload["edges"] if e["source"] not in ringed and e["target"] in ringed]
    assert inflows, "no victim->ring inflow edges exported"
    assert all(e["timestamp"] for e in inflows), "inflow edges must carry timestamps"


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


def test_demo_ring_with_custom_account_names(small_world):
    """The name-the-criminals moment: typed names must appear in a caught ring."""
    names = ["ravi", "pinky", "quickcash", "mule_raju"]
    injected = inject_demo_ring(small_world, district="Jamtara", account_names=names)
    features = compute_features(injected)
    labels = injected.accounts.set_index("account_id")["is_illicit"]
    clf, _ = train(features, labels)

    from aegis_fraud_graph.model import score_all

    scores = score_all(clf, features)
    rings, _ = detect_rings(injected, scores)
    named = [r for r in rings if set(names) <= set(r.account_ids)]
    assert named, "all custom-named accounts should land in one detected ring"
    assert named[0].district == "Jamtara"


@pytest.fixture(scope="module")
def console_world():
    """Richer training world for console tests — the tiny 4-ring fixture has a
    single cycle example, too little signal to learn the pattern (the
    production model trains on 12 rings and catches hand-built loops live)."""
    cfg = SynthConfig(n_legit_accounts=500, n_rings=9, n_background_tx=3000, seed=11)
    result = generate(cfg)
    return Dataset(accounts=result.accounts, transactions=result.transactions, name="console")


@pytest.fixture(scope="module")
def console_model(console_world):
    """Model trained on the base console world (before any custom accounts)."""
    features = compute_features(console_world)
    labels = console_world.accounts.set_index("account_id")["is_illicit"]
    clf, _ = train(features, labels)
    return clf


def _score_custom(world, clf, transactions, speed):
    """Mirror the /demo/score-custom flow: the model is trained on the base
    world FIRST, then scores accounts it has never seen (training on the
    already-injected dataset would teach it the judge's pattern is legit)."""
    from aegis_fraud_graph.model import score_all

    eval_ds, user_accounts = build_custom_dataset(
        world, transactions, district="Alwar", speed=speed
    )
    features = compute_features(eval_ds)
    scores = score_all(clf, features)
    rings, _ = detect_rings(eval_ds, scores)
    user_set = set(user_accounts)
    hit = next((r for r in rings if len(user_set & set(r.account_ids)) >= 3), None)
    return hit, {a: float(scores.get(a, 0.0)) for a in user_accounts}


def test_console_catches_hand_built_laundering(console_world, console_model):
    """A human-designed fast round-tripping loop must be caught."""
    loop = ["judge_a", "judge_b", "judge_c", "judge_d"]
    txs = []
    for rep in range(3):  # loop the money three times, big round amounts
        for i in range(len(loop)):
            txs.append(
                {"source": loop[i], "target": loop[(i + 1) % len(loop)], "amount": 250_000}
            )
    hit, scores = _score_custom(console_world, console_model, txs, speed="minutes")
    assert hit is not None, f"laundering loop not caught; scores={scores}"
    assert set(loop) <= set(hit.account_ids)


def test_console_ignores_normal_behaviour(console_world, console_model):
    """A couple of ordinary slow payments must NOT form a flagged ring."""
    txs = [
        {"source": "meena", "target": "landlord", "amount": 12_500},
        {"source": "meena", "target": "grocer", "amount": 1_840},
        {"source": "employer", "target": "meena", "amount": 45_000},
    ]
    hit, scores = _score_custom(console_world, console_model, txs, speed="days")
    assert hit is None, f"normal behaviour wrongly ringed; scores={scores}"


def test_build_custom_dataset_validation(small_world):
    with pytest.raises(ValueError):
        build_custom_dataset(small_world, [{"source": "a", "target": "a", "amount": 100}])
    with pytest.raises(ValueError):
        build_custom_dataset(small_world, [{"source": "a", "target": "b", "amount": -5}])
    with pytest.raises(ValueError):
        build_custom_dataset(small_world, [{"source": "a", "target": "b"}])


def test_clean_account_names_rules():
    assert clean_account_names(None) == []
    assert clean_account_names([]) == []
    # trims whitespace; case-insensitive dedupe keeps first spelling, order preserved
    assert clean_account_names(["  ravi ", "PINKY", "pinky", "", "quickcash"]) == [
        "ravi",
        "PINKY",
        "quickcash",
    ]
    # 1-2 usable names is an error (ring needs >= 3 members to be detectable)
    with pytest.raises(ValueError):
        clean_account_names(["only", "two"])
