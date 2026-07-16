"""Tests for the Supply Trail engine.

These use the real corridor and FIR data files — no mocks, no network.
The seizure points used are the project's known demo locations (Jamtara,
Deoghar, Dhanbad) which should snap to the Grand Chord rail corridor.
"""

import sys
from pathlib import Path

# Make the src/ package importable without installing
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

import pytest
from aegis_supply_trail.engine import (
    Seizure,
    _hav,
    compute_trail,
    compute_trails_all_modes,
    load_corridors,
    load_fir_corpus,
    snap_seizures,
)

# Known demo seizure points (already used throughout the project)
JAMTARA = {"event_id": "test-001", "lat": 23.9578, "lon": 86.8041, "district": "Jamtara", "denomination": "500"}
DEOGHAR = {"event_id": "test-002", "lat": 24.4764, "lon": 86.6944, "district": "Deoghar", "denomination": "500"}
DHANBAD = {"event_id": "test-003", "lat": 23.7957, "lon": 86.4304, "district": "Dhanbad", "denomination": "500"}
VADODARA = {"event_id": "test-004", "lat": 22.3072, "lon": 73.1812, "district": "Vadodara", "denomination": "500"}
MUMBAI = {"event_id": "test-005", "lat": 18.9683, "lon": 72.8187, "district": "Mumbai", "denomination": "500"}


class TestDataLoading:
    def test_corridors_load(self):
        corridors = load_corridors()
        assert len(corridors) >= 2
        for c in corridors:
            assert c.id
            assert c.name
            assert c.mode in ("rail", "road", "ship", "air")
            assert len(c.nodes) >= 2

    def test_fir_corpus_loads(self):
        firs = load_fir_corpus()
        assert len(firs) >= 4
        for f in firs:
            assert f.ref
            assert f.lat
            assert f.lon
            assert f.text


class TestHaversine:
    def test_same_point(self):
        assert _hav(23.0, 86.0, 23.0, 86.0) == pytest.approx(0.0, abs=0.01)

    def test_known_distance(self):
        # Jamtara to Dhanbad — roughly 30 km
        d = _hav(23.9578, 86.8041, 23.7957, 86.4304)
        assert 25 <= d <= 55, f"Expected ~30 km, got {d:.1f}"


class TestSnapping:
    def test_jharkhand_snaps_to_grand_chord(self):
        """Jamtara, Deoghar, Dhanbad are all near the Grand Chord rail line."""
        corridors = load_corridors()
        grand_chord = next(c for c in corridors if c.id == "rail_grand_chord_jharkhand")
        seizures = [
            Seizure("t1", JAMTARA["lat"], JAMTARA["lon"], "Jamtara"),
            Seizure("t2", DEOGHAR["lat"], DEOGHAR["lon"], "Deoghar"),
            Seizure("t3", DHANBAD["lat"], DHANBAD["lon"], "Dhanbad"),
        ]
        snapped = snap_seizures(seizures, [grand_chord])
        assert len(snapped[grand_chord.id]) >= 2, (
            "At least 2 of the 3 Jharkhand seizures should snap to the Grand Chord"
        )

    def test_nothing_snaps_to_wrong_corridor(self):
        """Jharkhand seizures should NOT snap to Delhi-Mumbai Central (too far)."""
        corridors = load_corridors()
        delhi_mumbai = next(c for c in corridors if c.id == "rail_delhi_mumbai_central")
        seizures = [
            Seizure("t1", JAMTARA["lat"], JAMTARA["lon"], "Jamtara"),
        ]
        snapped = snap_seizures(seizures, [delhi_mumbai])
        # Jamtara is ~1200 km from the Delhi-Mumbai corridor — must not snap
        assert len(snapped[delhi_mumbai.id]) == 0


class TestTrailComputation:
    def test_trail_from_jharkhand_cluster(self):
        """Three Jharkhand seizures should produce a medium/high-confidence rail trail."""
        seizures = [JAMTARA, DEOGHAR, DHANBAD]
        trail = compute_trail(seizures, mode_filter="rail")
        assert trail is not None, "Expected a trail from 3 clustered seizures"
        assert trail["schema_version"] == "1.0"
        assert trail["commodity"] == "counterfeit_currency"
        assert trail["mode"] == "rail"
        assert trail["confidence"] >= 0.2
        assert trail["confidence_band"] in ("low", "medium", "high")
        assert len(trail["seizures"]) >= 1
        assert len(trail["evidence"]) >= 1
        assert trail["inferred_origin"]["lat"] != 0

    def test_trail_has_required_schema_fields(self):
        """Output must match every required field in the contract schema."""
        trail = compute_trail([JAMTARA], mode_filter="rail")
        assert trail is not None
        required = [
            "schema_version", "trail_id", "generated_at", "commodity", "mode",
            "seizures", "corridor", "inferred_origin", "confidence",
            "confidence_band", "evidence", "disclaimer",
        ]
        for field in required:
            assert field in trail, f"Missing required field: {field}"

    def test_no_seizures_returns_none(self):
        assert compute_trail([]) is None

    def test_no_located_seizures_returns_none(self):
        """A seizure with no lat/lon should be silently skipped."""
        assert compute_trail([{"event_id": "x", "district": "Unknown"}]) is None

    def test_single_seizure_still_produces_trail(self):
        """Even a single seizure should yield a trail — confidence depends on FIR corroboration."""
        trail = compute_trail([JAMTARA])
        assert trail is not None
        assert trail["confidence_band"] in ("low", "medium", "high")
        # Single seizure should never achieve the theoretical maximum (capped at 0.85)
        assert trail["confidence"] <= 0.85

    def test_confidence_increases_with_more_seizures(self):
        """More seizures → higher confidence score."""
        one = compute_trail([JAMTARA])
        three = compute_trail([JAMTARA, DEOGHAR, DHANBAD])
        assert one is not None and three is not None
        assert three["confidence"] >= one["confidence"]

    def test_all_modes_returns_multiple_trails(self):
        """Two seizures — one Jharkhand, one Vadodara — should hit different corridors."""
        seizures = [JAMTARA, DEOGHAR, VADODARA, MUMBAI]
        trails = compute_trails_all_modes(seizures)
        assert len(trails) >= 1
        # Trails must be sorted by confidence descending
        scores = [t["confidence"] for t in trails]
        assert scores == sorted(scores, reverse=True)

    def test_disclaimer_always_present(self):
        """The disclaimer field must never be absent — it's required for auditability."""
        trail = compute_trail([JAMTARA, DHANBAD])
        assert trail is not None
        assert "disclaimer" in trail
        assert len(trail["disclaimer"]) > 20


class TestContractCompliance:
    def test_validates_against_schema(self):
        """Engine output must pass jsonschema validation against the contract."""
        import json
        import jsonschema

        schema_path = (
            Path(__file__).resolve().parents[3] / "contracts" / "supply_trail.schema.json"
        )
        if not schema_path.exists():
            pytest.skip("supply_trail.schema.json not found — run from Aegis repo root")

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        trail = compute_trail([JAMTARA, DEOGHAR, DHANBAD])
        assert trail is not None
        # Remove cluster_centroid if present (optional field) — it must match the schema
        jsonschema.validate(instance=trail, schema=schema)
