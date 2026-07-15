"""Agentic verification layer for Fraud Shield.

Additive, never overrides. The deterministic classifier decides the verdict
(auditable, court-defensible); this layer only *investigates* a flagged message
with real verification tools and reports evidence the regex/ML stack cannot
produce — where a shortlink actually redirects, whether a quoted IFSC is a real
bank, whether a UPI PSP exists.

Entry point: `verify_safe(text, det_result)` — mirrors the fusion narrator's
`narrate_safe()`: live tools with an offline fallback, an LLM synthesis with a
deterministic fallback, and `None` as the hard floor. It can never raise and
never touches verdict / risk_score / scam_type / markers.
"""

from .agent import verify_safe

__all__ = ["verify_safe"]
