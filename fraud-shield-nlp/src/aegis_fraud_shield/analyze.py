"""End-to-end analysis: text in → contract-valid scam_detection JSON out.

This is the hand-off surface to the command centre. Everything it emits
matches `contracts/scam_detection.schema.json` — validate with
`python shared/validate_contract.py scam <file>` before integration.

The `explanation` field is deterministic template text built from the marker
evidence (auditability: every sentence traces to a matched span). The LLM
version of this is the stretch goal and would slot in behind the same field.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime, timezone

from .config import CONTRACT_SCHEMA, SCHEMA_VERSION
from .markers import (
    AUTHORITY_IMPERSONATION,
    CRYPTO_OR_GIFTCARD_DEMAND,
    FAKE_FIR_OR_CASE,
    PERSONAL_DATA_REQUEST,
    SPOOFED_NUMBER,
    SUSPICIOUS_LINK,
    URGENCY_PRESSURE,
    VIDEO_CALL_ISOLATION,
    MarkerHit,
    detect_markers,
    infer_scam_type,
)
from .model import ScamClassifier
from .playbooks import PlaybookMatch, match_playbook

# One human sentence-fragment per marker; {evidence} is the first matched span.
# Straight quotes on purpose — Windows consoles mangle curly quotes in demos.
_MARKER_FRAGMENTS: dict[str, str] = {
    AUTHORITY_IMPERSONATION: "impersonates an authority ('{evidence}')",
    FAKE_FIR_OR_CASE: "claims a fake case or FIR ('{evidence}')",
    URGENCY_PRESSURE: "applies time pressure ('{evidence}')",
    CRYPTO_OR_GIFTCARD_DEMAND: "demands untraceable payment ('{evidence}')",
    VIDEO_CALL_ISOLATION: "isolates the victim on a call ('{evidence}')",
    PERSONAL_DATA_REQUEST: "asks for credentials or identity data ('{evidence}')",
    SUSPICIOUS_LINK: "pushes a suspicious link or remote-access app ('{evidence}')",
    SPOOFED_NUMBER: "tries to legitimise a spoofed number ('{evidence}')",
}

_VERDICT_LEAD = {
    "scam": "High-confidence scam.",
    "suspicious": "Suspicious message — treat with caution.",
    "legit": "No scam indicators found.",
}


def build_explanation(verdict: str, risk: float, hits: list[MarkerHit],
                      playbook: PlaybookMatch | None = None) -> str:
    lead = _VERDICT_LEAD[verdict]
    # A clean verdict must read clean — don't enumerate stray pattern matches
    # the classifier already judged harmless.
    if not hits or verdict == "legit":
        return f"{lead} Classifier risk score {risk:.2f}."

    # Reasoning chain: when the message follows a known scam script, walk it
    # stage by stage — each step cites the exact span that satisfied it.
    if playbook is not None:
        pb = playbook.playbook
        order = "in script order" if playbook.in_canonical_order else "out of script order"
        chain = " -> ".join(playbook.chain())
        extras = [
            _MARKER_FRAGMENTS[h.marker].format(evidence=h.evidence[0])
            for h in hits
            if not any(h.marker in st.stage.markers for st in playbook.stages if st.satisfied)
        ]
        extra_txt = (" It also " + ", and ".join(extras) + ".") if extras else ""
        return (
            f"{lead} Follows the {pb.name.replace('_', '-')} playbook "
            f"({playbook.n_satisfied}/{len(playbook.stages)} stages, {order}): "
            f"{chain}.{extra_txt} Classifier risk score {risk:.2f}."
        )

    fragments = [
        _MARKER_FRAGMENTS[h.marker].format(evidence=h.evidence[0]) for h in hits
    ]
    if len(fragments) == 1:
        body = fragments[0]
    else:
        body = ", ".join(fragments[:-1]) + ", and " + fragments[-1]
    return f"{lead} The message {body}. Classifier risk score {risk:.2f}."


def analyze(
    text: str,
    model: ScamClassifier,
    source: str = "manual_demo",
    phone_number: str | None = None,
    location_hint: dict | None = None,
) -> dict:
    """Analyse one message/transcript; returns a contract-valid payload dict."""
    hits = detect_markers(text)
    markers = [h.marker for h in hits]
    risk = model.risk_score(text)
    verdict = model.decide_verdict(risk, len(markers))
    playbook = match_playbook(text, hits) if verdict != "legit" else None
    # A matched playbook is the strongest type signal we have.
    if verdict == "legit":
        scam_type = "none"
    elif playbook is not None:
        scam_type = playbook.playbook.scam_type
    else:
        scam_type = infer_scam_type(text, markers)

    return {
        "schema_version": SCHEMA_VERSION,
        "event_id": f"scam_{uuid.uuid4().hex[:12]}",
        "source": source,
        "timestamp": datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z"),
        "raw_text": text,
        "verdict": verdict,
        "risk_score": round(risk, 4),
        "scam_type": scam_type,
        "markers": markers,
        "explanation": build_explanation(verdict, risk, hits, playbook),
        "phone_number": phone_number,
        "location_hint": location_hint,
    }


def validate_payload(payload: dict) -> None:
    """Raise jsonschema.ValidationError if payload breaks the contract."""
    import jsonschema

    schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
    jsonschema.validate(instance=payload, schema=schema)
