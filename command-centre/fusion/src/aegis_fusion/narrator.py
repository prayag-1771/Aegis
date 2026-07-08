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
    return Narrative(**_json.loads(text[start : end + 1]))


class GroqNarrator:
    """Groq-hosted open model (OpenAI-compatible API). Fast + free tier."""

    GROQ_MODEL = "llama-3.3-70b-versatile"
    name = f"groq/{GROQ_MODEL}+prompt-v{PROMPT_VERSION}"

    def __init__(self) -> None:
        self._key = os.environ["GROQ_API_KEY"]

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
    for env_key, cls in (
        ("ANTHROPIC_API_KEY", ClaudeNarrator),
        ("GROQ_API_KEY", GroqNarrator),
        ("GEMINI_API_KEY", GeminiNarrator),
    ):
        if os.environ.get(env_key):
            try:
                return cls()
            except Exception:
                continue
    return TemplateNarrator()


def narrate_safe(facts: dict) -> tuple[Narrative, str]:
    """Run the best narrator; on ANY failure fall through the chain down to the
    template. Returns (narrative, narrator_name) — the demo can never die."""
    _load_dotenv()
    chain: list = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        chain.append(ClaudeNarrator)
    if os.environ.get("GROQ_API_KEY"):
        chain.append(GroqNarrator)
    if os.environ.get("GEMINI_API_KEY"):
        chain.append(GeminiNarrator)
    chain.append(TemplateNarrator)
    for cls in chain:
        try:
            narrator = cls()
            return narrator.narrate(facts), narrator.name
        except Exception:
            continue
    # unreachable — TemplateNarrator cannot fail — but keep a hard floor anyway
    t = TemplateNarrator()
    return t.narrate(facts), t.name
