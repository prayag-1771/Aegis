"""Supply Trail Engine — counterfeit provenance inference.

What this does (honestly stated):
    Given a set of fake-note seizure locations, this engine:
    1. Snaps each seizure to the nearest transport corridor (rail/road/ship/air)
    2. Clusters seizures along each corridor using haversine distance
    3. Walks the corridor outward from the densest cluster; the last seizure
       before a major gap → candidate injection zone → inferred origin
    4. Corroborates with the FIR corpus (public news + police press releases)
    5. Scores and emits a SupplyTrail contract with every claim traceable

What this is NOT:
    Forensic proof. A note carries no origin label. This is a weighted
    hypothesis engine — exactly how real financial-crime intelligence works
    ("follow the corridor"). The output is labelled with a confidence band and
    a mandatory disclaimer. Frame it as an investigative lead, not a verdict.

Output: dict matching contracts/supply_trail.schema.json
"""

from __future__ import annotations

import json
import math
import re
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

# ── paths ──────────────────────────────────────────────────────────────────
#  __file__ = .../supply_trail/src/aegis_supply_trail/engine.py
#  parents[0] = aegis_supply_trail/
#  parents[1] = src/
#  parents[2] = supply_trail/      ← module root
#  parents[3] = command-centre/
#  parents[4] = Aegis/             ← repo root
_DATA = Path(__file__).resolve().parents[2] / "data"
CORRIDORS_FILE = _DATA / "corridors.json"
FIR_FILE = _DATA / "fir_corpus.json"
SCHEMA_FILE = (
    Path(__file__).resolve().parents[4] / "contracts" / "supply_trail.schema.json"
)

# ── tuning constants ────────────────────────────────────────────────────────
SNAP_RADIUS_KM = 60.0     # max distance from a seizure to count as "on" a corridor
GAP_KM = 150.0            # corridor gap that signals the end of the seizure cluster
FIR_MATCH_RADIUS_KM = 80.0  # how close a FIR location must be to a corridor node to count
MIN_SEIZURES_FOR_TRAIL = 1   # a single seizure still generates a (low-confidence) trail


# ── data structures ─────────────────────────────────────────────────────────

@dataclass
class Node:
    name: str
    lat: float
    lon: float
    is_major_hub: bool = False


@dataclass
class Corridor:
    id: str
    name: str
    mode: str
    nodes: list[Node]
    raw: dict = field(repr=False, default_factory=dict)


@dataclass
class Seizure:
    event_id: str
    lat: float
    lon: float
    district: str
    denomination: str = "unknown"
    timestamp: str = ""


@dataclass
class FirEntry:
    ref: str
    district: str
    lat: float
    lon: float
    date: str
    source: str
    text: str
    places: list[str]
    crime_types: list[str]


@dataclass
class SnapResult:
    seizure: Seizure
    corridor: Corridor
    nearest_node: Node
    dist_km: float
    node_index: int   # position in corridor.nodes — used for tracing direction


# ── haversine ───────────────────────────────────────────────────────────────

def _hav(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(min(h, 1.0)))


# ── loaders ─────────────────────────────────────────────────────────────────

def load_corridors() -> list[Corridor]:
    raw = json.loads(CORRIDORS_FILE.read_text(encoding="utf-8"))
    corridors = []
    for c in raw:
        nodes = [
            Node(
                name=n["name"],
                lat=n["lat"],
                lon=n["lon"],
                is_major_hub=n.get("is_major_hub", False),
            )
            for n in c["node_path"]
        ]
        corridors.append(Corridor(id=c["id"], name=c["name"], mode=c["mode"],
                                  nodes=nodes, raw=c))
    return corridors


def load_fir_corpus() -> list[FirEntry]:
    raw = json.loads(FIR_FILE.read_text(encoding="utf-8"))
    return [
        FirEntry(
            ref=e["ref"],
            district=e["district"],
            lat=e["lat"],
            lon=e["lon"],
            date=e["date"],
            source=e["source"],
            text=e["text"],
            places=e.get("places", []),
            crime_types=e.get("crime_types", []),
        )
        for e in raw
    ]


