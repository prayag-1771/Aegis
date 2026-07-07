"""Fusion layer tests — correlation correctness + contract compliance."""

import json

import pytest

from aegis_fusion.correlator import correlate
from aegis_fusion.fuse import SAMPLES, fuse, validate_against_contract


@pytest.fixture()
def sample_signals():
    scam = json.loads((SAMPLES / "scam_detection.sample.json").read_text(encoding="utf-8"))
    note = json.loads((SAMPLES / "counterfeit.sample.json").read_text(encoding="utf-8"))
    graph = json.loads((SAMPLES / "fraud_graph.sample.json").read_text(encoding="utf-8"))
    return [scam], [note], graph


def test_samples_correlate_to_critical(sample_signals):
    """The bundled samples are all in Jamtara within 90 minutes — the engine
    must link all three domains and flag a critical coordinated hub."""
    scams, notes, graph = sample_signals
    c = correlate(scams, notes, graph)
    assert c.threat_level == "critical"
    domains = {l.type for l in c.linked_signals}
    assert domains == {"scam", "counterfeit", "fraud_ring"}
    assert "shared_district" in c.correlation_basis
    assert "geospatial_overlap" in c.correlation_basis
    assert "temporal_proximity" in c.correlation_basis


def test_isolated_signals_stay_low():
    """Signals in different districts, far apart in time -> no links."""
    scam = {
        "event_id": "s1", "verdict": "scam", "risk_score": 0.9,
        "timestamp": "2026-07-01T00:00:00Z",
        "location_hint": {"district": "Chennai Central", "lat": 13.08, "lon": 80.27},
    }
    note = {
        "event_id": "n1", "verdict": "fake", "confidence": 0.9,
        "timestamp": "2026-07-30T00:00:00Z",
        "location_hint": {"district": "Mumbai South", "lat": 18.93, "lon": 72.83},
    }
    c = correlate([scam], [note], {"rings": []})
    assert c.linked_signals == []
    assert c.threat_level == "medium"  # signals exist but are unlinked


def test_no_signals_is_low():
    c = correlate([], [], {"rings": []})
    assert c.threat_level == "low"
    assert c.linked_signals == []


def test_legit_signals_never_link():
    """verdict=legit / genuine must be excluded from correlation entirely —
    false positives on citizens are the one unforgivable failure mode."""
    scam = {
        "event_id": "s1", "verdict": "legit", "risk_score": 0.05,
        "timestamp": "2026-07-07T10:00:00Z",
        "location_hint": {"district": "Jamtara", "lat": 23.79, "lon": 86.80},
    }
    note = {
        "event_id": "n1", "verdict": "genuine", "confidence": 0.95,
        "timestamp": "2026-07-07T10:30:00Z",
        "location_hint": {"district": "Jamtara", "lat": 23.79, "lon": 86.80},
    }
    c = correlate([scam], [note], {"rings": [{"ring_id": "r1", "account_ids": [],
                                              "risk_score": 0.9, "district": "Jamtara"}]})
    assert all(l.type != "scam" for l in c.linked_signals)
    assert all(l.type != "counterfeit" for l in c.linked_signals)


def test_fusion_output_matches_contract(sample_signals):
    """End-to-end: fuse() output must validate against the shared schema."""
    scams, notes, graph = sample_signals
    out = fuse(scams, notes, graph)
    payload = json.loads(out.model_dump_json())
    validate_against_contract(payload)  # raises on violation
    assert payload["schema_version"] == "1.0"
    assert payload["audit_trail"]["inputs_hash"]
    assert len(payload["recommended_actions"]) >= 2


def test_audit_hash_is_reproducible(sample_signals):
    """Same inputs -> same inputs_hash. This is the legal-admissibility anchor."""
    scams, notes, graph = sample_signals
    h1 = fuse(scams, notes, graph).audit_trail.inputs_hash
    h2 = fuse(scams, notes, graph).audit_trail.inputs_hash
    assert h1 == h2
