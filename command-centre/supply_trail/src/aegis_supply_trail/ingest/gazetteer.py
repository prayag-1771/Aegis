"""Offline place -> coordinates resolution.

A FIR record needs `lat`/`lon`, but a news article only ever gives a place NAME.
Rather than take a geocoding API dependency (a network call, a key, a rate
limit, and a failure mode), this builds a gazetteer from data the module already
ships:

  * `corridors.json` — 58 corridor nodes, each with a name and coordinates.
    These are exactly the places that matter: a seizure somewhere the corridor
    network has never heard of cannot be snapped to a corridor anyway.
  * `fir_corpus.json` — districts already in the corpus, with their coordinates
    and states.

So the gazetteer covers the network's own geography, needs no network, and
grows automatically as the corpus grows. A place it cannot resolve is reported
honestly rather than guessed at — the reviewer supplies coordinates by hand or
drops the record.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache

from ..engine import CORRIDORS_FILE, FIR_FILE

# Corridor node names carry railway/port decoration a news article never uses
# ("Kanpur Central" -> also match "Kanpur"; "Kolkata (CCU)" -> "Kolkata").
_DECORATION = re.compile(
    r"\s*(?:\((?:[^)]*)\)|\b(?:Jn|Junction|Central|Cantt|Port|Steel City)\b\.?)\s*",
    re.IGNORECASE,
)

# States are not on corridor nodes; this fills them in for the districts the
# demo geography actually spans. Used only to build a readable `ref` prefix.
_STATE_BY_PLACE: dict[str, str] = {
    "howrah": "West Bengal",
    "asansol": "West Bengal",
    "haldia": "West Bengal",
    "kolkata": "West Bengal",
    "dhanbad": "Jharkhand",
    "bokaro": "Jharkhand",
    "gomoh": "Jharkhand",
    "koderma": "Jharkhand",
    "hazaribagh": "Jharkhand",
    "jamtara": "Jharkhand",
    "deoghar": "Jharkhand",
    "gaya": "Bihar",
    "sasaram": "Bihar",
    "patna": "Bihar",
    "varanasi": "Uttar Pradesh",
    "allahabad": "Uttar Pradesh",
    "kanpur": "Uttar Pradesh",
    "agra": "Uttar Pradesh",
    "mathura": "Uttar Pradesh",
    "new delhi": "Delhi",
    "delhi": "Delhi",
    "gurugram": "Haryana",
    "nuh": "Haryana",
    "jaipur": "Rajasthan",
    "ajmer": "Rajasthan",
    "udaipur": "Rajasthan",
    "kota": "Rajasthan",
    "alwar": "Rajasthan",
    "bharatpur": "Rajasthan",
    "sawai madhopur": "Rajasthan",
    "ahmedabad": "Gujarat",
    "vadodara": "Gujarat",
    "surat": "Gujarat",
    "ratlam": "Madhya Pradesh",
    "mumbai": "Maharashtra",
    "borivali": "Maharashtra",
    "vapi": "Gujarat",
    "chennai": "Tamil Nadu",
    "visakhapatnam": "Andhra Pradesh",
    "paradip": "Odisha",
    "kochi": "Kerala",
    "kollam": "Kerala",
    "kozhikode": "Kerala",
    "mangalore": "Karnataka",
    "karwar": "Karnataka",
    "mormugao": "Goa",
    "ratnagiri": "Maharashtra",
    "nagapattinam": "Tamil Nadu",
}

# Two-letter-ish state codes for the `ref` prefix, matching the existing corpus
# convention (FIR-JHK-…, FIR-WB-…, FIR-UP-…).
_STATE_CODE: dict[str, str] = {
    "West Bengal": "WB",
    "Jharkhand": "JHK",
    "Bihar": "BR",
    "Uttar Pradesh": "UP",
    "Delhi": "DELHI",
    "Haryana": "HR",
    "Rajasthan": "RJ",
    "Gujarat": "GJ",
    "Madhya Pradesh": "MP",
    "Maharashtra": "MH",
    "Tamil Nadu": "TN",
    "Andhra Pradesh": "AP",
    "Odisha": "OD",
    "Kerala": "KL",
    "Karnataka": "KA",
    "Goa": "GA",
}


def _clean(name: str) -> str:
    """Strip station/port decoration and normalise for matching."""
    return _DECORATION.sub(" ", name).strip().lower()


def state_code(state: str | None) -> str:
    return _STATE_CODE.get(state or "", "IN")


@lru_cache(maxsize=1)
def gazetteer() -> dict[str, tuple[float, float, str | None]]:
    """name (lowercased) -> (lat, lon, state). Built once, cached.

    Corridor nodes are added under both their full name and their cleaned form,
    so "Kanpur Central" in the data matches "Kanpur" in a headline. FIR corpus
    districts win on conflict — they carry a real state and a district-level
    coordinate rather than a station platform.
    """
    table: dict[str, tuple[float, float, str | None]] = {}

    try:
        corridors = json.loads(CORRIDORS_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        corridors = []
    for corridor in corridors:
        for node in corridor.get("node_path", []):
            name = node.get("name")
            if not name or node.get("lat") is None or node.get("lon") is None:
                continue
            coords = (float(node["lat"]), float(node["lon"]))
            cleaned = _clean(name)
            # Both spellings inherit the same state: "Kanpur Central" is in the
            # same state as "Kanpur", but only the cleaned form is in the table.
            state = _STATE_BY_PLACE.get(cleaned) or _STATE_BY_PLACE.get(name.strip().lower())
            for key in {name.strip().lower(), cleaned}:
                if key and key not in table:
                    table[key] = (*coords, state)

    # FIR districts override — better provenance than a station coordinate.
    try:
        corpus = json.loads(FIR_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        corpus = []
    for entry in corpus:
        district = (entry.get("district") or "").strip()
        if not district or entry.get("lat") is None:
            continue
        table[district.lower()] = (
            float(entry["lat"]),
            float(entry["lon"]),
            entry.get("state") or _STATE_BY_PLACE.get(district.lower()),
        )

    return table


def resolve(place: str) -> tuple[float, float, str | None] | None:
    """Look up one place name. Tries the exact name, then the cleaned form."""
    if not place:
        return None
    table = gazetteer()
    for key in (place.strip().lower(), _clean(place)):
        if key in table:
            return table[key]
    return None


def find_places(text: str) -> list[str]:
    """Every gazetteer place mentioned in `text`, longest match first.

    Longest-first matters: "New Delhi" must not be reported as "Delhi", and a
    headline naming both a district and its state capital should surface both
    rather than collapsing them.
    """
    if not text:
        return []
    lowered = text.lower()
    hits: list[str] = []
    for name in sorted(gazetteer(), key=len, reverse=True):
        # Word-boundary match so "Gaya" does not fire inside "Gayathri".
        if re.search(rf"\b{re.escape(name)}\b", lowered):
            # Skip a shorter name already covered by a longer accepted match.
            if any(name in seen for seen in hits):
                continue
            hits.append(name)
    return [h.title() for h in hits]


def unresolved(places: list[str]) -> list[str]:
    """Places with no coordinates — the reviewer must supply or drop these."""
    return [p for p in places if resolve(p) is None]
