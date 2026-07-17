"""Turn computed routes into something an officer reads.

The engine decides; this only explains. `plausible_routes()` establishes every
fact here — which routes exist, how far, which mode, which FIRs sit on them,
and how plausible each is. The narrator receives those facts and writes prose.
It never ranks, never re-scores, never proposes a route the engine did not
return. Strip this module out and provenance still works, unchanged.

That split is deliberate and matches the rest of the project: deterministic
engines are auditable and survive a courtroom; a generated chain of reasoning
cannot be (see fraud_shield/playbooks.py). Dijkstra/Yen is *correct* on
shortest paths — asking a model to guess what a graph algorithm computed
exactly would be strictly worse, not better.

Fallback chain mirrors fusion/narrator.py: Claude -> Groq -> Gemini ->
template. The template is pure string formatting over the same facts, so with
no API key at all the feature still explains itself. It can never die.
"""

from __future__ import annotations

import os

from pydantic import BaseModel, Field

MODEL = "claude-opus-4-8"

SYSTEM_PROMPT = """You brief Indian police officers on counterfeit-currency (FICN) provenance.

A deterministic routing engine has ALREADY computed which transport routes could
have carried seized notes into a district, and scored each one. You receive those
computed routes as FACTS. Your only job is to explain them in plain English.

Write for an officer glancing at a dashboard:
1. `summary`: 2-4 sentences. Lead with the most plausible entry channel — name the
   mode, the corridor, and the transfer point (e.g. "Most likely entry is rail from
   Howrah via Asansol Jn, then roughly 35 km by road."). Name places and FIR
   references. No jargon.
2. `recommended_actions`: 2-5 short imperative next steps for an investigator
   (e.g. check parcel bookings at a named junction, brief the GRP post at a station,
   pull CCTV on a stretch of highway). Tie each to a place in the FACTS.

STRICT RULES:
- The engine's ranking is final. Never re-rank, never contradict a plausibility
  score, never argue a lower-scored route is really the best.
- Only mention routes, places, modes and FIR refs present in the FACTS. Never
  invent a station, highway, corridor or case reference.
- plausibility is a HYPOTHESIS score, not a probability of guilt and not proof.
  Never say a route is confirmed, certain, or established. Hedge: "most likely",
  "consistent with", "worth checking".
- A high score means "physically plausible and corroborated by seizure history",
  NOT "this is what happened". Nothing here observed the notes moving.
- If the top routes score close together, say the channels are hard to separate
  rather than manufacturing a winner.
- If no FIRs sit on a route, do not imply corroboration exists.
- A banknote carries no origin label. This is investigative direction, not evidence.
"""


class RouteNarrative(BaseModel):
    summary: str = Field(description="2-4 sentence plain-English provenance briefing")
    recommended_actions: list[str] = Field(description="2-5 short imperative next steps")


def _facts_block(facts: dict) -> str:
    import json

    return json.dumps(facts, indent=2, default=str)


def build_facts(district: str, routes: list[dict], seizure_count: int) -> dict:
    """Reduce engine output to the minimum the narrator needs. Passing the raw
    route objects would bury the signal in leg coordinates; this keeps every
    claim the narrator can make anchored to a computed number."""
    return {
        "district": district,
        "seizures_in_district": seizure_count,
        "routes_ranked_by_engine": [
            {
                "rank": i + 1,
                "plausibility": r.get("plausibility"),
                "modes": r.get("modes"),
                "total_km": r.get("total_km"),
                "firs_on_route": r.get("passes_fir", []),
                "path": [
                    {
                        "from": lg["from"],
                        "to": lg["to"],
                        "mode": lg["mode"],
                        "km": lg["distance_km"],
                        "kind": lg["kind"],
                    }
                    for lg in r.get("legs", [])
                ],
            }
            for i, r in enumerate(routes)
        ],
        "scoring_note": (
            "plausibility in [0, 0.9]: 0.45 distance decay + 0.35 mode risk "
            "(rail is the documented primary channel, air is heavily screened) "
            "+ 0.20 FIR corroboration on route. Capped below 1.0 because a route "
            "is a hypothesis — nothing observed the notes moving."
        ),
    }


