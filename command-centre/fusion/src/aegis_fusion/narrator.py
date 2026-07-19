"""Narrator: turns established correlations into a human-readable intelligence
summary + recommended actions.

Two implementations:
- **ClaudeNarrator** — the real Gen AI layer (model: claude-opus-4-8, structured
  output via pydantic so the response is guaranteed parseable).
- **TemplateNarrator** — deterministic fallback used when ANTHROPIC_API_KEY is
  absent or the API call fails. The demo must never die on stage.

The narrator only ever sees FACTS the correlator established. It is instructed
not to invent links — that keeps the output defensible ("the LLM writes prose,
the evidence comes from the engine").
"""

from __future__ import annotations

import os
import re
import time

from pydantic import BaseModel, Field

from . import PROMPT_VERSION

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """\
You are the intelligence narrator for Aegis, a digital public-safety command centre
used by police and financial-crime investigators in India.

You receive structured FACTS: scam-call detections, counterfeit-currency seizures,
detected fraud rings, and the concrete links between them that a correlation engine
has already established.

Write for an officer glancing at a dashboard:
1. `summary`: 2-4 sentences, plain English, lead with the most important correlated
   finding (e.g. "This scam call is linked to a fraud ring active in Alwar, where a
   counterfeit ₹500 note was also seized."). Mention districts by name. No jargon.
2. `recommended_actions`: 2-5 short imperative next steps an investigator could take
   (freeze accounts, alert bank branches in a district, notify telecom provider,
   escalate to cybercrime cell).

STRICT RULES:
- Only reference links present in the FACTS. Never invent connections.
- If there are no cross-domain links, say the signals appear isolated.
- Keep every claim traceable to a fact (use the district names and ring labels given).
- A link of kind "scam-ring-payment" is a TRACED MONEY TRAIL — the victim's reported
  payment was matched to a transaction landing in a named ring account. It is the
  strongest evidence available and must LEAD the summary (name the amount and account).
  This match is on amount + timing, NOT district — mule rings often operate far from
  their victims by design, so do not assume or claim the ring and victim are co-located
  unless the fact explicitly says same_district is true.
"""


class Narrative(BaseModel):
    summary: str = Field(description="2-4 sentence plain-English intelligence summary")
    recommended_actions: list[str] = Field(description="2-5 short imperative next steps")


def _facts_block(facts: dict) -> str:
    import json

    return json.dumps(facts, indent=2, default=str)


class TemplateNarrator:
    """Deterministic fallback — no API key required."""

    name = "template-fallback"

    def narrate(self, facts: dict) -> Narrative:
        links = facts.get("links", [])
        rings = facts.get("rings", [])
        scams = facts.get("scams", [])
        notes = facts.get("counterfeits", [])
        threat = facts.get("threat_level", "low")

        if links:
            # Name the district where links actually occurred — never a district
            # from an unlinked ring (the narrative must stay evidence-accurate).
            link_districts = sorted({l.get("district") for l in links if l.get("district")})
            where = link_districts[0] if link_districts else "the monitored area"
            parts = []
            trails = [l for l in links if l.get("kind") == "scam-ring-payment"]
            if trails:
                t = trails[0]
                ring_where = t.get("ring_district")
                victim_where = t.get("district")
                if t.get("same_district"):
                    place = f"in {ring_where}, the same district as the victim"
                elif ring_where and victim_where:
                    place = f"in {ring_where} — victim was in {victim_where}, hundreds of km away"
                elif ring_where:
                    place = f"in {ring_where}"
                else:
                    place = "in an unlisted district"
                parts.append(
                    f"a victim's payment of ₹{t['amount']:,.0f} made after a scam call was "
                    f"traced into collection account {t['account']} of {t['ring']} {place}"
                )
            if any(l["kind"] == "scam-ring" for l in links):
                parts.append(f"an active scam call is linked to a fraud ring operating in {where}")
            if any(l["kind"] in ("scam-counterfeit", "counterfeit-ring") for l in links):
                parts.append(f"a counterfeit note was seized in the same area")
            summary = (
                f"Threat level {threat.upper()}: " + " and ".join(parts) +
                ". Overlapping signals across independent detection systems indicate a "
                "coordinated operation."
            )
        elif scams or notes or rings:
            summary = (
                f"Threat level {threat.upper()}: {len(scams)} scam signal(s), "
                f"{len(notes)} counterfeit detection(s), and {len(rings)} fraud ring(s) "
                "detected. No cross-domain links established yet; signals appear isolated."
            )
        else:
            summary = "No active threats detected across the monitored signal streams."

        actions = []
        trail_links = [l for l in links if l.get("kind") == "scam-ring-payment"]
        if trail_links:
            t = trail_links[0]
            actions.append(
                f"Freeze account {t['account']} immediately and request transaction "
                "reversal through the bank's nodal officer."
            )
        if rings:
            # Prefer the ring that is actually implicated in a link; fall back to
            # the highest-risk ring only when nothing is linked.
            linked_ring_ids = {l.get("ring") for l in links if l.get("ring")}
            implicated = [r for r in rings if r.get("ring_id") in linked_ring_ids] or rings
            top = implicated[0]
            actions.append(
                f"Request account freezes for {top.get('size', 'the')} accounts in "
                f"{top.get('ring_id', 'the detected ring')} ({top.get('label', 'fraud ring')})."
            )
        if scams:
            actions.append("Notify the telecom provider to flag/block the originating number.")
        if notes:
            actions.append("Alert bank branches in the affected district to re-verify deposits.")
        if links:
            actions.append("Escalate the correlated intelligence package to the district cybercrime cell.")
        if not actions:
            actions = ["Continue monitoring all three signal streams."]
        return Narrative(summary=summary, recommended_actions=actions[:5])


