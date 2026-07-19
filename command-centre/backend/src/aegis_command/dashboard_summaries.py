import json
import os
from collections import Counter
from typing import Any

_SYSTEM = """You are the Aegis Public Safety Intelligence AI.
You write the intelligence briefing shown on an operational law-enforcement dashboard.

You receive a structured snapshot: scam detections (counts, scam types, districts,
risk scores, behavioural markers), counterfeit findings (verdicts, denominations,
districts, which security features failed) and fraud-ring topology (ring count,
account totals, rupee value, ring archetypes, districts, risk scores).

Output a strictly valid JSON object with exactly these two keys:

1. "modules_overview" — 4 to 6 sentences on the scam and counterfeit landscape.
   Name the dominant scam type and the districts involved, cite the risk scores,
   and say what the failed note-security features and repeated denominations
   suggest about the source. Finish with what an analyst should look at next.

2. "rings_summary" — 4 to 6 sentences on the fraud-ring topology. Name the ring
   archetypes present (mule collection hub, layering chain, round-tripping
   cycle), what each one means operationally, how many accounts and how much
   money are involved, and where they concentrate geographically. Note any
   district that appears in BOTH the scam/counterfeit data and the ring data —
   that overlap is the strongest lead available.

Rules:
- Analytical and professional. Written for an investigator, not a press release.
- Use ONLY the values in the snapshot. Never invent districts, amounts, numbers,
  arrests, timelines, or trends. You have a single snapshot, not a time series,
  so do not describe anything as "rising", "falling" or "accelerating".
- If a category is empty, say so plainly rather than padding.
- Do not use markdown, headings or bullet points — plain prose only.
"""


def build_context(scams: list, counterfeits: list, fraud_graph: dict) -> dict:
    """Condense the live event stream into the facts the briefing is built from.

    The endpoint used to pass three integers, which is why the briefing could
    only ever restate counts. Everything here is derived from the data — no
    thresholds, no interpretation — so the model has real material to work with
    and the deterministic fallback has the same material to fall back on.
    """
    def districts(items: list) -> list[str]:
        seen = {
            (i.get("location_hint") or {}).get("district")
            for i in items
            if (i.get("location_hint") or {}).get("district")
        }
        return sorted(seen)

    flagged = [s for s in scams if s.get("verdict") != "legit"]
    fakes = [c for c in counterfeits if c.get("verdict") == "fake"]
    rings = fraud_graph.get("rings", []) or []

    scam_risks = [s.get("risk_score") for s in flagged if isinstance(s.get("risk_score"), (int, float))]
    markers = Counter(m for s in flagged for m in (s.get("markers") or []))
    missing = Counter(f for c in fakes for f in (c.get("missing_features") or []))
    ring_risks = [r.get("risk_score") for r in rings if isinstance(r.get("risk_score"), (int, float))]

    scam_districts = districts(flagged)
    note_districts = districts(fakes)
    ring_districts = sorted({r.get("district") for r in rings if r.get("district")})

    return {
        "scams": {
            "total": len(scams),
            "flagged": len(flagged),
            "by_type": dict(Counter(s.get("scam_type") for s in flagged if s.get("scam_type"))),
            "districts": scam_districts,
            "max_risk": max(scam_risks, default=None),
            "avg_risk": round(sum(scam_risks) / len(scam_risks), 3) if scam_risks else None,
            "top_markers": [m for m, _ in markers.most_common(6)],
        },
        "counterfeits": {
            "total": len(counterfeits),
            "fake": len(fakes),
            "by_denomination": dict(Counter(c.get("denomination") for c in fakes if c.get("denomination"))),
            "districts": note_districts,
            "top_missing_security_features": [f for f, _ in missing.most_common(6)],
        },
        "rings": {
            "total": len(rings),
            "accounts": sum(r.get("size") or 0 for r in rings),
            "total_amount_inr": sum(r.get("total_amount") or 0 for r in rings),
            "by_archetype": dict(Counter(r.get("label") for r in rings if r.get("label"))),
            "districts": ring_districts,
            "max_risk": max(ring_risks, default=None),
        },
        # Districts carrying BOTH a detection and a ring — the cross-domain lead.
        "overlap_districts": sorted(
            set(scam_districts + note_districts) & set(ring_districts)
        ),
    }

def _parse_json_reply(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in LLM reply")
    out = json.loads(text[start:end + 1])
    for key in ("modules_overview", "rings_summary"):
        if key not in out:
            raise ValueError(f"LLM reply missing '{key}'")
    return out

def _claude(data: dict) -> dict:
    import anthropic
    # Explicit timeout: this endpoint is auto-fetched by the dashboard on every
    # data change — the SDK's default (10 min) would freeze the panel instead
    # of falling through the chain.
    client = anthropic.Anthropic(timeout=15.0)
    r = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=1400,
        system=_SYSTEM,
        messages=[{"role": "user", "content": "SYSTEM DATA:\n" + json.dumps(data, default=str)}],
    )
    return _parse_json_reply("".join(b.text for b in r.content if b.type == "text"))

