"""Weighted k-shortest plausible routes over the multi-modal network.

Given an origin city and a destination (the seizure cluster), find the k most
plausible multi-modal paths — ranked by weighted cost (distance × mode risk),
deduplicated by mode-sequence so the alternatives are genuinely different
(all-rail vs. rail+ship vs. air), and annotated with which FIR-corroborated
cities each route passes through.

Pure Python (Dijkstra + Yen's algorithm) — the graph is small (tens of nodes),
and determinism is the whole point: every route is reproducible and auditable.
"""

from __future__ import annotations

import heapq
from dataclasses import dataclass

from .engine import FirEntry, _hav
from .network import MODE_RISK, Edge, Network


@dataclass
class Leg:
    mode: str
    from_name: str
    from_lat: float
    from_lon: float
    to_name: str
    to_lat: float
    to_lon: float
    dist_km: float
    is_transfer: bool
    is_access: bool


# Penalty applied to a *haul* leg whose mode isn't the one we're preferring —
# lets us ask "what's the best route that travels mainly by ship / air / rail".
_OTHER_MODE_PENALTY = 4.0


def _edge_cost(e: Edge, prefer: str | None = None) -> float:
    base = e.dist_km * MODE_RISK.get(e.mode, 1.5)
    if prefer and e.mode != prefer and not (e.is_access or e.is_transfer):
        base *= _OTHER_MODE_PENALTY
    return base


def _dijkstra(net: Network, src: str, dst: str,
              banned_edges: set[tuple[str, str]] | None = None,
              banned_nodes: set[str] | None = None,
              prefer: str | None = None) -> list[str] | None:
    """Least-cost path src→dst as node keys, or None. `prefer` biases toward a
    haul mode so we can surface a genuinely rail/ship/air-primary alternative."""
    banned_edges = banned_edges or set()
    banned_nodes = banned_nodes or set()
    dist: dict[str, float] = {src: 0.0}
    prev: dict[str, str] = {}
    pq: list[tuple[float, str]] = [(0.0, src)]
    seen: set[str] = set()
    while pq:
        d, u = heapq.heappop(pq)
        if u in seen:
            continue
        seen.add(u)
        if u == dst:
            break
        for e in net.neighbours(u):
            if e.to in banned_nodes or (u, e.to) in banned_edges:
                continue
            nd = d + _edge_cost(e, prefer)
            if nd < dist.get(e.to, float("inf")):
                dist[e.to] = nd
                prev[e.to] = u
                heapq.heappush(pq, (nd, e.to))
    if dst not in dist:
        return None
    path = [dst]
    while path[-1] != src:
        path.append(prev[path[-1]])
    return path[::-1]


def _path_cost(net: Network, path: list[str]) -> float:
    total = 0.0
    for a, b in zip(path, path[1:]):
        e = _best_edge(net, a, b)
        total += _edge_cost(e) if e else 0.0
    return total


def _best_edge(net: Network, a: str, b: str) -> Edge | None:
    """Cheapest edge a→b (parallel edges of different modes may exist)."""
    best = None
    for e in net.neighbours(a):
        if e.to == b and (best is None or _edge_cost(e) < _edge_cost(best)):
            best = e
    return best


def _yen(net: Network, src: str, dst: str, k: int) -> list[list[str]]:
    """Yen's k-shortest loopless paths by weighted cost."""
    first = _dijkstra(net, src, dst)
    if not first:
        return []
    a_paths: list[list[str]] = [first]
    candidates: list[tuple[float, list[str]]] = []
    while len(a_paths) < k:
        prev_path = a_paths[-1]
        for i in range(len(prev_path) - 1):
            spur_node = prev_path[i]
            root = prev_path[: i + 1]
            banned_edges: set[tuple[str, str]] = set()
            for p in a_paths:
                if p[: i + 1] == root and i + 1 < len(p):
                    banned_edges.add((p[i], p[i + 1]))
                    banned_edges.add((p[i + 1], p[i]))
            banned_nodes = set(root[:-1])
            spur = _dijkstra(net, spur_node, dst, banned_edges, banned_nodes)
            if spur:
                total = root[:-1] + spur
                cost = _path_cost(net, total)
                if total not in a_paths and all(total != c[1] for c in candidates):
                    heapq.heappush(candidates, (cost, total))
        if not candidates:
            break
        a_paths.append(heapq.heappop(candidates)[1])
    return a_paths


