"""Transaction graph construction + per-account feature engineering.

The model never sees raw transactions — it sees *graph-shaped behaviour*:
how money moves around an account, how fast, how round the amounts are, and
how central the account sits in the flow network. These features are what let
a plain XGBoost model "follow the money" like an investigator.
"""

from __future__ import annotations

import networkx as nx
import numpy as np
import pandas as pd

from .data import Dataset

FEATURE_COLUMNS = [
    "in_degree",
    "out_degree",
    "unique_senders",
    "unique_receivers",
    "total_in",
    "total_out",
    "net_flow",
    "throughput_ratio",
    "avg_amount",
    "max_amount",
    "round_amount_ratio",
    "tx_count",
    "burst_ratio",
    "median_hold_minutes",
    "degree_centrality",
    "pagerank",
    "clustering_coeff",
    "core_number",
    # Fan-in/out shape as a MODEL feature, not just a post-hoc ring label.
    # A collector mule has many senders, one/few receivers -> fan_in_ratio -> 1.
    # A distributor has one/few senders, many receivers -> fan_out_ratio -> 1.
    # Previously this shape was only detected afterward in rings.py for labels;
    # now it feeds training so the classifier can learn the collector signature.
    "fan_in_ratio",
    "fan_out_ratio",
    "mule_score",
]


def build_graph(ds: Dataset) -> nx.MultiDiGraph:
    """Directed multigraph: nodes = accounts, edges = individual transactions."""
    g = nx.MultiDiGraph()
    g.add_nodes_from(ds.accounts["account_id"])
    for row in ds.transactions.itertuples(index=False):
        g.add_edge(row.source, row.target, amount=row.amount, timestamp=row.timestamp)
    return g


def compute_features(ds: Dataset, g: nx.MultiDiGraph | None = None) -> pd.DataFrame:
    """One row of behavioural features per account."""
    g = g or build_graph(ds)
    tx = ds.transactions.copy()
    # format="ISO8601": pandas 2 otherwise infers the format from the first row
    # and silently coerces every differently-formatted timestamp to NaT — which
    # zeroed all tempo features for demo-injected transactions (no microseconds)
    # mixed into the cached city (microseconds).
    tx["timestamp"] = pd.to_datetime(tx["timestamp"], errors="coerce", utc=True, format="ISO8601")

    # ---- flow aggregates (vectorised in pandas, cheap even at 100k tx) ----
    in_agg = tx.groupby("target").agg(
        total_in=("amount", "sum"),
        in_deg=("amount", "size"),
        unique_senders=("source", "nunique"),
    )
    out_agg = tx.groupby("source").agg(
        total_out=("amount", "sum"),
        out_deg=("amount", "size"),
        unique_receivers=("target", "nunique"),
    )

    # Round-amount ratio: fraud loves 10k/25k/50k-style figures.
    tx["is_round"] = ((tx["amount"] % 1000 < 1) | (tx["amount"] % 1000 > 999)).astype(int)
    round_in = tx.groupby("target")["is_round"].mean().rename("round_in")
    round_out = tx.groupby("source")["is_round"].mean().rename("round_out")

    # Max single amounts, precomputed once (a per-account scan would be O(n*m)).
    max_in = tx.groupby("target")["amount"].max()
    max_out = tx.groupby("source")["amount"].max()

    # Burstiness: share of an account's transactions that happen within 60min
    # of its previous one. Mule chains move money in minutes, people don't.
    events = pd.concat(
        [
            tx[["source", "timestamp"]].rename(columns={"source": "account_id"}),
            tx[["target", "timestamp"]].rename(columns={"target": "account_id"}),
        ]
    ).dropna(subset=["timestamp"]).sort_values(["account_id", "timestamp"])
    events["gap_min"] = (
        events.groupby("account_id")["timestamp"].diff().dt.total_seconds() / 60.0
    )
    burst = events.groupby("account_id")["gap_min"].apply(
        lambda s: float((s < 60).mean()) if s.notna().any() else 0.0
    ).rename("burst_ratio")

    # Median hold time: minutes between receiving money and next sending it.
    # Approximation via median gap between consecutive in->out events.
    med_gap = events.groupby("account_id")["gap_min"].median().rename("median_hold_minutes")

    # ---- pure graph-structure features ----
    simple = nx.DiGraph(g)  # collapse parallel edges for structure metrics
    und = simple.to_undirected()
    # Self-payments exist in real data but break k-core/clustering; drop them
    # from the *structure* view only (flow aggregates above still count them).
    und.remove_edges_from(nx.selfloop_edges(und))
    degree_centrality = nx.degree_centrality(simple)
    pagerank = nx.pagerank(simple, alpha=0.85)
    clustering = nx.clustering(und)
    core = nx.core_number(und)

    rows = []
    for aid in ds.accounts["account_id"]:
        ti = in_agg["total_in"].get(aid, 0.0)
        to = out_agg["total_out"].get(aid, 0.0)
        ind = int(in_agg["in_deg"].get(aid, 0))
        outd = int(out_agg["out_deg"].get(aid, 0))
        n_tx = ind + outd
        r_in = round_in.get(aid, 0.0)
        r_out = round_out.get(aid, 0.0)
        us = int(in_agg["unique_senders"].get(aid, 0))
        ur = int(out_agg["unique_receivers"].get(aid, 0))
        throughput = min(ti, to) / max(ti, to, 1e-9)
        # Fan shape from distinct counterparties: a collector pulls from many
        # senders and pushes to few (fan_in -> 1); a distributor is the mirror.
        fan_in_ratio = us / max(us + ur, 1)
        fan_out_ratio = ur / max(us + ur, 1)
        # Mule-likeness: a standalone 0-1 score (independent of ring membership)
        # combining the three textbook mule signatures — money passes straight
        # through (throughput~1), it arrives in a burst, and it's collected from
        # many senders. Cheap, explainable, and an extra signal for the model.
        mule_score = float(
            0.5 * throughput
            + 0.3 * float(burst.get(aid, 0.0))
            + 0.2 * fan_in_ratio
        )
        rows.append(
            {
                "account_id": aid,
                "in_degree": ind,
                "out_degree": outd,
                "unique_senders": us,
                "unique_receivers": ur,
                "total_in": ti,
                "total_out": to,
                "net_flow": ti - to,
                # Throughput ~1.0 == "money in ≈ money out" == classic mule.
                "throughput_ratio": throughput,
                "avg_amount": (ti + to) / max(n_tx, 1),
                "max_amount": max(max_in.get(aid, 0.0), max_out.get(aid, 0.0)),
                "round_amount_ratio": float(np.nanmean([r_in, r_out])) if n_tx else 0.0,
                "tx_count": n_tx,
                "burst_ratio": float(burst.get(aid, 0.0)),
                "median_hold_minutes": float(med_gap.get(aid, 0.0) or 0.0),
                "degree_centrality": degree_centrality.get(aid, 0.0),
                "pagerank": pagerank.get(aid, 0.0),
                "clustering_coeff": clustering.get(aid, 0.0),
                "core_number": core.get(aid, 0),
                "fan_in_ratio": fan_in_ratio,
                "fan_out_ratio": fan_out_ratio,
                "mule_score": mule_score,
            }
        )

    feats = pd.DataFrame(rows).set_index("account_id")
    return feats[FEATURE_COLUMNS]
