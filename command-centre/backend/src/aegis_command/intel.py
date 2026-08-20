"""Intelligence analysis over accumulated detections — stdlib only.

Plate-family linkage
--------------------
Counterfeits from the same production source fail the SAME security features:
a plate that can't reproduce the security thread fails it on every note it
prints. Grouping seizures by shared printing defects is standard currency
forensics (the US Secret Service classifies counterfeits into "classes" by
reproducible defects). Our `missing_features` field is a lightweight proxy for
that defect signature, so notes can be linked to a common source *candidate*.

Honestly stated: a defect overlap is an investigative lead, not forensic proof
— tiers make the strength explicit and every family lists its evidence.

    high      identical defect signature + same denomination
    probable  Jaccard(defects) >= 0.5    + same denomination
    possible  >=1 shared defect          + same denomination
"""

from __future__ import annotations

import hashlib
import math
import os
import re
from collections import defaultdict
from typing import Any

# ── PII redaction ───────────────────────────────────────────────────────────
#
# Everything built here travels further than it looks. Campaigns are returned by
# GET /intel/campaigns (no authentication — see docs/privacy.md P1) AND embedded
# whole into the AI Case Officer dossier, which is serialised to Claude / Groq /
# Gemini. So a raw phone number or a raw message excerpt in this module is a
# personal identifier published to the internet and shipped to a third-party
# processor outside India.
#
# Both are redacted at the source rather than at each consumer, so a new caller
# cannot reintroduce the leak by forgetting to sanitise.

_PHONE_SALT = os.environ.get("AEGIS_PII_SALT", "aegis-local-dev-salt").encode()

_DIGIT_RUN = re.compile(r"\d[\d\s\-]{4,}\d")   # phone / account / card / OTP runs
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_URL = re.compile(r"(https?://|www\.)\S+")
_UPI = re.compile(r"\b[\w.\-]{2,}@[a-z]{2,}\b", re.I)


def phone_ref(number: str | None) -> str | None:
    """Stable pseudonym for a phone number — same number gives the same ref, and
    the digits cannot be recovered without the salt. Correlation (the only thing
    campaign clustering actually needs) is preserved."""
    if not number:
        return None
    digest = hashlib.blake2b(str(number).encode(), key=_PHONE_SALT, digest_size=5).hexdigest()
    return f"ph_{digest}"


def redact(text: str | None) -> str:
    """Mask identifiers inside a free-text excerpt, keeping the scam WORDING —
    which is the whole investigative value of a sample — while removing digits,
    emails, links and UPI handles. 'Pay 50000 to x@ybl' becomes
    'Pay [number] to [upi]': still recognisably the same script, no payload."""
    if not text:
        return ""
    out = _URL.sub("[link]", str(text))
    out = _EMAIL.sub("[email]", out)
    out = _UPI.sub("[upi]", out)
    out = _DIGIT_RUN.sub("[number]", out)
    return out

# match tiers, strongest first — index doubles as sort rank
_TIERS = ("high", "probable", "possible")


def _haversine_km(a: tuple[float, float], b: tuple[float, float]) -> float:
    r = 6371.0
    p1, p2 = math.radians(a[0]), math.radians(b[0])
    dp = math.radians(b[0] - a[0])
    dl = math.radians(b[1] - a[1])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def _pair_tier(d1: frozenset[str], d2: frozenset[str]) -> str | None:
    """Match strength between two defect signatures (same denomination assumed)."""
    if not d1 or not d2:
        return None
    shared = d1 & d2
    if not shared:
        return None
    if d1 == d2:
        return "high"
    if len(shared) / len(d1 | d2) >= 0.5:
        return "probable"
    return "possible"


