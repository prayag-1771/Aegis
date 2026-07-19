"""Serial layer: format validation, registry dedup, and the cap-only rule —
serial/vision findings may block a genuine certification, never convict."""

import cv2
import jsonschema
import json
import numpy as np
import pytest
from PIL import Image

from aegis_counterfeit.analyze import analyze_image
from aegis_counterfeit.config import CONTRACT_SCHEMA
from aegis_counterfeit.serials import (
    SerialRegistry,
    cap_verdict_for_serial,
    inspect_serial,
    validate,
)
from aegis_counterfeit.synth import NoteSpec, render_note
from aegis_counterfeit.vision_agent import cap_verdict_for_vision, vision_review_safe


@pytest.fixture(autouse=True)
def _hermetic(monkeypatch, tmp_path):
    """No LLM keys, no shared registry file — every test gets its own store.

    MONGODB_URI is cleared too: with it set, the registry would talk to the real
    Atlas cluster and these dedup assertions would see production sightings (and
    write test serials into it)."""
    for key in ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY", "MONGODB_URI"):
        monkeypatch.delenv(key, raising=False)
    import aegis_counterfeit.prescreen as prescreen_mod
    import aegis_counterfeit.serials as serials_mod

    monkeypatch.setattr(prescreen_mod, "_load_env_keys", lambda: None)
    monkeypatch.setattr(serials_mod, "REGISTRY_FILE", tmp_path / "registry.json")
    # Neutralise the .env loader too — otherwise it would re-populate the
    # MONGODB_URI we just cleared and the suite would talk to the real cluster.
    monkeypatch.setattr(serials_mod, "_load_env", lambda: None)


# ── format validation ───────────────────────────────────────────────────────

@pytest.mark.parametrize(
    ("serial", "expected"),
    [
        ("4CB 738291", "valid"),
        ("4cb-738291", "valid"),          # normalisation: case + separators
        ("4CB 123456", "suspicious"),     # sequential — classic prop serial
        ("2AA 000000", "suspicious"),     # repeated digits — prop, but fancy numbers exist
        ("4IO 738291", "nonsense"),       # RBI never uses I/O in prefixes
        ("HELLO", "nonsense"),
        ("", "nonsense"),
        ("ABC 738291", "nonsense"),       # prefix must start with a digit
    ],
)
def test_validate(serial, expected):
    status, _ = validate(serial)
    assert status == expected


# ── registry dedup ──────────────────────────────────────────────────────────

def test_duplicate_serial_detected(tmp_path):
    reg = SerialRegistry(tmp_path / "reg.json")
    first = inspect_serial("4CB738291", "note_a", "Jamtara", reg)
    assert first["status"] == "valid" and first["prior_sightings"] == []
    second = inspect_serial("4cb 738291", "note_b", "Alwar", reg)  # same serial, normalised
    assert second["status"] == "duplicate"
    assert [p["event_id"] for p in second["prior_sightings"]] == ["note_a"]
    assert "printing run" in second["detail"]


# ── durable registry (MongoDB) — mocked, no network ─────────────────────────

class _FakeCursor:
    def __init__(self, docs):
        self._docs = docs

    def sort(self, key, direction=1):
        return iter(sorted(self._docs, key=lambda d: d.get(key) or ""))


class _FakeCollection:
    """Minimal stand-in for a pymongo collection (find/sort + insert_one)."""

    def __init__(self, fail: bool = False):
        self.docs: list[dict] = []
        self.fail = fail

    def find(self, flt, projection=None):
        if self.fail:
            raise RuntimeError("mongo unreachable")
        return _FakeCursor([d for d in self.docs if d["serial"] == flt["serial"]])

    def insert_one(self, doc):
        if self.fail:
            raise RuntimeError("mongo unreachable")
        self.docs.append(dict(doc))


