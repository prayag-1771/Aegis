"""Ring clustering: from per-account risk scores to named fraud rings.

Method:
1. Keep accounts with illicit_probability >= threshold (the "high-risk" set).
2. Induce the transaction subgraph over that set.
3. Louvain community detection splits it into money-movement communities;
   weakly-connected components catch anything Louvain leaves as singleton noise.
4. Each community of size >= min_ring_size becomes a ring, scored by the mean
   member probability, with a topology heuristic label (chain / fan-in / cycle)
   an investigator can read at a glance.
"""

from __future__ import annotations

from dataclasses import dataclass

import networkx as nx
import pandas as pd

from .config import RingConfig
from .data import Dataset


@dataclass
class Ring:
    ring_id: str
    account_ids: list[str]
    risk_score: float
    size: int
    total_amount: float
    label: str
    district: str | None


def _topology_label(sub: nx.DiGraph) -> str:
    """Human-readable structure tag for the ring."""
    n = sub.number_of_nodes()
    if n < 2:
        return "isolated"
    in_degs = [d for _, d in sub.in_degree()]
    out_degs = [d for _, d in sub.out_degree()]
    max_in = max(in_degs)
    try:
        has_cycle = len(nx.find_cycle(sub)) >= 3
    except nx.NetworkXNoCycle:
        has_cycle = False
    if has_cycle:
        return "round-tripping cycle"
    if max_in >= max(3, n - 2) or max(out_degs) >= max(3, n - 2):
        return "mule collection hub"
    # Mostly linear flow: many degree<=2 nodes in a path-like arrangement.
    linear = sum(1 for i, o in zip(in_degs, out_degs) if i <= 1 and o <= 1)
    if linear >= n - 1:
        return "layering chain"
    return "mixed laundering network"


def detect_rings(
    ds: Dataset,
    scores: pd.Series,
    cfg: RingConfig | None = None,
) -> tuple[list[Ring], pd.DataFrame]:
    """Return detected rings + per-account frame (with ring assignment)."""
    cfg = cfg or RingConfig()

    high_risk = scores[scores >= cfg.risk_threshold].index
    tx = ds.transactions
    sub_tx = tx[tx["source"].isin(high_risk) & tx["target"].isin(high_risk)]

    g = nx.DiGraph()
    g.add_nodes_from(high_risk)
    for row in sub_tx.itertuples(index=False):
        w = g.get_edge_data(row.source, row.target, {}).get("weight", 0.0)
        g.add_edge(row.source, row.target, weight=w + float(row.amount))

    # Louvain on the undirected weighted view; fall back to components.
    und = g.to_undirected()
    und.remove_edges_from(nx.selfloop_edges(und))
    communities: list[set] = []
    if und.number_of_edges() > 0:
        communities = list(nx.community.louvain_communities(und, weight="weight", seed=42))
    else:
        communities = [set(c) for c in nx.connected_components(und)]

    districts = (
        ds.accounts.set_index("account_id")["district"]
        if "district" in ds.accounts
        else pd.Series(dtype=object)
    )

    rings: list[Ring] = []
    assignment: dict[str, str] = {}
    idx = 0
    for members in sorted(communities, key=len, reverse=True):
        if len(members) < cfg.min_ring_size:
            continue
        idx += 1
        rid = f"ring_{idx:02d}"
        member_list = sorted(members)
        ring_sub = g.subgraph(members).copy()
        total = float(sum(d["weight"] for _, _, d in ring_sub.edges(data=True)))
        dominant_district = None
        if not districts.empty:
            counts = districts.reindex(member_list).dropna().value_counts()
            if len(counts):
                dominant_district = str(counts.index[0])
        rings.append(
            Ring(
                ring_id=rid,
                account_ids=member_list,
                risk_score=float(scores.reindex(member_list).mean()),
                size=len(member_list),
                total_amount=round(total, 2),
                label=_topology_label(ring_sub),
                district=dominant_district,
            )
        )
        assignment.update({aid: rid for aid in member_list})

    accounts_out = pd.DataFrame(
        {
            "account_id": scores.index,
            "illicit_probability": scores.values,
        }
    )
    accounts_out["ring_id"] = accounts_out["account_id"].map(assignment)
    return rings, accounts_out
