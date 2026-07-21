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
from aegis_counterfeit.features import locate_note
from aegis_counterfeit.prescreen import (
    narrate_triage_safe,
    prescreen,
    TriageResult,
    TriageCheck,
)
from aegis_counterfeit.synth import NoteSpec, render_note


@pytest.fixture(autouse=True)
def _no_llm_keys(monkeypatch):
    """Keep narration hermetic: template floor only, no network."""
    for key in ("ANTHROPIC_API_KEY", "GROQ_API_KEY", "GEMINI_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    import aegis_counterfeit.prescreen as prescreen_mod

    monkeypatch.setattr(prescreen_mod, "_load_env_keys", lambda: None)


@pytest.fixture(scope="module")
def schema():
    return json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))


def to_bgr(pil_img) -> np.ndarray:
    return cv2.cvtColor(np.asarray(pil_img.convert("RGB")), cv2.COLOR_RGB2BGR)


def to_pil(bgr: np.ndarray) -> Image.Image:
    return Image.fromarray(cv2.cvtColor(bgr, cv2.COLOR_BGR2RGB))


def run_prescreen(bgr: np.ndarray):
    return prescreen(bgr, locate_note(bgr))


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


# ── triage NEVER convicts — only the CNN owns the genuine/fake call ──────────
# These synth-collapsed inputs trip the tells, but the tells are calibrated on
# the renderer and mis-fire on real photos, so a "fake" verdict here would brand
# genuine phone-shot notes as counterfeit (the reported regression). Triage now
# only gates unscannable photos; every scannable note goes to the CNN authority.

def test_photocopy_does_not_convict():
    """A colour-collapsed (grayscale) note trips the photocopy/flat-print tells,
    but triage must NOT convict — the CNN decides. The evidence is still recorded
    on the checks for the triage block; the decision stays 'pass'."""
    gray3 = cv2.cvtColor(cv2.cvtColor(BASE, cv2.COLOR_BGR2GRAY), cv2.COLOR_GRAY2BGR)
    result = run_prescreen(gray3)
    assert result.decision == "pass"
    assert any(c.name == "photocopy" and not c.passed for c in result.checks)


def test_novelty_colour_does_not_convict():
    """An out-of-gamut (green) note is the CNN's call too — triage never brands
    it fake on colour alone."""
    hsv = cv2.cvtColor(BASE, cv2.COLOR_BGR2HSV)
    hsv[:, :, 0] = 60  # green — no circulating denomination
    hsv[:, :, 1] = np.clip(hsv[:, :, 1].astype(int) + 80, 0, 255).astype(np.uint8)
    result = run_prescreen(cv2.cvtColor(hsv, cv2.COLOR_HSV2BGR))
    assert result.decision == "pass"


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