def plate_families(counterfeits: list[dict]) -> list[dict]:
    """Cluster fake-note detections into candidate plate families.

    Returns one dict per family (>=2 members), strongest tier first:
    members, denomination, tier, shared_defects, districts, span_km, links.
    """
    fakes = [
        c for c in counterfeits
        if c.get("verdict") == "fake" and c.get("missing_features")
    ]
    by_denom: dict[str, list[dict]] = defaultdict(list)
    for c in fakes:
        by_denom[str(c.get("denomination", "?"))].append(c)

    families: list[dict] = []
    for denom, notes in by_denom.items():
        n = len(notes)
        if n < 2:
            continue
        sigs = [frozenset(c.get("missing_features") or []) for c in notes]
        # union-find over pairwise defect links
        parent = list(range(n))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        links: list[tuple[int, int, str]] = []
        for i in range(n):
            for j in range(i + 1, n):
                tier = _pair_tier(sigs[i], sigs[j])
                if tier:
                    links.append((i, j, tier))
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[ri] = rj

        groups: dict[int, list[int]] = defaultdict(list)
        for i in range(n):
            groups[find(i)].append(i)

        for members in groups.values():
            if len(members) < 2:
                continue
            mset = set(members)
            fam_links = [l for l in links if l[0] in mset and l[1] in mset]
            # family tier = strongest pair link inside it (per-link evidence kept)
            tier = min((l[2] for l in fam_links), key=_TIERS.index)
            shared_all = frozenset.intersection(*(sigs[i] for i in members))
            events = [notes[i] for i in members]
            events.sort(key=lambda c: c.get("timestamp") or "")
            coords = [
                (c["location_hint"]["lat"], c["location_hint"]["lon"])
                for c in events
                if (c.get("location_hint") or {}).get("lat") is not None
            ]
            span = max(
                (_haversine_km(a, b) for a in coords for b in coords), default=0.0
            )
            families.append({
                "family_id": f"plate_{denom}_{min(members):02d}",
                "denomination": denom,
                "tier": tier,
                "n_notes": len(events),
                "shared_defects": sorted(shared_all),
                "districts": sorted({
                    (c.get("location_hint") or {}).get("district")
                    for c in events
                    if (c.get("location_hint") or {}).get("district")
                }),
                "span_km": round(span, 1),
                "first_seen": events[0].get("timestamp"),
                "last_seen": events[-1].get("timestamp"),
                "events": [
                    {
                        "event_id": c.get("event_id"),
                        "district": (c.get("location_hint") or {}).get("district"),
                        "lat": (c.get("location_hint") or {}).get("lat"),
                        "lon": (c.get("location_hint") or {}).get("lon"),
                        "timestamp": c.get("timestamp"),
                        "missing_features": c.get("missing_features") or [],
                    }
                    for c in events
                ],
                "links": [
                    {
                        "a": notes[i].get("event_id"),
                        "b": notes[j].get("event_id"),
                        "tier": t,
                        "shared": sorted(sigs[i] & sigs[j]),
                    }
                    for i, j, t in fam_links
                ],
                "note": (
                    "Shared printing-defect signature is consistent with a common "
                    "production source — an investigative lead, not forensic proof."
                ),
            })

    families.sort(key=lambda f: (_TIERS.index(f["tier"]), -f["n_notes"]))
    return families


def plate_family_summary(families: list[dict]) -> dict[str, Any]:
    """Headline stats for the dashboard chip."""
    return {
        "n_families": len(families),
        "n_linked_notes": sum(f["n_notes"] for f in families),
        "multi_district": sum(1 for f in families if len(f["districts"]) > 1),
    }


# ── scam campaign fingerprinting ─────────────────────────────────────────────
#
# One gang runs one script. Near-identical scam texts hitting different
# districts are ONE campaign, not isolated complaints — the same insight
# phishing-campaign attribution uses. Detection is deterministic (token/bigram
# overlap + shared callback numbers), so the linkage is auditable.
#
#     high      token Jaccard >= 0.7, or the same callback phone number
#     probable  token Jaccard >= 0.5
#     possible  token Jaccard >= 0.3 AND >= 3 shared distinctive bigrams
#               (bigrams guard against generic-word coincidence)

import re as _re


def _tokens(text: str) -> frozenset[str]:
    return frozenset(_re.findall(r"[a-z]{3,}", (text or "").lower()))


def _bigrams(text: str) -> frozenset[tuple[str, str]]:
    ws = _re.findall(r"[a-z]{3,}", (text or "").lower())
    return frozenset(zip(ws, ws[1:]))


