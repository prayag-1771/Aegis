"""Contract-compliant export: pipeline results -> fraud_graph JSON.

The pydantic models below mirror ../../contracts/fraud_graph.schema.json
field-for-field. If the contract changes, change these models AND the schema
together (see contracts/README.md rules). `model_dump(exclude_none=...)` is NOT
used — the contract allows explicit nulls, and being explicit beats implicit.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd
from pydantic import BaseModel, Field

from .config import SCHEMA_VERSION, RingConfig
from .data import Dataset
from .rings import Ring


class AccountFeatures(BaseModel):
    degree_centrality: float
    clustering_coefficient: float
    in_degree: int
    out_degree: int
    # Behavioural evidence for the dashboard's "why flagged" view. Optional in
    # the contract (the features object allows extra keys), so older consumers
    # are unaffected.
    throughput_ratio: float | None = None
    burst_ratio: float | None = None
    round_amount_ratio: float | None = None
    tx_count: int | None = None


class AccountOut(BaseModel):
    account_id: str
    illicit_probability: float = Field(ge=0, le=1)
    ring_id: str | None = None
    features: AccountFeatures | None = None


class RingOut(BaseModel):
    ring_id: str
    account_ids: list[str]
    risk_score: float = Field(ge=0, le=1)
    size: int
    total_amount: float | None = None
    label: str | None = None
    district: str | None = None


class EdgeOut(BaseModel):
    source: str
    target: str
    amount: float | None = None
    timestamp: str | None = None


class FraudGraphOut(BaseModel):
    schema_version: str = SCHEMA_VERSION
    generated_at: str
    model: str
    rings: list[RingOut]
    accounts: list[AccountOut]
    edges: list[EdgeOut]


def build_output(
    ds: Dataset,
    rings: list[Ring],
    accounts: pd.DataFrame,
    features: pd.DataFrame,
    model_name: str = "graph_features+xgboost",
    cfg: RingConfig | None = None,
) -> FraudGraphOut:
    cfg = cfg or RingConfig()

    ring_out = [
        RingOut(
            ring_id=r.ring_id,
            account_ids=r.account_ids,
            risk_score=round(min(max(r.risk_score, 0.0), 1.0), 4),
            size=r.size,
            total_amount=r.total_amount,
            label=r.label,
            district=r.district,
        )
        for r in rings
    ]

    # Export features only for ringed accounts — the command centre colors
    # those nodes; shipping features for 2k+ clean accounts is wasted bytes.
    ringed = accounts.dropna(subset=["ring_id"])
    feats = features.reindex(ringed["account_id"])

    acc_out: list[AccountOut] = []
    for row in ringed.itertuples(index=False):
        f = feats.loc[row.account_id]
        acc_out.append(
            AccountOut(
                account_id=row.account_id,
                illicit_probability=round(float(row.illicit_probability), 4),
                ring_id=row.ring_id,
                features=AccountFeatures(
                    degree_centrality=round(float(f["degree_centrality"]), 6),
                    clustering_coefficient=round(float(f["clustering_coeff"]), 6),
                    in_degree=int(f["in_degree"]),
                    out_degree=int(f["out_degree"]),
                    throughput_ratio=round(float(f["throughput_ratio"]), 4),
                    burst_ratio=round(float(f["burst_ratio"]), 4),
                    round_amount_ratio=round(float(f["round_amount_ratio"]), 4),
                    tx_count=int(f["tx_count"]),
                ),
            )
        )

    # Edges between ringed accounts, largest flows first, capped for rendering.
    ringed_ids = set(ringed["account_id"])
    tx = ds.transactions
    ring_tx = tx[tx["source"].isin(ringed_ids) & tx["target"].isin(ringed_ids)]
    ring_tx = ring_tx.sort_values("amount", ascending=False).head(cfg.max_export_edges)
    # Inflows: payments from OUTSIDE the rings landing in a ring account —
    # victim -> collector transfers. Fusion traces a scam's reported_payment
    # against these (amount + time window + district), turning "same district"
    # into "this exact payment landed in this exact account".
    inflow_tx = tx[~tx["source"].isin(ringed_ids) & tx["target"].isin(ringed_ids)]
    inflow_tx = inflow_tx.sort_values("amount", ascending=False).head(cfg.max_inflow_edges)
    edges = [
        EdgeOut(
            source=row.source,
            target=row.target,
            amount=round(float(row.amount), 2),
            timestamp=str(row.timestamp) if pd.notna(row.timestamp) else None,
        )
        for chunk in (ring_tx, inflow_tx)
        for row in chunk.itertuples(index=False)
    ]

    return FraudGraphOut(
        generated_at=datetime.now(timezone.utc).isoformat(),
        model=model_name,
        rings=ring_out,
        accounts=acc_out,
        edges=edges,
    )
