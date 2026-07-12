"""Agentic verifier orchestration — offline path, latency budget, safety."""

import time

import httpx
import pytest

from aegis_fraud_shield.config import VerifyConfig
from aegis_fraud_shield.verify import agent
from aegis_fraud_shield.verify.agent import verify_safe

FLAGGED = ("This is CBI. Pay the verification fee to scammer@fakepsp and confirm "
           "IFSC SBIN0001234, then click https://bit.ly/verify-now immediately.")


@pytest.fixture(autouse=True)
def _no_key(monkeypatch):
    """Force the offline synthesis path — no LLM in tests."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr(agent, "_load_dotenv", lambda: None)


def test_offline_report_shape(monkeypatch):
    # Keep IFSC offline (no network) so the test is fully hermetic and fast.
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("x")))
    report = verify_safe(FLAGGED, {"verdict": "scam", "scam_type": "digital_arrest"})
    assert report is not None
    assert report["engine"] == "offline-fallback"
    assert report["synthesis"]
    assert any(c["entity_type"] == "upi" for c in report["checked"])
    assert report["any_live"] is False


def test_disabled_returns_none():
    assert verify_safe(FLAGGED, {"verdict": "scam"}, VerifyConfig(enabled=False)) is None


def test_no_entities_returns_none():
    assert verify_safe("This is a scam but has no links or accounts.",
                       {"verdict": "scam"}) is None


def test_never_raises_with_network_down(monkeypatch):
    def boom(*a, **k):
        raise httpx.ConnectError("network down")
    monkeypatch.setattr(httpx, "get", boom)
    # Must return a report (offline), not raise.
    report = verify_safe(FLAGGED, {"verdict": "scam"})
    assert report is not None and report["engine"] == "offline-fallback"


def test_hanging_tool_respects_budget(monkeypatch):
    """A slow tool must not blow the overall wall-clock budget."""
    def slow_get(*a, **k):
        time.sleep(2.0)
        raise httpx.ConnectError("x")
    monkeypatch.setattr(httpx, "get", slow_get)
    # Two live-capable entities (url + ifsc); budget 1.5s. Even one sleep(2)
    # exceeds it, so the second entity must be skipped by the deadline check.
    cfg = VerifyConfig(total_budget_s=1.5, tool_timeout_s=4.0)
    text = "pay https://bit.ly/x and IFSC SBIN0001234 now"
    start = time.monotonic()
    report = verify_safe(text, {"verdict": "scam"}, cfg)
    elapsed = time.monotonic() - start
    assert report is not None
    # First tool sleeps ~2s then fails offline; the deadline then stops the loop
    # before a *second* 2s sleep — so total stays well under 2 sleeps (4s).
    assert elapsed < 3.5


def test_verdict_fields_never_touched(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("x")))
    report = verify_safe(FLAGGED, {"verdict": "scam", "risk_score": 0.99})
    # The report is a separate object; it carries no verdict-shaped keys.
    assert "verdict" not in report and "risk_score" not in report
    assert set(report) == {"checked", "findings", "synthesis", "engine", "any_live"}
