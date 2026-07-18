import json
import os
from typing import Any

_SYSTEM = """You are the Aegis Public Safety Intelligence AI.
Your job is to generate a brief, authoritative intelligence summary based on the current system data.
You will receive the current counts of Scams, Counterfeits, and Fraud Rings.
You must output a strictly valid JSON object with exactly these two keys:
1. "modules_overview": A short 2-3 sentence summary of the scam and counterfeit threat landscape.
2. "rings_summary": A short 2-3 sentence analysis of the fraud ring topology.

Be concise, analytical, and professional. Do not invent data, just synthesize the numbers provided.
"""

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
        max_tokens=500,
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
            "max_tokens": 500,
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

    # Deterministic floor: counts only — never invent methodology or findings
    # the data does not contain.
    scams, fakes, rings = data.get("scams", 0), data.get("counterfeits", 0), data.get("rings", 0)
    return {
        "modules_overview": (
            f"The Fraud Shield module has flagged {scams} potential scam{'' if scams == 1 else 's'}, "
            f"while the Counterfeit Vision module has detected {fakes} fake note{'' if fakes == 1 else 's'}. "
            "No AI provider is reachable — this overview is generated directly from current system counts."
        ),
        "rings_summary": (
            f"The Graph ML engine is currently tracking {rings} fraud ring{'' if rings == 1 else 's'} "
            "across the monitored districts. Figures update as new detections stream in; "
            "AI narrative synthesis resumes when a provider is reachable."
        ),
        "engine": "template-fallback"
    }
