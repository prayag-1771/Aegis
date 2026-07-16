"""Plate-family linkage tests — defect-signature matching must be exact and honest."""

from aegis_command.intel import plate_families


def _note(eid, denom, defects, district, lat, lon, ts, verdict="fake"):
    return {
        "event_id": eid,
        "denomination": denom,
        "verdict": verdict,
        "missing_features": defects,
        "timestamp": ts,
        "location_hint": {"district": district, "lat": lat, "lon": lon},
    }


def test_identical_signature_is_high_tier():
    fams = plate_families([
        _note("n1", "500", ["security_thread", "microprint"], "Jamtara", 23.96, 86.80, "2026-07-07T10:00:00Z"),
        _note("n2", "500", ["security_thread", "microprint"], "Dhanbad", 23.79, 86.43, "2026-07-09T10:00:00Z"),
    ])
    assert len(fams) == 1
    assert fams[0]["tier"] == "high"
    assert fams[0]["shared_defects"] == ["microprint", "security_thread"]
    assert fams[0]["districts"] == ["Dhanbad", "Jamtara"]
    assert fams[0]["span_km"] > 30  # genuinely spans districts


def test_one_shared_defect_is_possible_tier():
    fams = plate_families([
        _note("n1", "500", ["security_thread", "microprint"], "Jamtara", 23.96, 86.80, "2026-07-07T10:00:00Z"),
        _note("n2", "500", ["security_thread", "latent_image"], "Dhanbad", 23.79, 86.43, "2026-07-09T10:00:00Z"),
    ])
    assert len(fams) == 1
    assert fams[0]["tier"] == "possible"
    assert fams[0]["shared_defects"] == ["security_thread"]


def test_no_shared_defects_no_family():
    fams = plate_families([
        _note("n1", "500", ["security_thread"], "Jamtara", 23.96, 86.80, "2026-07-07T10:00:00Z"),
        _note("n2", "500", ["color_shifting_ink"], "Deoghar", 24.48, 86.69, "2026-07-11T10:00:00Z"),
    ])
    assert fams == []


def test_different_denominations_never_link():
    """A ₹500 plate cannot print a ₹2000 note — denominations are separate."""
    fams = plate_families([
        _note("n1", "500", ["security_thread"], "Jamtara", 23.96, 86.80, "2026-07-07T10:00:00Z"),
        _note("n2", "2000", ["security_thread"], "Dhanbad", 23.79, 86.43, "2026-07-09T10:00:00Z"),
    ])
    assert fams == []


def test_genuine_notes_excluded():
    fams = plate_families([
        _note("n1", "500", ["security_thread"], "Jamtara", 23.96, 86.80, "2026-07-07T10:00:00Z"),
        _note("n2", "500", ["security_thread"], "Dhanbad", 23.79, 86.43, "2026-07-09T10:00:00Z", verdict="genuine"),
    ])
    assert fams == []


def test_events_ordered_by_time_and_links_reported():
    fams = plate_families([
        _note("n2", "500", ["security_thread", "microprint"], "Dhanbad", 23.79, 86.43, "2026-07-09T10:00:00Z"),
        _note("n1", "500", ["security_thread", "microprint"], "Jamtara", 23.96, 86.80, "2026-07-07T10:00:00Z"),
    ])
    ev = fams[0]["events"]
    assert [e["event_id"] for e in ev] == ["n1", "n2"]  # chronological
    assert fams[0]["links"][0]["tier"] == "high"