def test_registry_uses_mongo_when_uri_set(tmp_path, monkeypatch):
    """With a URI, sightings live in Mongo — and the JSON file stays untouched."""
    import aegis_counterfeit.serials as serials_mod

    fake = _FakeCollection()
    monkeypatch.setattr(serials_mod, "_mongo_collection", lambda uri: fake)

    path = tmp_path / "reg.json"
    reg = SerialRegistry(path, mongo_uri="mongodb://stub")
    assert reg.backend == "mongodb"

    first = inspect_serial("4CB738291", "note_a", "Jamtara", reg)
    second = inspect_serial("4cb 738291", "note_b", "Alwar", reg)

    assert first["prior_sightings"] == []
    assert second["status"] == "duplicate"
    assert [p["event_id"] for p in second["prior_sightings"]] == ["note_a"]
    assert len(fake.docs) == 2 and fake.docs[0]["serial"] == "4CB738291"
    assert not path.exists()  # nothing fell through to the file


def test_mongo_failure_falls_back_to_file(tmp_path, monkeypatch):
    """A DB hiccup must never break a scan — dedup still works via the file."""
    import aegis_counterfeit.serials as serials_mod

    monkeypatch.setattr(
        serials_mod, "_mongo_collection", lambda uri: _FakeCollection(fail=True)
    )

    path = tmp_path / "reg.json"
    reg = SerialRegistry(path, mongo_uri="mongodb://stub")
    inspect_serial("4CB738291", "note_a", "Jamtara", reg)
    second = inspect_serial("4CB738291", "note_b", "Alwar", reg)

    assert second["status"] == "duplicate"  # degraded, not broken
    assert path.exists()  # the file took over


def test_backend_is_file_without_uri(tmp_path):
    assert SerialRegistry(tmp_path / "reg.json").backend == "file"


def test_nonsense_serial_never_registered(tmp_path):
    reg = SerialRegistry(tmp_path / "reg.json")
    inspect_serial("HELLO", "note_a", None, reg)
    later = inspect_serial("HELLO", "note_b", None, reg)
    assert later["status"] == "nonsense"  # not "duplicate" — props aren't sightings


# ── cap-only rule ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("status", ["nonsense", "suspicious", "duplicate"])
def test_bad_serial_caps_genuine(status):
    payload = {"verdict": "genuine", "confidence": 0.97, "serial": {"status": status}}
    cap_verdict_for_serial(payload)
    assert payload["verdict"] == "uncertain"


def test_bad_serial_never_acquits_or_convicts():
    fake = {"verdict": "fake", "confidence": 0.95, "serial": {"status": "nonsense"}}
    cap_verdict_for_serial(fake)
    assert fake["verdict"] == "fake" and fake["confidence"] == 0.95
    ok = {"verdict": "genuine", "confidence": 0.97, "serial": {"status": "valid"}}
    cap_verdict_for_serial(ok)
    assert ok["verdict"] == "genuine"


def test_vision_findings_cap_only():
    for finding in (
        {"portrait_is_gandhi": False},
        {"specimen_overprint": True},
        {"header_correct": False},
    ):
        payload = {"verdict": "genuine", "confidence": 0.95,
                   "vision_review": {"engine": "x", **finding}}
        cap_verdict_for_vision(payload)
        assert payload["verdict"] == "uncertain", finding
    fake = {"verdict": "fake", "confidence": 0.95,
            "vision_review": {"engine": "x", "portrait_is_gandhi": False}}
    cap_verdict_for_vision(fake)
    assert fake["verdict"] == "fake"


def test_vision_review_absent_without_keys():
    img = render_note(NoteSpec(denomination="500", seed=3))
    assert vision_review_safe(img) is None


# ── payload integration (fast path — model untouched) ───────────────────────

def test_serial_block_in_contract_payload(tmp_path, monkeypatch):
    import aegis_counterfeit.serials as serials_mod

    reg = SerialRegistry(tmp_path / "reg.json")
    monkeypatch.setattr(serials_mod, "SerialRegistry", lambda *a, **k: reg)

    base = cv2.cvtColor(
        np.asarray(render_note(NoteSpec(denomination="500", seed=9)).convert("RGB")),
        cv2.COLOR_RGB2BGR)
    photocopy = Image.fromarray(cv2.cvtColor(
        cv2.cvtColor(cv2.cvtColor(base, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR),
        cv2.COLOR_BGR2RGB))
    payload = analyze_image(photocopy, model=None, serial_number="4CB 738291",
                            location_hint={"district": "Nuh"})
    schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["serial"]["value"] == "4CB738291"
    assert payload["serial"]["status"] == "valid"
    assert "vision_review" not in payload  # keyless => layer entirely absent