def _groq(data: dict) -> dict:
    import httpx
    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ['GROQ_API_KEY']}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.2,
            "max_tokens": 1400,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": "SYSTEM DATA:\n" + json.dumps(data, default=str)},
            ],
        },
        timeout=10.0,
    )
    r.raise_for_status()
    return _parse_json_reply(r.json()["choices"][0]["message"]["content"])

def _gemini(data: dict) -> dict:
    import httpx
    r = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={
            "system_instruction": {"parts": [{"text": _SYSTEM}]},
            "contents": [{"parts": [{"text": "SYSTEM DATA:\n" + json.dumps(data, default=str)}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        },
        timeout=10.0,
    )
    r.raise_for_status()
    return _parse_json_reply(r.json()["candidates"][0]["content"]["parts"][0]["text"])

def generate_summaries(data: dict) -> dict:
    try:
        from aegis_fusion.narrator import _load_dotenv
        _load_dotenv()
    except Exception:
        pass

    chain: list[tuple[str, Any]] = []
    if os.environ.get("ANTHROPIC_API_KEY"):
        chain.append(("claude-opus-4-8", _claude))
    if os.environ.get("GROQ_API_KEY"):
        chain.append(("groq/llama-3.3-70b", _groq))
    if os.environ.get("GEMINI_API_KEY"):
        chain.append(("gemini-2.0-flash", _gemini))

    for name, fn in chain:
        try:
            res = fn(data)
            res["engine"] = name
            return res
        except Exception as e:
            print(f"Fallback failed for {name}: {e}")
            continue

    # Deterministic floor: states only what the snapshot literally contains —
    # never invents methodology or findings. Reads the same enriched context the
    # model gets, so losing every provider costs detail, not correctness.
    s = data.get("scams") or {}
    c = data.get("counterfeits") or {}
    r = data.get("rings") or {}
    overlap = data.get("overlap_districts") or []

    def listed(values: list, empty: str = "no district recorded") -> str:
        values = [str(v) for v in values if v]
        if not values:
            return empty
        if len(values) == 1:
            return values[0]
        return ", ".join(values[:-1]) + f" and {values[-1]}"

    def counted(mapping: dict) -> str:
        if not mapping:
            return ""
        return listed([f"{k.replace('_', ' ')} ({v})" for k, v in mapping.items()])

    flagged, fakes, rings = s.get("flagged", 0), c.get("fake", 0), r.get("total", 0)

    modules = [
        f"Fraud Shield has flagged {flagged} scam signal{'' if flagged == 1 else 's'} "
        f"and Counterfeit Vision has confirmed {fakes} fake note{'' if fakes == 1 else 's'}."
    ]
    if s.get("by_type"):
        modules.append(f"Scam activity breaks down as {counted(s['by_type'])}, seen in {listed(s.get('districts', []))}.")
    if s.get("max_risk") is not None:
        modules.append(f"The highest scam risk score in this snapshot is {s['max_risk']}.")
    if s.get("top_markers"):
        modules.append(f"Recurring behavioural markers: {listed(s['top_markers'])}.")
    if c.get("by_denomination"):
        denoms = listed([f"Rs {k} x{v}" for k, v in c["by_denomination"].items()])
        modules.append(f"Fake notes recovered: {denoms}, across {listed(c.get('districts', []))}.")
    if c.get("top_missing_security_features"):
        modules.append(f"The security features failing most often are {listed(c['top_missing_security_features'])}.")
    modules.append("No AI provider is reachable, so this briefing is computed directly from the live event stream.")

    ring_text = [
        f"The graph engine is tracking {rings} fraud ring{'' if rings == 1 else 's'} "
        f"covering {r.get('accounts', 0)} accounts."
    ]
    if r.get("total_amount_inr"):
        ring_text.append(f"Combined traced value is Rs {r['total_amount_inr']:,}.")
    if r.get("by_archetype"):
        ring_text.append(f"Ring archetypes present: {counted(r['by_archetype'])}.")
    if r.get("districts"):
        ring_text.append(f"Activity concentrates in {listed(r['districts'])}.")
    if r.get("max_risk") is not None:
        ring_text.append(f"The highest ring risk score is {r['max_risk']}.")
    if overlap:
        one = len(overlap) == 1
        ring_text.append(
            f"{listed(overlap)} {'carries' if one else 'carry'} both detections and ring activity, "
            f"making {'it' if one else 'them'} the strongest cross-domain {'lead' if one else 'leads'}."
        )
    ring_text.append("AI narrative synthesis resumes when a provider is reachable.")

    return {
        "modules_overview": " ".join(modules),
        "rings_summary": " ".join(ring_text),
        "engine": "template-fallback",
    }