# ── step 1 — snap seizures to corridors ─────────────────────────────────────

def snap_seizures(
    seizures: list[Seizure],
    corridors: list[Corridor],
    radius_km: float = SNAP_RADIUS_KM,
) -> dict[str, list[SnapResult]]:
    """For each corridor, collect all seizures within radius_km of any node.
    Returns {corridor_id: [SnapResult, ...]}.
    """
    result: dict[str, list[SnapResult]] = {c.id: [] for c in corridors}

    for seizure in seizures:
        for corridor in corridors:
            best_dist = float("inf")
            best_node = None
            best_idx = 0
            for idx, node in enumerate(corridor.nodes):
                d = _hav(seizure.lat, seizure.lon, node.lat, node.lon)
                if d < best_dist:
                    best_dist = d
                    best_node = node
                    best_idx = idx
            if best_dist <= radius_km and best_node is not None:
                result[corridor.id].append(
                    SnapResult(
                        seizure=seizure,
                        corridor=corridor,
                        nearest_node=best_node,
                        dist_km=best_dist,
                        node_index=best_idx,
                    )
                )

    return result


# ── step 2 — cluster centroid ────────────────────────────────────────────────

def _centroid(snaps: list[SnapResult]) -> tuple[float, float]:
    lats = [s.seizure.lat for s in snaps]
    lons = [s.seizure.lon for s in snaps]
    return sum(lats) / len(lats), sum(lons) / len(lons)


def _cluster_radius(snaps: list[SnapResult], clat: float, clon: float) -> float:
    if len(snaps) < 2:
        return 0.0
    return max(_hav(s.seizure.lat, s.seizure.lon, clat, clon) for s in snaps)


# ── step 3 — trace to origin ────────────────────────────────────────────────

def _trace_origin(
    snaps: list[SnapResult],
    corridor: Corridor,
    gap_km: float = GAP_KM,
) -> Optional[Node]:
    """Walk the corridor from the seizure cluster outward in both directions.
    The direction with a clean gap past the last seizure = likely injection end.
    Returns the first major-hub node (or last node) beyond that gap.

    Logic:
    - Find the span of node_indices covered by seizures.
    - Beyond the last seizure index (toward both ends), walk until the first
      node whose cumulative step-distance > gap_km.
    - Prefer the end that first hits a major hub (terminus logic).
    """
    if not snaps:
        return None

    indices = sorted(s.node_index for s in snaps)
    lo, hi = indices[0], indices[-1]
    nodes = corridor.nodes

    def _walk_to_end(start: int, step: int) -> tuple[Optional[Node], float]:
        """Walk from 'start' in direction 'step', return (terminal_node, gap_km_walked)."""
        total_km = 0.0
        prev = nodes[start]
        i = start + step
        while 0 <= i < len(nodes):
            curr = nodes[i]
            total_km += _hav(prev.lat, prev.lon, curr.lat, curr.lon)
            if total_km >= gap_km:
                return curr, total_km
            if curr.is_major_hub:
                return curr, total_km
            prev = curr
            i += step
        # reached the end of the corridor
        return nodes[i - step], total_km

    origin_low, dist_low = _walk_to_end(lo, -1)  # walk toward corridor start
    origin_high, dist_high = _walk_to_end(hi, +1)  # walk toward corridor end

    # Pick the direction that went further (more gap = less contaminated by known seizures)
    if dist_low >= dist_high:
        return origin_low
    return origin_high


# ── step 4 — FIR corroboration ───────────────────────────────────────────────

def _corroborate(
    corridor: Corridor,
    fir_corpus: list[FirEntry],
    radius_km: float = FIR_MATCH_RADIUS_KM,
) -> list[FirEntry]:
    """Find FIR entries whose location is within radius_km of any corridor node."""
    hits = []
    for fir in fir_corpus:
        for node in corridor.nodes:
            if _hav(fir.lat, fir.lon, node.lat, node.lon) <= radius_km:
                hits.append(fir)
                break
    return hits


# ── step 5 — score ──────────────────────────────────────────────────────────

