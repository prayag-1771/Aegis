"""OpenCV security-feature checks — the feature-level detection layer.

This is what lifts the module beyond "whole-note fake/real": each check
inspects the region where a real security feature lives and reports
pass/fail **with a numeric score**, so the UI and the fusion LLM can say
*which* feature is missing (contract field `missing_features`) and the
result stays auditable.

Checks implemented:
- **security_thread** — column-darkness scan around the known thread x-band;
  a genuine windowed thread shows a narrow, strongly darker column.
- **watermark** — brightness lift of the watermark oval vs its surround.
- **microprint** — Laplacian variance (sharpness) of the microprint band;
  counterfeits reproduce it blurred or not at all.

**Layout provenance.** The region constants below live HERE, and `synth.py`
imports them from this module. That direction matters: they describe the
Mahatma Gandhi (New) Series layout, and the renderer is built to match it.
Previously the dependency ran the other way — the checks imported coordinates
out of the fake-note renderer, so "does this note have a thread where a real
note's thread is" really asked "does this note look like our own drawing".

**Trust boundary.** These are fixed-geometry scans. They are only meaningful
when the note was actually located and perspective-corrected — on a fallback
resize of a whole photo they read desk and shadow. `locate_note_ex` reports
whether localisation succeeded so callers can refuse to act on the result;
see `analyze.py` and `CheckSet.trustworthy`.
"""

from __future__ import annotations

from dataclasses import dataclass

import cv2
import numpy as np

from .config import NOTE_SIZE

# Feature names must match the contract enum (contracts/counterfeit.schema.json).
SECURITY_THREAD = "security_thread"
WATERMARK = "watermark"
MICROPRINT = "microprint"
CHECKABLE_FEATURES = [SECURITY_THREAD, WATERMARK, MICROPRINT]

# ── real-note layout (fractions of the note's width/height) ─────────────────
# Mahatma Gandhi (New) Series, obverse. The windowed security thread sits left
# of the portrait; the Gandhi watermark sits in the clear right-hand panel; the
# microprint band runs along the lower left. synth.py renders to these.
THREAD_X = 0.42
# MEASURED on a real Rs20 photograph, not assumed: the watermark is the clear
# unprinted window on the LEFT of the note. A column-brightness sweep of the
# warped note put the bright sustained region at x=10-35% (mean 221) and the
# region at 80% at mean 169 — because 80% is where Gandhi's PRINTED PORTRAIT
# is, which is darker than its surround, not brighter.
#
# 0.80 came from the synth renderer and was never checked against a real note,
# so `check_watermark` was measuring "is the portrait brighter than its
# background" — the answer is no, and every real note failed the watermark
# check. That single structural failure blocks certification, which is why a
# genuine Rs20 came back `uncertain`.
WATERMARK_X = 0.22
WATERMARK_Y = 0.45
MICROPRINT_Y = 0.84

# Watermark sampling windows as fractions, not hardcoded pixels — the previous
# `cy-40:cy+40` only made sense at exactly NOTE_SIZE and silently clipped or
# mis-sampled at any other resolution.
_WM_INNER_W, _WM_INNER_H = 0.0625, 0.19   # ~30x40 px at 480x212
_WM_OUTER_W, _WM_OUTER_H = 0.115, 0.283   # ~55x60 px at 480x212


@dataclass
class FeatureCheck:
    """Outcome of one security-feature inspection."""

    feature: str
    passed: bool
    score: float  # the measured statistic (interpretation depends on check)
    threshold: float
    detail: str


@dataclass
class CheckSet:
    """The three feature checks plus whether they may be believed.

    `trustworthy` is False when the note could not be isolated from the frame:
    the checks then ran against a plain resize of the whole photograph, and
    every region fraction points at background rather than note. Callers must
    not let an untrustworthy set influence a verdict.
    """

    checks: list[FeatureCheck]
    trustworthy: bool

    @property
    def failed(self) -> list[str]:
        return [c.feature for c in self.checks if not c.passed]

    @property
    def actionable_failures(self) -> list[str]:
        """Failures a verdict is allowed to react to — none when untrusted."""
        return self.failed if self.trustworthy else []

    @property
    def blocks_certification(self) -> bool:
        """Whether these findings should stop a `genuine` (never cause a `fake`).

        `security_thread` and `watermark` are STRUCTURAL — the feature is either
        printed into the note or it is not, so a single clean failure is enough
        to want a human's eyes. `microprint` measures sharpness, which soft
        focus and JPEG compression degrade on genuine notes too, so it only
        blocks alongside a second failure.
        """
        failures = set(self.actionable_failures)
        return bool(failures & {SECURITY_THREAD, WATERMARK}) or len(failures) >= 2


