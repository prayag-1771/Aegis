"""Multi-modal transport network — the city-wise routing graph.

The corridor engine (engine.py) answers "which single corridor and where does
it end". This module answers the richer question: given a seizure city, what
are the *plausible multi-modal routes* the notes could have travelled — rail,
then a sea leg, then a road last-mile — and how do the alternatives rank.

Design (deterministic on purpose — the routing must be auditable):
- **Nodes** are cities / junctions / ports / airports from corridors.json.
  Nodes at (nearly) the same place across modes are merged into one physical
  city, so a city that has both a station and a port becomes a transfer point.
- **Edges**:
    * intra-corridor  — consecutive corridor nodes, carrying that corridor's mode
    * transfer        — two nearby physical cities of *different* modes (a short
                        road hop between, say, a station and a port)
    * last-mile access — a seizure city to every node within reach, by road
- **Weight** = distance_km × MODE_RISK[mode]. MODE_RISK encodes how *plausible*
  each mode is for moving counterfeit cash (lower = more plausible): rail and
  coastal shipping are cheap and common; road is short-haul; air is fast but
  heavily screened, so expensive per note.

Routing (routes.py) runs weighted k-shortest paths over this graph.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from .engine import Corridor, _hav, load_corridors

# How plausible each mode is for counterfeit transit (lower = more plausible).
MODE_RISK: dict[str, float] = {
    "rail": 1.0,    # cheap, high-volume, the documented primary channel
    "ship": 0.9,    # bulk consignments, low per-note cost, slow (DRI intel)
    "road": 1.3,    # short-haul feeder / courier; more checkpoints
    "air": 2.6,     # fast but heavy BCAS screening — rare, high-risk
}

MERGE_KM = 8.0        # nodes closer than this are the same physical city
TRANSFER_KM = 55.0    # a road hop connecting different-mode cities (station↔port)
ACCESS_KM = 70.0      # last-mile reach from a seizure city into the network


@dataclass
class PhysNode:
    """A physical city / hub, possibly served by several modes."""

    key: str
    name: str
    lat: float
    lon: float
    modes: set[str] = field(default_factory=set)
    is_major_hub: bool = False


@dataclass
class Edge:
    to: str          # destination node key
    mode: str
    dist_km: float
    is_transfer: bool = False
    is_access: bool = False


@dataclass
class Network:
    nodes: dict[str, PhysNode]
    adj: dict[str, list[Edge]]

    def neighbours(self, key: str) -> list[Edge]:
        return self.adj.get(key, [])


def _merge_key(name: str) -> str:
    """Normalise a node name to a stable key (strip station suffixes/punct)."""
    base = name.lower()
    for junk in (" jn", " junction", " central", " cantt", " port", " (ccu)",
                 " (pat)", " (del)", " steel city"):
        base = base.replace(junk, "")
    return "".join(ch for ch in base if ch.isalnum())


def build_network(corridors: list[Corridor] | None = None) -> Network:
    """Assemble the multi-modal graph from the corridor definitions."""
    corridors = corridors or load_corridors()
    nodes: dict[str, PhysNode] = {}

    def _resolve(name: str, lat: float, lon: float, mode: str, hub: bool) -> str:
        # Merge onto an existing physical node if one is very close.
        for key, pn in nodes.items():
            if _hav(lat, lon, pn.lat, pn.lon) <= MERGE_KM:
                pn.modes.add(mode)
                pn.is_major_hub = pn.is_major_hub or hub
                return key
        key = _merge_key(name) or f"n{len(nodes)}"
        while key in nodes and _hav(lat, lon, nodes[key].lat, nodes[key].lon) > MERGE_KM:
            key += "_"
        nodes[key] = PhysNode(key=key, name=name, lat=lat, lon=lon,
                              modes={mode}, is_major_hub=hub)
        return key

    adj: dict[str, list[Edge]] = {}

    def _add(a: str, b: str, mode: str, dist: float, transfer=False, access=False) -> None:
        adj.setdefault(a, []).append(Edge(b, mode, dist, transfer, access))
        adj.setdefault(b, []).append(Edge(a, mode, dist, transfer, access))

    # 1) intra-corridor edges
    for corridor in corridors:
        keys = [_resolve(n.name, n.lat, n.lon, corridor.mode, n.is_major_hub)
                for n in corridor.nodes]
        for i in range(len(keys) - 1):
            a, b = keys[i], keys[i + 1]
            if a == b:
                continue
            _add(a, b, corridor.mode,
                 _hav(nodes[a].lat, nodes[a].lon, nodes[b].lat, nodes[b].lon))

    # 2) transfer edges — different-mode cities within a short road hop
    keys = list(nodes)
    for i in range(len(keys)):
        for j in range(i + 1, len(keys)):
            a, b = nodes[keys[i]], nodes[keys[j]]
            if a.modes == b.modes:
                continue  # same single mode — an intra-corridor edge already covers it
            d = _hav(a.lat, a.lon, b.lat, b.lon)
            if 0 < d <= TRANSFER_KM:
                _add(a.key, b.key, "road", d, transfer=True)

    return Network(nodes=nodes, adj=adj)


def attach_access(net: Network, name: str, lat: float, lon: float,
                  reach_km: float = ACCESS_KM) -> str:
    """Add a temporary seizure/origin city to the graph, linked by road to every
    node within reach. Returns the new node's key. Mutates `net` in place —
    call on a fresh copy per query, or remove afterwards."""
    key = f"pt_{_merge_key(name)}_{abs(hash((round(lat,3),round(lon,3))))%9999}"
    net.nodes[key] = PhysNode(key=key, name=name, lat=lat, lon=lon,
                              modes={"road"}, is_major_hub=False)
    net.adj.setdefault(key, [])
    linked = 0
    for other_key, pn in list(net.nodes.items()):
        if other_key == key:
            continue
        d = _hav(lat, lon, pn.lat, pn.lon)
        if d <= reach_km:
            net.adj[key].append(Edge(other_key, "road", d, is_access=True))
            net.adj.setdefault(other_key, []).append(Edge(key, "road", d, is_access=True))
            linked += 1
    if linked == 0:
        # Nearest node fallback so an isolated city still joins the graph.
        nearest = min((k for k in net.nodes if k != key),
                      key=lambda k: _hav(lat, lon, net.nodes[k].lat, net.nodes[k].lon))
        d = _hav(lat, lon, net.nodes[nearest].lat, net.nodes[nearest].lon)
        net.adj[key].append(Edge(nearest, "road", d, is_access=True))
        net.adj[nearest].append(Edge(key, "road", d, is_access=True))
    return key
