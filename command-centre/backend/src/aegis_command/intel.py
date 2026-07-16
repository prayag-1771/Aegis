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

import math
from collections import defaultdict
from typing import Any

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
