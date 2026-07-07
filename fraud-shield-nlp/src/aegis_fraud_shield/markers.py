"""Digital-arrest / scam marker detection (rule layer).

Design choices (defensible in judging):
- **Rules alongside the statistical model, not instead of it.** The classifier
  gives a calibrated risk score; the markers give the *evidence* — which exact
  phrases triggered the flag. That evidence powers the "why flagged" UI, the
  fusion LLM, and the auditability requirement (a named evaluation metric).
- **Marker names are locked by the contract** (`contracts/scam_detection.schema.json`).
  This module must only ever emit names from that enum.
- Patterns are written for the Indian scam landscape: CBI/ED/TRAI impersonation,
  fake FIRs, "digital arrest" video-call isolation, KYC-freeze pressure, UPI /
  gift-card / USDT payment demands.

Each detector returns the matched evidence spans so the UI can highlight them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

# The eight marker names locked in the contract enum.
AUTHORITY_IMPERSONATION = "authority_impersonation"
FAKE_FIR_OR_CASE = "fake_fir_or_case"
URGENCY_PRESSURE = "urgency_pressure"
CRYPTO_OR_GIFTCARD_DEMAND = "crypto_or_giftcard_demand"
VIDEO_CALL_ISOLATION = "video_call_isolation"
PERSONAL_DATA_REQUEST = "personal_data_request"
SUSPICIOUS_LINK = "suspicious_link"
SPOOFED_NUMBER = "spoofed_number"

ALL_MARKERS = [
    AUTHORITY_IMPERSONATION,
    FAKE_FIR_OR_CASE,
    URGENCY_PRESSURE,
    CRYPTO_OR_GIFTCARD_DEMAND,
    VIDEO_CALL_ISOLATION,
    PERSONAL_DATA_REQUEST,
    SUSPICIOUS_LINK,
    SPOOFED_NUMBER,
]

# --- pattern tables -------------------------------------------------------
# Grouped, case-insensitive regexes. Word boundaries where they matter; scam
# scripts are often ungrammatical, so patterns stay tolerant of glue text.

_MARKER_PATTERNS: dict[str, list[str]] = {
    AUTHORITY_IMPERSONATION: [
        r"\b(?:CBI|ED|NIA|RBI|TRAI|NCB|customs|cyber\s*(?:crime|cell)|income\s*tax|enforcement\s+directorate)\b",
        r"\b(?:inspector|constable|commissioner|sub[- ]?inspector|SP|DCP|ACP|IPS)\b.{0,40}\b(?:speaking|calling|here|from)\b",
        r"\bthis\s+is\s+(?:officer|inspector|constable|agent)\b",
        r"\b(?:police|crime\s*branch)\b.{0,30}\b(?:department|station|headquarters|calling|speaking)\b",
        r"\bcalling\s+from\s+(?:the\s+)?(?:police|court|ministry|government|telecom\s+department)\b",
    ],
    FAKE_FIR_OR_CASE: [
        r"\bFIR\b",
        r"\b(?:case|complaint|charge\s*sheet)\s+(?:has\s+been\s+|is\s+)?(?:registered|filed|lodged)\b",
        r"\b(?:arrest|non[- ]?bailable)\s+warrant\b",
        r"\bwarrant\s+(?:has\s+been\s+|will\s+be\s+)?issued\b",
        r"\b(?:money\s+laundering|drug\s+trafficking|hawala|narcotics)\s+(?:case|charges?|investigation)\b",
        r"\byour\s+(?:aadhaar|aadhar|PAN|sim|bank\s+account|parcel|courier)\b.{0,50}\b(?:linked|involved|used|found)\b.{0,40}\b(?:crime|illegal|laundering|fraud|drugs)\b",
        r"\b(?:legal\s+action|court\s+case|prosecution)\s+(?:will\s+be|has\s+been)\s+(?:taken|initiated|started)\b",
    ],
    URGENCY_PRESSURE: [
        r"\b(?:immediately|right\s+now|within\s+\d+\s*(?:minutes?|hours?)|urgent(?:ly)?|at\s+once)\b",
        r"\b(?:last|final)\s+(?:warning|notice|chance|reminder)\b",
        r"\b(?:account|card|sim|number|service)s?\s+will\s+be\s+(?:blocked|suspended|deactivated|frozen|disconnected)\b",
        r"\b(?:act|pay|respond|verify|update)\s+(?:now|today|immediately)\b",
        r"\bfailure\s+to\s+(?:comply|pay|respond)\b",
        r"\bdo\s+not\s+(?:delay|ignore)\b",
        r"\bexpires?\s+(?:today|tonight|in\s+\d+)\b",
    ],
    CRYPTO_OR_GIFTCARD_DEMAND: [
        r"\b(?:USDT|bitcoin|BTC|crypto(?:currency)?|tether)\b",
        r"\b(?:gift\s*cards?|google\s+play\s+(?:card|code)|amazon\s+(?:gift\s*)?card|iTunes\s+card)\b",
        r"\b(?:transfer|send|deposit|pay)\b.{0,50}\b(?:verification|security|refundable|clearance|settlement)\s+(?:amount|fee|deposit|money)\b",
        r"\b(?:RTGS|NEFT|IMPS|UPI)\b.{0,40}\b(?:immediately|now|verification|safe\s+custody)\b",
        r"\b(?:safe|government|RBI)\s+(?:custody\s+)?account\b.{0,40}\b(?:transfer|deposit|move)\b",
        r"\bmove\s+(?:all\s+)?(?:your\s+)?(?:funds|money|savings)\b.{0,40}\b(?:safe|secure|temporary|verification)\b",
    ],
    VIDEO_CALL_ISOLATION: [
        r"\b(?:stay|remain|keep)\s+on\s+(?:the\s+|this\s+)?(?:video\s+)?call\b",
        r"\bdo\s+not\s+(?:disconnect|hang\s+up|cut\s+the\s+call|leave\s+the\s+call)\b",
        r"\b(?:skype|whatsapp|zoom)\s+video\s+call\b.{0,40}\b(?:statement|interrogation|verification|questioning)\b",
        r"\bdo\s+not\s+(?:tell|inform|contact|call)\s+(?:anyone|your\s+family|relatives|friends|your\s+bank)\b",
        r"\b(?:digital|virtual|online)\s+(?:arrest|custody|surveillance)\b",
        r"\byou\s+are\s+under\s+(?:digital\s+|virtual\s+)?(?:arrest|surveillance|investigation)\b.{0,40}\b(?:camera|call|online)\b",
        r"\bkeep\s+(?:your\s+)?camera\s+on\b",
    ],
    PERSONAL_DATA_REQUEST: [
        r"\b(?:share|send|provide|confirm|verify|update)\b.{0,40}\b(?:OTP|one[- ]?time\s+password|PIN|CVV|passwords?)\b",
        r"\b(?:aadhaar|aadhar|PAN)\s+(?:number|card\s+details|details)\b",
        r"\b(?:bank|account)\s+(?:details|number|credentials)\b.{0,30}\b(?:share|send|provide|confirm|verify)\b",
        r"\b(?:share|send|provide|confirm|verify)\b.{0,30}\b(?:bank|account)\s+(?:details|number|credentials)\b",
        r"\b(?:net\s*banking|internet\s+banking)\s+(?:user\s*id|password|credentials)\b",
        r"\bdebit\s+card\s+(?:number|details)\b",
        r"\bKYC\b.{0,40}\b(?:update|verify|expire|complete|pending)\b",
    ],
    SUSPICIOUS_LINK: [
        r"\bhttps?://(?:bit\.ly|tinyurl\.com|t\.co|goo\.gl|cutt\.ly|rb\.gy|is\.gd|shorturl\.at)/\S+",
        r"\bhttps?://\d{1,3}(?:\.\d{1,3}){3}\b",  # raw-IP URL
        r"\b(?:click|tap|open|visit)\b.{0,30}\bhttps?://\S+",
        r"\bhttps?://[^\s/]*(?:-|\.)(?:kyc|verify|update|reward|refund|claim|prize|lucky)[^\s]*",
        r"\b(?:download|install)\s+(?:the\s+)?(?:anydesk|teamviewer|quick\s*support|screen\s+shar\w+)\b",
        r"\bwww\.[^\s]*(?:kyc|verify|claim|prize|reward|refund)[^\s]*",
    ],
    SPOOFED_NUMBER: [
        r"\b(?:call|dial|contact)\s+(?:back\s+)?(?:on\s+)?\+?\d{2,3}[- ]?\d{5}[- ]?\d{5}\b.{0,30}\b(?:official|government|helpline)\b",
        r"\bthis\s+(?:number|call)\s+is\s+(?:from|the)\s+(?:official|government|police|bank)\b",
        r"\b(?:landline|official)\s+number\s+of\s+(?:the\s+)?(?:police|CBI|court|department)\b",
        r"\bverify\s+(?:this|our)\s+number\s+on\s+(?:the\s+)?(?:website|portal|truecaller)\b",
    ],
}

_COMPILED: dict[str, list[re.Pattern[str]]] = {
    marker: [re.compile(p, re.IGNORECASE) for p in patterns]
    for marker, patterns in _MARKER_PATTERNS.items()
}


@dataclass
class MarkerHit:
    """One detected marker with the evidence that triggered it."""

    marker: str
    evidence: list[str]  # matched text spans, deduplicated, in document order


def detect_markers(text: str) -> list[MarkerHit]:
    """Run every marker's patterns over `text`; return hits with evidence spans."""
    hits: list[MarkerHit] = []
    for marker in ALL_MARKERS:
        spans: list[tuple[int, str]] = []
        for pattern in _COMPILED[marker]:
            for m in pattern.finditer(text):
                spans.append((m.start(), m.group(0).strip()))
        if spans:
            seen: set[str] = set()
            evidence = []
            for _, s in sorted(spans):
                key = s.lower()
                if key not in seen:
                    seen.add(key)
                    evidence.append(s)
            hits.append(MarkerHit(marker=marker, evidence=evidence))
    return hits


