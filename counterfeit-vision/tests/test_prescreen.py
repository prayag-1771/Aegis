"""Pre-flight triage: obvious fakes and unscannable photos must exit before
the CNN; genuine and subtle-fake renders must pass through untouched.

Fast-path tests pass `model=None` — the strongest possible proof the CNN is
never consulted on those paths (any touch would raise AttributeError)."""

import json

import cv2
import jsonschema
import numpy as np
import pytest
from PIL import Image

from aegis_counterfeit.analyze import analyze_image
from aegis_counterfeit.config import CONTRACT_SCHEMA
from aegis_counterfeit.features import locate_note_ex
from aegis_counterfeit.prescreen import (
    TriageCheck,
    TriageResult,
    narrate_triage_safe,
    prescreen,
)
from aegis_counterfeit.synth import NoteSpec, render_note


@pytest.fixture(scope="module")
def schema():
    return json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))


def to_bgr(pil_img) -> np.ndarray:
    return cv2.cvtColor(np.asarray(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)


def to_pil(bgr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def run_prescreen(bgr: np.ndarray):
    warped, located = locate_note_ex(bgr)
    return prescreen(bgr, warped, located=located)


BASE = to_bgr(render_note(NoteSpec(denomination="500", seed=9)))


# ── genuine and subtle fakes must reach the model ───────────────────────────

@pytest.mark.parametrize("denomination", ["500", "2000"])
@pytest.mark.parametrize("seed", [1, 2, 3, 4])
def test_genuine_renders_pass(denomination, seed):
    bgr = to_bgr(render_note(NoteSpec(denomination=denomination, seed=seed)))
    assert run_prescreen(bgr).decision == "pass"


def test_subtle_fake_is_the_models_job():
    """A missing security thread is invisible to triage by design — the CNN
    and feature checks own that call."""
    bgr = to_bgr(render_note(
        NoteSpec(denomination="500", is_fake=True, missing_features=["security_thread"], seed=5)))
    assert run_prescreen(bgr).decision == "pass"


# ── conviction: strict thresholds only, and never on a single soft tell ─────
# Two levels per tell. The ADVISORY level records evidence; only the strict
# `convicts` level counts toward a verdict. This is the middle ground between
# the build that convicted on the advisory level (and branded genuine
# phone-shot notes counterfeit) and the build that deleted the conviction path
# entirely (leaving the CNN as the only thing able to affect any verdict).

def test_colourless_note_is_conclusive_and_convicts():
    """A note with literally no ink colour cannot be genuine under any lighting
    — every circulating INR note is colour-printed. One conclusive tell is
    enough on its own."""
    gray3 = cv2.cvtColor(cv2.cvtColor(BASE, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    result = run_prescreen(gray3)
    assert result.decision == "obvious_fake"
    photocopy = next(c for c in result.checks if c.name == "photocopy")
    assert not photocopy.passed and photocopy.conclusive and photocopy.convicts


def test_single_non_conclusive_tell_never_convicts():
    """An out-of-gamut (green) note trips `unknown_colour` at the strict level,
    but one non-conclusive tell always has an innocent explanation — a colour
    cast from tungsten or LED light. Recorded as evidence, decision stays
    'pass', and the CNN gets its say."""
    hsv = cv2.cvtColor(BASE, cv2.COLOR_BGR2HSV)
    hsv[:, :, 0] = 60  # green — no circulating denomination
    hsv[:, :, 1] = np.clip(hsv[:, :, 1].astype(int) + 80, 0, 255).astype(np.uint8)
    result = run_prescreen(cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR))
    assert result.decision == "pass"
    assert len(result.convicting) == 1


def test_genuine_rs50_blue_is_not_flagged_wrong_colour():
    """Rs50 is fluorescent blue (OpenCV hue ~96). The old KNOWN_HUE_WINDOWS
    were [(0,40),(110,179)], leaving that blue in the gap, so a genuine Rs50
    read as 'matches no circulating denomination'."""
    hsv = cv2.cvtColor(BASE, cv2.COLOR_BGR2HSV)
    hsv[:, :, 0] = 96
    hsv[:, :, 1] = np.clip(hsv[:, :, 1].astype(int) + 80, 0, 255).astype(np.uint8)
    result = run_prescreen(cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR))
    colour = next(c for c in result.checks if c.name == "unknown_colour")
    assert colour.passed
    assert result.decision == "pass"


def test_unlocated_note_can_never_convict():
    """When no note outline is found the 'note' is a resize of the whole photo,
    so every tell is measuring background. Evidence is still recorded; the
    decision may not use it."""
    gray3 = cv2.cvtColor(cv2.cvtColor(BASE, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    result = prescreen(gray3, locate_note_ex(gray3)[0], located=False)
    assert result.decision == "pass"
    assert any(not c.passed and c.convicts for c in result.checks)


def test_convictions_can_be_disabled(monkeypatch):
    """COUNTERFEIT_TRIAGE_CONVICTS=0 restores advisory-only triage."""
    monkeypatch.setenv("COUNTERFEIT_TRIAGE_CONVICTS", "0")
    gray3 = cv2.cvtColor(cv2.cvtColor(BASE, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    assert run_prescreen(gray3).decision == "pass"


# ── unscannable photos ask for a rescan, not a verdict ──────────────────────

@pytest.mark.parametrize(
    "transform",
    [
        lambda b: cv2.GaussianBlur(b, (31, 31), 8),          # defocus
        lambda b: (b * 0.1).astype(np.uint8),                # nearly black
        lambda b: cv2.resize(b, (120, 52)),                  # too small
    ],
    ids=["blurred", "dark", "tiny"],
)
def test_unscannable_returns_uncertain(schema, transform):
    payload = analyze_image(to_pil(transform(BASE)), model=None)
    jsonschema.validate(instance=payload, schema=schema)
    assert payload["verdict"] == "uncertain"
    assert payload["confidence"] <= 0.5
    assert payload["missing_features"] == []
    assert payload["triage"]["decision"] == "unscannable"


def test_blurred_real_note_is_never_called_fake():
    """Ordering guarantee: defocus lands in the quality gate, so a bad photo
    of a REAL note can never be convicted by the flat-print tell."""
    blurred = cv2.GaussianBlur(BASE, (31, 31), 8)
    assert run_prescreen(blurred).decision == "unscannable"


# ── narration floor ─────────────────────────────────────────────────────────

def test_template_narration_never_fails():
    result = TriageResult(
        decision="obvious_fake",
        checks=[TriageCheck("photocopy", False, 0.0, "ink saturation 0", conclusive=True)],
    )
    narrative, engine = narrate_triage_safe(result)
    assert engine == "template"
    assert "photocopy" in narrative or "ink colour" in narrative