class TemplateRouteNarrator:
    """No-LLM floor. Formats the same facts deterministically, so the feature
    explains itself with zero API keys and cannot fail."""

    name = "template"

    def narrate(self, facts: dict) -> RouteNarrative:
        routes = facts.get("routes_ranked_by_engine") or []
        district = facts.get("district", "this district")
        if not routes:
            return RouteNarrative(
                summary=(
                    f"No transport route into {district} could be computed from the "
                    "known corridors. Provenance cannot be inferred."
                ),
                recommended_actions=["Record seizure location and denomination for future correlation."],
            )

        top = routes[0]
        modes = " + ".join(top.get("modes") or []) or "unknown"
        hauls = [lg for lg in top.get("path", []) if lg.get("kind") == "haul"]
        access = [lg for lg in top.get("path", []) if lg.get("kind") == "access"]
        origin = hauls[0]["from"] if hauls else (top.get("path") or [{}])[0].get("from", "unknown")
        n_fir = len(top.get("firs_on_route") or [])

        bits = [
            f"Most plausible entry into {district} is {modes} from {origin} "
            f"({top.get('total_km')} km, plausibility {top.get('plausibility')})."
        ]
        if access:
            a = access[-1]
            bits.append(f"Last leg is roughly {a['km']} km by {a['mode']} from {a['from']}.")
        if n_fir:
            bits.append(
                f"{n_fir} FICN case(s) on record sit on this route: "
                f"{', '.join((top.get('firs_on_route') or [])[:3])}."
            )
        else:
            bits.append("No FICN cases on record sit on this route — no corroboration.")
        if len(routes) > 1:
            second = routes[1]
            gap = (top.get("plausibility") or 0) - (second.get("plausibility") or 0)
            if gap < 0.05:
                bits.append(
                    f"A {' + '.join(second.get('modes') or [])} route scores "
                    f"{second.get('plausibility')} — too close to separate the channels."
                )
        bits.append("Investigative direction only — a banknote carries no origin label.")

        actions = []
        if hauls:
            actions.append(f"Check consignment and parcel bookings at {hauls[0]['from']}.")
        if access:
            actions.append(f"Brief the post at {access[-1]['from']} on the last-mile leg.")
        if n_fir:
            actions.append("Pull the FICN case files on this route for shared handlers.")
        actions.append(f"Correlate future {district} seizures to test this channel.")

        return RouteNarrative(summary=" ".join(bits), recommended_actions=actions[:5])


class ClaudeRouteNarrator:
    name = f"{MODEL}"

    def __init__(self) -> None:
        import anthropic

        self._client = anthropic.Anthropic()

    def narrate(self, facts: dict) -> RouteNarrative:
        response = self._client.messages.parse(
            model=MODEL,
            max_tokens=4000,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": "FACTS:\n" + _facts_block(facts)}],
            output_format=RouteNarrative,
        )
        return response.parsed_output


_JSON_INSTRUCTION = (
    "\n\nRespond with ONLY a JSON object, no markdown fences, matching exactly:\n"
    '{"summary": "<2-4 sentences>", "recommended_actions": ["<action>", ...]}'
)


def _parse_json(text: str) -> RouteNarrative:
    import json as _json

    text = text.strip()
    if text.startswith("```"):
        text = text.strip("`")
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0] if "```" in text else text
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1 or end < start:
        raise ValueError(f"no JSON object in narrator response: {text[:120]!r}")
    return RouteNarrative(**_json.loads(text[start : end + 1]))


class GroqRouteNarrator:
    name = "groq/llama-3.3-70b"

    def __init__(self) -> None:
        self._key = os.environ["GROQ_API_KEY"]

    def narrate(self, facts: dict) -> RouteNarrative:
        import httpx

        r = httpx.post(
            "https://api.groq.com/openai/v1/chat/completions",
            headers={"Authorization": f"Bearer {self._key}"},
            json={
                "model": "llama-3.3-70b-versatile",
                "max_tokens": 1024,
                "messages": [
                    {"role": "system", "content": SYSTEM_PROMPT + _JSON_INSTRUCTION},
                    {"role": "user", "content": "FACTS:\n" + _facts_block(facts)},
                ],
            },
            timeout=30.0,
        )
        r.raise_for_status()
        return _parse_json(r.json()["choices"][0]["message"]["content"])


class GeminiRouteNarrator:
    name = "gemini-2.0-flash"

    def __init__(self) -> None:
        self._key = os.environ["GEMINI_API_KEY"]

    def narrate(self, facts: dict) -> RouteNarrative:
        import httpx

        r = httpx.post(
            "https://generativelanguage.googleapis.com/v1beta/models/"
            f"gemini-2.0-flash:generateContent?key={self._key}",
            json={
                "system_instruction": {"parts": [{"text": SYSTEM_PROMPT + _JSON_INSTRUCTION}]},
                "contents": [{"parts": [{"text": "FACTS:\n" + _facts_block(facts)}]}],
            },
            timeout=30.0,
        )
        r.raise_for_status()
        return _parse_json(r.json()["candidates"][0]["content"]["parts"][0]["text"])


def _load_dotenv() -> None:
    """Reuse the fusion .env (gitignored) so one key file serves both narrators."""
    from pathlib import Path

    for parents_up in (3, 4):
        try:
            root = Path(__file__).resolve().parents[parents_up]
        except IndexError:
            continue
        env_file = root / "fusion" / ".env"
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, value = line.partition("=")
                    os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))
            return


def narrate_routes_safe(facts: dict) -> tuple[RouteNarrative, str]:
    """Best available narrator; on ANY failure fall through to the template.
    Returns (narrative, engine_name). Never raises — the caller always gets prose."""
    _load_dotenv()
    chain: list = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        chain.append(ClaudeRouteNarrator)
    if os.environ.get("GROQ_API_KEY"):
        chain.append(GroqRouteNarrator)
    if os.environ.get("GEMINI_API_KEY"):
        chain.append(GeminiRouteNarrator)
    chain.append(TemplateRouteNarrator)
    for cls in chain:
        try:
            n = cls()
            return n.narrate(facts), n.name
        except Exception:
            continue
    t = TemplateRouteNarrator()
    return t.narrate(facts), t.name