def _order_corners(quad: np.ndarray) -> np.ndarray:
    """Order 4 points as top-left, top-right, bottom-right, bottom-left."""
    s = quad.sum(axis=1)
    d = np.diff(quad, axis=1).ravel()
    return np.array(
        [quad[np.argmin(s)], quad[np.argmin(d)], quad[np.argmax(s)], quad[np.argmax(d)]],
        dtype=np.float32,
    )


def locate_note_ex(img_bgr: np.ndarray) -> tuple[np.ndarray, bool]:
    """Find the note in a camera frame and perspective-correct it.

    Returns `(warped, located)`. `located` is False when no plausible note
    outline was found and the fallback — a plain resize of the ENTIRE frame —
    was used. That fallback is correct for images that already *are* the note
    (our renders, tight crops) and wrong for a photo of a note on a desk, where
    it silently feeds background pixels to every downstream measurement. It
    used to be indistinguishable from success; now it is not.
    """
    h, w = img_bgr.shape[:2]
    gray = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(cv2.GaussianBlur(gray, (5, 5), 0), 50, 150)
    edges = cv2.dilate(edges, np.ones((3, 3), np.uint8))
    contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)

    best_quad, best_area = None, 0.0
    frame_area = float(h * w)
    for contour in contours:
        area = cv2.contourArea(contour)
        if not (0.15 * frame_area <= area <= 0.95 * frame_area):
            continue
        approx = cv2.approxPolyDP(contour, 0.02 * cv2.arcLength(contour, True), True)
        if len(approx) == 4 and area > best_area:
            best_quad, best_area = approx.reshape(4, 2).astype(np.float32), area

    if best_quad is None:
        # An image that already IS the note (a render, a tight crop) is a
        # legitimate "no outline" case — the frame and the note are the same
        # thing, so the resize is exact and the checks stay meaningful.
        already_canonical = abs((w / max(h, 1)) - (NOTE_SIZE[0] / NOTE_SIZE[1])) < 0.25
        return (cv2.resize(img_bgr, NOTE_SIZE, interpolation=cv2.INTER_AREA),
                already_canonical)

    src = _order_corners(best_quad)
    dst_w, dst_h = NOTE_SIZE
    dst = np.array([[0, 0], [dst_w - 1, 0], [dst_w - 1, dst_h - 1], [0, dst_h - 1]],
                   dtype=np.float32)
    return cv2.warpPerspective(img_bgr, cv2.getPerspectiveTransform(src, dst), NOTE_SIZE), True


def locate_note(img_bgr: np.ndarray) -> np.ndarray:
    """Backwards-compatible wrapper — the warped note only."""
    return locate_note_ex(img_bgr)[0]


def _to_canonical(img_bgr: np.ndarray) -> np.ndarray:
    """Canonical working frame: pass through if already canonical (avoids
    re-running localisation), otherwise locate + warp."""
    if img_bgr.shape[1::-1] == NOTE_SIZE:
        return img_bgr
    return locate_note(img_bgr)


def check_security_thread(img_bgr: np.ndarray) -> FeatureCheck:
    """Genuine thread = narrow column much darker than its neighbourhood."""
    img = _to_canonical(img_bgr)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape
    x0, x1 = int(w * (THREAD_X - 0.08)), int(w * (THREAD_X + 0.08))
    band = gray[int(h * 0.08): int(h * 0.92), x0:x1]
    col_means = band.mean(axis=0)
    # Contrast of the darkest column against the band's own median.
    contrast = float(np.median(col_means) - col_means.min())
    threshold = 12.0
    return FeatureCheck(
        feature=SECURITY_THREAD,
        passed=contrast >= threshold,
        score=round(contrast, 2),
        threshold=threshold,
        detail=f"thread-band darkness contrast {contrast:.1f} (needs >= {threshold})",
    )


def check_watermark(img_bgr: np.ndarray) -> FeatureCheck:
    """Genuine watermark = local brightness lift in the watermark oval."""
    img = _to_canonical(img_bgr)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY).astype(np.float32)
    h, w = gray.shape
    cx, cy = int(w * WATERMARK_X), int(h * WATERMARK_Y)
    iw, ih = max(int(w * _WM_INNER_W), 2), max(int(h * _WM_INNER_H), 2)
    ow, oh = max(int(w * _WM_OUTER_W), iw + 2), max(int(h * _WM_OUTER_H), ih + 2)
    # Clamp to the frame so an off-centre warp can't silently yield an empty
    # or lopsided slice (an empty inner block used to produce a NaN lift).
    def _box(half_w: int, half_h: int) -> np.ndarray:
        return gray[max(cy - half_h, 0): min(cy + half_h, h),
                    max(cx - half_w, 0): min(cx + half_w, w)]

    inner, outer = _box(iw, ih), _box(ow, oh)
    threshold = 4.0
    if inner.size == 0 or outer.size <= inner.size:
        return FeatureCheck(WATERMARK, True, 0.0, threshold,
                            "watermark window outside the frame — check skipped")
    # True annulus: subtract the inner block so the surround isn't diluted.
    ring_mean = (outer.sum() - inner.sum()) / (outer.size - inner.size)
    lift = float(inner.mean() - ring_mean)
    return FeatureCheck(
        feature=WATERMARK,
        passed=lift >= threshold,
        score=round(lift, 2),
        threshold=threshold,
        detail=f"watermark brightness lift {lift:.1f} (needs >= {threshold})",
    )


