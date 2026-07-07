"""Synthetic Indian-scam corpus generator.

Why this exists: every public SMS/phishing dataset predates the digital-arrest
wave (₹1,776 crore stolen in 9 months of 2024). A model trained only on UCI
spam has literally never seen "CBI officer on a video call demanding USDT".
We close that gap with template-generated scripts covering the scam families
the demo must catch, plus **hard legit negatives** — genuine bank OTPs, real
police-verification calls, actual courier updates — so the model cannot cheat
by keying on surface words like "police", "bank" or "OTP".

Templates use `{slot}` placeholders expanded with seeded randomness, giving a
deterministic corpus (same seed → same rows → reproducible metrics).
"""

from __future__ import annotations

import random

import pandas as pd

from .config import CorpusConfig

# --- slot vocabularies ------------------------------------------------------

_SLOTS: dict[str, list[str]] = {
    "officer": ["Inspector Sharma", "Officer Verma", "Inspector Rathod", "ACP Krishnan",
                "Sub-Inspector Yadav", "Officer Deshmukh", "Inspector Iyer"],
    "agency": ["CBI", "ED", "Mumbai Cyber Cell", "Delhi Police Crime Branch", "NCB",
               "Customs Department", "TRAI", "Income Tax Department"],
    "crime": ["money laundering", "drug trafficking", "hawala transactions",
              "illegal parcel shipment", "financial fraud", "narcotics smuggling"],
    "id_doc": ["Aadhaar", "PAN card", "SIM card", "bank account", "courier parcel"],
    "amount": ["Rs 24,500", "Rs 98,000", "Rs 1,45,000", "Rs 3,80,000", "Rs 52,300", "Rs 2,10,000"],
    "pay_channel": ["USDT", "Bitcoin", "a Google Play gift card", "RTGS to the safe custody account",
                    "UPI to the verification account", "NEFT to the RBI settlement account"],
    "minutes": ["10 minutes", "30 minutes", "2 hours", "1 hour", "45 minutes"],
    "bank": ["HDFC Bank", "SBI", "ICICI Bank", "Axis Bank", "Kotak Bank", "PNB"],
    "telco": ["Airtel", "Jio", "Vi", "BSNL"],
    "courier": ["FedEx", "DHL", "Blue Dart", "India Post"],
    "city": ["Mumbai", "Delhi", "Bengaluru", "Chennai", "Hyderabad", "Kolkata", "Pune"],
    "prize": ["Rs 25,00,000", "Rs 10,00,000", "a Tata Safari", "Rs 50,00,000", "an iPhone 16 Pro"],
    "lottery_org": ["KBC Lucky Draw", "Jio Anniversary Lottery", "WhatsApp Mega Prize",
                    "National Savings Lucky Customer"],
    "short_link": ["bit.ly/kyc-upd8", "tinyurl.com/claim-rwd", "cutt.ly/verify-acct",
                   "rb.gy/prize-claim", "bit.ly/parcel-fee"],
    "name": ["Ramesh", "Priya", "Arjun", "Sneha", "Vikram", "Divya", "Karthik", "Ananya"],
    "otp": ["482913", "730451", "156208", "994127", "603785"],
    "time": ["1pm", "6:30", "tomorrow morning", "Saturday", "tonight 8"],
}

# --- scam templates (label = 1) ----------------------------------------------
# (template, origin) — origin tags let us report per-family recall later.

_SCAM_TEMPLATES: list[tuple[str, str]] = [
    # digital arrest — call transcripts
    ("This is {officer} from {agency}. An FIR has been registered against your {id_doc} for "
     "{crime}. You are under digital arrest. Stay on this video call, do not disconnect and do "
     "not inform anyone. Transfer {amount} as verification amount in {pay_channel} immediately "
     "or an arrest warrant will be issued.", "digital_arrest"),
    ("I am {officer} calling from {agency} {city} branch. Your {id_doc} was found linked to a "
     "{crime} case. A non-bailable warrant will be issued within {minutes} unless you cooperate. "
     "Keep your camera on, remain on this call and do not contact your family. Move your funds "
     "to the safe custody account for verification.", "digital_arrest"),
    ("{agency} speaking, this is {officer}. A parcel booked on your {id_doc} containing illegal "
     "items was seized in {city}. A case has been filed. To avoid arrest, pay the clearance fee "
     "of {amount} via {pay_channel} within {minutes}. Do not tell anyone about this "
     "investigation, it is confidential.", "digital_arrest"),
    ("Hello, calling from the telecom department. Your {id_doc} is involved in {crime}. Your case "
     "has been transferred to {agency}. {officer} will interrogate you now on Skype video call. "
     "Stay on the call and do not hang up. Failure to comply means immediate arrest.", "digital_arrest"),
    ("This is {officer}, {agency}. Your bank account shows transactions related to {crime}. RBI "
     "has flagged it. Transfer your balance of {amount} to the government verification account "
     "now. This is your last warning. Do not disconnect this call or police will reach your "
     "home in {minutes}.", "digital_arrest"),
    # KYC / account freeze
    ("Dear customer your {bank} account KYC has expired. Account will be blocked within "
     "{minutes}. Update immediately at {short_link} to avoid suspension.", "kyc"),
    ("{telco} notice: your SIM card KYC verification is pending. Your number will be "
     "deactivated today. Call this official number and share your Aadhaar number and OTP to "
     "complete verification.", "kyc"),
    ("URGENT: Your {bank} net banking will be suspended. Complete re-KYC now. Click "
     "{short_link} and confirm your account number, debit card number and PIN.", "kyc"),
    # lottery
    ("Congratulations {name}! Your mobile number has won {prize} in the {lottery_org}. To claim "
     "your prize deposit the processing fee of {amount} and share your bank details. Offer "
     "expires today. Visit {short_link} now.", "lottery"),
    ("Winner alert! You are selected for {prize} in {lottery_org}. Send your Aadhaar number, "
     "bank account details and pay {amount} registration charge to claim immediately.", "lottery"),
    # loan
    ("Pre-approved instant loan of {amount} for you {name}! Zero documentation, zero interest "
     "for 3 months. Pay {amount} file charge to activate. Apply now at {short_link}, offer "
     "valid {minutes} only.", "loan"),
    ("Dear customer, your loan of {prize} is sanctioned. To release the amount pay insurance "
     "fee via UPI immediately. Share OTP received on your number to confirm disbursal.", "loan"),
    # phishing
    ("{bank} alert: unusual login detected on your account from {city}. Verify your identity "
     "immediately at {short_link} or your account will be frozen. Confirm card number and CVV.", "phishing"),
    ("Your {courier} parcel is held at {city} customs. Pay the duty fee of {amount} at "
     "{short_link} within {minutes} to avoid return. Enter your card details to complete "
     "payment.", "phishing"),
    ("Income tax refund of {amount} approved for PAN ending 4821. Claim now at {short_link}. "
     "Confirm your net banking user id and password to receive the refund today.", "phishing"),
    ("Your electricity connection will be disconnected tonight at 9.30pm because previous "
     "month bill was not updated. Immediately contact electricity officer and download the "
     "AnyDesk app for bill verification.", "phishing"),
]

