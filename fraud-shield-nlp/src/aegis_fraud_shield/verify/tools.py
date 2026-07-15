"""Verification tools — the hard-evidence layer.

Each tool returns a dict shaped `{"entity", "entity_type", "ok", "source",
...findings}` where `source` is "live" (a real network call succeeded) or
"offline" (heuristics / fixtures only). Every tool tries live first and falls
back to offline within a per-call timeout, so a flaky venue network degrades
gracefully instead of hanging the demo.

None of these need an API key:
- resolve_url        -> a plain HTTP GET of a public page (SSRF-hardened)
- validate_ifsc      -> Razorpay's free public IFSC API (no key, no signup)
- validate_upi       -> pure offline PSP-handle validation
- phone_reputation   -> pure offline heuristics

Only the LLM *synthesis* (agent.py) uses a key, and it has its own fallback.
"""

from __future__ import annotations

import ipaddress
import re
import socket
from urllib.parse import urlparse

# Reuse the URL / phone patterns the marker layer already defines — don't
# reinvent detection here.
from ..markers import _COMPILED  # noqa: F401 (kept for parity / future use)

# --- entity extraction -----------------------------------------------------

_URL_RE = re.compile(
    r"\b(?:https?://)?(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,}(?:/[^\s]*)?",
    re.IGNORECASE,
)
_UPI_RE = re.compile(r"\b[a-z0-9.\-_]{2,256}@[a-z]{2,64}\b", re.IGNORECASE)
_IFSC_RE = re.compile(r"\b[A-Z]{4}0[A-Z0-9]{6}\b")
_PHONE_RE = re.compile(r"(?<!\d)(?:\+?91[\-\s]?|0)?[6-9]\d{9}(?!\d)")

# A UPI handle and an email look alike; these PSP suffixes mark a real UPI VPA.
_KNOWN_PSPS = {
    "okhdfcbank", "okicici", "oksbi", "okaxis", "ybl", "ibl", "axl", "paytm",
    "apl", "upi", "phonepe", "gpay", "airtel", "freecharge", "fbl",
}
_EMAIL_TLDS = {"com", "in", "org", "net", "co", "io", "gov", "edu"}


def extract_entities(text: str) -> dict[str, list[str]]:
    """Pull the concrete identifiers a scammer relies on. No network."""
    ifscs = _IFSC_RE.findall(text)
    # UPI vs email: an @suffix that's a known PSP (or not a TLD) is a UPI handle.
    upis, emails = [], []
    for m in _UPI_RE.findall(text):
        suffix = m.rsplit("@", 1)[1].lower()
        (upis if (suffix in _KNOWN_PSPS or suffix not in _EMAIL_TLDS) else emails).append(m)
    urls = []
    for m in _URL_RE.findall(text):
        # Drop bare emails the URL regex may catch; keep things with a path or a
        # known-shortener/lookalike shape.
        if "@" in m:
            continue
        urls.append(m if m.lower().startswith("http") else "http://" + m)
    return {
        "urls": _dedupe(urls),
        "upi_handles": _dedupe(upis),
        "ifsc_codes": _dedupe([c.upper() for c in ifscs]),
        "phone_numbers": _dedupe(_PHONE_RE.findall(text)),
    }


def _dedupe(items: list[str]) -> list[str]:
    seen, out = set(), []
    for it in items:
        k = it.lower()
        if k not in seen:
            seen.add(k)
            out.append(it)
    return out


# --- SSRF guard ------------------------------------------------------------

_BRANDS = ["paytm", "phonepe", "sbi", "hdfc", "icici", "axis", "rbi", "npci",
          "kotak", "airtel", "amazon", "flipkart"]
_SHORTENERS = {"bit.ly", "tinyurl.com", "t.co", "goo.gl", "cutt.ly", "rb.gy",
               "is.gd", "shorturl.at", "ow.ly", "buff.ly"}


