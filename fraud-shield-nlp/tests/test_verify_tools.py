"""Verification tools — hermetic (all network mocked or offline-only)."""

import httpx
import pytest

from aegis_fraud_shield.verify import tools


def test_extract_entities_pulls_all_types():
    text = ("Update KYC at https://bit.ly/kyc-upd8 or pay to scammer@okhdfcbank, "
            "IFSC SBIN0001234, call 9876543210.")
    ents = tools.extract_entities(text)
    assert any("bit.ly" in u for u in ents["urls"])
    assert "scammer@okhdfcbank" in ents["upi_handles"]
    assert "SBIN0001234" in ents["ifsc_codes"]
    assert "9876543210" in ents["phone_numbers"]


def test_extract_separates_upi_from_email():
    ents = tools.extract_entities("mail me at ravi@gmail.com or pay ravi@okicici")
    assert "ravi@okicici" in ents["upi_handles"]
    assert "ravi@gmail.com" not in ents["upi_handles"]


def test_validate_ifsc_bad_format():
    r = tools.validate_ifsc("NOTANIFSC")
    assert r["ok"] is False and r["well_formed"] is False


def _resp(status, **kw):
    # httpx.raise_for_status() needs a bound request even on 2xx.
    return httpx.Response(status, request=httpx.Request("GET", "https://ifsc.razorpay.com/x"), **kw)


def test_validate_ifsc_live_mismatch(monkeypatch):
    monkeypatch.setattr(httpx, "get",
                        lambda url, timeout=None: _resp(200, json={"BANK": "Canara Bank", "BRANCH": "MG Road"}))
    r = tools.validate_ifsc("CNRB0001234", claimed_bank="SBI")
    assert r["source"] == "live" and r["exists"] is True
    assert r["bank_mismatch"] is True and "Canara" in r["bank"]


def test_validate_ifsc_live_not_found(monkeypatch):
    monkeypatch.setattr(httpx, "get", lambda url, timeout=None: _resp(404))
    r = tools.validate_ifsc("SBIN0009999")
    assert r["exists"] is False


def test_validate_ifsc_offline_fallback(monkeypatch):
    def boom(url, timeout=None):
        raise httpx.ConnectError("no network")
    monkeypatch.setattr(httpx, "get", boom)
    r = tools.validate_ifsc("SBIN0001234")
    assert r["source"] == "offline" and "State Bank" in r["bank"]


def test_resolve_url_typosquat_offline():
    # No scheme host that's a typo of a brand; offline path (no network call).
    r = tools.resolve_url("http://paytn.com/pay", max_redirects=0)
    # paytn ~ paytm (edit distance 1)
    assert r["typosquat_of"] == "paytm"


def test_resolve_url_blocks_internal_host(monkeypatch):
    # Must never fetch a private/metadata address, even if DNS resolves it.
    monkeypatch.setattr(tools, "_is_public_host", lambda h: False)
    called = {"n": 0}

    def spy_get(*a, **k):
        called["n"] += 1
        return httpx.Response(200, text="ok")
    monkeypatch.setattr(httpx, "get", spy_get)
    r = tools.resolve_url("http://169.254.169.254/latest/meta-data")
    assert called["n"] == 0  # never fetched
    assert r["source"] == "offline"


def test_validate_upi_unknown_psp():
    r = tools.validate_upi("winner@fakepsp")
    assert r["known_psp"] is False


def test_validate_upi_known_psp():
    assert tools.validate_upi("real@okhdfcbank")["known_psp"] is True


def test_phone_reputation_flags_bad_number():
    assert tools.phone_reputation("+91 12345")["suspicious"] is True


def test_phone_reputation_ok_number():
    assert tools.phone_reputation("9876543210")["suspicious"] is False
