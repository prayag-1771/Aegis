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

Obvious-fake tells -> "obvious_fake" when a CONCLUSIVE tell fires, or when TWO
OR MORE tells fire at their conviction threshold:
- photocopy: saturation collapse — a B&W / laser-copied note has no ink colour
- flat_print: no high-frequency intaglio texture anywhere on the note face
- geometry: located note outline far outside any real note's aspect ratio
- unknown_colour: healthy saturation but a dominant hue no circulating
  denomination uses (novelty / joke / toy notes)

**Two thresholds per tell, and why.** An earlier build convicted on the single
advisory threshold and branded real phone-shot notes counterfeit — warm indoor
light collapses saturation, JPEG compression collapses face texture, and one
genuine note trips two tells at once. The fix then was to delete the conviction
path entirely: `prescreen` returned only "pass" or "unscannable", which left the
CNN as the sole authority over every verdict and let anything with real print
physics through, however tampered. Neither extreme is right.

So each tell now reports at TWO levels: an `advisory` threshold that records
evidence in the triage block, and a much stricter `convicts` threshold that a
genuine note cannot reach under any lighting. Only the strict level counts
toward a verdict. Conviction additionally requires the note to have been
LOCATED — the tells measure the note, and on a failed localisation they are
measuring somebody's desk.

Set COUNTERFEIT_TRIAGE_CONVICTS=0 to force the advisory-only behaviour back.

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

from .env import load_env
from .features import MICROPRINT

# Contract enum names (contracts/counterfeit.schema.json) that only the triage
# layer maps to — the synth renderer doesn't model these two features.
COLOR_SHIFTING_INK = "color_shifting_ink"
INTAGLIO = "intaglio_print"

# ── thresholds (calibrated against the synth renderer — see tests) ──────────
MIN_WIDTH, MIN_HEIGHT = 200, 90     # below this no security feature is resolvable
BLUR_MIN_LAPVAR = 40.0              # genuine renders ~1500+; heavy defocus < 40
EXPOSURE_DARK, EXPOSURE_BRIGHT = 35.0, 235.0

# Each tell: ADVISORY records evidence, CONVICTS is the level a genuine note
# cannot reach under any lighting. Only CONVICTS influences a verdict.
PHOTOCOPY_MAX_SAT = 14.0            # advisory: genuine ₹500 (greyest note) median sat ~21+
PHOTOCOPY_BW_SAT = 5.0              # convicts, and CONCLUSIVE alone: every INR note is colour-printed
FLAT_PRINT_MIN_LAPVAR = 100.0       # advisory: genuine renders measure 130+
FLAT_PRINT_CONVICTS_LAPVAR = 25.0   # convicts: below this the face carries no print structure at all
ASPECT_MIN, ASPECT_MAX = 1.70, 3.10           # advisory: real notes span 2.15 (₹100) – 2.52 (₹2000)
ASPECT_CONVICTS_MIN, ASPECT_CONVICTS_MAX = 1.40, 3.60  # convicts: not a banknote shape at all

# Hue families of every circulating Mahatma Gandhi (New) Series note
# (OpenCV hue, 0-179):  ₹10 brown ~13 and ₹200 yellow ~22 and ₹20 ~30 -> (0,50);
# ₹50 fluorescent blue ~96 -> (80,120); ₹100 lavender ~135 and ₹2000 magenta
# ~160 -> (120,179). ₹500 is near-neutral and excluded by the saturation gate.
# The old windows were [(0,40),(110,179)], which left ₹50's blue in the gap: a
# genuine ₹50 tripped "matches no circulating denomination".
KNOWN_HUE_WINDOWS = [(0, 50), (80, 120), (120, 179)]
UNKNOWN_COLOUR_MIN_SAT = 45.0       # advisory: only claim "wrong colour" when colour is vivid
UNKNOWN_COLOUR_CONVICTS_SAT = 90.0  # convicts: vivid, unambiguous novelty-note colour


@dataclass
class TriageCheck:
    """One deterministic measurement. `passed=True` means nothing suspicious."""

    name: str
    passed: bool
    measurement: float
    evidence: str
    maps_to: list[str] = field(default_factory=list)  # contract missing_features names
    conclusive: bool = False  # a single conclusive tell convicts on its own
    # True only at the strict threshold a genuine note cannot reach. `passed`
    # False with `convicts` False means "recorded as evidence, not acted on".
    convicts: bool = False


