"""AI Case Officer — one click turns a district's signals into a case brief.

Two strictly separated layers (the project's evidence-hierarchy rule):

1. `build_dossier()` — DETERMINISTIC evidence gathering. Runs every analysis
   "tool" over the district: scam events, fraud rings, seizures, plate
   families, scam campaigns, the supply trail + temporal flow. Every item in
   the dossier is real module output, so the dossier itself is auditable.

2. `write_case_file_safe()` — the GenAI layer. An LLM (Claude → Groq → Gemini,
   same fallback chain as the fusion narrator) reads ONLY the dossier and
   writes the brief: summary, timeline, a *hedged* hypothesis, and recommended
   actions, each citing dossier evidence ids. A deterministic template writer
   guarantees a brief even with zero API keys — the demo never dies.

The LLM never invents evidence: the prompt forbids references outside the
dossier, and the template path proves the feature works without any LLM.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any

from .intel import plate_families, scam_campaigns

# ── layer 1: deterministic dossier ──────────────────────────────────────────


def _in_district(obj: dict, district: str) -> bool:
    d = ((obj.get("location_hint") or {}).get("district") or obj.get("district") or "")
    return d.lower() == district.lower()


def build_dossier(
    district: str,
    scams: list[dict],
    counterfeits: list[dict],
    fraud_graph: dict | None,
    trail: dict | None = None,
) -> dict:
    """Gather every module's evidence about one district. Pure function."""
    d_scams = [s for s in scams if _in_district(s, district)]
    d_notes = [c for c in counterfeits if _in_district(c, district) and c.get("verdict") == "fake"]
    d_rings = [
        r for r in (fraud_graph or {}).get("rings", [])
        if (r.get("district") or "").lower() == district.lower()
    ]
    # cross-district intelligence that TOUCHES this district
    fams = [f for f in plate_families(counterfeits) if district in f["districts"]]
    camps = [c for c in scam_campaigns(scams) if district in c["district_spread"]]
    trail_hit = None
    if trail and any((s.get("district") or "").lower() == district.lower() for s in trail.get("seizures", [])):
        trail_hit = {
            "trail_id": trail.get("trail_id"),
            "corridor": trail.get("corridor", {}).get("name"),
            "mode": trail.get("mode"),
            "inferred_origin": trail.get("inferred_origin", {}).get("name"),
            "confidence_band": trail.get("confidence_band"),
            "flow": trail.get("flow"),
        }

    # chronological timeline of raw events (evidence ids let the brief cite)
    timeline = sorted(
        [
            *({"when": s.get("timestamp"), "what": f"scam call flagged ({s.get('scam_type', 'scam')})",
               "ref": s.get("event_id")} for s in d_scams),
            *({"when": c.get("timestamp"), "what": f"counterfeit ₹{c.get('denomination', '?')} seized",
               "ref": c.get("event_id")} for c in d_notes),
        ],
        key=lambda e: e["when"] or "",
    )

    return {
        "district": district,
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "counts": {
            "scams": len(d_scams),
            "fake_notes": len(d_notes),
            "rings": len(d_rings),
            "ring_accounts": sum(r.get("size", 0) for r in d_rings),
        },
        "scams": [
            {"ref": s.get("event_id"), "type": s.get("scam_type"), "risk": s.get("risk_score"),
             "phone": s.get("phone_number"), "when": s.get("timestamp")}
            for s in d_scams
        ],
        "fake_notes": [
            {"ref": c.get("event_id"), "denomination": c.get("denomination"),
             "missing_features": c.get("missing_features"), "when": c.get("timestamp")}
            for c in d_notes
        ],
        "rings": [
            {"ref": r.get("ring_id"), "label": r.get("label"), "size": r.get("size"),
             "total_amount": r.get("total_amount")}
            for r in d_rings
        ],
        "plate_families": fams,
        "campaigns": camps,
        "supply_trail": trail_hit,
        "timeline": timeline,
    }


# ── layer 2: the brief writers ───────────────────────────────────────────────

_SYSTEM = """\
You are the case officer for Aegis, writing for Indian police investigators.
You receive a DOSSIER of machine-established facts about one district. Write:
1. summary: 2-4 plain sentences, lead with the strongest cross-signal finding.
2. timeline: chronological one-liners (reuse dossier timeline, keep refs).
3. hypothesis: ONE hedged paragraph connecting the signals ("consistent with",
   "suggests"), never certainty, never named individuals.
4. recommended_actions: 3-6 short imperative steps, most urgent first.
STRICT: cite only dossier refs; if evidence is thin, say so plainly.
Respond with ONLY a JSON object: {"summary": "...", "timeline": ["..."],
"hypothesis": "...", "recommended_actions": ["..."]}"""