class ClaudeNarrator:
    """Anthropic narrator — first choice when ANTHROPIC_API_KEY is set."""

    name = f"{MODEL}+prompt-v{PROMPT_VERSION}"

    def __init__(self) -> None:
        import anthropic

        self._client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY from env

    def narrate(self, facts: dict) -> Narrative:
        response = self._client.messages.parse(
            model=MODEL,
            max_tokens=16000,
            system=SYSTEM_PROMPT,
            messages=[
                {
                    "role": "user",
                    "content": "FACTS:\n" + _facts_block(facts),
                }
            ],
            output_format=Narrative,
        )
        return response.parsed_output


# JSON-only instruction appended for providers without native pydantic parsing.
_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY a JSON object, no markdown fences, matching exactly:\n"
    '{"summary": "<2-4 sentence summary>", "recommended_actions": ["<action>", ...]}'
)


def _parse_json_narrative(text: str) -> Narrative:
    import json as _json

    text = text.strip()
    if text.startswith("```"):  # tolerate fenced output anyway
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0] if "```" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        # No JSON object in the response — raise a clear error instead of slicing
        # garbage. narrate_safe() catches this and falls through to the next provider.
        raise ValueError(f"no JSON object in narrator response: {text[:120]!r}")
    return Narrative(**_json.loads(text[start : end + 1]))


class GroqNarrator:
    """Groq-hosted open model (OpenAI-compatible API). Fast + free tier."""

    GROQ_MODEL = "llama-3.3-70b-versatile"
    name = f"groq/{GROQ_MODEL}+prompt-v{PROMPT_VERSION}"

    def __init__(self, env_key: str = "GROQ_API_KEY") -> None:
        # Which key slot this instance uses. Groq's free tier caps tokens per
        # DAY (100k), so one key runs dry mid-demo; separate keys have separate
        # budgets and are tried in turn. The slot is carried into `name` so the
        # audit trail records which one actually produced the narrative.
        self._key = os.environ[env_key]
        suffix = env_key.removeprefix("GROQ_API_KEY").lstrip("_")
        self.name = (
            f"groq{'#' + suffix if suffix else ''}/{self.GROQ_MODEL}+prompt-v{PROMPT_VERSION}"
        )

    def narrate(self, facts: dict) -> Narrative:
        import httpx

        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": self.GROQ_MODEL,
                "temperature": 0.2,
                "max_tokens": 1024,
                "response_format": {"type": "json_object"},
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT + _JSON_INSTRUCTION},
                    {"role": "user", "content": "FACTS:\n" + _facts_block(facts)},
                ],
            },
            timeout=30.0,
        )
        r.raise_for_status()
        return _parse_json_narrative(r.json()["choices"][0]["message"]["content"])


class GeminiNarrator:
    """Google Gemini via the Generative Language REST API."""

    GEMINI_MODEL = "gemini-2.0-flash"
    name = f"gemini/{GEMINI_MODEL}+prompt-v{PROMPT_VERSION}"

    def __init__(self) -> None:
        self._key = os.environ["GEMINI_API_KEY"]

    def narrate(self, facts: dict) -> Narrative:
        import httpx

        r = httpx.post(
            f"https://generativelanguage.googleapis.com/v1beta/models/{self.GEMINI_MODEL}:generateContent",
            headers={"x-goog-api-key": self._key},
            json={
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT + _JSON_INSTRUCTION}]},
                "contents": [{"parts": [{"text": "FACTS:\n" + _facts_block(facts)}]}],
                "generationConfig": {
                    "temperature": 0.2,
                    "responseMimeType": "application/json",
                },
            },
            timeout=30.0,
        )
        r.raise_for_status()
        return _parse_json_narrative(r.json()["candidates"][0]["content"]["parts"][0]["text"])


def _load_dotenv() -> None:
    """Load command-centre/fusion/.env (gitignored) if present — lets Prayag
    drop ANTHROPIC_API_KEY in a file instead of setting a system env var."""
    from pathlib import Path

    env_file = Path(__file__).resolve().parents[2] / ".env"
    if not env_file.exists():
        return
    for line in env_file.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def get_narrator() -> TemplateNarrator | ClaudeNarrator | GroqNarrator | GeminiNarrator:
    """Pick the best available narrator: Claude > Groq > Gemini > template.
    Construction never raises; call-time failures are handled by narrate_safe."""
    _load_dotenv()
    for factory in _available_narrators():
        try:
            return factory()
        except Exception as exc:
            print(
                f"[narrator] {getattr(factory, '__name__', 'provider')} construction "
                f"failed: {type(exc).__name__}: {exc}",
                flush=True,
            )
            continue
    return TemplateNarrator()


