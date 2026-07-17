"""Ghost Ring — federated cross-bank fraud detection.

N isolated "banks" (partitions of the transaction graph), each blind to the
others, reveal a shared fraud ring by exchanging *only* embedding vectors for
boundary nodes.  A central matcher links outgoing→incoming transfers across
banks using cosine similarity + amount/time proximity, then Leiden clustering
on the fused graph recovers the cross-bank ring.

The proof: ring-recall per-bank vs. fused.  The gap IS the result.

Pipeline:
  1. Partition Elliptic++/synthetic graph into N silos (Louvain communities).
  2. Per silo: train a 2-layer GraphSAGE, extract 64-dim boundary embeddings.
  3. Central matcher: cosine + amount/time → Hungarian assignment.
  4. Fuse matched edges → Leiden + XGBoost → detect cross-bank rings.

Limitation (stated honestly): the whole result rests on matching precision.
A bad match fuses two unrelated accounts and INVENTS a ring that does not
exist — worse than missing one. So the report carries `false_merge_rate`
(1 - matching precision) next to the recall gap, and `min_score` on the
matcher is the knob that trades recall for precision. Judge the gap and the
false-merge rate together; either alone is misleading.

Stack: PyTorch Geometric, NetworkX, leidenalg, scipy.
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field
from typing import Any

import networkx as nx
import numpy as np
import pandas as pd

from .config import RingConfig
from .data import Dataset

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Soft-imports: these are heavy deps in the [advanced] optional group.
# The module is importable without them (for tests/docs), but the actual
# pipeline functions raise clear errors if they're missing.
# ---------------------------------------------------------------------------

_TORCH_AVAILABLE = False
_PYG_AVAILABLE = False
_LEIDEN_AVAILABLE = False

try:
    import torch
    import torch.nn.functional as F
    _TORCH_AVAILABLE = True
except ImportError:
    torch = None  # type: ignore[assignment]
    F = None  # type: ignore[assignment]

try:
    from torch_geometric.data import Data as PygData
    from torch_geometric.nn import SAGEConv
    _PYG_AVAILABLE = True
except ImportError:
    PygData = None  # type: ignore[assignment]
    SAGEConv = None  # type: ignore[assignment]

try:
    import leidenalg
    import igraph as ig
    _LEIDEN_AVAILABLE = True
except ImportError:
    leidenalg = None  # type: ignore[assignment]
    ig = None  # type: ignore[assignment]


def _require_advanced():
    """Raise if optional deps are missing."""
    missing = []
    if not _TORCH_AVAILABLE:
        missing.append("torch")
    if not _PYG_AVAILABLE:
        missing.append("torch-geometric")
    if not _LEIDEN_AVAILABLE:
        missing.append("leidenalg + igraph")
    if missing:
        raise ImportError(
            f"Ghost Ring requires: {', '.join(missing)}. "
            "Install with: pip install -e '.[advanced]'"
        )


# ── Data structures ────────────────────────────────────────────────────────


@dataclass
class BankSilo:
    """One isolated bank partition."""
    bank_id: int
    node_ids: list[str]
    subgraph: nx.DiGraph
    boundary_nodes: set[str]  # nodes that had cross-partition edges
    accounts: pd.DataFrame
    transactions: pd.DataFrame
    # Populated after training:
    model: Any = None
    embeddings: dict[str, np.ndarray] = field(default_factory=dict)


@dataclass
class BoundaryInfo:
    """Published info for a boundary node (shared with central matcher)."""
    pseudo_id: str
    bank_id: int
    account_id: str  # real id — in production this would be hashed
    embedding: np.ndarray  # 64-dim
    direction: str  # "outgoing" or "incoming"
    amount_bucket: int  # quantized total amount
    time_bucket: int  # quantized avg timestamp


@dataclass
class MatchedEdge:
    """A matched cross-bank link."""
    source_bank: int
    target_bank: int
    source_account: str
    target_account: str
    score: float


@dataclass
class GhostRingReport:
    """Final evaluation: per-bank vs fused detection."""
    n_banks: int
    per_bank_ring_recall: dict[int, float]
    fused_ring_recall: float
    fused_ring_precision: float
    n_ground_truth_cross_edges: int
    n_matched_edges: int
    matching_precision: float  # of matched edges, how many are real cross-edges
    false_merge_rate: float
    recall_gap: float  # fused_recall - avg(per_bank_recall)

    def to_dict(self) -> dict:
        return {
            "n_banks": self.n_banks,
            "per_bank_ring_recall": {str(k): round(v, 4) for k, v in self.per_bank_ring_recall.items()},
            "fused_ring_recall": round(self.fused_ring_recall, 4),
            "fused_ring_precision": round(self.fused_ring_precision, 4),
            "n_ground_truth_cross_edges": self.n_ground_truth_cross_edges,
            "n_matched_edges": self.n_matched_edges,
            "matching_precision": round(self.matching_precision, 4),
            "false_merge_rate": round(self.false_merge_rate, 4),
            "recall_gap": round(self.recall_gap, 4),
        }


# ── Step 1: Partition into bank silos ──────────────────────────────────────


def partition_into_banks(
    ds: Dataset,
    n_banks: int = 4,
    seed: int = 42,
) -> tuple[list[BankSilo], set[tuple[str, str]]]:
    """Partition the graph into N isolated banks via Louvain communities.

    Returns (list of BankSilos, ground-truth cross-partition edges).
    Cross-partition edges are CUT — they become the rings we try to recover.
    """
    # Build full graph
    g = nx.DiGraph()
    for _, row in ds.accounts.iterrows():
        g.add_node(row["account_id"])
    for _, row in ds.transactions.iterrows():
        if row["source"] in g and row["target"] in g:
            g.add_edge(row["source"], row["target"],
                       amount=float(row["amount"]),
                       timestamp=str(row.get("timestamp", "")))

    # Louvain on undirected view for community detection
    und = g.to_undirected()
    communities = list(nx.community.louvain_communities(und, seed=seed))

    # Merge small communities and assign to N banks
    # Sort communities by size descending, assign round-robin to N banks
    communities = sorted(communities, key=len, reverse=True)
    bank_assignments: dict[str, int] = {}
    bank_sizes = [0] * n_banks
    for community in communities:
        # Assign to the smallest bank (greedy load-balancing)
        target_bank = int(np.argmin(bank_sizes))
        for node in community:
            bank_assignments[node] = target_bank
        bank_sizes[target_bank] += len(community)

    # Find cross-partition edges (ground truth)
    cross_edges: set[tuple[str, str]] = set()
    for u, v in g.edges():
        if bank_assignments.get(u, -1) != bank_assignments.get(v, -1):
            cross_edges.add((u, v))

    logger.info(
        "Partitioned %d nodes into %d banks. %d cross-partition edges (ground truth).",
        g.number_of_nodes(), n_banks, len(cross_edges),
    )

    # Build silos
    silos: list[BankSilo] = []
    accounts_indexed = ds.accounts.set_index("account_id")
    for bank_id in range(n_banks):
        bank_nodes = [n for n, b in bank_assignments.items() if b == bank_id]
        if not bank_nodes:
            continue
        bank_set = set(bank_nodes)

        # Boundary nodes: any node with a cut edge
        boundary = set()
        for u, v in cross_edges:
            if u in bank_set:
                boundary.add(u)
            if v in bank_set:
                boundary.add(v)

        # Induced subgraph (intra-bank edges only)
        sub = g.subgraph(bank_nodes).copy()
        # Remove cross-partition edges from subgraph
        edges_to_remove = [(u, v) for u, v in sub.edges() if (u, v) in cross_edges]
        sub.remove_edges_from(edges_to_remove)

        # Bank-local transactions
        bank_tx = ds.transactions[
            ds.transactions["source"].isin(bank_set)
            & ds.transactions["target"].isin(bank_set)
            & ~(  # exclude cross edges
                ds.transactions.apply(
                    lambda r: (r["source"], r["target"]) in cross_edges, axis=1
                )
            )
        ].reset_index(drop=True)

        bank_accs = ds.accounts[ds.accounts["account_id"].isin(bank_set)].reset_index(drop=True)

        silos.append(BankSilo(
            bank_id=bank_id,
            node_ids=bank_nodes,
            subgraph=sub,
            boundary_nodes=boundary,
            accounts=bank_accs,
            transactions=bank_tx,
        ))

    return silos, cross_edges


# ── Step 2: GraphSAGE local models ────────────────────────────────────────


class GraphSAGEEncoder(torch.nn.Module if _TORCH_AVAILABLE else object):
    """2-layer GraphSAGE encoder producing 64-dim node embeddings.

    Inductive: works on any graph structure, not just the training graph.
    """

    def __init__(self, in_channels: int, hidden_channels: int = 64, out_channels: int = 64):
        super().__init__()
        self.conv1 = SAGEConv(in_channels, hidden_channels)
        self.conv2 = SAGEConv(hidden_channels, out_channels)

    def forward(self, x, edge_index):
        x = self.conv1(x, edge_index)
        x = F.relu(x)
        x = F.dropout(x, p=0.3, training=self.training)
        x = self.conv2(x, edge_index)
        return x

    def get_embeddings(self, x, edge_index) -> torch.Tensor:
        """Extract embeddings (no gradient)."""
        self.eval()
        with torch.no_grad():
            return self.forward(x, edge_index)


def _build_pyg_data(silo: BankSilo) -> tuple:
    """Convert a BankSilo into a PyG Data object.

    Node features: [in_degree, out_degree, total_in, total_out, n_txs]
    normalized to [0, 1].
    """
    _require_advanced()
    node_list = sorted(silo.subgraph.nodes())
    node_to_idx = {n: i for i, n in enumerate(node_list)}
    n = len(node_list)

    # Build edge index
    edges_src, edges_dst = [], []
    for u, v in silo.subgraph.edges():
        edges_src.append(node_to_idx[u])
        edges_dst.append(node_to_idx[v])
    if edges_src:
        edge_index = torch.tensor([edges_src, edges_dst], dtype=torch.long)
    else:
        edge_index = torch.zeros((2, 0), dtype=torch.long)

    # Node features from transaction aggregates
    tx = silo.transactions
    in_deg = tx.groupby("target").size().reindex(node_list, fill_value=0).values.astype(float)
    out_deg = tx.groupby("source").size().reindex(node_list, fill_value=0).values.astype(float)
    total_in = tx.groupby("target")["amount"].sum().reindex(node_list, fill_value=0).values.astype(float)
    total_out = tx.groupby("source")["amount"].sum().reindex(node_list, fill_value=0).values.astype(float)
    n_txs = (in_deg + out_deg)

    features = np.stack([in_deg, out_deg, total_in, total_out, n_txs], axis=1)
    # Normalize per-column
    for col in range(features.shape[1]):
        mx = features[:, col].max()
        if mx > 0:
            features[:, col] /= mx

    x = torch.tensor(features, dtype=torch.float32)

    # Labels
    acc_labels = silo.accounts.set_index("account_id")["is_illicit"]
    y = torch.tensor(
        [int(acc_labels.get(n, False) or False) for n in node_list],
        dtype=torch.long,
    )

    data = PygData(x=x, edge_index=edge_index, y=y)
    return data, node_list, node_to_idx


def train_local_model(
    silo: BankSilo,
    epochs: int = 100,
    lr: float = 0.01,
) -> GraphSAGEEncoder:
    """Train a GraphSAGE on the silo's local subgraph.

    Objective: node classification (illicit vs licit) — we want embeddings
    that separate fraud from legitimate, so cross-bank boundary embeddings
    of the same ring member will cluster together.
    """
    _require_advanced()

    data, node_list, node_to_idx = _build_pyg_data(silo)
    in_channels = data.x.shape[1]

    model = GraphSAGEEncoder(in_channels=in_channels)
    classifier = torch.nn.Linear(64, 2)

    optimizer = torch.optim.Adam(
        list(model.parameters()) + list(classifier.parameters()),
        lr=lr, weight_decay=5e-4,
    )

    # Class weights for imbalanced data
    n_pos = (data.y == 1).sum().item()
    n_neg = (data.y == 0).sum().item()
    weight = torch.tensor([1.0, max(n_neg / max(n_pos, 1), 1.0)])

    model.train()
    classifier.train()
    for epoch in range(epochs):
        optimizer.zero_grad()
        emb = model(data.x, data.edge_index)
        logits = classifier(emb)
        loss = F.cross_entropy(logits, data.y, weight=weight)
        loss.backward()
        optimizer.step()

    silo.model = model

    # Extract embeddings for all nodes
    emb = model.get_embeddings(data.x, data.edge_index)
    silo.embeddings = {
        node_list[i]: emb[i].numpy() for i in range(len(node_list))
    }

    logger.info(
        "Bank %d: trained GraphSAGE on %d nodes, %d edges (loss=%.4f)",
        silo.bank_id, len(node_list), data.edge_index.shape[1], loss.item(),
    )
    return model


# ── Step 3: Extract boundary info ──────────────────────────────────────────


def _amount_bucket(total: float) -> int:
    """Quantize amount into log-scale buckets."""
    if total <= 0:
        return 0
    return int(np.log10(max(total, 1.0)))


def _time_bucket(timestamps: list[str]) -> int:
    """Quantize average timestamp into day-of-month bucket."""
    valid = []
    for t in timestamps:
        try:
            dt = pd.to_datetime(t, utc=True)
            if pd.notna(dt):
                valid.append(dt.day)
        except Exception:
            pass
    return int(np.mean(valid)) if valid else 0


def extract_boundary_info(
    silo: BankSilo,
    ds_full: Dataset,
) -> list[BoundaryInfo]:
    """Extract publishable boundary information for the central matcher.

    For each boundary node, we publish:
    - pseudo_id (bank_id + hash)
    - 64-dim embedding from the local GraphSAGE
    - direction (outgoing/incoming based on cut edges)
    - amount_bucket (log-scale quantization)
    - time_bucket (day-of-month quantization)
    """
    infos: list[BoundaryInfo] = []
    bank_set = set(silo.node_ids)
    full_tx = ds_full.transactions

    for node in silo.boundary_nodes:
        if node not in silo.embeddings:
            continue

        # Determine direction and aggregate amounts/times for cross-bank edges
        outgoing_tx = full_tx[
            (full_tx["source"] == node) & (~full_tx["target"].isin(bank_set))
        ]
        incoming_tx = full_tx[
            (full_tx["target"] == node) & (~full_tx["source"].isin(bank_set))
        ]

        # Publish one entry per direction
        if len(outgoing_tx) > 0:
            infos.append(BoundaryInfo(
                pseudo_id=f"b{silo.bank_id}_out_{node}",
                bank_id=silo.bank_id,
                account_id=node,
                embedding=silo.embeddings[node],
                direction="outgoing",
                amount_bucket=_amount_bucket(outgoing_tx["amount"].sum()),
                time_bucket=_time_bucket(outgoing_tx["timestamp"].astype(str).tolist()),
            ))

        if len(incoming_tx) > 0:
            infos.append(BoundaryInfo(
                pseudo_id=f"b{silo.bank_id}_in_{node}",
                bank_id=silo.bank_id,
                account_id=node,
                embedding=silo.embeddings[node],
                direction="incoming",
                amount_bucket=_amount_bucket(incoming_tx["amount"].sum()),
                time_bucket=_time_bucket(incoming_tx["timestamp"].astype(str).tolist()),
            ))

    logger.info(
        "Bank %d: %d boundary infos extracted (%d boundary nodes)",
        silo.bank_id, len(infos), len(silo.boundary_nodes),
    )
    return infos


# ── Step 4: Central matcher ───────────────────────────────────────────────


class CentralMatcher:
    """Links boundary nodes across banks using embedding similarity.

    Score = cosine_sim(emb_a, emb_b) × amount_proximity × time_proximity
    Assignment: Hungarian algorithm (scipy.optimize.linear_sum_assignment).
    """

    def __init__(
        self,
        cosine_weight: float = 0.6,
        amount_weight: float = 0.2,
        time_weight: float = 0.2,
        min_score: float = 0.3,
    ):
        self.cosine_weight = cosine_weight
        self.amount_weight = amount_weight
        self.time_weight = time_weight
        self.min_score = min_score

    def _cosine_similarity(self, a: np.ndarray, b: np.ndarray) -> float:
        """Cosine similarity between two vectors."""
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a < 1e-9 or norm_b < 1e-9:
            return 0.0
        return float(np.dot(a, b) / (norm_a * norm_b))

    def _amount_proximity(self, bucket_a: int, bucket_b: int) -> float:
        """Proximity score based on amount bucket difference."""
        diff = abs(bucket_a - bucket_b)
        return max(0.0, 1.0 - diff * 0.3)

    def _time_proximity(self, bucket_a: int, bucket_b: int) -> float:
        """Proximity score based on time bucket difference."""
        diff = abs(bucket_a - bucket_b)
        return max(0.0, 1.0 - diff * 0.1)

    def match(self, all_boundary_infos: list[list[BoundaryInfo]]) -> list[MatchedEdge]:
        """Match outgoing nodes from one bank to incoming nodes of another.

        Uses the Hungarian algorithm for optimal assignment.
        """
        from scipy.optimize import linear_sum_assignment

        # Collect all outgoing and incoming entries across banks
        outgoing: list[BoundaryInfo] = []
        incoming: list[BoundaryInfo] = []
        for bank_infos in all_boundary_infos:
            for info in bank_infos:
                if info.direction == "outgoing":
                    outgoing.append(info)
                else:
                    incoming.append(info)

        if not outgoing or not incoming:
            return []

        # Build cost matrix (negate scores for minimization)
        n_out, n_in = len(outgoing), len(incoming)
        cost = np.zeros((n_out, n_in))

        for i, out_info in enumerate(outgoing):
            for j, in_info in enumerate(incoming):
                # Don't match within the same bank
                if out_info.bank_id == in_info.bank_id:
                    cost[i, j] = 1e6  # prohibitive cost
                    continue

                cos_sim = self._cosine_similarity(out_info.embedding, in_info.embedding)
                amt_prox = self._amount_proximity(out_info.amount_bucket, in_info.amount_bucket)
                time_prox = self._time_proximity(out_info.time_bucket, in_info.time_bucket)

                score = (
                    self.cosine_weight * cos_sim
                    + self.amount_weight * amt_prox
                    + self.time_weight * time_prox
                )
                cost[i, j] = -score  # negate for minimization

        # Hungarian assignment
        row_ind, col_ind = linear_sum_assignment(cost)

        matched: list[MatchedEdge] = []
        for r, c in zip(row_ind, col_ind):
            score = -cost[r, c]
            if score >= self.min_score:
                matched.append(MatchedEdge(
                    source_bank=outgoing[r].bank_id,
                    target_bank=incoming[c].bank_id,
                    source_account=outgoing[r].account_id,
                    target_account=incoming[c].account_id,
                    score=float(score),
                ))

        logger.info(
            "Matched %d cross-bank edges (from %d outgoing × %d incoming, threshold=%.2f)",
            len(matched), n_out, n_in, self.min_score,
        )
        return matched


# ── Step 5: Fuse and detect ───────────────────────────────────────────────


def _leiden_communities(g: nx.Graph, seed: int = 42) -> list[set]:
    """Run Leiden community detection (better small-cluster resolution than Louvain).

    Converts NetworkX graph → igraph → Leiden → back to sets of node ids.
    """
    _require_advanced()
    if g.number_of_nodes() == 0:
        return []

    # Convert to igraph
    node_list = list(g.nodes())
    node_to_idx = {n: i for i, n in enumerate(node_list)}
    ig_edges = [(node_to_idx[u], node_to_idx[v]) for u, v in g.edges()
                if u in node_to_idx and v in node_to_idx]

    ig_graph = ig.Graph(n=len(node_list), edges=ig_edges, directed=False)

    # Leiden with RBConfigurationVertexPartition for better resolution
    partition = leidenalg.find_partition(
        ig_graph,
        leidenalg.RBConfigurationVertexPartition,
        resolution_parameter=1.0,
        seed=seed,
    )

    communities: list[set] = []
    for comm in partition:
        communities.append({node_list[i] for i in comm})

    return communities


def fuse_and_detect(
    silos: list[BankSilo],
    matched_edges: list[MatchedEdge],
    ds_full: Dataset,
) -> tuple[list, pd.DataFrame]:
    """Rebuild one graph with matched pairs as edges, run Leiden + XGBoost."""
    from .graph import compute_features
    from .model import load_model, score_all
    from .rings import Ring

    # Rebuild fused graph: all intra-bank edges + matched cross-bank edges
    fused_accounts = pd.concat([s.accounts for s in silos], ignore_index=True).drop_duplicates(
        subset=["account_id"]
    )
    fused_tx_parts = [s.transactions for s in silos]

    # Add matched edges as synthetic transactions
    matched_tx_rows = []
    for i, me in enumerate(matched_edges):
        matched_tx_rows.append({
            "tx_id": f"matched_{i:06d}",
            "source": me.source_account,
            "target": me.target_account,
            "amount": 1.0,  # placeholder
            "timestamp": "",
        })
    if matched_tx_rows:
        fused_tx_parts.append(pd.DataFrame(matched_tx_rows))

    fused_tx = pd.concat(fused_tx_parts, ignore_index=True).drop_duplicates(subset=["tx_id"])

    fused_ds = Dataset(
        accounts=fused_accounts,
        transactions=fused_tx,
        name="fused",
    )

    # Compute features and score with the existing XGBoost model
    features = compute_features(fused_ds)
    try:
        clf = load_model()
    except Exception:
        # No pre-trained model — train one on the fused data
        from .model import train as train_model
        labels = fused_ds.accounts.set_index("account_id")["is_illicit"]
        clf, _ = train_model(features, labels)

    scores = score_all(clf, features)

    # Use Leiden for clustering instead of Louvain
    high_risk = scores[scores >= 0.5].index
    sub_tx = fused_tx[fused_tx["source"].isin(high_risk) & fused_tx["target"].isin(high_risk)]

    g = nx.Graph()
    g.add_nodes_from(high_risk)
    for _, row in sub_tx.iterrows():
        if row["source"] in g and row["target"] in g:
            g.add_edge(row["source"], row["target"])

    if _LEIDEN_AVAILABLE and g.number_of_edges() > 0:
        communities = _leiden_communities(g)
    else:
        # Fallback to connected components
        communities = [set(c) for c in nx.connected_components(g)]

    districts = (
        fused_ds.accounts.set_index("account_id")["district"]
        if "district" in fused_ds.accounts
        else pd.Series(dtype=object)
    )

    rings: list[Ring] = []
    assignment: dict[str, str] = {}
    idx = 0
    for members in sorted(communities, key=len, reverse=True):
        if len(members) < 3:
            continue
        idx += 1
        rid = f"fused_ring_{idx:02d}"
        member_list = sorted(members)
        rings.append(Ring(
            ring_id=rid,
            account_ids=member_list,
            risk_score=float(scores.reindex(member_list).mean()),
            size=len(member_list),
            total_amount=0.0,
            label="cross-bank",
            district=None,
        ))
        assignment.update({aid: rid for aid in member_list})

    accounts_out = pd.DataFrame({
        "account_id": scores.index,
        "illicit_probability": scores.values,
    })
    accounts_out["ring_id"] = accounts_out["account_id"].map(assignment)

    return rings, accounts_out


# ── Step 6: Per-bank detection (for comparison) ──────────────────────────


def detect_per_bank(silo: BankSilo) -> tuple[list, pd.DataFrame]:
    """Run standalone detection on a single bank silo."""
    from .graph import compute_features
    from .model import load_model, score_all
    from .rings import Ring, detect_rings

    bank_ds = Dataset(
        accounts=silo.accounts,
        transactions=silo.transactions,
        name=f"bank_{silo.bank_id}",
    )

    features = compute_features(bank_ds)
    try:
        clf = load_model()
    except Exception:
        from .model import train as train_model
        labels = bank_ds.accounts.set_index("account_id")["is_illicit"]
        clf, _ = train_model(features, labels)

    scores = score_all(clf, features)
    rings, accounts = detect_rings(bank_ds, scores)
    return rings, accounts


# ── Step 7: Full pipeline + evaluation ────────────────────────────────────


def _compute_ring_recall(
    detected_rings: list,
    ground_truth_accounts: pd.DataFrame,
) -> float:
    """Fraction of truly illicit accounts that ended up in a detected ring."""
    illicit = set(
        ground_truth_accounts[
            ground_truth_accounts["is_illicit"] == True  # noqa: E712
        ]["account_id"]
    )
    if not illicit:
        return 0.0

    ringed = set()
    for r in detected_rings:
        ringed.update(r.account_ids)

    return len(ringed & illicit) / len(illicit)


def run_ghost_ring(
    source: str = "synthetic",
    n_banks: int = 4,
) -> GhostRingReport:
    """End-to-end Ghost Ring pipeline.

    1. Partition → 2. Local GraphSAGE per bank → 3. Boundary extraction →
    4. Central matching → 5. Fuse + detect → 6. Compare per-bank vs fused.
    """
    _require_advanced()
    from .data import load

    logger.info("=== Ghost Ring Pipeline (n_banks=%d, source=%s) ===", n_banks, source)

    # Load full dataset
    ds = load(source)

    # Step 1: Partition
    silos, cross_edges = partition_into_banks(ds, n_banks=n_banks)
    logger.info("Partitioned into %d banks with %d cross edges", len(silos), len(cross_edges))

    # Step 2: Train local models
    for silo in silos:
        train_local_model(silo, epochs=80)

    # Step 3: Extract boundary info
    all_boundary_infos: list[list[BoundaryInfo]] = []
    for silo in silos:
        infos = extract_boundary_info(silo, ds)
        all_boundary_infos.append(infos)

    # Step 4: Match
    matcher = CentralMatcher()
    matched = matcher.match(all_boundary_infos)

    # Step 5: Fuse and detect
    fused_rings, fused_accounts = fuse_and_detect(silos, matched, ds)

    # Step 6: Per-bank detection
    per_bank_recall: dict[int, float] = {}
    for silo in silos:
        bank_rings, bank_accs = detect_per_bank(silo)
        recall = _compute_ring_recall(bank_rings, silo.accounts)
        per_bank_recall[silo.bank_id] = recall

    # Fused recall
    fused_recall = _compute_ring_recall(fused_rings, ds.accounts)

    # Matching precision: of matched edges, how many correspond to real cross edges
    cross_set = cross_edges
    true_matches = sum(
        1 for m in matched
        if (m.source_account, m.target_account) in cross_set
        or (m.target_account, m.source_account) in cross_set
    )
    matching_precision = true_matches / max(len(matched), 1)
    false_merge_rate = 1.0 - matching_precision

    avg_per_bank = float(np.mean(list(per_bank_recall.values()))) if per_bank_recall else 0.0

    report = GhostRingReport(
        n_banks=len(silos),
        per_bank_ring_recall=per_bank_recall,
        fused_ring_recall=fused_recall,
        fused_ring_precision=matching_precision,
        n_ground_truth_cross_edges=len(cross_edges),
        n_matched_edges=len(matched),
        matching_precision=matching_precision,
        false_merge_rate=false_merge_rate,
        recall_gap=fused_recall - avg_per_bank,
    )

    logger.info("=== Ghost Ring Results ===")
    logger.info("Per-bank recall: %s", per_bank_recall)
    logger.info("Fused recall: %.4f", fused_recall)
    logger.info("Recall gap (THE result): %.4f", report.recall_gap)
    logger.info("Matching precision: %.4f, false-merge rate: %.4f",
                matching_precision, false_merge_rate)

    return report