def _score(
    n_seizures: int,
    cluster_radius: float,
    fir_hits: int,
    origin_node: Optional[Node],
    fir_hits_near_origin: int,
) -> tuple[float, str]:
    """Weighted confidence score → (float 0-1, band label).

    Weights (sum to 1.0):
      - n_seizures:          0.35  (more independent seizures = stronger signal)
      - cluster_tightness:   0.25  (tighter cluster = more consistent evidence)
      - fir_corroboration:   0.25  (FIRs near corridor = intelligence backing)
      - origin_quality:      0.15  (FIR near inferred origin = strongest corroboration)

    Hard cap at 0.85: we never claim near-certainty — no note carries a GPS tag.
    """
    # Seizure score: 1 = 0.2, 2 = 0.45, 3 = 0.65, 4+ = 0.85+
    seizure_score = min(0.2 + (n_seizures - 1) * 0.2, 0.85)

    # Tightness: radius < 20km = tight (1.0), > 150km = loose (0.0)
    tightness = max(0.0, 1.0 - cluster_radius / 150.0) if cluster_radius > 0 else 1.0

    # FIR score: 0 = 0, 1 = 0.5, 2+ = 1.0
    fir_score = min(fir_hits * 0.5, 1.0)

    # Origin quality: FIR right at the origin is strong
    origin_score = 1.0 if fir_hits_near_origin > 0 else (0.3 if origin_node else 0.0)

    raw = (
        0.35 * seizure_score
        + 0.25 * tightness
        + 0.25 * fir_score
        + 0.15 * origin_score
    )
    score = min(raw, 0.85)  # hard cap

    if score >= 0.60:
        band = "high"
    elif score >= 0.35:
        band = "medium"
    else:
        band = "low"

    return round(score, 3), band


# ── temporal flow: direction + speed from time-ordered seizures ─────────────

def _parse_ts(ts: str) -> Optional[datetime]:
    if not ts:
        return None
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None


def _cumulative_km(corridor: Corridor) -> list[float]:
    """Distance from node 0 to each node, walking the node_path."""
    cum = [0.0]
    for a, b in zip(corridor.nodes, corridor.nodes[1:]):
        cum.append(cum[-1] + _hav(a.lat, a.lon, b.lat, b.lon))
    return cum

# Flow slower than this is indistinguishable from stationary seizures.
MIN_FLOW_KM_PER_DAY = 5.0


