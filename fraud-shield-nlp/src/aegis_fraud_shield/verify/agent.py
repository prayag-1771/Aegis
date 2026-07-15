"""Agentic verifier — the GenAI layer.

Orchestration (deliberately mirrors the fusion narrator's get_narrator /
narrate_safe shape rather than a synchronous LLM tool-loop, so it can never
hang or die on stage):

    verify_safe(text, det_result)
      1. extract concrete entities from the flagged message
      2. run the verification tools against them, each with a per-tool timeout
         and an overall wall-clock budget (partial results are fine)
      3. synthesise: an LLM narrates ONLY the tool-confirmed findings + does an
         in-prompt claim cross-check ("CBI does not arrest over WhatsApp") ...
         ... falling back to the deterministic offline synthesis, then to None.

The agent NEVER writes verdict / risk_score / scam_type / markers — it returns
a separate `verification` object. Remove this whole package and every existing
test and consumer still passes.
"""

from __future__ import annotations

import os
import time

from ..config import VerifyConfig
from . import offline, tools

# --- system prompt: same restraint as the fusion narrator's STRICT RULES ---

SYSTEM_PROMPT = """\
You are the verification analyst for Aegis Fraud Shield, an Indian anti-scam system.

A deterministic classifier has ALREADY decided this message is a scam or suspicious.
That verdict is authoritative and court-defensible. You do NOT change it.

You are given the message and the results of real verification tools that were run
against the concrete entities in it (links resolved, IFSC codes checked against the
bank registry, UPI handles and phone numbers validated).

Write a 1-3 sentence `synthesis` for an investigator:
- Report ONLY what the tool results actually establish. Cite the specific finding.
- You MAY add a claim cross-check from general knowledge of Indian scams — e.g.
  "CBI/police do not conduct arrests over WhatsApp video calls", "RBI never asks
  citizens to move funds to a 'safe account'" — but frame these as
  "commonly a scam indicator", never as legal fact.
- Hedge anything the tools did not confirm (source "offline" means unconfirmed).
- Never assert the verdict, a risk score, or that something "is illegal".
"""


def _run_tools(text: str, cfg: VerifyConfig) -> tuple[list[dict], bool]:
    """Extract entities and run each tool under the overall time budget."""
    ents = tools.extract_entities(text)
    checked: list[dict] = []
    any_live = False
    deadline = time.monotonic() + cfg.total_budget_s

    def _budget_left() -> float:
        return deadline - time.monotonic()

    for url in ents["urls"]:
        if _budget_left() <= 0:
            break
        r = tools.resolve_url(url, timeout_s=min(cfg.tool_timeout_s, _budget_left()),
                              max_redirects=cfg.max_redirects, max_body_bytes=cfg.max_body_bytes)
        any_live |= r.get("source") == "live"
        checked.append(r)
    for ifsc in ents["ifsc_codes"]:
        if _budget_left() <= 0:
            break
        r = tools.validate_ifsc(ifsc, timeout_s=min(cfg.tool_timeout_s, _budget_left()))
        any_live |= r.get("source") == "live"
        checked.append(r)
    for upi in ents["upi_handles"]:
        checked.append(tools.validate_upi(upi))
    for phone in ents["phone_numbers"]:
        checked.append(tools.phone_reputation(phone))
    return checked, any_live


def _synthesize_llm(text: str, det_result: dict, checked: list[dict],
                    any_live: bool, cfg: VerifyConfig) -> dict:
    """LLM synthesis via messages.parse (same surface the fusion narrator uses).
    Raises on any failure so verify_safe falls through to the offline report."""
    import json

    from pydantic import BaseModel, Field

    class Synthesis(BaseModel):
        synthesis: str = Field(description="1-3 sentence investigator-facing summary")

    import anthropic

    client = anthropic.Anthropic()  # reads ANTHROPIC_API_KEY
    payload = {
        "message": text,
        "deterministic_verdict": det_result.get("verdict"),
        "scam_type": det_result.get("scam_type"),
        "tool_results": checked,
    }
    resp = client.messages.parse(
        model=cfg.model,
        max_tokens=8000,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": "EVIDENCE:\n" + json.dumps(payload, indent=2)}],
        output_format=Synthesis,
    )
    return {
        "checked": checked,
        "findings": [c["detail"] for c in checked if c.get("detail")],
        "synthesis": resp.parsed_output.synthesis,
        "engine": "claude-agent",
        "any_live": any_live,
    }


def _load_dotenv() -> None:
    """Load command-centre/fusion/.env if present (shared key location)."""
    from pathlib import Path

    for env_file in (
        Path(__file__).resolve().parents[4] / "command-centre" / "fusion" / ".env",
        Path.cwd() / ".env",
    ):
        if env_file.exists():
            for line in env_file.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


def verify_safe(text: str, det_result: dict, cfg: VerifyConfig | None = None) -> dict | None:
    """Investigate a flagged message. Never raises; returns None if disabled or
    if verification produced nothing usable. Chain: Claude synthesis -> offline
    synthesis -> None."""
    cfg = cfg or VerifyConfig()
    if not cfg.enabled:
        return None
    try:
        checked, any_live = _run_tools(text, cfg)
    except Exception:  # noqa: BLE001 — tool orchestration must never break /analyze
        return None
    if not checked:
        return None

    _load_dotenv()
    if os.environ.get("ANTHROPIC_API_KEY"):
        try:
            return _synthesize_llm(text, det_result, checked, any_live, cfg)
        except Exception:  # noqa: BLE001 — any LLM failure -> deterministic report
            pass
    return offline.build_report(checked, any_live)
