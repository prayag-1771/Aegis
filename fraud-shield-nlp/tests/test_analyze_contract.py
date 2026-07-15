"""End-to-end: analyze() output must satisfy contracts/scam_detection.schema.json.

Trains a small model on the synthetic corpus only — no network, runs in seconds.
"""

import json

import jsonschema
import pytest

from aegis_fraud_shield.analyze import analyze, build_explanation
from aegis_fraud_shield.config import CONTRACT_SCHEMA, CorpusConfig, ModelConfig
from aegis_fraud_shield.corpus import generate_corpus
from aegis_fraud_shield.model import train

DIGITAL_ARREST = (
    "This is Inspector Sharma from CBI. An FIR has been registered against your Aadhaar "
    "for money laundering. Stay on this video call and do not disconnect. Transfer the "
    "verification amount in USDT immediately or a warrant will be issued."
)
LEGIT = "Hey, are we still meeting for lunch tomorrow at 1pm? Let me know."


@pytest.fixture(scope="module")
def model():
    frame = generate_corpus(CorpusConfig(variants_per_template=8))
    clf, _report = train(frame, ModelConfig(test_size=0.3))
    return clf


@pytest.fixture(scope="module")
def schema():
    return json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))


def test_scam_payload_matches_contract(model, schema):
    payload = analyze(DIGITAL_ARREST, model, source="call_transcript",
                      phone_number="+91-9900112233",
                      location_hint={"district": "Jamtara", "lat": 23.795, "lon": 86.803})
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["verdict"] == "scam"
    assert payload["scam_type"] == "digital_arrest"
    assert "video_call_isolation" in payload["markers"]


def test_legit_payload_matches_contract(model, schema):
    payload = analyze(LEGIT, model, source="whatsapp")
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["verdict"] == "legit"
    assert payload["scam_type"] == "none"
    assert payload["markers"] == []


def test_legit_explanation_never_lists_markers(model):
    payload = analyze("482913 is your OTP. Do not share this OTP with anyone.", model)
    if payload["verdict"] == "legit":
        assert "The message" not in payload["explanation"]


def test_risk_score_orders_scam_above_legit(model):
    assert model.risk_score(DIGITAL_ARREST) > model.risk_score(LEGIT)


def test_explanation_carries_evidence():
    from aegis_fraud_shield.markers import detect_markers

    hits = detect_markers(DIGITAL_ARREST)
    text = build_explanation("scam", 0.99, hits)
    assert "impersonates an authority" in text
    assert "0.99" in text


# --- agentic verification gating (additive block) --------------------------

FLAGGED_WITH_ENTITIES = (
    "Dear customer your SBI account KYC has expired. Update at https://bit.ly/kyc-upd8 "
    "and confirm IFSC SBIN0001234 or your account will be blocked immediately."
)


@pytest.fixture(autouse=True)
def _offline_verify(monkeypatch):
    """Keep verification hermetic: no key (offline synthesis) and no live net."""
    import httpx

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("aegis_fraud_shield.verify.agent._load_dotenv", lambda: None)
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("x")))


def test_verification_present_for_flagged(model, schema):
    payload = analyze(FLAGGED_WITH_ENTITIES, model, source="sms")
    jsonschema.validate(instance=payload, schema=schema)
    if payload["verdict"] != "legit":
        assert "verification" in payload
        assert payload["verification"]["engine"] == "offline-fallback"
        # verdict/risk untouched by the verification layer
        assert payload["verification"].get("verdict") is None


def test_no_verification_for_legit(model, schema):
    payload = analyze(LEGIT, model, source="whatsapp")
    jsonschema.validate(instance=payload, schema=schema)
    assert "verification" not in payload


def test_verify_flag_off_skips_layer(model):
    payload = analyze(FLAGGED_WITH_ENTITIES, model, source="sms", verify=False)
    assert "verification" not in payload
