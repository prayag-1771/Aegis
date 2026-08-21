"""Vision-LLM second look: the module's only SEMANTIC channel.

Everything else in this pipeline measures print physics — ink saturation,
intaglio texture, thread darkness, paper sharpness. The CNN included: it was
trained on real notes versus physically counterfeited ones, where the separable
signal is print quality, so it learned print quality. None of it reads what is
actually ON the note.

That is a real hole, not a theoretical one. A genuine note with a different
face pasted over Gandhi has genuine paper, genuine intaglio texture, genuine
colour — every physical measurement passes, and the CNN pools a single altered
region into nothing at 224x224. It came back `genuine` at ~0.95 confidence.
Same for an altered denomination numeral, an edited serial, or a wrong header:
any tampering that preserves print physics is invisible to every other layer.

This module asks a multimodal model the questions the optical checks cannot:
is the portrait Mahatma Gandhi, does the header read "RESERVE BANK OF INDIA",
what denomination is printed, is there a SPECIMEN-style overprint, and what is
the serial. Chain: Claude vision -> Gemini vision -> Groq vision -> unavailable.

The Groq leg exists because Groq now serves multimodal models — the older note
in this file that "Groq's text models can't see" is out of date. It is placed
last because the model behind it is far smaller than Claude's or Gemini's
vision stacks, and because Groq's free tier rate-limits aggressively; a 429
degrades to `unavailable_error`, which caps confidence rather than convicting.

Authority (deliberately narrow, and stronger than it used to be):
- `portrait_is_gandhi: false` or `header_correct: false` CONVICTS. A note whose
  portrait is not Gandhi is not a genuine Indian banknote under any lighting or
  framing — this is a fact about the note's content, not a fragile measurement
  of its surface, so it does not carry the false-positive risk that stopped the
  optical checks from convicting. Only an explicit `false` counts; `null`
  ("can't tell") never does.
- `specimen_overprint: true` caps to `uncertain`, never convicts — genuine RBI
  specimen notes exist. It means "not legal tender", so: manual check.
- The layer NEVER acquits. It cannot turn a `fake` into a `genuine`.

Absence is REPORTED, not silent. With no key this used to return None and the
payload was byte-identical to a build without the module — a note that had
never been semantically checked was indistinguishable from one that passed the
check. It now always returns a block carrying `status`, so `genuine` cannot
masquerade as fully vetted when the only layer that reads the note never ran.
"""

from __future__ import annotations

import base64
import io
import json
import os
import time

from PIL import Image

from .env import load_env

_PROMPT = """You are inspecting a photograph of what is claimed to be an Indian rupee banknote.
Answer ONLY from what is visible. Respond with ONLY a JSON object, no markdown fences:

{
  "portrait_is_gandhi": true | false | null,   // is the main portrait Mahatma Gandhi? null when no portrait is visible/decidable
  "specimen_overprint": true | false | null,   // SPECIMEN / COPY / PROP style overprint visible?
  "header_correct": true | false | null,       // does the header read exactly "RESERVE BANK OF INDIA"?
  "printed_denomination": "10"|"20"|"50"|"100"|"200"|"500"|"2000"|null,  // the numeral printed on the note
  "serial_text": "<serial as printed>" | null, // the serial number, if legible
  "tampering_signs": ["<short factual observation>", ...],  // max 3: pasted/edited regions, mismatched fonts, cut-and-paste edges
  "observations": ["<short factual observation>", ...]  // max 3, only what you can see
}

CRITICAL: "portrait_is_gandhi" must be false ONLY when you can clearly see the
portrait and it is somebody other than Mahatma Gandhi. If the portrait is
obscured, cropped, blurred or you are in any doubt, answer null. Never guess."""

MAX_SIDE = 768  # enough for portrait/text questions at a fraction of the tokens

# Status values placed on the returned block.
OK = "ok"
NO_KEY = "unavailable_no_key"
FAILED = "unavailable_error"
RATE_LIMITED = "unavailable_rate_limited"
DISABLED = "disabled"

_DENOMS = {"10", "20", "50", "100", "200", "500", "2000"}


def _jpeg_b64(img: Image.Image, max_side: int = MAX_SIDE) -> str:
    img = img.convert("RGB")
    img.thumbnail((max_side, max_side))
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=85)
    return base64.b64encode(buf.getvalue()).decode()


def _tri(value: object) -> bool | None:
    """Strictly tri-state. Anything that isn't a real bool becomes None, so a
    model answering "unsure" or "" can never be read as a conviction."""
    return value if isinstance(value, bool) else None


