"""Synthetic transaction-network generator with injected fraud rings.

Why synthetic data (and why it's not a cop-out):
- Real fraud datasets (Elliptic++, IEEE-CIS) are anonymised — no districts, no
  interpretable account ids — which makes a live demo unreadable.
- Here we inject rings with *known ground truth* and realistic laundering
  topologies, so we can (a) train/evaluate honestly against labels and
  (b) demo rings that light up in named districts on the crime map.
- The loader interface in `data.py` treats this as just another source, so the
  real Elliptic++ dataset can be swapped in without touching the pipeline.

Injected fraud topologies (mirrors real laundering patterns):
1. **Mule chain (layering)** — A -> B -> C -> D rapid transfers of slightly
   decaying amounts (each mule takes a cut).
2. **Fan-in (smurfing/collection)** — many victim accounts send small amounts
   into a collector, which forwards the pool onward.
3. **Cycle (round-tripping)** — money loops back to its origin through 3+ hops
   to fake legitimate turnover.
"""

from __future__ import annotations

import random
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

import networkx as nx
import pandas as pd

from .config import SynthConfig

EPOCH = datetime(2026, 6, 1, tzinfo=timezone.utc)


@dataclass
class SynthResult:
    accounts: pd.DataFrame  # account_id, district, is_illicit, ring_id
    transactions: pd.DataFrame  # tx_id, source, target, amount, timestamp
    ring_truth: dict[str, list[str]] = field(default_factory=dict)  # ring_id -> members


def _acc(i: int) -> str:
    return f"acc_{i:05d}"


