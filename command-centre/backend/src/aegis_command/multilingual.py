"""Citizen Fraud Shield — multilingual advisory via Sarvam AI.

The illustrative "advisory in 12 regional languages" is a *transport/translation*
concern, not a new model: a citizen's message is translated to English, run through
the existing Fraud Shield classifier, and the verdict + safety advisory are
translated back into the citizen's language. This is a wrapper, not a retrain.

Sarvam AI (api.sarvam.ai/translate) does the translation. The key loads from a
gitignored `.env` (SARVAM_API_KEY). Every call fails SAFE: on no key / network
error, the text passes through untranslated (English), so the scam verdict — the
thing that actually protects the citizen — is never blocked by a translation
outage. Nothing here is faked: if translation did not happen, `translated` is false.
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

SARVAM_URL = "https://api.sarvam.ai/translate"
BACKEND_ROOT = Path(__file__).resolve().parents[2]  # command-centre/backend/

# English + 11 scheduled Indian languages = the "12 languages". Sarvam codes.
LANGUAGES: dict[str, str] = {
    "en-IN": "English",
    "hi-IN": "Hindi",
    "bn-IN": "Bengali",
    "ta-IN": "Tamil",
    "te-IN": "Telugu",
    "mr-IN": "Marathi",
    "gu-IN": "Gujarati",
    "kn-IN": "Kannada",
    "ml-IN": "Malayalam",
    "pa-IN": "Punjabi",
    "od-IN": "Odia",
    "as-IN": "Assamese",
}


def _load_env() -> None:
    """Minimal .env reader — loads SARVAM_API_KEY without adding a dependency.
    Does not override an already-set process env var."""
    p = BACKEND_ROOT / ".env"
    if not p.exists():
        return
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())
    except OSError:
        pass


def sarvam_key() -> str | None:
    _load_env()
    return os.environ.get("SARVAM_API_KEY")


def translate(text: str, target: str, source: str = "auto") -> tuple[str, str, bool]:
    """Translate `text` into `target`. Returns (translated_text, detected_source, ok).

    Fails safe: on no key / same language / network error, returns the input text
    unchanged with ok=False, so the caller can be honest about whether translation
    actually happened.
    """
    text = (text or "").strip()
    if not text:
        return text, source, False
    if target == source:
        return text, source, True
    key = sarvam_key()
    if not key:
        return text, source, False
    try:
        with httpx.Client(timeout=8.0) as client:
            r = client.post(
                SARVAM_URL,
                headers={"api-subscription-key": key, "Content-Type": "application/json"},
                # Sarvam caps input length; a scam message / short advisory fits well under.
                json={
                    "input": text[:900],
                    "source_language_code": source,
                    "target_language_code": target,
                },
            )
            r.raise_for_status()
            d = r.json()
            return d.get("translated_text", text), d.get("source_language_code", source), True
    except (httpx.HTTPError, ValueError):
        return text, source, False


def build_advisory(verdict: str, scam_type: str | None, risk_score: float) -> str:
    """Plain-English citizen advisory from the deterministic verdict. Factual and
    safety-first — never tells the citizen anything the classifier did not support."""
    pct = round(float(risk_score) * 100)
    kind = (scam_type or "scam").replace("_", " ")
    if verdict == "scam":
        return (
            f"WARNING: this looks like a {kind} scam (risk {pct}%). Do NOT pay money or share "
            "any OTP, PIN, or password. No real police, CBI, or bank officer arrests you over a "
            "call or video, or asks you to move money to a 'safe account'. Hang up and report "
            "free on 1930 or at cybercrime.gov.in."
        )
    if verdict == "suspicious":
        return (
            f"CAUTION: this message has {kind} scam warning signs (risk {pct}%). Do not share "
            "OTP/PIN or pay anything until you independently verify the caller. When unsure, "
            "call 1930."
        )
    return (
        "No strong scam signals were found in this message. Stay careful anyway: never share "
        "your OTP or PIN, and if anything feels urgent or threatening, call 1930 to check."
    )