def _template_case_file(dossier: dict) -> dict:
    """Deterministic writer — no API key required, never fails."""
    d = dossier["district"]
    c = dossier["counts"]
    parts = []
    if c["scams"]:
        parts.append(f"{c['scams']} flagged scam call(s)")
    if c["fake_notes"]:
        parts.append(f"{c['fake_notes']} counterfeit seizure(s)")
    if c["rings"]:
        parts.append(f"{c['rings']} fraud ring(s) spanning {c['ring_accounts']} accounts")
    summary = (
        f"{d}: " + (", ".join(parts) if parts else "no direct events") + "."
    )
    if dossier["campaigns"]:
        camp = dossier["campaigns"][0]
        summary += (
            f" A {camp['tier']}-confidence scam campaign links reports across "
            f"{' → '.join(camp['district_spread'])}."
        )
    if dossier["plate_families"]:
        fam = dossier["plate_families"][0]
        summary += (
            f" Counterfeits share a defect signature with notes in "
            f"{', '.join(x for x in fam['districts'] if x != d) or 'other districts'} "
            f"({fam['tier']} tier)."
        )
    if dossier["supply_trail"]:
        st = dossier["supply_trail"]
        summary += (
            f" Seizures sit on the {st['corridor']}; likely origin "
            f"{st['inferred_origin']} ({st['confidence_band']} confidence)."
        )

    hypothesis = (
        "The co-occurrence of independent signals in one district is consistent "
        "with a coordinated operation rather than isolated incidents. This is an "
        "investigative hypothesis from correlated detections — not proof."
    )

    actions = []
    if dossier["campaigns"]:
        actions.append("Consolidate the linked scam complaints into a single case file.")
        if dossier["campaigns"][0]["phone_numbers"]:
            actions.append("Request CDRs for the campaign's callback numbers from the telecom provider.")
    if dossier["rings"]:
        actions.append("Request freezes on the flagged ring accounts via the bank nodal officer.")
    if dossier["supply_trail"]:
        st = dossier["supply_trail"]
        flow = st.get("flow") or {}
        nxt = flow.get("next_hub_at_risk")
        if nxt:
            actions.append(
                f"Alert {nxt['name']} units: flow analysis puts it at risk within "
                f"{nxt['eta_days_min']}–{nxt['eta_days_max']} days."
            )
        actions.append(f"Coordinate checks along the {st['corridor']} ({st['mode']}).")
    if dossier["fake_notes"]:
        actions.append("Alert bank branches in the district to re-verify recent cash deposits.")
    if not actions:
        actions = ["Continue monitoring; no actionable evidence in this district yet."]

    return {
        "summary": summary,
        "timeline": [f"{e['when'] or '?'} — {e['what']} [{e['ref']}]" for e in dossier["timeline"]],
        "hypothesis": hypothesis,
        "recommended_actions": actions[:6],
    }


def _parse_json_reply(text: str) -> dict:
    text = text.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("no JSON object in LLM reply")
    out = json.loads(text[start:end + 1])
    for key in ("summary", "timeline", "hypothesis", "recommended_actions"):
        if key not in out:
            raise ValueError(f"LLM reply missing '{key}'")
    return out


def _claude(dossier: dict) -> dict:
    import anthropic

    client = anthropic.Anthropic()
    r = client.messages.create(
        model="claude-opus-4-8",
        max_tokens=2000,
        system=_SYSTEM,
        messages=[{"role": "user", "content": "DOSSIER:\n" + json.dumps(dossier, default=str)}],
    )
    return _parse_json_reply("".join(b.text for b in r.content if b.type == "text"))


def _groq(dossier: dict) -> dict:
    import httpx

    r = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {os.environ[env_key]}"},
        json={
            "model": "llama-3.3-70b-versatile",
            "temperature": 0.2,
            "max_tokens": 1200,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": _SYSTEM},
                {"role": "user", "content": "DOSSIER:\n" + json.dumps(dossier, default=str)},
            ],
        },
        timeout=30.0,
    )
    r.raise_for_status()
    return _parse_json_reply(r.json()["choices"][0]["message"]["content"])


def _gemini(dossier: dict) -> dict:
    import httpx

    r = httpx.post(
        "https://generativelanguage.googleapis.com/v1beta/models/gemini-2.0-flash:generateContent",
        headers={"x-goog-api-key": os.environ["GEMINI_API_KEY"]},
        json={
            "system_instruction": {"parts": [{"text": _SYSTEM}]},
            "contents": [{"parts": [{"text": "DOSSIER:\n" + json.dumps(dossier, default=str)}]}],
            "generationConfig": {"temperature": 0.2, "responseMimeType": "application/json"},
        },
        timeout=30.0,
    )
    r.raise_for_status()
    return _parse_json_reply(r.json()["candidates"][0]["content"]["parts"][0]["text"])


def write_case_file_safe(dossier: dict) -> tuple[dict, str]:
    """Best available writer → (case_file, engine_name). Never raises."""
    try:  # reuse the fusion .env so one key powers both features
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
    # Spare Groq keys last: separate daily token budgets, used only once the
    # primary key and Gemini are exhausted.
    for slot, label in (("GROQ_API_KEY_2", "groq#2/llama-3.3-70b"),
                        ("GROQ_API_KEY_3", "groq#3/llama-3.3-70b")):
        if os.environ.get(slot):
            chain.append((label, lambda d, k=slot: _groq(d, k)))
    for name, fn in chain:
        try:
            return fn(dossier), name
        except Exception as exc:
            # Same reasoning as the fusion narrator: log why a provider dropped
            # out instead of silently degrading to the template.
            print(f"[case-officer] {name} failed: {type(exc).__name__}: {exc}", flush=True)
            continue
    return _template_case_file(dossier), "template-fallback"