def _is_public_host(host: str) -> bool:
    """Resolve `host` and reject if ANY resolved IP is private / loopback /
    link-local / reserved. Re-checked on every redirect hop by the caller —
    redirect-to-internal is the classic SSRF bypass."""
    try:
        infos = socket.getaddrinfo(host, None)
    except (socket.gaierror, UnicodeError):
        return False
    for info in infos:
        ip = ipaddress.ip_address(info[4][0])
        if (ip.is_private or ip.is_loopback or ip.is_link_local
                or ip.is_reserved or ip.is_multicast or ip.is_unspecified):
            return False
    return True


def _levenshtein(a: str, b: str) -> int:
    """Tiny pure-Python edit distance (no dependency) for typosquat scoring."""
    if a == b:
        return 0
    if not a or not b:
        return len(a) or len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _typosquat_of(host: str) -> str | None:
    """Nearest brand a host label mimics, else None. Shorteners are never
    squats (they don't pretend to be a brand), exact brand substrings are
    legit ('hdfcbank'), and the edit-distance bar scales with brand length so
    short common words ('bit' in bit.ly) don't collide with short brands
    ('sbi')."""
    host = host.lower()
    if host in _SHORTENERS:
        return None
    for label in host.split("."):
        for brand in _BRANDS:
            if brand in label or label in brand:
                return None  # contains / is the real brand token — not a squat
            bar = 1 if len(brand) <= 4 else 2
            # Only compare similar-length labels (a squat mimics the brand).
            if abs(len(label) - len(brand)) <= 1 and 0 < _levenshtein(label, brand) <= bar:
                return brand
    return None


def _offline_url(url: str) -> dict:
    host = (urlparse(url).hostname or "").lower()
    squat = _typosquat_of(host)
    return {
        "entity": url, "entity_type": "url", "ok": True, "source": "offline",
        "final_host": host, "is_shortener": host in _SHORTENERS,
        "typosquat_of": squat, "redirects": None, "solicits_credentials": None,
        "detail": _url_detail(host, host in _SHORTENERS, squat, None),
    }


def _url_detail(host, is_short, squat, solicits) -> str:
    bits = []
    if is_short:
        bits.append(f"{host} is a URL shortener (destination hidden)")
    if squat:
        bits.append(f"host '{host}' looks like a typo of '{squat}'")
    if solicits:
        bits.append("landing page solicits OTP/card details")
    return "; ".join(bits) or f"resolved to {host}"


def resolve_url(url: str, timeout_s: float = 4.0, max_redirects: int = 5,
                max_body_bytes: int = 2048) -> dict:
    """Follow a shortlink to its real destination and sniff the landing page.

    SSRF-hardened: http/https only, and every hop's host must resolve to a
    public IP (re-checked after each redirect). Falls back to offline
    string-only heuristics on any failure."""
    host0 = (urlparse(url if url.startswith("http") else "http://" + url).hostname or "")
    try:
        import httpx

        current = url if url.startswith("http") else "http://" + url
        for _ in range(max_redirects + 1):
            parsed = urlparse(current)
            if parsed.scheme not in ("http", "https"):
                return _offline_url(url)
            if not _is_public_host(parsed.hostname or ""):
                # internal/metadata target — refuse and report offline view
                return _offline_url(url)
            resp = httpx.get(current, follow_redirects=False, timeout=timeout_s,
                             headers={"User-Agent": "AegisFraudShield/1.0"})
            if resp.is_redirect and "location" in resp.headers:
                current = str(resp.next_request.url) if resp.next_request else resp.headers["location"]
                continue
            body = resp.text[:max_body_bytes].lower()
            host = urlparse(current).hostname or ""
            solicits = bool(re.search(r"\b(otp|cvv|card number|net ?banking|password|pin)\b", body))
            squat = _typosquat_of(host)
            return {
                "entity": url, "entity_type": "url", "ok": True, "source": "live",
                "final_host": host, "is_shortener": host0 in _SHORTENERS,
                "typosquat_of": squat, "redirects": current != url,
                "solicits_credentials": solicits,
                "detail": _url_detail(host, host0 in _SHORTENERS, squat, solicits),
            }
        return _offline_url(url)
    except Exception:  # noqa: BLE001 — any network/parse failure degrades offline
        return _offline_url(url)


# --- IFSC (Razorpay free public API) --------------------------------------

