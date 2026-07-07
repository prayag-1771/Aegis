"""Dataset loaders.

Every loader returns the same shape (`Dataset`), so the rest of the pipeline
doesn't care where data came from. Swap synthetic -> Elliptic++ by changing one
CLI flag, not the code.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

from .config import DATA_DIR, SynthConfig
from .synth import generate, save


@dataclass
class Dataset:
    """Normalized dataset the pipeline consumes.

    accounts:     account_id, district (nullable), is_illicit (nullable for unlabeled), ring_id (nullable)
    transactions: tx_id, source, target, amount, timestamp
    """

    accounts: pd.DataFrame
    transactions: pd.DataFrame
    name: str = "unnamed"


def load_synthetic(cfg: SynthConfig | None = None, cache: bool = True) -> Dataset:
    """Generate (or load cached) synthetic data with ground-truth rings."""
    cache_dir = DATA_DIR / "synthetic"
    if cache and (cache_dir / "accounts.csv").exists():
        return Dataset(
            accounts=pd.read_csv(cache_dir / "accounts.csv"),
            transactions=pd.read_csv(cache_dir / "transactions.csv"),
            name="synthetic(cached)",
        )
    result = generate(cfg)
    if cache:
        save(result, cache_dir)
    return Dataset(accounts=result.accounts, transactions=result.transactions, name="synthetic")


def load_elliptic(
    root: Path | None = None,
    max_licit: int = 50_000,
    seed: int = 42,
) -> Dataset:
    """Load the Elliptic++ *actors* dataset (Bitcoin wallets) from data/elliptic/.

    Full graph is 823k wallets / 2.9M edges — too large for NetworkX feature
    extraction in RAM. We validate on a stratified subsample: **every illicit
    wallet (14,266)** plus `max_licit` randomly sampled licit wallets, with the
    induced edge set. Honest caveat for the deck: real-data metrics are on this
    labeled subsample, not the full graph (standard practice at hackathon scale;
    the pipeline itself is unchanged).

    Files (github.com/git-disl/EllipticPlusPlus, Google Drive release):
      AddrAddr_edgelist.csv  (input_address,output_address)
      wallets_classes.csv    (address,class)  1=illicit 2=licit 3=unknown
    """
    root = root or (DATA_DIR / "elliptic")
    edge_file = root / "AddrAddr_edgelist.csv"
    cls_file = root / "wallets_classes.csv"
    if not edge_file.exists():
        raise FileNotFoundError(
            f"Elliptic++ files not found under {root}. "
            "Download AddrAddr_edgelist.csv and wallets_classes.csv from the "
            "Elliptic++ release (github.com/git-disl/EllipticPlusPlus) into that folder."
        )

    classes = pd.read_csv(cls_file).rename(columns={"address": "account_id", "class": "cls"})
    illicit = classes[classes["cls"] == 1]
    licit = classes[classes["cls"] == 2]
    if len(licit) > max_licit:
        licit = licit.sample(n=max_licit, random_state=seed)
    selected = pd.concat([illicit, licit])
    selected["is_illicit"] = selected["cls"] == 1
    keep = set(selected["account_id"])

    edges = pd.read_csv(edge_file).rename(
        columns={"input_address": "source", "output_address": "target"}
    )
    edges = edges[edges["source"].isin(keep) & edges["target"].isin(keep)].reset_index(drop=True)
    edges["tx_id"] = [f"tx_{i:07d}" for i in range(len(edges))]
    # Address-level edge list has no amounts/timestamps; neutral fills mean the
    # tempo/amount features go flat and the model relies on pure structure.
    edges["amount"] = 1.0
    edges["timestamp"] = pd.NaT

    accounts = selected[["account_id", "is_illicit"]].copy()
    accounts["district"] = None
    accounts["ring_id"] = None

    return Dataset(
        accounts=accounts.reset_index(drop=True),
        transactions=edges[["tx_id", "source", "target", "amount", "timestamp"]],
        name=f"elliptic++(all-illicit+{len(licit)}-licit)",
    )


LOADERS = {
    "synthetic": load_synthetic,
    "elliptic": load_elliptic,
}


def load(source: str = "synthetic") -> Dataset:
    if source not in LOADERS:
        raise ValueError(f"Unknown source '{source}'. Options: {sorted(LOADERS)}")
    return LOADERS[source]()
