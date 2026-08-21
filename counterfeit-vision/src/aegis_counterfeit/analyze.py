"""End-to-end scan: note image in → contract-valid counterfeit JSON out.

Hand-off surface to the command centre; every payload matches
`contracts/counterfeit.schema.json` (validate with
`python shared/validate_contract.py counterfeit <file>`).

Verdict fusion, and who is allowed to say what:

- **triage** (prescreen.py) may reject an unscannable photo, or convict on a
  conclusive/two-strict-tell obvious fake. Requires a located note.
- **the CNN** (model.py) owns the print-physics fake/genuine call.
- **the feature checks** (features.py) may BLOCK a certification — two or more
  actionable failures turn `genuine` into `uncertain` — but never convict.
- **the semantic layer** (vision_agent.py) reads what is printed on the note. A
  wrong portrait or header CONVICTS; a SPECIMEN overprint or a denomination
  mismatch caps to `uncertain`.
- **the serial layer** (serials.py) caps a certification on a bad or duplicated
  serial.
- Nothing acquits. No layer can turn a `fake` into a `genuine`.

The contract's `confidence` is the model's confidence *in the verdict it
returns* (p_fake for "fake", 1-p_fake for "genuine", the distance from certainty
for "uncertain"), capped for a `genuine` the semantic layer never saw.
"""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

# Absolute base for capture URLs so the dashboard (a different origin, :3000)
# can load the scanned-note image. Override via env when deployed elsewhere.
SERVICE_BASE_URL = os.environ.get("COUNTERFEIT_PUBLIC_URL", "http://127.0.0.1:8002")

import cv2
import numpy as np
from PIL import Image

from .config import CAPTURES_DIR, CONTRACT_SCHEMA, SCHEMA_VERSION, TrainConfig
from .features import infer_denomination, locate_note_ex, run_all_checks, run_check_set
from .model import CounterfeitModel
from .prescreen import TriageResult, narrate_triage_safe, prescreen, triage_block
from .serials import cap_verdict_for_serial, inspect_serial
from .vision_agent import apply_vision_review, vision_review_safe


def _to_bgr(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)


_RAM_FLOOR_BYTES = 1024 * 1024 * 1024  # 1 GB: below this, skip the Grad-CAM backward pass


def _detected_ram_bytes() -> int:
    """Best-effort memory ceiling for this host. Reads the cgroup limit first
    (that is what a container/Render instance is actually capped at), then total
    RAM. Returns a huge sentinel when it cannot tell (e.g. Windows dev boxes), so
    heatmaps stay ON where they have always worked."""
    for p in ("/sys/fs/cgroup/memory.max",                     # cgroup v2
              "/sys/fs/cgroup/memory/memory.limit_in_bytes"):   # cgroup v1
        try:
            v = open(p).read().strip()
            if v.isdigit() and 0 < int(v) < (1 << 62):  # v2 "max" is a huge sentinel
                return int(v)
        except OSError:
            pass
    try:
        return os.sysconf("SC_PHYS_PAGES") * os.sysconf("SC_PAGE_SIZE")
    except (ValueError, AttributeError, OSError):
        return 1 << 62  # unknown host => assume plenty


def _gradcam_enabled() -> bool:
    """Which heatmap method to use — a heatmap is produced either way.

    Grad-CAM is class-specific but needs a backward pass that ~triples peak
    memory and OOM-kills a 512MB free-tier box mid-scan (the whole service 502s —
    the 'Unexpected end of JSON' the UI shows). On a memory-constrained host we
    fall back to Eigen-CAM, a forward-only heatmap that fits. Grad-CAM is used by
    default (local dev has RAM), auto-swapped on a constrained host, and always
    overridable:
        COUNTERFEIT_LOW_MEMORY=1  -> force forward-only Eigen-CAM
        COUNTERFEIT_LOW_MEMORY=0  -> force Grad-CAM
    The verdict is identical either way; only the heatmap's method changes."""
    override = os.environ.get("COUNTERFEIT_LOW_MEMORY")
    if override is not None:
        return override.strip().lower() in ("0", "false", "no", "")
    return _detected_ram_bytes() >= _RAM_FLOOR_BYTES


