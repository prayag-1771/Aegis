"""End-to-end: analyze_image() output must satisfy contracts/counterfeit.schema.json.

Uses the `tiny` backbone on a small rendered set — fast, offline, no weight
downloads. CNN accuracy is NOT asserted here (that's the training report's
job); contract shape, verdict enum and feature wiring are.
"""

import json

import jsonschema
import pytest

from aegis_counterfeit.analyze import analyze_image, validate_payload
from aegis_counterfeit.config import CONTRACT_SCHEMA, SynthConfig, TrainConfig
from aegis_counterfeit.model import train
from aegis_counterfeit.synth import NoteSpec, generate_dataset, render_note


@pytest.fixture(scope="module")
def model(tmp_path_factory):
    data_dir = tmp_path_factory.mktemp("synth")
    generate_dataset(SynthConfig(n_genuine=40, n_fake=40), out_dir=data_dir)
    clf, _ = train(data_dir, TrainConfig(backbone="tiny", epochs=2, batch_size=16))
    return clf


@pytest.fixture(scope="module")
def schema():
    return json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))


def test_payload_matches_contract(model, schema):
    img = render_note(NoteSpec(denomination="500", seed=777))
    payload = analyze_image(img, model,
                            location_hint={"district": "Jamtara", "lat": 23.79, "lon": 86.81})
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["verdict"] in {"fake", "genuine", "uncertain"}
    assert payload["denomination"] in {"100", "200", "500", "2000", "unknown"}
    assert 0.0 <= payload["confidence"] <= 1.0


def test_fake_note_reports_missing_features(model, schema):
    img = render_note(NoteSpec(denomination="500", is_fake=True,
                               missing_features=["security_thread"], seed=778))
    payload = analyze_image(img, model)
    jsonschema.validate(instance=payload, schema=schema)
    # Whatever the CNN says, the feature layer must surface the missing thread
    # unless the note was (wrongly) certified genuine — and a note with a
    # missing thread must never be certified genuine.
    assert payload["verdict"] != "genuine"
    assert "security_thread" in payload["missing_features"]


def test_genuine_verdict_reports_no_missing_features(model):
    img = render_note(NoteSpec(denomination="2000", seed=779))
    payload = analyze_image(img, model)
    if payload["verdict"] == "genuine":
        assert payload["missing_features"] == []


def test_validate_payload_rejects_bad_verdict(model):
    img = render_note(NoteSpec(seed=780))
    payload = analyze_image(img, model)
    payload["verdict"] = "definitely_fake"  # not in the enum
    with pytest.raises(jsonschema.ValidationError):
        validate_payload(payload)