def _temporal_flow(
    snaps: list[SnapResult],
    corridor: Corridor,
    origin_node: Optional[Node],
) -> Optional[dict]:
    """Direction + speed of movement from time-ordered corridor positions.

    Geometry alone cannot prove direction — but if seizures appear
    progressively FURTHER along the corridor over days, the least-squares fit
    of position-vs-time gives direction, speed, and a consistency (R²) that
    makes the strength of the inference explicit. Needs >=2 time-stamped
    seizures at distinct positions; anything less returns None.
    """
    cum = _cumulative_km(corridor)
    obs: list[tuple[float, float]] = []  # (days since epoch, km along corridor)
    for s in snaps:
        t = _parse_ts(s.seizure.timestamp)
        if t is not None:
            obs.append((t.timestamp() / 86400.0, cum[s.node_index]))
    if len(obs) < 2:
        return None
    t0 = min(o[0] for o in obs)
    xs = [o[0] - t0 for o in obs]
    ys = [o[1] for o in obs]
    if max(xs) == min(xs) or max(ys) == min(ys):
        return None  # simultaneous, or no movement along the corridor

    n = len(obs)
    mx, my = sum(xs) / n, sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    slope = sxy / sxx  # km/day along the corridor (sign = direction)
    if abs(slope) < MIN_FLOW_KM_PER_DAY:
        return None
    syy = sum((y - my) ** 2 for y in ys)
    r2 = (sxy * sxy) / (sxx * syy) if syy > 0 else 0.0

    forward = slope > 0  # toward higher node index
    toward = corridor.nodes[-1] if forward else corridor.nodes[0]

    # Next major hub beyond the furthest seizure, in the flow direction.
    edge_idx = max(s.node_index for s in snaps) if forward else min(s.node_index for s in snaps)
    edge_pos = cum[edge_idx]
    ahead = (
        range(edge_idx + 1, len(corridor.nodes)) if forward
        else range(edge_idx - 1, -1, -1)
    )
    hub_idx = next((i for i in ahead if corridor.nodes[i].is_major_hub), None)
    if hub_idx is None:
        hub_idx = len(corridor.nodes) - 1 if forward else 0
        if hub_idx == edge_idx:
            hub_idx = None

    speed = abs(slope)
    next_hub = None
    if hub_idx is not None:
        hub = corridor.nodes[hub_idx]
        dist = abs(cum[hub_idx] - edge_pos)
        if dist > 1.0:
            eta = dist / speed
            next_hub = {
                "name": hub.name,
                "lat": hub.lat,
                "lon": hub.lon,
                "distance_km": round(dist, 1),
                # honest window, not a point estimate — speed fits are noisy
                "eta_days_min": round(eta * 0.7, 1),
                "eta_days_max": round(eta * 1.5, 1),
            }

    # Independent corroboration: does the flow point AWAY from the inferred
    # origin (i.e. the origin sits upstream of the movement)?
    origin_consistent: Optional[bool] = None
    if origin_node is not None:
        o_idx = next(
            (i for i, nd in enumerate(corridor.nodes) if nd.name == origin_node.name),
            None,
        )
        if o_idx is not None:
            origin_consistent = (cum[o_idx] <= edge_pos) if forward else (cum[o_idx] >= edge_pos)

    return {
        "direction_toward": toward.name,
        "speed_km_per_day": round(speed, 1),
        "consistency": round(max(0.0, min(1.0, r2)), 3),
        "basis": f"{n} time-stamped seizures fitted position-vs-time along the corridor",
        "next_hub_at_risk": next_hub,
        "origin_consistent": origin_consistent,
        "note": (
            "Forecast aid from seizure timing, not a claim — direction/speed hold "
            "only if the seizures belong to one consignment flow."
        ),
    }


# ── main API ────────────────────────────────────────────────────────────────

