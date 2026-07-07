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
import uuid
from datetime import datetime, timezone
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

from .config import CAPTURES_DIR, CONTRACT_SCHEMA, SCHEMA_VERSION
from .features import infer_denomination, run_all_checks
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
    bgr = _to_bgr(img)
    checks = run_all_checks(bgr)
    failed = [c.feature for c in checks if not c.passed]
    p_fake = model.p_fake(img)
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
        # POSIX separators: this path lands in a web dashboard, not a shell.
        image_ref = capture_path.relative_to(CAPTURES_DIR.parents[1]).as_posix()

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": event_id,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "denomination": infer_denomination(bgr),
        "verdict": verdict,
        "confidence": round(confidence, 4),
        # Only report failed features when the note isn't being certified
        # genuine — matches the field's "why fake" purpose.
        "missing_features": failed if verdict != "genuine" else [],
        "image_ref": image_ref,
        "location_hint": location_hint,
    }


def analyze_file(path: Path, model: CounterfeitModel, **kwargs) -> dict:
    return analyze_image(Image.open(path), model, **kwargs)


def validate_payload(payload: dict) -> None:
    """Raise jsonschema.ValidationError if payload breaks the contract."""
    import jsonschema

    schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
