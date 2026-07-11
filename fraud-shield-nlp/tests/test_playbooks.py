"""Playbook layer: scripts must match stage-by-stage with cited evidence."""

from aegis_fraud_shield.markers import detect_markers
from aegis_fraud_shield.playbooks import match_playbook

DIGITAL_ARREST = (
    "This is Inspector Sharma from CBI. An FIR has been registered against your Aadhaar "
    "for money laundering. Stay on this video call and do not disconnect. Transfer the "
    "verification amount in USDT immediately or a warrant will be issued."
)


def _match(text):
    return match_playbook(text, detect_markers(text))


def test_digital_arrest_full_script_in_order():
    m = _match(DIGITAL_ARREST)
    assert m is not None and m.playbook.name == "digital_arrest"
    assert m.n_satisfied == 4 and m.completeness == 1.0
    assert m.in_canonical_order
    chain = m.chain()
    assert len(chain) == 4
    assert "establishes authority" in chain[0] and "Inspector" in chain[0]
    assert "coerces payment" in chain[3]


def test_partial_script_still_matches_at_min_stages():
    text = ("Officer Verma from Delhi Police Crime Branch speaking. A case has been "
            "registered against your PAN card.")
    m = _match(text)
    assert m is not None and m.playbook.name == "digital_arrest"
    assert m.n_satisfied == 2


def test_kyc_script_matches_kyc_playbook():
    text = ("Dear customer your SBI account KYC has expired. Account will be blocked "
            "within 24 hours. Update immediately at bit.ly/kyc-upd8 to avoid suspension.")
    m = _match(text)
    assert m is not None and m.playbook.name == "kyc_fraud"
    assert m.completeness == 1.0


def test_lottery_matches_advance_fee_playbook():
    text = ("Congratulations! You won Rs 25,00,000 in the KBC Lucky Draw. Deposit the "
            "processing fee and share your bank details to claim.")
    m = _match(text)
    assert m is not None and m.playbook.name == "advance_fee"
    assert m.in_canonical_order


def test_normal_chat_matches_no_playbook():
    assert _match("Hey, are we still meeting for lunch tomorrow at 1pm?") is None


def test_genuine_otp_matches_no_playbook():
    assert _match("482913 is your OTP for HDFC net banking login. Valid for 10 minutes. "
                  "Do not share this OTP with anyone.") is None


def test_single_marker_is_not_a_script():
    # One trick alone (urgency) must not be called a playbook.
    assert _match("Please respond today, the offer expires tonight.") is None