def _strip_reasoning(text: str) -> str:
    """Drop a reasoning model's <think> block.

    Qwen on Groq emits its chain of thought before the answer, and that prose
    routinely contains braces ("the JSON should be {...}"), so scanning for the
    first `{` in the raw reply can parse the model's scratchpad instead of its
    result. Everything up to the final closing tag goes.
    """
    for tag in ("</think>", "</thinking>"):
        if tag in text:
            text = text.rsplit(tag, 1)[-1]
    return text.strip()


def _parse(text: str) -> dict:
    text = _strip_reasoning(text)
    # Prefer a fenced block when present, else the last {...} in the reply —
    # the last one, because any preamble braces come earlier.
    if "```" in text:
        parts = [p for p in text.split("```") if "{" in p]
        if parts:
            text = parts[-1].removeprefix("json").strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in vision reply")
    out = json.loads(text[start : end + 1])
    denom = out.get("printed_denomination")
    serial = out.get("serial_text")
    return {
        "portrait_is_gandhi": _tri(out.get("portrait_is_gandhi")),
        "specimen_overprint": _tri(out.get("specimen_overprint")),
        "header_correct": _tri(out.get("header_correct")),
        "printed_denomination": str(denom) if str(denom) in _DENOMS else None,
        "serial_text": str(serial).strip() if serial else None,
        "tampering_signs": [str(o) for o in (out.get("tampering_signs") or [])][:3],
        "observations": [str(o) for o in (out.get("observations") or [])][:3],
    }


def _claude(b64: str) -> dict:
    import anthropic

    client = anthropic.Anthropic(timeout=PROVIDER_TIMEOUT)
    r = client.messages.create(
        model=os.environ.get("COUNTERFEIT_VISION_MODEL", "claude-opus-4-8"),
        max_tokens=400,
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
        f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_VISION_MODEL}:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={
            "contents": [{"parts": [
                {"inline_data": {"mime_type": "image/jpeg", "data": b64}},
                {"text": _PROMPT},
            ]}],
            "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
        },
        timeout=PROVIDER_TIMEOUT,
    )
    r.raise_for_status()
    return _parse(r.json()["candidates"][0]["content"]["parts"][0]["text"])


# Groq's multimodal model. Overridable: Groq rotates model availability often,
# and what an account can reach varies — GET /openai/v1/models lists yours.
# Gemini's model id and the 45s timeouts below come from 466862f ("revive the
# LLM chain — dead Gemini model and timeouts that expired mid-generation").
# Named here so the id lives in ONE place: it was previously repeated in the URL
# and in the chain entry, which is how the two drifted apart in the first place.
GEMINI_VISION_MODEL = os.environ.get("COUNTERFEIT_GEMINI_VISION_MODEL", "gemini-flash-lite-latest")
# A vision request carries an image and can take far longer than a text call.
# 10-12s expired mid-generation and looked like a provider outage.
PROVIDER_TIMEOUT = 45.0

GROQ_VISION_MODEL = os.environ.get("COUNTERFEIT_GROQ_VISION_MODEL", "qwen/qwen3.6-27b")

# Groq's free tier meters TOKENS PER MINUTE (8k on the tier this was built
# against), and an image is the expensive part of the request. Requests/day are
# generous by comparison. So the Groq leg sends a SMALLER image than the other
# providers and caps reasoning tightly — the questions here are "whose face is
# this" and "what does the header say", which do not need a large raster.
GROQ_MAX_SIDE = 512
GROQ_MAX_TOKENS = 600
# Qwen on Groq is a reasoning model: left to itself it spends the ENTIRE
# completion budget inside <think> and returns finish_reason="length" with no
# JSON at all — the layer then reports itself unavailable for what looks like a
# broken call. `reasoning_effort: "none"` suppresses the scratchpad: measured
# 193 completion tokens instead of 1200, and the answer actually arrives. It
# also nearly halves total tokens (1299 vs 2304), which matters against a
# per-minute token quota. Groq accepts only "none" or "default" here.
GROQ_REASONING_EFFORT = os.environ.get("COUNTERFEIT_GROQ_REASONING", "none")


class RateLimited(Exception):
    """Provider refused for quota reasons — distinct from a broken call, and
    reported as such so the payload does not blame the note for a billing limit."""


