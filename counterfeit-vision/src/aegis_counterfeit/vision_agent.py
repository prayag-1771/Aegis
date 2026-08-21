"""Vision-LLM second look: portrait + printed-text review. Additive only.

A multimodal model examines the scanned note and answers three narrow
questions the optical checks cannot: is the portrait Mahatma Gandhi, does the
note carry a SPECIMEN-style overprint, and does the header text read
"RESERVE BANK OF INDIA". Chain: Claude vision -> Gemini vision -> None
(Groq's text models can't see; there is no meaningful template for sight).

Hard rules, same doctrine as every AI layer in Aegis:
- findings can BLOCK a genuine certification (cap to `uncertain`) or enrich
  the explanation — they can never produce a `fake` verdict and never acquit;
- SPECIMEN is NOT treated as counterfeit: genuine RBI specimen notes exist.
  It means "not legal tender" -> manual check, whatever the print quality;
- no key / no network / bad reply -> returns None and the pipeline is
  byte-identical to a build without this module.
"""

from __future__ import annotations

import base64
import io
import json
import os

from PIL import Image

from .prescreen import _load_env_keys

_PROMPT = """You are inspecting a photograph of what is claimed to be an Indian rupee banknote.
Answer ONLY from what is visible. Respond with ONLY a JSON object, no markdown fences:

{
  "portrait_is_gandhi": true | false | null,   // null when no portrait is visible/decidable
  "specimen_overprint": true | false | null,   // SPECIMEN / COPY / PROP style overprint visible?
  "header_correct": true | false | null,       // does the header read exactly "RESERVE BANK OF INDIA"?
  "observations": ["<short factual observation>", ...]  // max 3, only what you can see
}

Be conservative: when unsure, use null. Never guess."""

MAX_SIDE = 768  # enough for portrait/text questions at a fraction of the tokens


def _jpeg_b64(img: Image.Image) -> str:
    img = img.convert("RGB")
    img.thumbnail((MAX_SIDE, MAX_SIDE))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _parse(text: str) -> dict:
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in vision reply")
    out = json.loads(text[start : end + 1])
    return {
        "portrait_is_gandhi": out.get("portrait_is_gandhi"),
        "specimen_overprint": out.get("specimen_overprint"),
        "header_correct": out.get("header_correct"),
        "observations": [str(o) for o in (out.get("observations") or [])][:3],
    }


def _claude(b64: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(timeout=12.0)
    r = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=300,
        messages=[{
            "role": "user",
            "content": [
                {"type": "image",
                 "source": {"type": "base64", "media_type": "image/jpeg", "data": b64}},
                {"type": "text", "text": _PROMPT},
            ],
        }],
    )
    return _parse("".join(b.text for b in r.content if b.type == "text"))


def _gemini(b64: str) -> dict:
    import httpx

    r = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-3.6-flash:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={
            "contents": [{"parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                {"text": _PROMPT},
            ]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        },
        timeout=12.0,
    )
    r.raise_for_status()
    return _parse(r.json()["candidates"][0]["content"]["parts"][0]["text"])


def vision_review_safe(img: Image.Image) -> dict | None:
    """Best available vision reviewer, or None. Never raises."""
    if os.environ.get("COUNTERFEIT_VISION_LLM", "").lower() in ("off", "0", "false"):
        return None
    try:
        _load_env_keys()
        chain: list[tuple[str, object]] = []
        if os.environ.get("ANTHROPIC_API_KEY"):
            chain.append(("claude-opus-4-8", _claude))
        if os.environ.get("GEMINI_API_KEY"):
            chain.append(("gemini-3.6-flash", _gemini))
        if not chain:
            return None
        b64 = _jpeg_b64(img)
        for name, fn in chain:
            try:
                return {**fn(b64), "engine": name}  # type: ignore[operator]
            except Exception:
                continue
    except Exception:
        pass
    return None


def cap_verdict_for_vision(payload: dict) -> None:
    """Wrong portrait, SPECIMEN overprint, or wrong header text blocks a
    genuine certification — cap to `uncertain`, never convict. Mutates the
    payload; does nothing when the review is absent or clean."""
    review = payload.get("vision_review")
    if not review or payload["verdict"] != "genuine":
        return
    blocked = (
        review.get("portrait_is_gandhi") is False
        or review.get("specimen_overprint") is True
        or review.get("header_correct") is False
    )
    if blocked:
        payload["verdict"] = "uncertain"
        payload["confidence"] = 0.75