@dataclass
class TriageResult:
    decision: str  # "pass" | "obvious_fake" | "unscannable"
    checks: list[TriageCheck]

    @property
    def failed(self) -> list[TriageCheck]:
        return [c for c in self.checks if not c.passed]

    @property
    def convicting(self) -> list[TriageCheck]:
        """Failed tells that reached the strict conviction threshold."""
        return [c for c in self.checks if not c.passed and c.convicts]

    def mapped_features(self) -> list[str]:
        """Contract-enum feature names implied by the CONVICTING tells, deduped.

        Advisory-only failures are deliberately excluded: `missing_features` is
        what the officer is shown as the reason for a verdict, so it must not
        carry measurements the verdict itself refused to act on.
        """
        out: list[str] = []
        for c in self.convicting:
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
        convicts=sat < PHOTOCOPY_BW_SAT,
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
        # Soft focus and JPEG compression routinely push a genuine note under
        # the advisory 100; nothing with real print on it reaches under 25.
        convicts=lapvar < FLAT_PRINT_CONVICTS_LAPVAR,
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
        # A partly-occluded or creased note can sit just outside the advisory
        # band; nothing shaped like a banknote lands outside the wide one.
        convicts=not (ASPECT_CONVICTS_MIN <= aspect <= ASPECT_CONVICTS_MAX),
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
        # Colour casts from tungsten/LED light can drift a genuine note's hue
        # out of its window; a vividly saturated wrong hue is a novelty note.
        convicts=(not ok) and sat >= UNKNOWN_COLOUR_CONVICTS_SAT,
    )


# ── decision ────────────────────────────────────────────────────────────────

def convictions_enabled() -> bool:
    """Whether triage may return `obvious_fake`. Default on; set
    COUNTERFEIT_TRIAGE_CONVICTS=0 to fall back to advisory-only triage."""
    return os.environ.get("COUNTERFEIT_TRIAGE_CONVICTS", "1").strip().lower() not in (
        "0", "false", "no", "off",
    )


def prescreen(img_bgr: np.ndarray, warped_bgr: np.ndarray,
              located: bool = True) -> TriageResult:
    """Run the full triage.

    `img_bgr` is the original frame (geometry needs the background), `warped_bgr`
    the perspective-corrected note, and `located` whether that warp came from a
    real note outline. When `located` is False the "note" being measured is a
    resize of the whole photograph — the tells are recorded as evidence but can
    never convict, because they are measuring background.
    """
    gate = [check_resolution(img_bgr), check_blur(warped_bgr), check_exposure(img_bgr)]
    if any(not c.passed for c in gate):
        return TriageResult("unscannable", gate)

    tells = [
        check_photocopy(warped_bgr),
        check_flat_print(warped_bgr),
        check_geometry(img_bgr),
        check_unknown_colour(warped_bgr),
    ]
    result = TriageResult("pass", gate + tells)

    # Conviction needs (a) the strict thresholds, (b) a genuinely located note,
    # and (c) either one conclusive tell or two independent ones. A single
    # non-conclusive tell always has an innocent explanation; two at the strict
    # level on one located note do not. See the module docstring for the history
    # of this gate being too loose, then deleted outright.
    if not (located and convictions_enabled()):
        return result
    convicting = result.convicting
    if any(c.conclusive for c in convicting) or len(convicting) >= 2:
        result.decision = "obvious_fake"
    return result


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
    """Provider keys from the module/shared .env. Thin alias over `env.load_env`
    — kept as a name so existing callers and test monkeypatches keep working."""
    load_env()


def _claude_narrate(facts: str) -> str:
    import anthropic

    client = anthropic.Anthropic(timeout=25.0)
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
        timeout=25.0,
    )
    r.raise_for_status()
    text = r.json()["choices"][0]["message"]["content"].strip()
    if not text:
        raise ValueError("empty narrator reply")
    return text


def _gemini_narrate(facts: str) -> str:
    import httpx

    r = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-flash-lite-latest:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={
            "system_instruction": {"parts": [{"text": _NARRATE_SYSTEM}]},
            "contents": [{"parts": [{"text": "FACTS:\n" + facts}]}],
            "generationConfig": {"temperature": 0.2},
        },
        timeout=25.0,
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
        chain.append(("gemini-flash-lite-latest", _gemini_narrate))
    for name, fn in chain:
        try:
            return fn(facts), name  # type: ignore[operator]
        except Exception:
            continue
    return _template_narrative(result), "template"