def _groq(b64: str) -> dict:
    import httpx

    body = {
        "model": GROQ_VISION_MODEL,
        "temperature": 0.1,
        "max_tokens": GROQ_MAX_TOKENS,
        "reasoning_effort": GROQ_REASONING_EFFORT,
        "messages": [{
            "role": "user",
            "content": [
                {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{b64}"}},
                {"type": "text", "text": _PROMPT},
            ],
        }],
    }
    load_env()  # so a direct call (tests, debugging) works like the chain does
    headers = {"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"}
    for attempt in range(2):
        r = httpx.post("https://api.groq.com/openai/v1/chat/completions",
                       headers=headers, json=body, timeout=90.0)
        if r.status_code != 429:
            r.raise_for_status()
            return _parse(r.json()["choices"][0]["message"]["content"])
        # Token buckets refill within the minute; one short wait recovers most
        # bursts. Anything longer belongs to the caller, not to a note scan.
        wait = min(float(r.headers.get("retry-after", 8) or 8), 20.0)
        if attempt == 0 and wait <= 20.0:
            time.sleep(wait)
    raise RateLimited(f"{GROQ_VISION_MODEL} token-per-minute quota exhausted")


def _blank(status: str) -> dict:
    """A review block for the cases where no model looked at the note.

    Returned rather than None so the payload always states whether the semantic
    channel ran. `available: false` is what stops `analyze` from issuing a
    fully-confident `genuine`.
    """
    return {
        "engine": "none",
        "status": status,
        "available": False,
        "portrait_is_gandhi": None,
        "specimen_overprint": None,
        "header_correct": None,
        "printed_denomination": None,
        "serial_text": None,
        "tampering_signs": [],
        "observations": [],
    }


def vision_review_safe(img: Image.Image) -> dict:
    """Always returns a review block; `status`/`available` say whether a model
    actually looked. Never raises."""
    if os.environ.get("COUNTERFEIT_VISION_LLM", "").lower() in ("off", "0", "false"):
        return _blank(DISABLED)
    try:
        load_env()
        chain: list[tuple[str, object, int]] = []
        if os.environ.get("ANTHROPIC_API_KEY"):
            chain.append((os.environ.get("COUNTERFEIT_VISION_MODEL", "claude-opus-4-8"),
                          _claude, MAX_SIDE))
        if os.environ.get("GEMINI_API_KEY"):
            chain.append((GEMINI_VISION_MODEL, _gemini, MAX_SIDE))
        if os.environ.get("GROQ_API_KEY"):
            chain.append((f"groq/{GROQ_VISION_MODEL}", _groq, GROQ_MAX_SIDE))
        if not chain:
            return _blank(NO_KEY)
        rate_limited = False
        encoded: dict[int, str] = {}
        for name, fn, max_side in chain:
            try:
                if max_side not in encoded:
                    encoded[max_side] = _jpeg_b64(img, max_side)
                return {**fn(encoded[max_side]), "engine": name,  # type: ignore[operator]
                        "status": OK, "available": True}
            except RateLimited:
                rate_limited = True
                continue
            except Exception:
                continue
        return _blank(RATE_LIMITED if rate_limited else FAILED)
    except Exception:
        return _blank(FAILED)


def apply_vision_review(payload: dict) -> None:
    """Fold the semantic findings into the verdict. Mutates `payload`.

    Convicts on a wrong portrait or wrong header; caps to `uncertain` on a
    SPECIMEN overprint or a printed denomination that contradicts the optical
    one. Never acquits.
    """
    review = payload.get("vision_review")
    if not review or not review.get("available"):
        return

    # ── conviction: the note's CONTENT is wrong ────────────────────────────
    hard_fail = []
    if review.get("portrait_is_gandhi") is False:
        hard_fail.append("portrait is not Mahatma Gandhi")
    if review.get("header_correct") is False:
        hard_fail.append('header does not read "RESERVE BANK OF INDIA"')
    if hard_fail and payload["verdict"] != "fake":
        payload["verdict"] = "fake"
        payload["confidence"] = 0.90
        # No `missing_features` enum value describes "wrong portrait" — the
        # contract's list is security-feature names. The reason travels in
        # `semantic_failures` instead.
        payload["semantic_failures"] = hard_fail
        return
    if hard_fail:  # already fake — record the reason, leave the verdict alone
        payload["semantic_failures"] = hard_fail

    if payload["verdict"] != "genuine":
        return

    # ── caps: suspicious, but a genuine explanation exists ─────────────────
    blocked = []
    if review.get("specimen_overprint") is True:
        blocked.append("SPECIMEN/COPY overprint — not legal tender, genuine specimens exist")
    printed = review.get("printed_denomination")
    optical = payload.get("denomination")
    if printed and optical not in (None, "unknown") and printed != optical:
        blocked.append(f"printed denomination {printed} does not match detected {optical}")
    if blocked:
        payload["verdict"] = "uncertain"
        payload["confidence"] = 0.75
        payload["semantic_failures"] = blocked


# Backwards-compatible alias for the previous name.
cap_verdict_for_vision = apply_vision_review