def _legs(net: Network, path: list[str]) -> list[Leg]:
    legs = []
    for a, b in zip(path, path[1:]):
        e = _best_edge(net, a, b)
        na, nb = net.nodes[a], net.nodes[b]
        legs.append(Leg(
            mode=e.mode if e else "road",
            from_name=na.name, from_lat=na.lat, from_lon=na.lon,
            to_name=nb.name, to_lat=nb.lat, to_lon=nb.lon,
            dist_km=round(e.dist_km if e else _hav(na.lat, na.lon, nb.lat, nb.lon), 1),
            is_transfer=bool(e and e.is_transfer),
            is_access=bool(e and e.is_access),
        ))
    return legs


def _collapse_modes(legs: list[Leg]) -> list[str]:
    """Ordered distinct modes, ignoring short access/transfer road hops so the
    'signature' reflects the real long-haul channel (rail / ship / air)."""
    out: list[str] = []
    for leg in legs:
        if leg.is_access or leg.is_transfer:
            continue
        if not out or out[-1] != leg.mode:
            out.append(leg.mode)
    return out or ["road"]


def _build_route(net: Network, path: list[str], fir_corpus, fir_radius_km) -> dict:
    legs = _legs(net, path)
    sig = tuple(_collapse_modes(legs))
    passes = []
    if fir_corpus:
        for fir in fir_corpus:
            if any(_hav(fir.lat, fir.lon, lg.to_lat, lg.to_lon) <= fir_radius_km
                   or _hav(fir.lat, fir.lon, lg.from_lat, lg.from_lon) <= fir_radius_km
                   for lg in legs):
                passes.append(fir.ref)
    return {
        "modes": list(sig),
        "total_km": round(sum(lg.dist_km for lg in legs), 1),
        "_cost": _path_cost(net, path),
        "passes_fir": sorted(set(passes)),
        "legs": [
            {"mode": lg.mode, "from": lg.from_name, "to": lg.to_name,
             "from_lat": lg.from_lat, "from_lon": lg.from_lon,
             "to_lat": lg.to_lat, "to_lon": lg.to_lon,
             "distance_km": lg.dist_km,
             "kind": "transfer" if lg.is_transfer else "access" if lg.is_access else "haul"}
            for lg in legs
        ],
    }


def plausible_routes(net: Network, src_key: str, dst_key: str, k: int = 4,
                     fir_corpus: list[FirEntry] | None = None,
                     fir_radius_km: float = 80.0) -> list[dict]:
    """Plausible multi-modal routes src→dst. Returns the overall cheapest route
    plus the best route that travels *primarily* by each haul mode (rail / ship
    / air / road) where one exists — so the alternatives are genuinely
    different channels, not variations of the same one. Ranked by plausibility
    (true weighted cost), deduplicated by mode-signature."""
    best_by_sig: dict[tuple[str, ...], dict] = {}

    def _consider(path: list[str] | None) -> None:
        if not path:
            return
        route = _build_route(net, path, fir_corpus, fir_radius_km)
        sig = tuple(route["modes"])
        if sig not in best_by_sig or route["_cost"] < best_by_sig[sig]["_cost"]:
            best_by_sig[sig] = route

    # 1) global optimum (+ a couple of k-shortest variants for mixed routes)
    for p in _yen(net, src_key, dst_key, 3):
        _consider(p)
    # 2) best route biased toward each haul mode → surfaces rail/ship/air options
    for mode in ("rail", "ship", "air", "road"):
        _consider(_dijkstra(net, src_key, dst_key, prefer=mode))

    routes = list(best_by_sig.values())
    if routes:
        best_cost = min(r["_cost"] for r in routes)
        for r in routes:
            base = best_cost / r["_cost"] if r["_cost"] else 1.0
            fir_boost = min(0.15, 0.05 * len(r["passes_fir"]))
            r["plausibility"] = round(min(1.0, base + fir_boost), 3)
            del r["_cost"]
    routes.sort(key=lambda r: r["plausibility"], reverse=True)
    return routes[:k]