def analyze_image(
    img: Image.Image,
    model: CounterfeitModel,
    location_hint: dict | None = None,
    save_capture: bool = False,
    serial_number: str | None = None,
) -> dict:
    """Analyse one note photo; returns a contract-valid payload dict."""
    payload = _analyze_core(img, model, location_hint, save_capture)

    # Semantic layer FIRST, because it is the only one that reads the note's
    # content and it may convict (wrong portrait / wrong header). It always
    # returns a block — `available: false` when no model looked — so the payload
    # can never imply a semantic check that did not happen.
    review = vision_review_safe(img)
    payload["vision_review"] = review
    apply_vision_review(payload)

    # Optical hue cannot separate Rs10/Rs20/Rs200 (one warm colour band), so it
    # honestly reports "unknown". The semantic layer READ the numeral off the
    # note — use it rather than showing "denom. unknown" next to a note whose
    # value we were in fact told. Only fills a gap; a disagreement is handled by
    # apply_vision_review above, which caps the verdict instead.
    if payload.get("denomination") == "unknown" and review.get("printed_denomination"):
        payload["denomination"] = review["printed_denomination"]
        payload["denomination_source"] = "vision"

    # Serial layer: nonsense format flags, valid serials go through the
    # sighting registry (duplicate serial = counterfeit printing run). Can
    # only cap a genuine certification, never acquit or convict.
    # Falls back to the serial the vision model read off the note, so the
    # registry still works when nobody typed one into the UI.
    serial = serial_number or review.get("serial_text")
    if serial:
        payload["serial"] = inspect_serial(
            serial, payload["event_id"],
            (location_hint or {}).get("district"),
        )
        payload["serial"]["source"] = "manual" if serial_number else "vision"
        cap_verdict_for_serial(payload)

    _temper_unverified_genuine(payload)
    return payload


# A `genuine` reached without the semantic channel has only been checked for
# print physics. That is a real but partial clearance, so the verdict stands and
# the confidence is capped: the officer sees "genuine, but nothing read what is
# printed on this note". Previously such a scan was reported at up to 0.95 and
# was indistinguishable from a fully reviewed one.
UNVERIFIED_GENUINE_MAX_CONFIDENCE = 0.80


def _temper_unverified_genuine(payload: dict) -> None:
    review = payload.get("vision_review") or {}
    if payload["verdict"] != "genuine" or review.get("available"):
        return
    payload["confidence"] = round(
        min(payload["confidence"], UNVERIFIED_GENUINE_MAX_CONFIDENCE), 4
    )
    payload["caveats"] = payload.get("caveats", []) + [
        "No semantic review ran (" + str(review.get("status", "unavailable")) + "): "
        "print quality was checked, the note's printed content was not. "
        "Tampering that preserves print quality — an altered portrait, numeral "
        "or serial — would not be detected."
    ]