def compute_trail(
    seizures: list[dict],
    mode_filter: Optional[str] = None,
) -> Optional[dict]:
    """Compute the best supply trail for a list of seizure dicts.

    Each seizure dict should have: event_id, lat, lon, district, denomination (optional).
    Returns the highest-scoring trail as a contract-valid dict, or None if no
    corridor has at least MIN_SEIZURES_FOR_TRAIL seizures snapped to it.
    """
    if not seizures:
        return None

    # Parse inputs
    sz_objs = [
        Seizure(
            event_id=s.get("event_id", str(uuid.uuid4())),
            lat=float(s["lat"]),
            lon=float(s["lon"]),
            district=s.get("district", "unknown"),
            denomination=s.get("denomination", "unknown"),
            timestamp=s.get("timestamp", ""),
        )
        for s in seizures
        if s.get("lat") and s.get("lon")
    ]
    if not sz_objs:
        return None

    corridors = load_corridors()
    if mode_filter:
        corridors = [c for c in corridors if c.mode == mode_filter]

    fir_corpus = load_fir_corpus()
    snapped = snap_seizures(sz_objs, corridors)

    best_trail: Optional[dict] = None
    best_score = -1.0

    for corridor in corridors:
        corridor_snaps = snapped[corridor.id]
        if len(corridor_snaps) < MIN_SEIZURES_FOR_TRAIL:
            continue

        # Cluster centroid
        clat, clon = _centroid(corridor_snaps)
        radius = _cluster_radius(corridor_snaps, clat, clon)

        # Trace origin
        origin_node = _trace_origin(corridor_snaps, corridor)

        # FIR corroboration
        fir_hits = _corroborate(corridor, fir_corpus)
        fir_near_origin = []
        if origin_node:
            fir_near_origin = [
                f for f in fir_corpus
                if _hav(f.lat, f.lon, origin_node.lat, origin_node.lon) <= FIR_MATCH_RADIUS_KM
            ]

        # Score
        score, band = _score(
            n_seizures=len(corridor_snaps),
            cluster_radius=radius,
            fir_hits=len(fir_hits),
            origin_node=origin_node,
            fir_hits_near_origin=len(fir_near_origin),
        )

        if score <= best_score:
            continue
        best_score = score

        # Build evidence list
        evidence = []

        # Evidence 1: corridor snap
        districts = ", ".join({s.seizure.district for s in corridor_snaps})
        evidence.append({
            "type": "corridor_snap",
            "detail": (
                f"{len(corridor_snaps)} seizure(s) in {districts} "
                f"snap to '{corridor.name}' (within {SNAP_RADIUS_KM:.0f} km of corridor nodes)"
            ),
            "weight": 0.35,
        })

        # Evidence 2: cluster stats
        if len(corridor_snaps) >= 2:
            evidence.append({
                "type": "seizure_cluster",
                "detail": (
                    f"{len(corridor_snaps)} independent seizures cluster within "
                    f"{radius:.0f} km of each other along this corridor — "
                    f"consistent with a single distribution route"
                ),
                "weight": 0.25,
            })

        # Evidence 3: transport gap → origin
        if origin_node:
            evidence.append({
                "type": "corridor_terminus",
                "detail": (
                    f"Seizure cluster ends before '{origin_node.name}'; "
                    f"no seizures detected beyond this point → "
                    f"'{origin_node.name}' is the likely injection/origin zone"
                ),
                "weight": 0.15,
            })

        # Evidence 4: temporal flow — time-ordered seizures prove direction
        flow = _temporal_flow(corridor_snaps, corridor, origin_node)
        if flow and flow["consistency"] >= 0.5:
            arrow = f"moving toward {flow['direction_toward']} at ~{flow['speed_km_per_day']:.0f} km/day"
            nxt = flow.get("next_hub_at_risk")
            eta_txt = (
                f"; next hub at risk: {nxt['name']} in {nxt['eta_days_min']:.0f}–{nxt['eta_days_max']:.0f} days"
                if nxt else ""
            )
            evidence.append({
                "type": "temporal_flow",
                "detail": (
                    f"Seizure timestamps progress along the corridor — {arrow} "
                    f"(consistency R²={flow['consistency']:.2f}){eta_txt}"
                ),
                "weight": 0.15,
            })

        # Evidence 5: FIR corroboration
        for fir in fir_hits[:3]:  # cap at 3 to avoid flooding the evidence panel
            evidence.append({
                "type": "fir_mention",
                "ref": fir.ref,
                "detail": (
                    f"{fir.source} ({fir.date}): {fir.text[:200].rstrip()}…"
                    if len(fir.text) > 200 else fir.text
                ),
                "weight": 0.25 / max(len(fir_hits), 1),
            })

        # Build corridor output (node_path matches schema)
        corridor_out = {
            "id": corridor.id,
            "name": corridor.name,
            "mode": corridor.mode,
            "node_path": [
                {"name": n.name, "lat": n.lat, "lon": n.lon, "is_major_hub": n.is_major_hub}
                for n in corridor.nodes
            ],
        }

        # Build inferred origin
        if origin_node:
            origin_out = {
                "name": origin_node.name,
                "lat": origin_node.lat,
                "lon": origin_node.lon,
                "reasoning": (
                    f"Last corridor node beyond the seizure cluster gap (>{GAP_KM:.0f} km). "
                    f"{'FIR corroboration: ' + fir_near_origin[0].ref if fir_near_origin else 'No FIR corroboration near this node — inference only.'}"
                ),
            }
        else:
            # Fallback: use the corridor's terminal node
            terminal = corridor.nodes[-1]
            origin_out = {
                "name": terminal.name,
                "lat": terminal.lat,
                "lon": terminal.lon,
                "reasoning": "No clear gap in seizures — corridor terminus used as default. Confidence reduced.",
            }

        best_trail = {
            "schema_version": "1.0",
            "trail_id": f"trail_{uuid.uuid4().hex[:8]}",
            "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "commodity": "counterfeit_currency",
            "mode": corridor.mode,
            "seizures": [
                {
                    "event_id": s.seizure.event_id,
                    "lat": s.seizure.lat,
                    "lon": s.seizure.lon,
                    "district": s.seizure.district,
                    "denomination": s.seizure.denomination,
                    "timestamp": s.seizure.timestamp,
                }
                for s in corridor_snaps
            ],
            "corridor": corridor_out,
            "cluster_centroid": {
                "lat": round(clat, 5),
                "lon": round(clon, 5),
                "radius_km": round(radius, 1),
            },
            "inferred_origin": origin_out,
            "confidence": score,
            "confidence_band": band,
            "evidence": evidence,
            "flow": flow,
            "disclaimer": (
                "This trail is an investigative hypothesis — a weighted inference "
                "from seizure locations, transport geodata, and public intelligence. "
                "A banknote carries no origin label; this is not forensic proof. "
                "FIR corpus is a representative sample pending law-enforcement data integration."
            ),
        }

    return best_trail


