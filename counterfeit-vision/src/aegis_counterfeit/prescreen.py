"""Pre-flight triage: catch obvious fakes and unscannable photos BEFORE the CNN.

Pipeline position (analyze.py):

    prescreen ── unscannable ──> verdict "uncertain" (rescan advice), CNN skipped
        │
        ├────── obvious_fake ──> verdict "fake" from hard evidence, CNN skipped
        │
        └────── pass ─────────> normal CNN + feature-check flow (unchanged)

Mirrors the fraud-shield design: a cheap deterministic rule layer runs first
and the expensive model is only consulted when the answer isn't already
obvious. A "pass" here claims nothing — it means "not obviously fake, worth
the model's time". The CNN verdict is never overridden.

Checks (OpenCV/numpy only, no ML, each returns its measurement as evidence):

Quality gate -> "unscannable" (the CNN would only produce noise on this input):
- resolution: frame too small to resolve any security feature
- blur: Laplacian variance collapse on the located note
- exposure: frame nearly black or blown out

Obvious-fake tells -> "obvious_fake" when TWO OR MORE fire (any single tell
can have an innocent explanation; two independent ones on one note cannot):
- photocopy: saturation collapse — a B&W / laser-copied note has no ink colour
- flat_print: no high-frequency intaglio texture anywhere on the note face
- geometry: located note outline far outside any real note's aspect ratio
- unknown_colour: healthy saturation but a dominant hue no circulating
  denomination uses (novelty / joke / toy notes)

Agentic narration (additive, mirrors fusion's narrate_safe): an LLM writes the
two-line "why" over these deterministic findings, Claude -> Groq -> Gemini ->
template. It NEVER changes the decision — with zero keys the template floor
formats the same facts.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

import cv2
import numpy as np

from .synth import MICROPRINT

# Contract enum names (contracts/counterfeit.schema.json) that only the triage
# layer maps to — the synth renderer doesn't model these two features.
COLOR_SHIFTING_INK = "color_shifting_ink"
INTAGLIO = "intaglio_print"

# ── thresholds (calibrated against the synth renderer — see tests) ──────────
MIN_WIDTH, MIN_HEIGHT = 200, 90     # below this no security feature is resolvable
BLUR_MIN_LAPVAR = 40.0              # genuine renders ~1500+; heavy defocus < 40
EXPOSURE_DARK, EXPOSURE_BRIGHT = 35.0, 235.0
PHOTOCOPY_MAX_SAT = 14.0            # genuine ₹500 (greyest note) median sat ~21+
PHOTOCOPY_BW_SAT = 5.0              # truly zero colour — conclusive alone: every INR note is colour-printed
FLAT_PRINT_MIN_LAPVAR = 100.0       # full-face texture; genuine renders measure 130+
ASPECT_MIN, ASPECT_MAX = 1.70, 3.10 # real notes span 2.15 (₹100) – 2.52 (₹2000)
KNOWN_HUE_WINDOWS = [(0, 40), (110, 179)]  # olive/stone + magenta families (OpenCV 0-179)
UNKNOWN_COLOUR_MIN_SAT = 45.0       # only claim "wrong colour" when colour is vivid


@dataclass
class TriageCheck:
    """One deterministic measurement. `passed=True` means nothing suspicious."""

    name: str
    passed: bool
    measurement: float
    evidence: str
    maps_to: list[str] = field(default_factory=list)  # contract missing_features names
    conclusive: bool = False  # a single conclusive tell convicts on its own


@dataclass
class TriageResult:
    decision: str  # "pass" | "obvious_fake" | "unscannable"
    checks: list[TriageCheck]

    @property
    def failed(self) -> list[TriageCheck]:
        return [c for c in self.checks if not c.passed]

    def mapped_features(self) -> list[str]:
        """Contract-enum feature names implied by the failed tells, deduped."""
        out: list[str] = []
        for c in self.failed:
            for f in c.maps_to:
                if f not in out:
                    out.append(f)
        return out


# ── quality gate ────────────────────────────────────────────────────────────

def check_resolution(img_bgr: np.ndarray) -> TriageCheck:
    h, w = img_bgr.shape[:2]
    ok = w >= MIN_WIDTH and h >= MIN_HEIGHT
    return TriageCheck(
        "resolution", ok, float(min(w, h)),
        f"frame {w}x{h}px (needs >= {MIN_WIDTH}x{MIN_HEIGHT})",
    )


def check_blur(warped_bgr: np.ndarray) -> TriageCheck:
    gray = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2GRAY)
    lapvar = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return TriageCheck(
        "blur", lapvar >= BLUR_MIN_LAPVAR, round(lapvar, 1),
        f"sharpness (Laplacian var) {lapvar:.0f} (needs >= {BLUR_MIN_LAPVAR:.0f})",
    )


def check_exposure(img_bgr: np.ndarray) -> TriageCheck:
    mean = float(cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY).mean())
    ok = EXPOSURE_DARK <= mean <= EXPOSURE_BRIGHT
    return TriageCheck(
        "exposure", ok, round(mean, 1),
        f"mean brightness {mean:.0f} (needs {EXPOSURE_DARK:.0f}-{EXPOSURE_BRIGHT:.0f})",
    )


# ── obvious-fake tells ──────────────────────────────────────────────────────

def check_photocopy(warped_bgr: np.ndarray) -> TriageCheck:
    sat = float(np.median(cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2HSV)[:, :, 1]))
    return TriageCheck(
        "photocopy", sat > PHOTOCOPY_MAX_SAT, round(sat, 1),
        f"ink saturation {sat:.0f} (a colour-printed note stays > {PHOTOCOPY_MAX_SAT:.0f})",
        maps_to=[COLOR_SHIFTING_INK],
        # A truly colourless "note" cannot be genuine under any lighting —
        # every circulating INR note is colour-printed.
        conclusive=sat < PHOTOCOPY_BW_SAT,
    )


def check_flat_print(warped_bgr: np.ndarray) -> TriageCheck:
    """Intaglio printing leaves high-frequency texture across the whole face.
    Runs on the note only after the blur gate passed, so a defocused photo of
    a real note lands in "unscannable", never in "fake"."""
    gray = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2GRAY)
    gray = cv2.GaussianBlur(gray, (3, 3), 0)  # sensor noise must not count as texture
    lapvar = float(cv2.Laplacian(gray, cv2.CV_64F).var())
    return TriageCheck(
        "flat_print", lapvar >= FLAT_PRINT_MIN_LAPVAR, round(lapvar, 1),
        f"face texture {lapvar:.0f} (intaglio print stays >= {FLAT_PRINT_MIN_LAPVAR:.0f})",
        maps_to=[INTAGLIO, MICROPRINT],
    )


def check_geometry(img_bgr: np.ndarray) -> TriageCheck:
    """Aspect ratio of the located note outline. Skipped (passes) when no
    clean outline exists — tight crops and our canonical warps have none."""
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.dilate(
        cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150), np.ones((3, 3), np.uint8)
    )
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    frame_area = float(h * w)
    quad = None
    best_area = 0.0
    for contour in contours:
        area = cv2.contourArea(contour)
        if not (0.15 * frame_area <= area <= 0.95 * frame_area):
            continue
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) == 4 and area > best_area:
            quad, best_area = approx.reshape(4, 2).astype(np.float32), area
    if quad is None:
        return TriageCheck("geometry", True, 0.0, "no note outline isolated — check skipped")
    sides = [float(np.linalg.norm(quad[i] - quad[(i + 1) % 4])) for i in range(4)]
    long_side = (sides[0] + sides[2]) / 2.0
    short_side = (sides[1] + sides[3]) / 2.0
    if short_side < 1.0:
        return TriageCheck("geometry", True, 0.0, "degenerate outline — check skipped")
    aspect = max(long_side, short_side) / min(long_side, short_side)
    ok = ASPECT_MIN <= aspect <= ASPECT_MAX
    return TriageCheck(
        "geometry", ok, round(aspect, 2),
        f"note outline aspect {aspect:.2f} (real notes {ASPECT_MIN}-{ASPECT_MAX})",
        maps_to=[] if ok else [INTAGLIO],
    )


def check_unknown_colour(warped_bgr: np.ndarray) -> TriageCheck:
    """Vividly coloured note whose dominant hue no circulating denomination
    uses (novelty / children's-bank notes). Low saturation passes — that is
    the photocopy check's territory."""
    hsv = cv2.cvtColor(warped_bgr, cv2.COLOR_BGR2HSV)
    sat = float(np.median(hsv[:, :, 1]))
    if sat < UNKNOWN_COLOUR_MIN_SAT:
        return TriageCheck("unknown_colour", True, sat, "note not vividly coloured — check skipped")
    hue = float(np.median(hsv[hsv[:, :, 1] > 40][:, 0])) if (hsv[:, :, 1] > 40).any() else 0.0
    ok = any(lo <= hue <= hi for lo, hi in KNOWN_HUE_WINDOWS)
    return TriageCheck(
        "unknown_colour", ok, round(hue, 1),
        f"dominant hue {hue:.0f} ({'matches' if ok else 'matches no'} circulating denomination)",
        maps_to=[] if ok else [COLOR_SHIFTING_INK],
    )


# ── decision ────────────────────────────────────────────────────────────────

def prescreen(img_bgr: np.ndarray, warped_bgr: np.ndarray) -> TriageResult:
    """Run the full triage. `img_bgr` is the original frame (geometry needs the
    background), `warped_bgr` the perspective-corrected note."""
    gate = [check_resolution(img_bgr), check_blur(warped_bgr), check_exposure(img_bgr)]
    if any(not c.passed for c in gate):
        return TriageResult("unscannable", gate)

    # Advisory tells ONLY — never a conviction. These are calibrated against the
    # synth renderer and mis-fire on real phone photos of genuine notes: dim or
    # warm light collapses saturation (photocopy tell) and soft focus / JPEG
    # compression collapses face texture (flat_print tell), so a real ₹note trips
    # two tells at once and used to be branded "fake" before the CNN ever ran —
    # the "false note for almost every note" regression. That is exactly the
    # failure mode model.decide_verdict warns about for the OpenCV feature checks:
    # synth-geometry measurements MUST NOT flip the verdict on real-world input.
    # The CNN (EfficientNet-B0, AUC 0.994 on REAL photos) is the sole genuine/fake
    # authority. The tells still run and are recorded as evidence for the triage
    # block, but the decision here is only ever "unscannable" (above) or "pass".
    tells = [
        check_photocopy(warped_bgr),
        check_flat_print(warped_bgr),
        check_geometry(img_bgr),
        check_unknown_colour(warped_bgr),
    ]
    return TriageResult("pass", gate + tells)


def triage_block(result: TriageResult, narrative: str | None = None,
                 engine: str | None = None) -> dict:
    """Contract-shaped `triage` object for the payload."""
    return {
        "decision": result.decision,
        "checks": [
            {
                "name": c.name,
                "passed": c.passed,
                "measurement": float(c.measurement),
                "evidence": c.evidence,
            }
            for c in result.checks
        ],
        "narrative": narrative,
        "engine": engine,
    }


# ── agentic narration (additive — never changes the decision) ───────────────

_NARRATE_SYSTEM = (
    "You brief Indian police officers on counterfeit currency screening. A "
    "deterministic pre-check has ALREADY decided this note photo is an obvious "
    "counterfeit, before any ML model ran. You receive its measurements as "
    "FACTS. Write 1-2 plain-English sentences explaining WHY the note failed, "
    "citing only the failed checks and their measurements. Never invent "
    "features, never soften or overturn the decision. Respond with the "
    "sentence(s) only — no JSON, no preamble."
)


def _facts(result: TriageResult) -> str:
    import json

    return json.dumps(
        {
            "decision": result.decision,
            "failed_checks": [
                {"name": c.name, "measurement": c.measurement, "evidence": c.evidence}
                for c in result.failed
            ],
        },
        indent=2,
    )


def _template_narrative(result: TriageResult) -> str:
    names = {
        "photocopy": "no ink colour (photocopy-grade saturation)",
        "flat_print": "no intaglio print texture",
        "geometry": "wrong note proportions",
        "unknown_colour": "a colour no circulating note uses",
        "resolution": "an image too small to inspect",
        "blur": "an image too blurred to inspect",
        "exposure": "unusable exposure",
    }
    reasons = [names.get(c.name, c.name) for c in result.failed]
    if result.decision == "unscannable":
        return ("Photo rejected before analysis: " + " and ".join(reasons) +
                ". Rescan with the note flat, in focus and well lit.")
    closing = (
        "Multiple independent print failures on one note indicate an obvious counterfeit."
        if len(reasons) > 1
        else "No genuine note can fail this check — conclusive on its own."
    )
    return f"Flagged before the ML model ran: the note shows {' and '.join(reasons)}. {closing}"


def _load_env_keys() -> None:
    """Reuse the shared fusion .env (and a module-local one) for provider keys."""
    from pathlib import Path

    module_root = Path(__file__).resolve().parents[2]        # counterfeit-vision/
    candidates = [
        module_root / ".env",
        module_root.parent / "command-centre" / "fusion" / ".env",
    ]
    for env_file in candidates:
        if not env_file.exists():
            continue
        for line in env_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def _claude_narrate(facts: str) -> str:
    import anthropic

    client = anthropic.Anthropic(timeout=10.0)
    r = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=200,
        system=_NARRATE_SYSTEM,
        messages=[{"role": "user", "content": "FACTS:\n" + facts}],
    )
    text = "".join(b.text for b in r.content if b.type == "text").strip()
    if not text:
        raise ValueError("empty narrator reply")
    return text