def _analyze_core(
    img: Image.Image,
    model: CounterfeitModel,
    location_hint: dict | None = None,
    save_capture: bool = False,
) -> dict:
    # The CNN (trained on real photos with varied framing/background) scores the
    # ORIGINAL image — it is robust to framing and, critically, the perspective
    # warp mis-fires on out-of-distribution inputs (e.g. novelty/joke notes),
    # distorting them into looking genuine. The warped, perspective-corrected
    # note is used ONLY for the OpenCV feature-checks, which need canonical
    # geometry but are advisory (they never flip the CNN verdict).
    bgr = _to_bgr(img)
    # `located` says whether a real note outline was found. When it is False the
    # "note" is a resize of the whole photograph, so every fixed-geometry
    # measurement below is reading background — it is recorded as evidence but
    # must not touch the verdict.
    warped, located = locate_note_ex(bgr)

    # Pre-flight triage: obvious fakes and unscannable photos exit here — the
    # CNN is only consulted when the answer isn't already certain. `model` is
    # untouched on these paths.
    triage = prescreen(bgr, warped, located=located)
    if triage.decision != "pass":
        return _fast_path_payload(img, triage, warped, located, location_hint, save_capture)

    check_set = run_check_set(warped, located)
    failed = check_set.failed
    # Both paths return p_fake AND a heatmap of the regions that drove the
    # decision. Grad-CAM (class-specific) needs a backward pass that ~triples
    # peak memory, so on a memory-constrained host (512MB free tier) we use
    # Eigen-CAM, a forward-only heatmap that fits. Same verdict either way — only
    # the heatmap method changes. See _gradcam_enabled().
    if _gradcam_enabled():
        p_fake, heatmap = model.gradcam(img.convert("RGB"))
        heatmap_method = "grad_cam"
    else:
        p_fake, heatmap = model.activation_cam(img.convert("RGB"))
        heatmap_method = "eigen_cam"
    # ACTIONABLE failures only — see decide_verdict and CheckSet.actionable_failures.
    verdict = model.decide_verdict(
        p_fake, len(check_set.actionable_failures),
        blocks_certification=check_set.blocks_certification,
    )

    if verdict == "fake":
        # A conviction may come from the CNN, the feature checks, or both —
        # confidence reflects the stronger line of evidence.
        feature_conf = 0.0 if not failed else min(0.95, 0.75 + 0.10 * (len(failed) - 1))
        confidence = max(p_fake, feature_conf)
    elif verdict == "genuine":
        confidence = 1.0 - p_fake
    elif check_set.blocks_certification:
        # `uncertain` because the FEATURE LAYER blocked a certification the CNN
        # was happy with — not because the CNN was torn. The mid-band formula
        # below is meaningless here: it measures distance from p_fake=0.5, so a
        # confidently-genuine 0.003 scored 0.6% and the UI showed "UNCERTAIN 1%"
        # on a real note. This is a definite finding ("a security feature did
        # not verify"), so it reports as one.
        confidence = 0.70
    else:  # uncertain — the CNN itself landed in the manual-review band
        confidence = 1.0 - 2.0 * abs(p_fake - 0.5)

    event_id = f"note_{uuid.uuid4().hex[:12]}"
    image_ref: str | None = None
    heatmap_ref: str | None = None
    if save_capture:
        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        capture_path = CAPTURES_DIR / f"{event_id}.jpg"
        img.convert("RGB").save(capture_path, quality=88)
        _prune_captures()
        # Absolute URL on this service (api.py mounts CAPTURES_DIR at /captures),
        # so the dashboard on a different origin can actually display the note.
        image_ref = f"{SERVICE_BASE_URL}/captures/{capture_path.name}"
        # Grad-CAM overlay: the note with a heatmap marking the suspicious
        # regions. Only when heatmaps ran (heatmap is None in low-memory mode).
        if heatmap is not None:
            heat_path = CAPTURES_DIR / f"{event_id}_cam.jpg"
            _save_heatmap_overlay(img.convert("RGB"), heatmap, heat_path)
            heatmap_ref = f"{SERVICE_BASE_URL}/captures/{heat_path.name}"

    analysis = {
        "note_located": located,
        "feature_checks_applied": check_set.trustworthy,
        # Which method actually produced heatmap_ref. Grad-CAM is class-specific
        # ("what drove FAKE"); Eigen-CAM is class-agnostic ("where the model
        # looked") and is substituted on low-memory hosts. They are not the same
        # explanation, and the payload used to call both of them Grad-CAM.
        "heatmap_method": heatmap_method if heatmap is not None else None,
        "feature_scores": [
            {"feature": c.feature, "passed": c.passed, "score": c.score,
             "threshold": c.threshold, "detail": c.detail}
            for c in check_set.checks
        ],
    }

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        # `located` gates this too: on a failed localisation the median hue
        # describes the desk, not the note.
        "denomination": infer_denomination(warped, located),
        "verdict": verdict,
        "confidence": round(confidence, 4),
        # Reported whatever the verdict. These used to be force-emptied on a
        # `genuine`, which deleted the only hint that anything was off from the
        # exact payloads where it mattered most. A genuine verdict now already
        # implies fewer than two ACTIONABLE failures (decide_verdict), so a
        # non-empty list here is an honest "cleared, with one soft flag".
        "missing_features": check_set.actionable_failures,
        "image_ref": image_ref,
        "heatmap_ref": heatmap_ref,
        "location_hint": location_hint,
        # Full pipeline ran: record that triage saw nothing obvious.
        "triage": triage_block(triage),
        "analysis": analysis,
    }