_IFSC_BANK_PREFIX = {
    "SBIN": "State Bank of India", "HDFC": "HDFC Bank", "ICIC": "ICICI Bank",
    "UTIB": "Axis Bank", "PUNB": "Punjab National Bank", "KKBK": "Kotak Mahindra Bank",
    "CNRB": "Canara Bank", "BARB": "Bank of Baroda", "IOBA": "Indian Overseas Bank",
    "UBIN": "Union Bank of India",
}


def validate_ifsc(ifsc: str, claimed_bank: str | None = None, timeout_s: float = 4.0) -> dict:
    """Confirm an IFSC is real and whose it is. Razorpay's keyless public API,
    with an offline format+prefix fallback."""
    ifsc = ifsc.upper().strip()
    well_formed = bool(_IFSC_RE.fullmatch(ifsc))
    base = {"entity": ifsc, "entity_type": "ifsc", "well_formed": well_formed}
    if not well_formed:
        return {**base, "ok": False, "source": "offline",
                "detail": f"{ifsc} is not a valid IFSC format"}
    try:
        import httpx

        resp = httpx.get(f"https://ifsc.razorpay.com/{ifsc}", timeout=timeout_s)
        if resp.status_code == 404:
            return {**base, "ok": True, "source": "live", "exists": False,
                    "bank": None, "detail": f"{ifsc} is not a real IFSC code (not found)"}
        resp.raise_for_status()
        data = resp.json()
        bank = data.get("BANK")
        mism = bool(claimed_bank and bank and claimed_bank.lower() not in bank.lower())
        return {**base, "ok": True, "source": "live", "exists": True, "bank": bank,
                "branch": data.get("BRANCH"), "bank_mismatch": mism,
                "detail": (f"IFSC {ifsc} belongs to {bank}"
                           + (f", not '{claimed_bank}' as claimed" if mism else ""))}
    except Exception:  # noqa: BLE001
        bank = _IFSC_BANK_PREFIX.get(ifsc[:4])
        return {**base, "ok": True, "source": "offline", "exists": None, "bank": bank,
                "detail": (f"IFSC {ifsc} format valid; prefix maps to {bank}" if bank
                           else f"IFSC {ifsc} format valid; bank unknown offline")}


def validate_upi(handle: str) -> dict:
    """Validate a name@psp UPI handle offline — flag unknown/lookalike PSPs."""
    handle = handle.strip()
    if "@" not in handle:
        return {"entity": handle, "entity_type": "upi", "ok": False,
                "source": "offline", "detail": f"{handle} is not a UPI handle"}
    psp = handle.rsplit("@", 1)[1].lower()
    known = psp in _KNOWN_PSPS
    squat = None if known else next(
        (p for p in _KNOWN_PSPS if 0 < _levenshtein(psp, p) <= 2), None)
    return {"entity": handle, "entity_type": "upi", "ok": True, "source": "offline",
            "psp": psp, "known_psp": known, "lookalike_of": squat,
            "detail": (f"UPI PSP '{psp}' is recognised" if known
                       else f"UPI PSP '{psp}' is not a known provider"
                            + (f" (looks like '{squat}')" if squat else ""))}


def phone_reputation(number: str) -> dict:
    """Offline reputation heuristics for an Indian phone number."""
    digits = re.sub(r"\D", "", number)
    # Strip a leading country/trunk code so `local` is the 10-digit subscriber part.
    trunk = digits
    if len(trunk) > 10 and trunk.startswith("91"):
        trunk = trunk[2:]
    trunk = trunk.lstrip("0")
    local = trunk[-10:]
    flags = []
    if len(digits) > 12:
        flags.append("unusually long / possibly spoofed")
    if len(local) < 10:
        flags.append("too short to be a valid Indian mobile")
    if local and local[0] in "12345":
        flags.append("does not start 6-9 (not a valid Indian mobile)")
    if len(set(local)) <= 2 and local:
        flags.append("repeated-digit pattern")
    return {"entity": number, "entity_type": "phone", "ok": True, "source": "offline",
            "normalized": local, "suspicious": bool(flags),
            "detail": ("; ".join(flags) if flags else f"{local} looks like a normal number")}