def check_microprint(img_bgr: np.ndarray) -> FeatureCheck:
    """Genuine microprint = sharp band => high Laplacian variance."""
    img = _to_canonical(img_bgr)
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape
    y = int(h * MICROPRINT_Y)
    band = gray[max(y - 4, 0): min(y + 20, h), int(w * 0.06): int(w * 0.60)]
    # 3x3 denoise first so sensor noise can't masquerade as sharp print.
    band = cv2.GaussianBlur(band, (3, 3), 0)
    sharpness = float(cv2.Laplacian(band, cv2.CV_64F).var())
    threshold = 60.0
    return FeatureCheck(
        feature=MICROPRINT,
        passed=sharpness >= threshold,
        score=round(sharpness, 2),
        threshold=threshold,
        detail=f"microprint sharpness {sharpness:.1f} (needs >= {threshold})",
    )


def run_all_checks(img_bgr: np.ndarray) -> list[FeatureCheck]:
    return [
        check_security_thread(img_bgr),
        check_watermark(img_bgr),
        check_microprint(img_bgr),
    ]


def run_check_set(warped_bgr: np.ndarray, located: bool) -> CheckSet:
    """The three checks bundled with whether localisation earned the right to
    believe them."""
    return CheckSet(run_all_checks(warped_bgr), trustworthy=located)


def missing_features(img_bgr: np.ndarray) -> list[str]:
    """Contract-ready list of failed security features."""
    return [c.feature for c in run_all_checks(img_bgr) if not c.passed]


# ── denomination ────────────────────────────────────────────────────────────
# Mahatma Gandhi (New) Series base colours, as OpenCV HSV hue (0-179) windows
# with the saturation range that separates the overlapping ones. Ordered most
# distinctive first. A frame matching zero or several windows is "unknown" —
# saying "unknown" is free, and a wrong denomination on a seizure record is not.
#
# The previous rule was `120 <= hue <= 179 and sat >= 30 -> "2000"`, which
# swallowed the whole magenta-through-lavender range: a genuine Rs100
# (lavender, hue ~135, sat ~52) was reported as a Rs2000. The other rule,
# `sat < 30 -> "500"`, labelled any desaturated frame — a grey desk, a dim
# photo, a failed localisation — a confident Rs500.
_DENOM_WINDOWS: list[tuple[str, int, int, int, int]] = [
    # (denomination, hue_lo, hue_hi, sat_lo, sat_hi)
    ("2000", 150, 179, 40, 255),   # magenta
    ("100", 120, 149, 30, 255),    # lavender
    ("50", 85, 115, 40, 255),      # fluorescent blue
    # Rs10 (chocolate brown, hue ~13), Rs20 (greenish yellow, ~28) and Rs200
    # (bright yellow, ~20) share one warm band and cannot be told apart by hue.
    # Their windows OVERLAP DELIBERATELY so all three match and the result
    # resolves to "unknown" rather than to whichever one the ordering happened
    # to hit. Separating them needs the printed numeral, which the semantic
    # layer reads as `vision_review.printed_denomination`.
    ("200", 5, 45, 40, 255),
    ("10", 5, 45, 40, 255),
    ("20", 5, 45, 40, 255),
]
_STONE_GREY_MAX_SAT = 30  # Rs500 is the only near-neutral note in circulation


def infer_denomination(img_bgr: np.ndarray, located: bool = True) -> str:
    """Best-effort denomination from the note's dominant hue.

    `located=False` (the whole photo was resized rather than the note isolated)
    returns "unknown": the median hue then describes the desk, not the note.
    """
    img = _to_canonical(img_bgr)
    if not located:
        return "unknown"
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    sat = float(np.median(hsv[:, :, 1]))
    if sat < _STONE_GREY_MAX_SAT:
        return "500"
    # Hue median over coloured pixels only — neutral paper would drag it.
    coloured = hsv[hsv[:, :, 1] > 40]
    if coloured.size == 0:
        return "unknown"
    hue = float(np.median(coloured[:, 0]))
    matches = {d for d, h_lo, h_hi, s_lo, s_hi in _DENOM_WINDOWS
               if h_lo <= hue <= h_hi and s_lo <= sat <= s_hi}
    # Exactly one window may claim the note; ambiguity is reported honestly.
    return matches.pop() if len(matches) == 1 else "unknown"