def _fast_path_payload(
    img: Image.Image,
    triage: TriageResult,
    warped: np.ndarray,
    located: bool,
    location_hint: dict | None,
    save_capture: bool,
) -> dict:
    """Payload for scans that never reach the CNN: an unscannable photo
    (verdict `uncertain` — rescan advice) or an obvious fake (verdict `fake`
    from hard measurements). No heatmap exists on these paths — no model ran."""
    if triage.decision == "unscannable":
        verdict, denomination = "uncertain", "unknown"
        missing = []
        # Confidence that a manual check / rescan is warranted, not in a
        # fake-vs-genuine call — the photo carries too little signal for one.
        confidence = 0.2
        narrative, engine = None, None  # quality advice needs no LLM
    else:  # obvious_fake — only reachable on a LOCATED note, see prescreen()
        verdict = "fake"
        denomination = infer_denomination(warped, located)
        # Feature checks are cheap OpenCV — still run them so missing_features
        # carries the richest available evidence alongside the triage tells.
        failed_checks = [c.feature for c in run_all_checks(warped) if not c.passed]
        missing = failed_checks + [f for f in triage.mapped_features() if f not in failed_checks]
        # Scale with the CONVICTING tells, not every advisory one — confidence
        # must track the evidence the verdict was actually allowed to use.
        n_evidence = len(triage.convicting) + len(failed_checks)
        confidence = min(0.98, 0.90 + 0.02 * max(n_evidence - 1, 0))
        narrative, engine = narrate_triage_safe(triage)

    event_id = f"note_{uuid.uuid4().hex[:12]}"
    image_ref: str | None = None
    if save_capture:
        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        capture_path = CAPTURES_DIR / f"{event_id}.jpg"
        img.convert("RGB").save(capture_path, quality=88)
        _prune_captures()
        image_ref = f"{SERVICE_BASE_URL}/captures/{capture_path.name}"

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "denomination": denomination,
        "verdict": verdict,
        "confidence": round(confidence, 4),
        "missing_features": missing,
        "image_ref": image_ref,
        "heatmap_ref": None,
        "location_hint": location_hint,
        "triage": triage_block(triage, narrative, engine),
        "analysis": {
            "note_located": located,
            # No CNN and no fixed-geometry certification happened on this path.
            "feature_checks_applied": located and triage.decision == "obvious_fake",
            "heatmap_method": None,
            "feature_scores": [],
        },
    }


def _save_heatmap_overlay(img: Image.Image, heatmap: np.ndarray, path: Path) -> None:
    """Blend the heatmap (red = suspicious) over the note and save it."""
    # Cap the overlay resolution. On a 512MB host the full-res cv2 arrays below
    # (base + colormap + blend, several copies) are what's left of the memory
    # budget after inference; ~1024px is ample for a dashboard overlay.
    _MAX_SIDE = 1024
    if max(img.size) > _MAX_SIDE:
        scale = _MAX_SIDE / max(img.size)
        img = img.resize((max(1, round(img.width * scale)), max(1, round(img.height * scale))))
    w, h = img.size
    if heatmap is None or heatmap.size == 0:
        img.save(path, quality=88)
        return
    cam = cv2.resize(heatmap.astype(np.float32), (w, h), interpolation=cv2.INTER_CUBIC)
    cam = np.clip(cam, 0, 1)
    colored = cv2.applyColorMap((cam * 255).astype(np.uint8), cv2.COLORMAP_JET)  # BGR
    base = cv2.cvtColor(np.asarray(img), cv2.COLOR_RGB2BGR)
    overlay = cv2.addWeighted(base, 0.6, colored, 0.4, 0)
    cv2.imwrite(str(path), overlay, [cv2.IMWRITE_JPEG_QUALITY, 88])


def _prune_captures() -> None:
    """Cap on-disk demo captures (oldest first) — every scan writes a JPEG and
    a long demo day would otherwise grow the folder unbounded."""
    keep = TrainConfig().max_captures
    files = sorted(CAPTURES_DIR.glob("*.jpg"), key=lambda p: p.stat().st_mtime)
    for stale in files[:-keep]:
        stale.unlink(missing_ok=True)


def analyze_file(path: Path, model: CounterfeitModel, **kwargs) -> dict:
    return analyze_image(Image.open(path), model, **kwargs)


def validate_payload(payload: dict) -> None:
    """Raise jsonschema.ValidationError if payload breaks the contract."""
    import jsonschema

    schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
