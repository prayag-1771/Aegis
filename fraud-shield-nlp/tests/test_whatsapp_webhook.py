"""Twilio WhatsApp webhook: form-in, TwiML-out, signature gating.

The webhook is the live half of the /whatsapp simulator page — its reply body
must come from the same template (build_whatsapp_reply)."""

import base64
import hashlib
import hmac

import pytest
from fastapi.testclient import TestClient

from aegis_fraud_shield.api import app, build_whatsapp_reply

SCAM_TEXT = (
    "This is Inspector Sharma from CBI. An FIR has been registered against your "
    "Aadhaar for money laundering. Stay on this video call and do not disconnect. "
    "Transfer the verification amount in USDT immediately."
)
LEGIT_TEXT = "Hey, are we still meeting for lunch tomorrow at 1pm?"


@pytest.fixture(autouse=True)
def _offline_verify(monkeypatch):
    """Keep verification hermetic: no key (offline synthesis) and no live net."""
    import httpx

    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.setattr("aegis_fraud_shield.verify.agent._load_dotenv", lambda: None)
    monkeypatch.setattr(
        httpx, "get", lambda *a, **k: (_ for _ in ()).throw(httpx.ConnectError("x")))


@pytest.fixture
def client(monkeypatch):
    # No token in the environment -> signature validation off (dev mode).
    monkeypatch.delenv("TWILIO_AUTH_TOKEN", raising=False)
    return TestClient(app)


def _post(client, body, **extra):
    return client.post(
        "/webhook/whatsapp",
        data={"Body": body, "From": "whatsapp:+919876543210", **extra},
    )


def test_scam_message_gets_high_risk_twiml(client):
    resp = _post(client, SCAM_TEXT)
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/xml")
    assert "<Response><Message>" in resp.text
    assert "HIGH RISK" in resp.text
    assert "1930" in resp.text  # helpline always present in scam replies


def test_legit_message_reads_safe(client):
    resp = _post(client, LEGIT_TEXT)
    assert resp.status_code == 200
    assert "Looks safe" in resp.text


def test_empty_body_returns_help_text(client):
    resp = _post(client, "")
    assert resp.status_code == 200
    assert "Aegis Shield" in resp.text


def test_reply_is_xml_escaped(client):
    resp = _post(client, "click <b>here</b> & pay now to verify your KYC details")
    assert resp.status_code == 200
    assert "<b>" not in resp.text.split("<Message>")[1].split("</Message>")[0]


def test_signature_required_when_token_set(monkeypatch):
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "testtoken")
    client = TestClient(app)
    resp = _post(client, LEGIT_TEXT)
    assert resp.status_code == 403  # unsigned request refused


def test_valid_signature_accepted(monkeypatch):
    token = "testtoken"
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", token)
    client = TestClient(app)
    form = {"Body": LEGIT_TEXT, "From": "whatsapp:+919876543210"}
    url = "http://testserver/webhook/whatsapp"
    payload = url + "".join(k + v for k, v in sorted(form.items()))
    signature = base64.b64encode(
        hmac.new(token.encode(), payload.encode("utf-8"), hashlib.sha1).digest()
    ).decode()
    resp = client.post(
        "/webhook/whatsapp", data=form, headers={"X-Twilio-Signature": signature})
    assert resp.status_code == 200
    assert "Looks safe" in resp.text


def test_reply_template_matches_simulator_contract():
    """Spot-check the shared template shape the simulator promises."""
    reply = build_whatsapp_reply({
        "risk_score": 0.99, "verdict": "scam", "scam_type": "kyc",
        "markers": ["urgency_pressure", "suspicious_link"],
    })
    assert reply.startswith("🚨 *HIGH RISK — 99%*")
    assert "KYC scam" in reply
    assert "urgency pressure, suspicious link" in reply