def compute_trails_all_modes(seizures: list[dict]) -> list[dict]:
    """Compute a trail for each transport mode that has at least one seizure snapped to it.
    Returns a list sorted by confidence descending.
    """
    modes = ["rail", "road", "ship", "air"]
    trails = []
    for mode in modes:
        t = compute_trail(seizures, mode_filter=mode)
        if t:
            trails.append(t)
    trails.sort(key=lambda t: t["confidence"], reverse=True)
    return trails


# ── multi-modal provenance (city-wise routing) ──────────────────────────────

def _nearest_node_key(net, lat: float, lon: float):
    """Key of the closest physical node, and its distance (km)."""
    from .network import attach_access  # local import avoids a cycle

    best_key, best_d = None, float("inf")
    for key, pn in net.nodes.items():
        d = _hav(lat, lon, pn.lat, pn.lon)
        if d < best_d:
            best_key, best_d = key, d
    return best_key, best_d


def compute_provenance(seizures: list[dict], k: int = 4) -> Optional[dict]:
    """The full picture: the best corridor trail PLUS the k most plausible
    multi-modal routes (rail / road / ship / air) from the inferred origin to
    the seizure cluster, over the city-wise transport network.

    Returns the trail dict augmented with `routes` and `route_summary`, or None
    if no trail could be formed.
    """
    from .network import ACCESS_KM, attach_access, build_network
    from .routes import plausible_routes

    trail = compute_trail(seizures)
    if trail is None:
        return None

    net = build_network()
    fir_corpus = load_fir_corpus()

    origin = trail["inferred_origin"]
    centroid = trail.get("cluster_centroid") or {
        "lat": trail["seizures"][0]["lat"], "lon": trail["seizures"][0]["lon"]}

    # Origin is a corridor node → snap to it; the seizure cluster is a point →
    # attach it as a temporary city with road access into the network.
    origin_key, od = _nearest_node_key(net, origin["lat"], origin["lon"])
    if od > 8.0:  # origin not co-located with a node — attach it too
        origin_key = attach_access(net, origin["name"], origin["lat"], origin["lon"])
    dst_key = attach_access(net, "Seizure cluster", centroid["lat"], centroid["lon"])

    routes = plausible_routes(net, origin_key, dst_key, k=k, fir_corpus=fir_corpus)

    trail["routes"] = routes
    trail["route_summary"] = _summarise_routes(origin["name"], routes)
    return trail


def _summarise_routes(origin_name: str, routes: list[dict]) -> str:
    """Deterministic one-paragraph summary of the route options (the offline
    narrator — the GenAI version slots in behind the same string)."""
    if not routes:
        return f"No multi-modal route could be traced from {origin_name}."
    primary = routes[0]
    mode_phrase = " → ".join(primary["modes"])
    line = (f"Most plausible channel from {origin_name}: a {mode_phrase} route "
            f"(~{primary['total_km']:.0f} km, plausibility {primary['plausibility']:.0%})")
    if primary["passes_fir"]:
        line += f", corroborated by {len(primary['passes_fir'])} FIR(s) along the way"
    if len(routes) > 1:
        alts = "; ".join(" → ".join(r["modes"]) for r in routes[1:3])
        line += f". Alternatives considered: {alts}"
    return line + "."
