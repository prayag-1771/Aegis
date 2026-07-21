# -*- coding: utf-8 -*-
"""Multilingual input normalisation for /analyze.

The classifier is English-only, so a message in a native Indian script scores as
noise. `/analyze` translates a non-Latin message to English (via the command
centre, which holds the Sarvam key) before classifying — additively, without
changing the deterministic verdict path. These tests pin that behaviour:

  * the language gate fires on the 22 scheduled scripts and never on English,
  * a non-Latin scam is translated then correctly flagged, with the citizen's
    ORIGINAL message preserved in raw_text and the payload still contract-valid,
  * English is never sent to translation,
  * translation failure falls through to English-only — /analyze never breaks.

Hermetic: the Sarvam round-trip is stubbed, the model is trained on the synthetic
corpus, and the agentic verify layer is neutralised. No network.
"""

import json

import jsonschema
import pytest

from aegis_fraud_shield import api
from aegis_fraud_shield.config import CONTRACT_SCHEMA, CorpusConfig, ModelConfig
from aegis_fraud_shield.corpus import generate_corpus
from aegis_fraud_shield.model import train

# A real Hindi bank-KYC-freeze scam (Devanagari). English-only, this scores ~0.06
# and is cleared; translated, it is an obvious scam.
HINDI_KYC_SCAM = (
    "प्रिय ग्राहक, आपका बैंक KYC समाप्त हो गया है। यदि आप अगले 30 मिनट में KYC अपडेट "
    "नहीं करते हैं तो आपका बैंक खाता और UPI सेवा बंद कर दी जाएगी। अपडेट करने के लिए दिए "
    "गए लिंक पर क्लिक करें।"
)
HINDI_KYC_ENGLISH = (
    "Dear customer, your bank KYC has expired. If you do not update KYC within the "
    "next 30 minutes your bank account and UPI service will be blocked. Click the "
    "link given to update."
)
ENGLISH_LEGIT = "Hey, are we still on for lunch tomorrow at 1pm? Let me know."


@pytest.fixture(scope="module")
def model():
    frame = generate_corpus(CorpusConfig(variants_per_template=8))
    clf, _ = train(frame, ModelConfig(test_size=0.3))
    return clf


@pytest.fixture(autouse=True)
def _wired(model, monkeypatch):
    """Serve the trained model from get_model() and keep verification hermetic."""
    monkeypatch.setattr(api, "get_model", lambda: model)
    monkeypatch.setattr("aegis_fraud_shield.verify.verify_safe", lambda *a, **k: None)


@pytest.mark.parametrize(
    "text, expected",
    [
        (HINDI_KYC_SCAM, True),                       # Hindi (Devanagari)
        ("உங்கள் வங்கி KYC காலாவधியானது", True),        # Tamil
        ("آپ کا بینک کے وائی سی ختم ہو گیا ہے", True),  # Urdu (Perso-Arabic)
        (ENGLISH_LEGIT, False),                        # English
        ("Pay ₹5000 now to avoid penalty", False),     # English + rupee sign
    ],
)
def test_language_gate(text, expected):
    assert api._needs_translation(text) is expected


def test_non_latin_scam_is_translated_then_flagged(model, monkeypatch):
    from aegis_fraud_shield.analyze import analyze

    # Untranslated, the English-only classifier misses the Devanagari scam.
    raw = analyze(HINDI_KYC_SCAM, model, source="sms", verify=False)

    # Stub the Sarvam round-trip with the English the /translate endpoint returns.
    monkeypatch.setattr(api, "_translate_to_english", lambda t: HINDI_KYC_ENGLISH)
    payload = api.analyze_endpoint(api.AnalyzeRequest(text=HINDI_KYC_SCAM, source="sms"))

    # Translation is what turns a missed message into a flagged one: the verdict
    # is no longer "legit" and the risk jumps well above the untranslated score.
    assert payload["verdict"] != "legit"
    assert payload["risk_score"] > raw["risk_score"] + 0.2
    # The classifier scored the English, but the stored message stays in Hindi.
    assert payload["raw_text"] == HINDI_KYC_SCAM
    # Still a valid scam_detection payload (no new fields added).
    jsonschema.validate(instance=payload, schema=json.loads(CONTRACT_SCHEMA.read_text(encoding="utf-8")))


def test_english_is_never_translated(monkeypatch):
    def _boom(_):
        raise AssertionError("English must not be sent to translation")

    monkeypatch.setattr(api, "_translate_to_english", _boom)
    payload = api.analyze_endpoint(api.AnalyzeRequest(text=ENGLISH_LEGIT, source="sms"))
    assert payload["verdict"] == "legit"
    assert payload["raw_text"] == ENGLISH_LEGIT


def test_translation_failure_falls_through_to_original():
    # Nothing is listening on this port: httpx errors, and we must get the input
    # back unchanged rather than raise — /analyze then classifies the original.
    import os

    os.environ["COMMAND_CENTRE_URL"] = "http://127.0.0.1:9"
    assert api._translate_to_english(HINDI_KYC_SCAM) == HINDI_KYC_SCAM