# --- hard legit negatives (label = 0) ----------------------------------------
# Real-world messages that *share vocabulary* with scams: genuine OTPs (never
# ask you to share), real police verification (no payment demand), courier
# updates (no fee link), bank reminders (branch visit, not link + OTP).

_LEGIT_TEMPLATES: list[tuple[str, str]] = [
    ("{otp} is your OTP for {bank} net banking login. Valid for 10 minutes. Do not share this "
     "OTP with anyone. {bank} never calls to ask for it.", "legit_bank"),
    ("Dear customer, {amount} was debited from your {bank} account at {city} ATM. If this was "
     "not you, call the number on the back of your card.", "legit_bank"),
    ("Your {bank} KYC is due for periodic update. Please visit your nearest branch with your "
     "original Aadhaar and PAN before month end. No online submission is required.", "legit_bank"),
    ("Reminder: your {bank} credit card statement is ready. Total due {amount}, minimum due "
     "payable by 15th. View it in the official mobile app.", "legit_bank"),
    ("Your {courier} shipment is out for delivery and will arrive today between 10am and 2pm. "
     "Track it in the app.", "legit_courier"),
    ("{courier} update: your parcel from {city} has reached the local facility. Expected "
     "delivery {time}.", "legit_courier"),
    ("This is constable {name} from {city} police station regarding your passport verification "
     "appointment. Please be available at home {time} with your original documents.", "legit_police"),
    ("Your police clearance certificate application is approved. Collect it from the {city} "
     "commissionerate counter 4 on any working day.", "legit_police"),
    ("Hi {name}, are we still meeting for lunch {time}? Let me know if you want to move it.", "legit_personal"),
    ("Mom said the train reaches {city} at {time}. Can you pick her up from the station?", "legit_personal"),
    ("Team, standup moved to {time} because of the client call. Same meet link as always.", "legit_personal"),
    ("Hey {name}, I transferred the {amount} rent to your account, check and confirm.", "legit_personal"),
    ("{telco} bill of {amount} for your number is due on 18th. Pay via the official app or "
     "any authorised store.", "legit_telco"),
    ("Your {telco} recharge of {amount} is successful. Validity 84 days, 2GB per day.", "legit_telco"),
    ("Appointment confirmed with Dr {name} at {time}, {city} clinic. Reply C to cancel.", "legit_other"),
    ("Your income tax return for AY 2025-26 has been processed. Refund if any will be "
     "credited to your pre-validated bank account. No action needed.", "legit_other"),
]


def _expand(template: str, rng: random.Random) -> str:
    out = template
    # Re-scan after each replacement is unnecessary: slots never nest.
    for slot, values in _SLOTS.items():
        while "{" + slot + "}" in out:
            out = out.replace("{" + slot + "}", rng.choice(values), 1)
    return out


def generate_corpus(cfg: CorpusConfig | None = None) -> pd.DataFrame:
    """Deterministic (seeded) corpus of scam scripts + hard legit negatives."""
    cfg = cfg or CorpusConfig()
    rng = random.Random(cfg.seed)
    rows: list[dict] = []
    for label, templates in ((1, _SCAM_TEMPLATES), (0, _LEGIT_TEMPLATES)):
        for template, origin in templates:
            for _ in range(cfg.variants_per_template):
                rows.append({
                    "text": _expand(template, rng),
                    "label": label,
                    "origin": f"synth_{origin}",
                })
    frame = pd.DataFrame(rows).drop_duplicates(subset="text").reset_index(drop=True)
    return frame
