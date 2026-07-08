"""Fusion orchestrator: signals in -> contract-compliant fusion_output JSON out."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel, Field

from . import PROMPT_VERSION
from .correlator import correlate
from .narrator import Narrative, narrate_safe

FUSION_ROOT = Path(__file__).resolve().parents[2]  # command-centre/fusion/
REPO_ROOT = FUSION_ROOT.parents[1]  # Aegis/
CONTRACT_SCHEMA = REPO_ROOT / "contracts" / "fusion_output.schema.json"
SAMPLES = REPO_ROOT / "contracts" / "samples"


# ---- pydantic models mirroring contracts/fusion_output.schema.json ----
class LinkedSignal(BaseModel):
    type: str
    ref_event_id: str
    reason: str | None = None


class MapHotspot(BaseModel):
    type: str
    district: str | None = None
    lat: float
    lon: float
    weight: float | None = None


class AuditTrail(BaseModel):
    model: str
    inputs_hash: str
    prompt_version: str


class FusionOutput(BaseModel):
    schema_version: str = "1.0"
    generated_at: str = ""
    summary: str = ""
    threat_level: str = "low"
    linked_signals: list[LinkedSignal] = Field(default_factory=list)
    correlation_basis: list[str] = Field(default_factory=list)
    recommended_actions: list[str] = Field(default_factory=list)
    map_hotspots: list[MapHotspot] = Field(default_factory=list)
    audit_trail: AuditTrail | None = None


def _inputs_hash(scams: list[dict], counterfeits: list[dict], fraud_graph: dict | None) -> str:
    """Stable hash of the exact inputs — the auditability anchor. Anyone can
    re-run the engine on the same inputs and verify the same package."""
    canonical = json.dumps(
        {"scams": scams, "counterfeits": counterfeits, "fraud_graph": fraud_graph},
        sort_keys=True,
        default=str,
    )
    return hashlib.sha256(canonical.encode()).hexdigest()[:16]


def fuse(
    scams: list[dict],
    counterfeits: list[dict],
    fraud_graph: dict | None,
) -> FusionOutput:
    """The fusion moment: correlate deterministically, then narrate."""
    correlation = correlate(scams, counterfeits, fraud_graph)
    narrative, narrator_name = narrate_safe(correlation.facts)

    return FusionOutput(
        generated_at=datetime.now(timezone.utc).isoformat(),
        summary=narrative.summary,
        threat_level=correlation.threat_level,
        linked_signals=[
            LinkedSignal(type=l.type, ref_event_id=l.ref_event_id, reason=l.reason)
            for l in correlation.linked_signals
        ],
        correlation_basis=correlation.correlation_basis,
        recommended_actions=narrative.recommended_actions,
        map_hotspots=[MapHotspot(**h) for h in correlation.map_hotspots],
        audit_trail=AuditTrail(
            model=narrator_name,
            inputs_hash=_inputs_hash(scams, counterfeits, fraud_graph),
            prompt_version=PROMPT_VERSION,
        ),
    )


def validate_against_contract(payload: dict) -> None:
    from jsonschema import validate

    schema = json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8"))
    validate(instance=payload, schema=schema)


def demo() -> FusionOutput:
    """Run fusion on the contract samples (plus live fraud-graph output if present)."""
    scams = [json.loads((SAMPLES / "scam_detection.sample.json").read_text(encoding="utf-8"))]
    counterfeits = [json.loads((SAMPLES / "counterfeit.sample.json").read_text(encoding="utf-8"))]

    live_graph = REPO_ROOT / "fraud-graph-ml" / "output" / "fraud_graph.json"
    graph_file = live_graph if live_graph.exists() else SAMPLES / "fraud_graph.sample.json"
    fraud_graph = json.loads(graph_file.read_text(encoding="utf-8"))

    output = fuse(scams, counterfeits, fraud_graph)
    payload = json.loads(output.model_dump_json())
    validate_against_contract(payload)

    out_file = FUSION_ROOT / "output" / "fusion_output.json"
    out_file.parent.mkdir(parents=True, exist_ok=True)
    out_file.write_text(output.model_dump_json(indent=2), encoding="utf-8")
    return output


if __name__ == "__main__":
    import sys

    sys.stdout.reconfigure(encoding="utf-8")  # Windows console defaults to cp1252; ₹ needs UTF-8
    result = demo()
    print(f"threat_level : {result.threat_level}")
    print(f"narrator     : {result.audit_trail.model}")
    print(f"links        : {len(result.linked_signals)}")
    print(f"summary      : {result.summary}")
    for a in result.recommended_actions:
        print(f"  -> {a}")
    print("contract validation: PASS")