def _script_tier(t1: frozenset, t2: frozenset, b1: frozenset, b2: frozenset) -> tuple[str | None, float]:
    if not t1 or not t2:
        return None, 0.0
    jac = len(t1 & t2) / len(t1 | t2)
    if jac >= 0.7:
        return "high", jac
    if jac >= 0.5:
        return "probable", jac
    if jac >= 0.3 and len(b1 & b2) >= 3:
        return "possible", jac
    return None, jac


def scam_campaigns(scams: list[dict]) -> list[dict]:
    """Cluster non-legit scam events into campaigns (>=2 events each)."""
    events = [s for s in scams if s.get("verdict") != "legit" and s.get("raw_text")]
    n = len(events)
    if n < 2:
        return []
    toks = [_tokens(s["raw_text"]) for s in events]
    bigs = [_bigrams(s["raw_text"]) for s in events]
    phones = [s.get("phone_number") for s in events]

    parent = list(range(n))

    def find(i: int) -> int:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    links: list[dict] = []
    for i in range(n):
        for j in range(i + 1, n):
            tier, jac = _script_tier(toks[i], toks[j], bigs[i], bigs[j])
            basis = []
            if tier:
                basis.append("script")
            if phones[i] and phones[i] == phones[j]:
                basis.append("phone")
                tier = "high"  # same callback device = same operator
            if not basis:
                continue
            links.append({
                "a": events[i].get("event_id"), "b": events[j].get("event_id"),
                "i": i, "j": j, "tier": tier,
                "similarity": round(jac, 3), "basis": basis,
            })
            ri, rj = find(i), find(j)
            if ri != rj:
                parent[ri] = rj

    groups: dict[int, list[int]] = defaultdict(list)
    for i in range(n):
        groups[find(i)].append(i)

    campaigns: list[dict] = []
    for members in groups.values():
        if len(members) < 2:
            continue
        mset = set(members)
        camp_links = [l for l in links if l["i"] in mset and l["j"] in mset]
        tier = min((l["tier"] for l in camp_links), key=_TIERS.index)
        evs = sorted((events[i] for i in members), key=lambda s: s.get("timestamp") or "")
        # district spread in chronological order — the campaign's movement story
        spread: list[str] = []
        for s in evs:
            d = (s.get("location_hint") or {}).get("district")
            if d and d not in spread:
                spread.append(d)
        camp_phones = sorted({p for i in members if (p := phones[i])})
        types = [s.get("scam_type") for s in evs if s.get("scam_type")]
        campaigns.append({
            "campaign_id": f"campaign_{min(members):02d}",
            "tier": tier,
            "n_events": len(evs),
            "scam_type": max(set(types), key=types.count) if types else "other",
            "district_spread": spread,
            # Pseudonymous refs, not digits. The dashboard only renders
            # len(phone_numbers), so the count is unaffected.
            "phone_numbers": [phone_ref(p) for p in camp_phones],
            "first_seen": evs[0].get("timestamp"),
            "last_seen": evs[-1].get("timestamp"),
            "sample_text": redact((evs[0].get("raw_text") or ""))[:180],
            "events": [
                {
                    "event_id": s.get("event_id"),
                    "district": (s.get("location_hint") or {}).get("district"),
                    "timestamp": s.get("timestamp"),
                    "phone_number": phone_ref(s.get("phone_number")),
                }
                for s in evs
            ],
            "links": [
                {k: v for k, v in l.items() if k not in ("i", "j")}
                for l in camp_links
            ],
            "note": (
                "Near-identical scripts (and/or a shared callback number) across "
                "events indicate one operation — an investigative lead for "
                "consolidating complaints into a single case."
            ),
        })

    campaigns.sort(key=lambda c: (_TIERS.index(c["tier"]), -c["n_events"]))
    return campaigns


def campaign_summary(campaigns: list[dict]) -> dict[str, Any]:
    return {
        "n_campaigns": len(campaigns),
        "n_linked_events": sum(c["n_events"] for c in campaigns),
        "multi_district": sum(1 for c in campaigns if len(c["district_spread"]) > 1),
    }