# A rate-limited provider is worth waiting for; a broken one is not. Bounded so
# a user who clicked "Run Fusion" never waits on a hang.
_MAX_RETRY_WAIT_S = 12.0

# Provider order: Claude, then the first Groq key, then Gemini, then the spare
# Groq keys. Groq's free tier caps tokens per DAY, so one key is exhausted by a
# few hours of demoing — the spares are separate accounts with separate daily
# budgets, deliberately placed AFTER Gemini so a Gemini window that has rolled
# over is preferred over burning a reserve key.
_PROVIDER_CHAIN: tuple[tuple[str, str], ...] = (
    ("ANTHROPIC_API_KEY", "claude"),
    ("GROQ_API_KEY", "groq"),
    ("GEMINI_API_KEY", "gemini"),
    ("GROQ_API_KEY_2", "groq"),
    ("GROQ_API_KEY_3", "groq"),
)


def _available_narrators() -> list:
    """Narrator factories for every provider whose key is set, in chain order."""
    factories: list = []
    for env_key, kind in _PROVIDER_CHAIN:
        if not os.environ.get(env_key):
            continue
        if kind == "claude":
            factories.append(ClaudeNarrator)
        elif kind == "gemini":
            factories.append(GeminiNarrator)
        else:  # groq — bind the specific key slot this entry refers to
            factory = lambda k=env_key: GroqNarrator(k)  # noqa: E731
            # Without this the failure log reads "<lambda> failed", which hides
            # WHICH key slot ran out — the one thing you need from that line.
            factory.__name__ = f"GroqNarrator[{env_key}]"
            factories.append(factory)
    return factories


def _duration_seconds(raw: str) -> float | None:
    """Parse the duration formats these APIs use: '5.345s', '1m26.4s', '3'."""
    raw = raw.strip()
    if not raw:
        return None
    try:
        return float(raw)  # plain seconds, e.g. Retry-After: 3
    except ValueError:
        pass
    match = re.fullmatch(r"(?:(\d+(?:\.\d+)?)m)?(?:(\d+(?:\.\d+)?)s)?", raw)
    if not match or not any(match.groups()):
        return None
    minutes, seconds = match.groups()
    return float(minutes or 0) * 60 + float(seconds or 0)


def _rate_limit_wait(exc: Exception) -> float | None:
    """Seconds to wait before retrying this provider, or None if not worth it.

    Groq's free tier caps tokens-per-minute, but the budget REFILLS
    CONTINUOUSLY — x-ratelimit-reset-tokens is typically ~5s, not 60. So two
    panels generating at once exhaust it briefly and the next attempt succeeds.
    Falling straight to the template threw away a briefing that was seconds
    from being available.

    Returns None for anything that is not a 429, or when the provider asks for
    longer than we are willing to make the user wait.
    """
    response = getattr(exc, "response", None)
    if response is None or getattr(response, "status_code", None) != 429:
        return None
    for header in ("retry-after", "x-ratelimit-reset-tokens", "x-ratelimit-reset-requests"):
        raw = response.headers.get(header) if hasattr(response, "headers") else None
        if not raw:
            continue
        seconds = _duration_seconds(str(raw))
        if seconds is not None and seconds <= _MAX_RETRY_WAIT_S:
            return min(seconds, _MAX_RETRY_WAIT_S) + 0.5  # cushion past the boundary
    return None


def narrate_safe(facts: dict) -> tuple[Narrative, str]:
    """Run the best narrator; on ANY failure fall through the chain down to the
    template. Returns (narrative, narrator_name) — the demo can never die."""
    _load_dotenv()
    chain: list = [*_available_narrators(), TemplateNarrator]
    for cls in chain:
        retried = False
        while True:
            try:
                narrator = cls()
                return narrator.narrate(facts), narrator.name
            except Exception as exc:
                wait = None if retried else _rate_limit_wait(exc)
                if wait is not None:
                    print(
                        f"[narrator] {cls.__name__} rate-limited; retrying in {wait:.1f}s",
                        flush=True,
                    )
                    time.sleep(wait)
                    retried = True
                    continue  # same provider, one more attempt
                # Log, then fall through. Swallowing this silently made a
                # provider that was rate-limited or misconfigured look identical
                # to one that was simply absent: the fusion card reported
                # "template-fallback" with nothing anywhere saying why. The
                # chain still cannot break the demo.
                print(
                    f"[narrator] {cls.__name__} failed: {type(exc).__name__}: {exc}",
                    flush=True,
                )
                break  # next provider in the chain
    # unreachable — TemplateNarrator cannot fail — but keep a hard floor anyway
    t = TemplateNarrator()
    return t.narrate(facts), t.name