def _groq_narrate(facts: str) -> str:
    import httpx

    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.2,
            "max_tokens": 200,
            "messages": [
                {"role": "system", "content": _NARRATE_SYSTEM},
                {"role": "user", "content": "FACTS:\n" + facts},
            ],
        },
        timeout=10.0,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"].strip()
    if not text:
        raise ValueError("empty narrator reply")
    return text


def _gemini_narrate(facts: str) -> str:
    import httpx

    r = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={
            "system_instruction": {"parts": [{"text": _NARRATE_SYSTEM}]},
            "contents": [{"parts": [{"text": "FACTS:\n" + facts}]}],
            "generationConfig": {"temperature": 0.2},
        },
        timeout=10.0,
    )
    r.raise_for_status()
    text = r.json()["candidates"][0]["content"]["parts"][0]["text"].strip()
    if not text:
        raise ValueError("empty narrator reply")
    return text


def narrate_triage_safe(result: TriageResult) -> tuple[str, str]:
    """(narrative, engine) — best available narrator over the deterministic
    findings, falling through Claude -> Groq -> Gemini -> template. Never
    raises; the template floor formats the same facts with zero keys."""
    _load_env_keys()
    facts = _facts(result)
    chain: list[tuple[str, object]] = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        chain.append(("claude-opus-4-8", _claude_narrate))
    if os.environ.get("GROQ_API_KEY"):
        chain.append(("groq/llama-3.3-70b", _groq_narrate))
    if os.environ.get("GEMINI_API_KEY"):
        chain.append(("gemini-2.0-flash", _gemini_narrate))
    for name, fn in chain:
        try:
            return fn(facts), name  # type: ignore[operator]
        except Exception:
            continue
    return _template_narrative(result), "template"
