"""Demo-only helpers for injecting fresh fraud rings into the synthetic graph."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Literal

import pandas as pd

from .data import Dataset

DemoTopology = Literal["cycle", "chain", "fan_in"]

_DEMO_DISTRICTS = (
    "Jamtara",
    "Deoghar",
    "Alwar",
    "Bharatpur",
    "Nuh",
    "Chennai Central",
    "Mumbai South",
    "Delhi East",
)


def clean_account_names(raw: list[str] | None) -> list[str]:
    """Trim, dedupe (case-insensitive), and cap user-supplied account names.

    Returns [] when nothing usable was given; raises ValueError when 1-2 names
    survive cleaning — a ring needs at least 3 members to be detectable
    (RingConfig.min_ring_size), and silently padding would surprise the demo.
    """
    if not raw:
        return []
    seen: set[str] = set()
    names: list[str] = []
    for item in raw:
        name = str(item).strip()[:24]
        if not name or name.lower() in seen:
            continue
        seen.add(name.lower())
        names.append(name)
    if 0 < len(names) < 3:
        raise ValueError("need at least 3 account names to form a detectable ring")
    return names[:10]


def inject_demo_ring(
    ds: Dataset,
    district: str = "Jamtara",
    topology: DemoTopology = "cycle",
    size: int = 6,
    account_names: list[str] | None = None,
) -> Dataset:
    """Return a copy of *ds* with a fresh illicit ring appended.

    The injected cluster is intentionally high-signal: six new accounts, dense
    transfers, short time gaps, and round-ish values so the graph detector
    catches it on the next pass. Pass *account_names* (3-10 strings) to name
    the ring members yourself — the stage moment where a judge's name shows up
    inside a caught fraud ring.
    """

    district = district if district in _DEMO_DISTRICTS else "Jamtara"
    accounts = ds.accounts.copy(deep=True)
    transactions = ds.transactions.copy(deep=True)

    names = clean_account_names(account_names)
    if names:
        size = len(names)

    next_account = _next_numeric_id(accounts["account_id"], prefix="acc_")
    next_tx = _next_numeric_id(transactions["tx_id"], prefix="tx_")
    next_ring_index = int(accounts["ring_id"].dropna().nunique()) + 1 if "ring_id" in accounts else 1
    ring_id = f"ring_{next_ring_index:02d}"

    existing_ids = set(accounts["account_id"].astype(str))

    def unique_id(base: str) -> str:
        candidate, n = base, 2
        while candidate in existing_ids:
            candidate = f"{base}_{n}"
            n += 1
        existing_ids.add(candidate)
        return candidate

    members: list[str] = []
    for i in range(size):
        if names:
            account_id = unique_id(names[i])
        else:
            account_id = unique_id(f"acc_{next_account:05d}")
            next_account += 1
        members.append(account_id)
        accounts.loc[len(accounts)] = {
            "account_id": account_id,
            "district": district,
            "is_illicit": True,
            "ring_id": ring_id,
        }

    base_ts = datetime.now(timezone.utc).replace(microsecond=0, second=0)
    amount = 420_000.0

    def add_tx(source: str, target: str, value: float, offset_minutes: int) -> None:
        nonlocal next_tx
        transactions.loc[len(transactions)] = {
            "tx_id": f"tx_{next_tx:06d}",
            "source": source,
            "target": target,
            "amount": round(value, 2),
            "timestamp": (base_ts + timedelta(minutes=offset_minutes)).isoformat(),
        }
        next_tx += 1

    if topology == "fan_in":
        collector, *mules = members
        for i, source in enumerate(members[1:], start=1):
            add_tx(source, collector, amount * (0.98 - i * 0.01), i * 7)
        for i, mule in enumerate(mules, start=1):
            add_tx(collector, mule, amount * (0.76 - i * 0.02), 45 + i * 6)
    elif topology == "chain":
        for round_idx in range(3):
            current_amount = amount * (0.99 - round_idx * 0.02)
            start_minute = round_idx * 35
            for i in range(size - 1):
                add_tx(
                    members[i],
                    members[i + 1],
                    current_amount * (0.97**i),
                    start_minute + i * 5,
                )
    else:  # cycle
        for round_idx in range(3):
            current_amount = amount * (1.0 - round_idx * 0.02)
            start_minute = round_idx * 30
            for i in range(size):
                add_tx(
                    members[i],
                    members[(i + 1) % size],
                    current_amount * (0.98**i),
                    start_minute + i * 4,
                )

    return Dataset(
        accounts=accounts.reset_index(drop=True),
        transactions=transactions.reset_index(drop=True),
        name=f"{ds.name}+demo-ring",
    )


def _next_numeric_id(values: pd.Series, prefix: str) -> int:
    extracted = values.astype(str).str.extract(rf"^{prefix}(\d+)$")[0].dropna()
    if extracted.empty:
        return 0
    return int(extracted.astype(int).max()) + 1