def marker_names(text: str) -> list[str]:
    """Just the marker names, for feature vectors and the contract payload."""
    return [h.marker for h in detect_markers(text)]


# --- scam-type inference ---------------------------------------------------
# The contract's scam_type enum: digital_arrest | phishing | lottery | loan |
# kyc | other | none. Inferred from markers + a few type-specific cues; only
# consulted when the classifier's verdict is not "legit".

_TYPE_CUES: dict[str, list[re.Pattern[str]]] = {
    "lottery": [
        re.compile(p, re.IGNORECASE)
        for p in [
            r"\b(?:lottery|lucky\s+draw|jackpot|prize|winner|won\s+(?:rs|₹|\$|\d))\b",
            r"\bclaim\s+(?:your\s+)?(?:prize|reward|winnings)\b",
        ]
    ],
    "loan": [
        re.compile(p, re.IGNORECASE)
        for p in [
            r"\b(?:instant|pre[- ]?approved|easy)\s+loan\b",
            r"\bloan\s+(?:approved|sanctioned|offer)\b",
            r"\bzero\s+(?:interest|documentation)\b",
        ]
    ],
    "kyc": [
        re.compile(p, re.IGNORECASE)
        for p in [
            r"\bKYC\b",
            r"\b(?:sim|account|wallet)\s+(?:will\s+be\s+)?(?:blocked|suspended|deactivated)\b.{0,40}\b(?:verify|update)\b",
        ]
    ],
}


def infer_scam_type(text: str, markers: list[str]) -> str:
    """Best-guess scam category. Digital arrest wins over everything: it's the
    flagship threat and its markers are the most specific."""
    digital_arrest_core = {AUTHORITY_IMPERSONATION, FAKE_FIR_OR_CASE, VIDEO_CALL_ISOLATION}
    if len(digital_arrest_core & set(markers)) >= 2:
        return "digital_arrest"
    for scam_type, patterns in _TYPE_CUES.items():
        if any(p.search(text) for p in patterns):
            return scam_type
    if SUSPICIOUS_LINK in markers or PERSONAL_DATA_REQUEST in markers:
        return "phishing"
    if AUTHORITY_IMPERSONATION in markers:
        return "digital_arrest"
    return "other"
