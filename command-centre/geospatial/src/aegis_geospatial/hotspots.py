"""Cross-domain crime hotspot clustering (innovation #3).

Takes the map points from all three signal domains (scam origins, counterfeit
seizures, fraud-ring districts) and clusters them with DBSCAN on haversine
distance. A cluster containing MULTIPLE domains is the headline signal:
independent detection systems converging on one place = coordinated crime hub.

No heavy deps: DBSCAN at demo scale (hundreds of points) is implemented
directly — O(n^2) is fine and keeps the geospatial layer dependency-free.
Swap for sklearn.cluster.DBSCAN(metric="haversine") if point counts grow.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

EPS_KM = 25.0  # neighbourhood radius
MIN_POINTS = 2  # a hub needs at least 2 signals


def _haversine_km(a: dict, b: dict) -> float:
    r = 6371.0
    p1, p2 = math.radians(a["lat"]), math.radians(b["lat"])
    dp = math.radians(b["lat"] - a["lat"])
    dl = math.radians(b["lon"] - a["lon"])
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


@dataclass
class Hub:
    hub_id: str
    lat: float  # centroid
    lon: float
    domains: list[str]  # which signal types converge here
    cross_domain: bool  # >= 2 distinct domains -> coordinated hub candidate
    intensity: float  # sum of point weights
    district: str | None
    points: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return {
            "hub_id": self.hub_id,
            "lat": round(self.lat, 5),
            "lon": round(self.lon, 5),
            "domains": self.domains,
            "cross_domain": self.cross_domain,
            "intensity": round(self.intensity, 3),
            "district": self.district,
            "n_points": len(self.points),
            "points": self.points,
        }


def cluster_hotspots(points: list[dict], eps_km: float = EPS_KM, min_points: int = MIN_POINTS) -> list[Hub]:
    """DBSCAN over map points. Each point: {type, lat, lon, weight?, district?}."""
    points = [p for p in points if p.get("lat") is not None and p.get("lon") is not None]
    n = len(points)
    labels = [None] * n  # None = unvisited, -1 = noise, >=0 cluster id
    cluster = 0

    def neighbours(i: int) -> list[int]:
        return [j for j in range(n) if j != i and _haversine_km(points[i], points[j]) <= eps_km]

    for i in range(n):
        if labels[i] is not None:
            continue
        nbrs = neighbours(i)
        if len(nbrs) + 1 < min_points:
            labels[i] = -1
            continue
        labels[i] = cluster
        seeds = list(nbrs)
        while seeds:
            j = seeds.pop()
            if labels[j] == -1:
                labels[j] = cluster
            if labels[j] is not None:
                continue
            labels[j] = cluster
            j_nbrs = neighbours(j)
            if len(j_nbrs) + 1 >= min_points:
                seeds.extend(k for k in j_nbrs if labels[k] is None)
        cluster += 1

    hubs: list[Hub] = []
    for cid in range(cluster):
        members = [points[i] for i in range(n) if labels[i] == cid]
        if not members:
            continue
        domains = sorted({m["type"] for m in members})
        districts = [m.get("district") for m in members if m.get("district")]
        hubs.append(
            Hub(
                hub_id=f"hub_{cid + 1:02d}",
                lat=sum(m["lat"] for m in members) / len(members),
                lon=sum(m["lon"] for m in members) / len(members),
                domains=domains,
                cross_domain=len(domains) >= 2,
                intensity=sum(float(m.get("weight", 0.5)) for m in members),
                district=max(set(districts), key=districts.count) if districts else None,
                points=members,
            )
        )
    # cross-domain hubs first, then by intensity — render order for the map
    hubs.sort(key=lambda h: (not h.cross_domain, -h.intensity))
    return hubs
