"""Offline verifier — runs the tools and builds a deterministic synthesis with
no LLM. This is the fallback the agent degrades to when no API key is set or
the LLM call fails, mirroring the fusion layer's TemplateNarrator."""

from __future__ import annotations


def build_report(checked: list[dict], any_live: bool) -> dict:
    """Flat, deterministic verification report from tool results."""
    findings = [c["detail"] for c in checked if c.get("detail")]
    # Lead with the most damning tool signal so the card reads well.
    highlights = [c for c in checked if (
        c.get("bank_mismatch") or c.get("typosquat_of") or c.get("solicits_credentials")
        or c.get("exists") is False or c.get("known_psp") is False or c.get("suspicious")
    )]
    if highlights:
        synthesis = "Verification found hard evidence: " + "; ".join(
            h["detail"] for h in highlights[:3]) + "."
    elif checked:
        synthesis = ("Checked " + ", ".join(sorted({c["entity_type"] for c in checked}))
                     + "; nothing conclusive, treat with caution.")
    else:
        synthesis = "No verifiable entities (links, UPI, IFSC, numbers) found in the message."
    return {
        "checked": checked,
        "findings": findings,
        "synthesis": synthesis,
        "engine": "offline-fallback",
        "any_live": any_live,
    }