def generate(cfg: SynthConfig | None = None) -> SynthResult:
    cfg = cfg or SynthConfig()
    rng = random.Random(cfg.seed)

    hotspots = cfg.districts[: cfg.n_hotspots]
    cold = cfg.districts[cfg.n_hotspots :]

    accounts: list[dict] = []
    txs: list[dict] = []
    ring_truth: dict[str, list[str]] = {}
    next_id = 0
    next_tx = 0

    def new_account(district: str, illicit: bool, ring_id: str | None) -> str:
        nonlocal next_id
        aid = _acc(next_id)
        next_id += 1
        accounts.append(
            {"account_id": aid, "district": district, "is_illicit": illicit, "ring_id": ring_id}
        )
        return aid

    def add_tx(src: str, dst: str, amount: float, ts: datetime) -> None:
        nonlocal next_tx
        txs.append(
            {
                "tx_id": f"tx_{next_tx:06d}",
                "source": src,
                "target": dst,
                "amount": round(amount, 2),
                "timestamp": ts.isoformat(),
            }
        )
        next_tx += 1

    # ---------------------------------------------------------------- legit background
    legit_ids = [new_account(rng.choice(cfg.districts), False, None) for _ in range(cfg.n_legit_accounts)]

    # Background traffic on a scale-free skeleton (few popular merchants, many
    # ordinary users) — Barabási–Albert mirrors how payment networks look.
    ba = nx.barabasi_albert_graph(cfg.n_legit_accounts, 2, seed=cfg.seed)
    ba_edges = list(ba.edges())
    for _ in range(cfg.n_background_tx):
        u, v = rng.choice(ba_edges)
        if rng.random() < 0.5:
            u, v = v, u
        # Organic amounts: skewed small, rarely round numbers.
        amount = rng.lognormvariate(7.2, 1.1)  # median ~1300
        ts = EPOCH + timedelta(minutes=rng.uniform(0, 30 * 24 * 60))
        add_tx(legit_ids[u], legit_ids[v], amount, ts)

    # ------------------------------------------------- legit high-value actors
    # Without these, "big amount == fraud" would be trivially learnable and the
    # model would never need graph features. Real payment networks have heavy
    # legitimate flows: merchants (fan-in!), payroll (fan-out!), B2B transfers
    # in the same lakh-range as laundering. The classifier must separate fraud
    # by *behaviour* (speed, throughput, round amounts), not by amount.
    n_merchants = max(10, cfg.n_legit_accounts // 100)
    merchants = rng.sample(legit_ids, n_merchants * 3)
    for m in merchants[:n_merchants]:
        # Merchant fan-in: many customers, organic timing, non-round amounts.
        for _ in range(rng.randint(40, 120)):
            c = rng.choice(legit_ids)
            ts = EPOCH + timedelta(minutes=rng.uniform(0, 30 * 24 * 60))
            add_tx(c, m, rng.lognormvariate(8.0, 1.0), ts)
        # Merchant settles out to suppliers in large sums.
        for _ in range(rng.randint(4, 10)):
            s = rng.choice(legit_ids)
            ts = EPOCH + timedelta(days=rng.uniform(1, 29))
            add_tx(m, s, rng.uniform(200_000, 1_200_000), ts)
    for p in merchants[n_merchants : n_merchants * 2]:
        # Payroll fan-out: monthly bursts of similar salaries (legit "burst"!).
        employees = rng.sample(legit_ids, rng.randint(15, 40))
        for month_day in (1, 30):
            base = EPOCH + timedelta(days=month_day - 1)
            for e in employees:
                ts = base + timedelta(hours=rng.uniform(0, 8))
                add_tx(p, e, rng.uniform(25_000, 90_000), ts)
    for b in merchants[n_merchants * 2 :]:
        # B2B: few counterparties, large invoices, slow cadence.
        partners = rng.sample(legit_ids, rng.randint(2, 5))
        for _ in range(rng.randint(3, 8)):
            ts = EPOCH + timedelta(days=rng.uniform(0, 28))
            add_tx(b, rng.choice(partners), rng.uniform(150_000, 900_000), ts)

    # ---------------------------------------------------------------- fraud rings
    topologies = ["chain", "fan_in", "cycle"]
    for r in range(cfg.n_rings):
        ring_id = f"ring_{r + 1:02d}"
        size = rng.randint(cfg.ring_size_min, cfg.ring_size_max)
        district = rng.choice(hotspots) if rng.random() < 0.8 else rng.choice(cold or hotspots)
        members = [new_account(district, True, ring_id) for _ in range(size)]
        ring_truth[ring_id] = members
        topo = topologies[r % len(topologies)]
        base_ts = EPOCH + timedelta(days=rng.uniform(2, 26))

        if topo == "chain":
            # Layering: one dirty sum hops down the chain fast, shrinking ~3% per hop.
            amount = rng.uniform(300_000, 900_000)
            for i in range(size - 1):
                ts = base_ts + timedelta(minutes=rng.uniform(3, 45) * (i + 1))
                add_tx(members[i], members[i + 1], amount, ts)
                amount *= rng.uniform(0.95, 0.99)
            # Repeat the run a few times over days (rings reuse their pipes).
            for rep in range(rng.randint(1, 3)):
                amount = rng.uniform(200_000, 700_000)
                start = base_ts + timedelta(days=rep + 1)
                for i in range(size - 1):
                    add_tx(members[i], members[i + 1], amount, start + timedelta(minutes=10 * i))
                    amount *= rng.uniform(0.95, 0.99)

        elif topo == "fan_in":
            # Smurfing: victims (legit accounts!) pay the collector; collector forwards to mules.
            collector, *mules = members
            n_victims = rng.randint(8, 20)
            victims = rng.sample(legit_ids, n_victims)
            for v in victims:
                # Scam payments are often round amounts under reporting thresholds.
                amount = rng.choice([9_999, 24_999, 49_999, 10_000, 25_000, 50_000])
                ts = base_ts + timedelta(hours=rng.uniform(0, 72))
                add_tx(v, collector, amount, ts)
            pooled = n_victims * 25_000
            for m in mules:
                share = pooled / len(mules) * rng.uniform(0.8, 1.1)
                add_tx(collector, m, share, base_ts + timedelta(hours=rng.uniform(72, 96)))

        else:  # cycle
            # Round-tripping: money loops through the ring back to the start.
            amount = rng.uniform(150_000, 500_000)
            for rep in range(rng.randint(2, 4)):
                start = base_ts + timedelta(days=rep * 2)
                for i in range(size):
                    ts = start + timedelta(hours=rng.uniform(1, 6) * (i + 1))
                    add_tx(members[i], members[(i + 1) % size], amount * rng.uniform(0.9, 1.0), ts)

        # Camouflage: mules also make a little organic-looking traffic.
        for m in members:
            for _ in range(rng.randint(1, 3)):
                peer = rng.choice(legit_ids)
                amount = rng.lognormvariate(6.5, 0.9)
                ts = base_ts + timedelta(days=rng.uniform(-2, 4))
                if rng.random() < 0.5:
                    add_tx(m, peer, amount, ts)
                else:
                    add_tx(peer, m, amount, ts)

    return SynthResult(
        accounts=pd.DataFrame(accounts),
        transactions=pd.DataFrame(txs),
        ring_truth=ring_truth,
    )


def save(result: SynthResult, out_dir) -> None:
    from pathlib import Path

    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    result.accounts.to_csv(out / "accounts.csv", index=False)
    result.transactions.to_csv(out / "transactions.csv", index=False)
