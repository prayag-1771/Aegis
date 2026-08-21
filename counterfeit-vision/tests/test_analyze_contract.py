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
    assert payload["denomination"] in {"10", "20", "50", "100", "200", "500", "2000", "unknown"}
    assert 0.0 <= payload["confidence"] <= 1.0


def test_low_memory_mode_same_verdict_forward_only_heatmap(model, schema, monkeypatch):
    """Low-memory hosts (512MB free tier) swap Grad-CAM (a backward pass that
    ~triples peak memory and OOM-kills the box mid-scan) for Eigen-CAM, a
    forward-only heatmap that fits. The verdict/confidence must be IDENTICAL and
    a heatmap is STILL produced — only its method changes. This is the fix for
    the deployed 'fake to all / 502' regression."""
    img = render_note(NoteSpec(denomination="500", seed=4242))

    monkeypatch.setenv("COUNTERFEIT_LOW_MEMORY", "0")   # Grad-CAM (backward pass)
    full = analyze_image(img, model, save_capture=True)

    monkeypatch.setenv("COUNTERFEIT_LOW_MEMORY", "1")   # Eigen-CAM (forward-only)
    lean = analyze_image(img, model, save_capture=True)

    jsonschema.validate(instance=lean, schema=schema)
    assert lean["verdict"] == full["verdict"]
    assert lean["confidence"] == full["confidence"]
    # A heatmap is produced in BOTH modes — the free tier keeps its 'why' overlay.
    assert lean["heatmap_ref"] is not None
    assert full["heatmap_ref"] is not None
    # ...and the payload SAYS which method produced it. Grad-CAM is
    # class-specific, Eigen-CAM is class-agnostic; they are different
    # explanations and the contract used to call both of them Grad-CAM.
    assert full["analysis"]["heatmap_method"] == "grad_cam"
    assert lean["analysis"]["heatmap_method"] == "eigen_cam"


def test_fake_note_reports_missing_features(model, schema):
    img = render_note(NoteSpec(denomination="500", is_fake=True,
                               missing_features=["security_thread"], seed=778))
    payload = analyze_image(img, model)
    jsonschema.validate(instance=payload, schema=schema)
    # The security thread is STRUCTURAL — printed into the note or not — so a
    # single clean failure blocks certification on its own. The CNN may still
    # decline to convict; it may not certify.
    assert payload["verdict"] != "genuine"
    assert "security_thread" in payload["missing_features"]


def test_feature_evidence_survives_a_genuine_verdict(model):
    """`missing_features` used to be force-emptied whenever the verdict was
    `genuine`, deleting the only hint that anything was off from exactly the
    payloads where it mattered. A genuine now implies certification was not
    blocked, so anything left in the list is an honest soft flag."""
    from aegis_counterfeit.features import SECURITY_THREAD, WATERMARK

    img = render_note(NoteSpec(denomination="2000", seed=779))
    payload = analyze_image(img, model)
    if payload["verdict"] == "genuine":
        assert SECURITY_THREAD not in payload["missing_features"]
        assert WATERMARK not in payload["missing_features"]


def test_unverified_genuine_is_capped_and_says_so(model, schema):
    """With no vision key the semantic channel never runs. The payload must
    say so and cap the confidence: a note nothing read the content of is not
    a fully vetted note. This is the face-swapped-portrait hole — the CNN
    measures print physics and returned ~0.95 'genuine' on a tampered note."""
    img = render_note(NoteSpec(denomination="500", seed=781))
    payload = analyze_image(img, model)
    jsonschema.validate(instance=payload, schema=schema)

    review = payload["vision_review"]
    assert review["available"] is False
    assert review["status"] == "unavailable_no_key"
    if payload["verdict"] == "genuine":
        assert payload["confidence"] <= 0.80
        assert any("semantic" in c for c in payload["caveats"])


def test_wrong_portrait_convicts(model):
    """The semantic layer's whole reason to exist: a note whose portrait is not
    Gandhi is not a genuine Indian banknote, whatever its print quality says."""
    from aegis_counterfeit.vision_agent import apply_vision_review

    payload = {"verdict": "genuine", "confidence": 0.95, "denomination": "500",
               "vision_review": {"engine": "test", "status": "ok", "available": True,
                                 "portrait_is_gandhi": False, "specimen_overprint": None,
                                 "header_correct": True, "printed_denomination": "500"}}
    apply_vision_review(payload)
    assert payload["verdict"] == "fake"
    assert "portrait is not Mahatma Gandhi" in payload["semantic_failures"]


def test_unsure_portrait_never_convicts(model):
    """`null` means 'cannot tell'. Only an explicit false may convict."""
    from aegis_counterfeit.vision_agent import apply_vision_review

    payload = {"verdict": "genuine", "confidence": 0.95, "denomination": "500",
               "vision_review": {"engine": "test", "status": "ok", "available": True,
                                 "portrait_is_gandhi": None, "specimen_overprint": None,
                                 "header_correct": None, "printed_denomination": None}}
    apply_vision_review(payload)
    assert payload["verdict"] == "genuine"


def test_specimen_caps_but_does_not_convict(model):
    """Genuine RBI specimen notes exist — 'not legal tender', not 'counterfeit'."""
    from aegis_counterfeit.vision_agent import apply_vision_review

    payload = {"verdict": "genuine", "confidence": 0.95, "denomination": "500",
               "vision_review": {"engine": "test", "status": "ok", "available": True,
                                 "portrait_is_gandhi": True, "specimen_overprint": True,
                                 "header_correct": True, "printed_denomination": "500"}}
    apply_vision_review(payload)
    assert payload["verdict"] == "uncertain"


def test_semantic_layer_never_acquits(model):
    """No layer may turn a fake into a genuine."""
    from aegis_counterfeit.vision_agent import apply_vision_review

    payload = {"verdict": "fake", "confidence": 0.93, "denomination": "500",
               "vision_review": {"engine": "test", "status": "ok", "available": True,
                                 "portrait_is_gandhi": True, "specimen_overprint": False,
                                 "header_correct": True, "printed_denomination": "500"}}
    apply_vision_review(payload)
    assert payload["verdict"] == "fake"


def test_validate_payload_rejects_bad_verdict(model):
    img = render_note(NoteSpec(seed=780))
    payload = analyze_image(img, model)
    payload["verdict"] = "definitely_fake"  # not in the enum
    with pytest.raises(jsonschema.ValidationError):
        validate_payload(payload)
