"""End-to-end scan: note image in → contract-valid counterfeit JSON out.

Hand-off surface to the command centre; every payload matches
`contracts/counterfeit.schema.json` (validate with
`python shared/validate_contract.py counterfeit <file>`).

Verdict fusion: the CNN gives the whole-note fake probability; the OpenCV
checks say which security features failed. The contract's `confidence` is the
model's confidence *in the verdict it returns* (p_fake for "fake", 1-p_fake
for "genuine", the distance from certainty for "uncertain").
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
from .features import infer_denomination, locate_note, run_all_checks
from .model import CounterfeitModel


def _to_bgr(img: Image.Image) -> np.ndarray:
    return cv2.cvtColor(np.asarray(img.convert("RGB")), cv2.COLOR_RGB2BGR)


def analyze_image(
    img: Image.Image,
    model: CounterfeitModel,
    location_hint: dict | None = None,
    save_capture: bool = False,
) -> dict:
    """Analyse one note photo; returns a contract-valid payload dict."""
    # The CNN (trained on real photos with varied framing/background) scores the
    # ORIGINAL image — it is robust to framing and, critically, the perspective
    # warp mis-fires on out-of-distribution inputs (e.g. novelty/joke notes),
    # distorting them into looking genuine. The warped, perspective-corrected
    # note is used ONLY for the OpenCV feature-checks, which need canonical
    # geometry but are advisory (they never flip the CNN verdict).
    warped = locate_note(_to_bgr(img))
    checks = run_all_checks(warped)
    failed = [c.feature for c in checks if not c.passed]
    p_fake = model.p_fake(img.convert("RGB"))
    verdict = model.decide_verdict(p_fake, len(failed))

    if verdict == "fake":
        # A conviction may come from the CNN, the feature checks, or both —
        # confidence reflects the stronger line of evidence.
        feature_conf = 0.0 if not failed else min(0.95, 0.75 + 0.10 * (len(failed) - 1))
        confidence = max(p_fake, feature_conf)
    elif verdict == "genuine":
        confidence = 1.0 - p_fake
    else:  # uncertain — confidence that a manual check is warranted
        confidence = 1.0 - 2.0 * abs(p_fake - 0.5)

    event_id = f"note_{uuid.uuid4().hex[:12]}"
    image_ref: str | None = None
    if save_capture:
        CAPTURES_DIR.mkdir(parents=True, exist_ok=True)
        capture_path = CAPTURES_DIR / f"{event_id}.jpg"
        img.convert("RGB").save(capture_path, quality=88)
        _prune_captures()
        # Absolute URL on this service (api.py mounts CAPTURES_DIR at /captures),
        # so the dashboard on a different origin can actually display the note.
        image_ref = f"{SERVICE_BASE_URL}/captures/{capture_path.name}"

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "denomination": infer_denomination(warped),
        "verdict": verdict,
        "confidence": round(confidence, 4),
        # Only report failed features when the note isn't being certified
        # genuine — matches the field's "why fake" purpose.
        "missing_features": failed if verdict != "genuine" else [],
        "image_ref": image_ref,
        "location_hint": location_hint,
    }


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
