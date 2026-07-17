"""Frequency of Fraud — spectral graph analysis for fraud detection.

A spectral lens over transaction communities: eigendecomposition of the
normalized Laplacian reveals how fraud rings shift energy into high-frequency
modes.  Beta wavelet filters (BWGNN, Tang et al. 2022) isolate frequency
bands and produce node features for the classifier.

Pipeline:
  1. Per community (Leiden), not global — O(n³) on the full graph is death.
  2. Build normalized Laplacian L_sym = I - D^(-1/2) A D^(-1/2).
  3. Eigendecompose (scipy.sparse.linalg.eigsh).
  4. Measure spectral shift via Rayleigh quotient / spectral energy distribution.
  5. Beta wavelet band-pass filters → concatenated node features → classifier.

Limitation (stated honestly): on real, sparse transaction graphs the
high-frequency shift is far subtler than the published figures suggest —
those are measured on dense benchmark graphs. The validation path here is
therefore injected rings, where the effect is guaranteed and the shift can be
measured against a matched clean community (`measure_spectral_shift`). Report
what the numbers actually say on real data; do not assume the paper's gap.

Stack: scipy.sparse, numpy, networkx, leidenalg (optional).
"""

from __future__ import annotations

import logging
import warnings
from dataclasses import dataclass, field

import networkx as nx
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import eigsh

from .data import Dataset

logger = logging.getLogger(__name__)

_LEIDEN_AVAILABLE = False
try:
    import leidenalg
    import igraph as ig
    _LEIDEN_AVAILABLE = True
except ImportError:
    pass


# ── Laplacian construction ─────────────────────────────────────────────────


def build_normalized_laplacian(
    g: nx.Graph,
    node_order: list[str] | None = None,
) -> tuple[sparse.csr_matrix, list[str]]:
    """Build the symmetric normalized Laplacian L_sym = I - D^(-1/2) A D^(-1/2).

    Eigenvalues of L_sym land in [0, 2] — that's the frequency axis.
    Returns (L_sym as sparse CSR, ordered node list).
    """
    if node_order is None:
        node_order = sorted(g.nodes())
    n = len(node_order)
    node_to_idx = {nd: i for i, nd in enumerate(node_order)}

    # Build adjacency
    rows, cols, vals = [], [], []
    for u, v in g.edges():
        if u in node_to_idx and v in node_to_idx:
            i, j = node_to_idx[u], node_to_idx[v]
            rows.extend([i, j])
            cols.extend([j, i])
            vals.extend([1.0, 1.0])

    A = sparse.csr_matrix((vals, (rows, cols)), shape=(n, n))
    degrees = np.array(A.sum(axis=1)).flatten()
    # Avoid division by zero for isolated nodes
    degrees_inv_sqrt = np.where(degrees > 0, 1.0 / np.sqrt(degrees), 0.0)
    D_inv_sqrt = sparse.diags(degrees_inv_sqrt)

    I = sparse.eye(n, format="csr")
    L_sym = I - D_inv_sqrt @ A @ D_inv_sqrt

    return L_sym, node_order


# ── Eigendecomposition ─────────────────────────────────────────────────────


def compute_spectrum(
    L: sparse.csr_matrix,
    k: int = 50,
) -> tuple[np.ndarray, np.ndarray]:
    """Compute the k smallest eigenvalues/eigenvectors of the Laplacian.

    Returns (eigenvalues shape (k,), eigenvectors shape (n, k)).
    """
    n = L.shape[0]
    k = min(k, n - 2) if n > 2 else 1
    if k < 1:
        return np.array([0.0]), np.ones((n, 1)) / np.sqrt(n)

    try:
        eigenvalues, eigenvectors = eigsh(L, k=k, which="SM", tol=1e-6)
    except Exception:
        # Fallback to dense for very small graphs
        L_dense = L.toarray()
        eigenvalues_full, eigenvectors_full = np.linalg.eigh(L_dense)
        eigenvalues = eigenvalues_full[:k]
        eigenvectors = eigenvectors_full[:, :k]

    # Sort by eigenvalue (eigsh doesn't guarantee order)
    order = np.argsort(eigenvalues)
    eigenvalues = eigenvalues[order]
    eigenvectors = eigenvectors[:, order]

    # Clamp to [0, 2] (numerical noise can push slightly outside)
    eigenvalues = np.clip(eigenvalues, 0.0, 2.0)

    return eigenvalues, eigenvectors


# ── Spectral energy distribution ───────────────────────────────────────────


def spectral_energy_distribution(
    x: np.ndarray,
    eigenvalues: np.ndarray,
    eigenvectors: np.ndarray,
) -> np.ndarray:
    """Project signal x onto eigenvectors and compute energy per eigenvalue.

    SED[i] = (x^T u_i)^2  where u_i is the i-th eigenvector.
    Returns array of shape (k,).
    """
    # x should be (n,) or (n, 1)
    x = x.flatten()
    coeffs = eigenvectors.T @ x  # shape (k,)
    energy = coeffs ** 2
    # Normalize to sum to 1
    total = energy.sum()
    if total > 0:
        energy = energy / total
    return energy


def rayleigh_quotient(x: np.ndarray, L: sparse.csr_matrix) -> float:
    """Compute the Rayleigh quotient R(x) = (x^T L x) / (x^T x).

    This is literally "how much energy sits in high frequencies."
    Higher value = more high-frequency content = more suspicious.
    """
    x = x.flatten().astype(float)
    xtx = x @ x
    if xtx < 1e-12:
        return 0.0
    xtLx = x @ (L @ x)
    return float(xtLx / xtx)


# ── Spectral shift measurement ────────────────────────────────────────────


@dataclass
class SpectralShiftResult:
    """Comparison of spectral properties between clean and ring communities."""
    clean_rayleigh: float
    ring_rayleigh: float
    shift_magnitude: float  # ring - clean (positive = right-shift = suspicious)
    clean_sed: np.ndarray
    ring_sed: np.ndarray
    clean_eigenvalues: np.ndarray
    ring_eigenvalues: np.ndarray

    def to_dict(self) -> dict:
        return {
            "clean_rayleigh": round(self.clean_rayleigh, 6),
            "ring_rayleigh": round(self.ring_rayleigh, 6),
            "shift_magnitude": round(self.shift_magnitude, 6),
            "clean_high_freq_energy": round(float(self.clean_sed[len(self.clean_sed)//2:].sum()), 4),
            "ring_high_freq_energy": round(float(self.ring_sed[len(self.ring_sed)//2:].sum()), 4),
        }


def measure_spectral_shift(
    clean_graph: nx.Graph,
    ring_graph: nx.Graph,
    feature_signal: str = "degree",
) -> SpectralShiftResult:
    """Compare the spectral energy of a clean community vs one with an injected ring.

    The ring shifts energy rightward (into high-frequency modes) because fraud
    accounts create unusual connectivity patterns that break the smooth
    low-frequency structure of legitimate communities.
    """
    def _get_signal(g: nx.Graph, nodes: list[str]) -> np.ndarray:
        if feature_signal == "degree":
            deg = dict(g.degree())
            return np.array([deg.get(n, 0) for n in nodes], dtype=float)
        elif feature_signal == "ones":
            return np.ones(len(nodes), dtype=float)
        else:
            return np.array([g.degree(n) for n in nodes], dtype=float)

    # Clean community
    L_clean, nodes_clean = build_normalized_laplacian(clean_graph)
    evals_clean, evecs_clean = compute_spectrum(L_clean, k=min(50, len(nodes_clean) - 1))
    x_clean = _get_signal(clean_graph, nodes_clean)
    sed_clean = spectral_energy_distribution(x_clean, evals_clean, evecs_clean)
    rq_clean = rayleigh_quotient(x_clean, L_clean)

    # Ring community
    L_ring, nodes_ring = build_normalized_laplacian(ring_graph)
    evals_ring, evecs_ring = compute_spectrum(L_ring, k=min(50, len(nodes_ring) - 1))
    x_ring = _get_signal(ring_graph, nodes_ring)
    sed_ring = spectral_energy_distribution(x_ring, evals_ring, evecs_ring)
    rq_ring = rayleigh_quotient(x_ring, L_ring)

    return SpectralShiftResult(
        clean_rayleigh=rq_clean,
        ring_rayleigh=rq_ring,
        shift_magnitude=rq_ring - rq_clean,
        clean_sed=sed_clean,
        ring_sed=sed_ring,
        clean_eigenvalues=evals_clean,
        ring_eigenvalues=evals_ring,
    )


# ── Beta Wavelet Filters (BWGNN, Tang et al. 2022) ────────────────────────


class BetaWaveletFilter:
    """Band-pass spectral filters using Beta-distribution-shaped windows.

    Each filter isolates a frequency band of the Laplacian spectrum.  Multiple
    filters at different bands produce multi-scale node features that capture
    both low-frequency (smooth community structure) and high-frequency
    (anomalous ring connections) signals.

    The Beta(α, β) PDF on [0, 2] peaks at 2(α-1)/(α+β-2), so by varying α, β
    we slide the passband across the spectrum.

    Implementation: Chebyshev polynomial approximation of the spectral filter,
    avoiding explicit eigendecomposition for the filtering step.
    """

    def __init__(
        self,
        n_bands: int = 4,
        polynomial_order: int = 8,
    ):
        self.n_bands = n_bands
        self.polynomial_order = polynomial_order

        # Design filter banks: Beta(α, β) parameters for each band
        # Band 0: low-pass  (α=2, β=5)  — peak near 0.25
        # Band 1: low-mid   (α=3, β=3)  — peak at 1.0
        # Band 2: mid-high  (α=5, β=2)  — peak near 1.75
        # Band 3: high-pass (α=8, β=2)  — peak near 1.75+
        self.filter_params = self._design_filter_banks(n_bands)

    def _design_filter_banks(self, n_bands: int) -> list[tuple[float, float]]:
        """Generate (α, β) parameters that tile [0, 2] with overlapping bands."""
        params = []
        for i in range(n_bands):
            # Slide from low-pass to high-pass
            t = i / max(n_bands - 1, 1)
            alpha = 2.0 + t * 6.0   # 2 → 8
            beta = 8.0 - t * 6.0    # 8 → 2
            alpha = max(alpha, 1.01)
            beta = max(beta, 1.01)
            params.append((alpha, beta))
        return params

    def _beta_pdf(self, x: np.ndarray, alpha: float, beta: float) -> np.ndarray:
        """Beta PDF on [0, 2], normalized to peak = 1."""
        from scipy.stats import beta as beta_dist
        # Scale x from [0, 2] to [0, 1] for scipy's beta
        x_scaled = np.clip(x / 2.0, 1e-10, 1.0 - 1e-10)
        pdf = beta_dist.pdf(x_scaled, alpha, beta)
        mx = pdf.max()
        if mx > 0:
            pdf = pdf / mx
        return pdf

    def _chebyshev_coefficients(
        self, alpha: float, beta: float, order: int,
    ) -> np.ndarray:
        """Fit Chebyshev polynomial coefficients to approximate the Beta filter.

        The filter h(λ) ≈ Σ_k c_k T_k(λ̃) where λ̃ = λ - 1 maps [0,2] → [-1,1].
        """
        # Sample the filter on Chebyshev nodes
        n_sample = max(order * 4, 64)
        # Chebyshev nodes on [-1, 1]
        nodes = np.cos(np.pi * (2 * np.arange(n_sample) + 1) / (2 * n_sample))
        # Map to [0, 2]
        lambdas = nodes + 1.0
        h_values = self._beta_pdf(lambdas, alpha, beta)

        # Fit coefficients via discrete cosine transform
        coeffs = np.zeros(order + 1)
        for k in range(order + 1):
            Tk = np.cos(k * np.arccos(nodes))
            coeffs[k] = 2.0 / n_sample * np.dot(h_values, Tk)
        coeffs[0] /= 2.0
        return coeffs

    def filter_signal(
        self,
        x: np.ndarray,
        L: sparse.csr_matrix,
        band: int,
    ) -> np.ndarray:
        """Apply one band-pass filter to signal x using Chebyshev recursion.

        h(L) x ≈ Σ_k c_k T_k(L̃) x  where L̃ = L - I.
        This avoids eigendecomposition — O(k × nnz(L)) per filter.
        """
        alpha, beta = self.filter_params[band]
        coeffs = self._chebyshev_coefficients(alpha, beta, self.polynomial_order)

        n = L.shape[0]
        x = x.flatten().astype(float)

        # L̃ = L - I (maps eigenvalues from [0,2] to [-1,1])
        L_tilde = L - sparse.eye(n, format="csr")

        # Chebyshev recursion: T_0(L̃)x = x, T_1(L̃)x = L̃x, T_k = 2L̃T_{k-1} - T_{k-2}
        T_prev = x.copy()             # T_0 x
        T_curr = L_tilde @ x          # T_1 x
        result = coeffs[0] * T_prev
        if len(coeffs) > 1:
            result += coeffs[1] * T_curr

        for k in range(2, len(coeffs)):
            T_next = 2.0 * (L_tilde @ T_curr) - T_prev
            result += coeffs[k] * T_next
            T_prev = T_curr
            T_curr = T_next

        return result

    def multi_scale_features(
        self,
        X: np.ndarray,
        L: sparse.csr_matrix,
    ) -> np.ndarray:
        """Apply all band-pass filters to feature matrix X.

        X: (n, d) node features
        Returns: (n, d × n_bands) — concatenated filtered features per band.
        """
        if X.ndim == 1:
            X = X.reshape(-1, 1)

        n, d = X.shape
        outputs = []
        for band in range(self.n_bands):
            band_output = np.zeros((n, d))
            for col in range(d):
                band_output[:, col] = self.filter_signal(X[:, col], L, band)
            outputs.append(band_output)

        return np.hstack(outputs)  # (n, d * n_bands)


# ── Community detection + per-community analysis ──────────────────────────


def _leiden_or_louvain(g: nx.Graph, seed: int = 42) -> list[set]:
    """Leiden if available, else Louvain fallback."""
    if _LEIDEN_AVAILABLE and g.number_of_nodes() > 0:
        node_list = list(g.nodes())
        node_to_idx = {n: i for i, n in enumerate(node_list)}
        ig_edges = [(node_to_idx[u], node_to_idx[v]) for u, v in g.edges()
                    if u in node_to_idx and v in node_to_idx]
        ig_graph = ig.Graph(n=len(node_list), edges=ig_edges, directed=False)
        partition = leidenalg.find_partition(
            ig_graph, leidenalg.RBConfigurationVertexPartition, seed=seed,
        )
        return [{node_list[i] for i in comm} for comm in partition]
    else:
        und = g.to_undirected() if g.is_directed() else g
        return list(nx.community.louvain_communities(und, seed=seed))


@dataclass
class CommunitySpectralReport:
    """Spectral analysis of one community."""
    community_id: int
    size: int
    n_edges: int
    rayleigh_quotient: float
    high_freq_energy: float  # energy in upper half of spectrum
    spectral_gap: float  # λ_2 - λ_1 (algebraic connectivity indicator)
    has_anomaly: bool
    eigenvalues: np.ndarray = field(repr=False)
    sed: np.ndarray = field(repr=False)

    def to_dict(self) -> dict:
        return {
            "community_id": self.community_id,
            "size": self.size,
            "n_edges": self.n_edges,
            "rayleigh_quotient": round(self.rayleigh_quotient, 6),
            "high_freq_energy": round(self.high_freq_energy, 4),
            "spectral_gap": round(self.spectral_gap, 6),
            "has_anomaly": self.has_anomaly,
        }


@dataclass
class SpectralAnalysisReport:
    """Full spectral analysis across all communities."""
    n_communities: int
    anomalous_communities: int
    community_reports: list[CommunitySpectralReport]
    shift_result: SpectralShiftResult | None = None

    def to_dict(self) -> dict:
        return {
            "n_communities": self.n_communities,
            "anomalous_communities": self.anomalous_communities,
            "communities": [c.to_dict() for c in self.community_reports],
            "spectral_shift": self.shift_result.to_dict() if self.shift_result else None,
        }


def run_spectral_analysis(
    source: str = "synthetic",
    anomaly_threshold: float = 0.15,
) -> SpectralAnalysisReport:
    """End-to-end spectral analysis pipeline.

    1. Load data, build graph.
    2. Leiden community detection.
    3. Per-community: Laplacian → eigendecompose → SED → Rayleigh quotient.
    4. Flag communities with anomalously high-frequency energy.
    5. If ground truth available, measure clean-vs-ring spectral shift.
    """
    from .data import load
    from .graph import build_graph

    ds = load(source)
    g_full = build_graph(ds)
    und = g_full.to_undirected()
    und.remove_edges_from(nx.selfloop_edges(und))

    # Community detection
    communities = _leiden_or_louvain(und)
    logger.info("Found %d communities", len(communities))

    # Analyze each community
    reports: list[CommunitySpectralReport] = []
    rayleigh_values: list[float] = []

    for idx, members in enumerate(sorted(communities, key=len, reverse=True)):
        if len(members) < 5:
            continue

        sub = und.subgraph(members).copy()
        n_edges = sub.number_of_edges()
        if n_edges < 2:
            continue

        node_list = sorted(sub.nodes())
        L, nodes = build_normalized_laplacian(sub, node_list)
        k = min(50, len(nodes) - 1)
        evals, evecs = compute_spectrum(L, k=k)

        # Signal: node degree
        deg = dict(sub.degree())
        x = np.array([deg.get(n, 0) for n in nodes], dtype=float)

        sed = spectral_energy_distribution(x, evals, evecs)
        rq = rayleigh_quotient(x, L)

        # High-frequency energy: upper half of spectrum
        half = len(sed) // 2
        hf_energy = float(sed[half:].sum())

        # Spectral gap
        gap = float(evals[1] - evals[0]) if len(evals) > 1 else 0.0

        rayleigh_values.append(rq)
        reports.append(CommunitySpectralReport(
            community_id=idx,
            size=len(members),
            n_edges=n_edges,
            rayleigh_quotient=rq,
            high_freq_energy=hf_energy,
            spectral_gap=gap,
            has_anomaly=False,  # set below
            eigenvalues=evals,
            sed=sed,
        ))

    # Flag anomalies: communities with Rayleigh quotient significantly above median
    if rayleigh_values:
        median_rq = float(np.median(rayleigh_values))
        for r in reports:
            r.has_anomaly = (r.rayleigh_quotient - median_rq) > anomaly_threshold

    n_anomalous = sum(1 for r in reports if r.has_anomaly)

    # If we have ground truth, build a clean-vs-ring comparison
    shift_result = None
    if "is_illicit" in ds.accounts.columns and "ring_id" in ds.accounts.columns:
        illicit = set(ds.accounts[ds.accounts["is_illicit"] == True]["account_id"])  # noqa
        clean_nodes = set(ds.accounts[ds.accounts["is_illicit"] != True]["account_id"])  # noqa

        # Pick a community with ring members and one without
        ring_comm = None
        clean_comm = None
        for members in sorted(communities, key=len, reverse=True):
            overlap = members & illicit
            if overlap and len(members) >= 10 and ring_comm is None:
                ring_comm = members
            elif not overlap and len(members) >= 10 and clean_comm is None:
                clean_comm = members
            if ring_comm and clean_comm:
                break

        if ring_comm and clean_comm:
            shift_result = measure_spectral_shift(
                und.subgraph(clean_comm).copy(),
                und.subgraph(ring_comm).copy(),
            )
            logger.info(
                "Spectral shift: clean RQ=%.4f, ring RQ=%.4f, shift=%.4f",
                shift_result.clean_rayleigh,
                shift_result.ring_rayleigh,
                shift_result.shift_magnitude,
            )

    report = SpectralAnalysisReport(
        n_communities=len(reports),
        anomalous_communities=n_anomalous,
        community_reports=reports,
        shift_result=shift_result,
    )

    logger.info(
        "Spectral analysis: %d communities, %d anomalous",
        report.n_communities, report.anomalous_communities,
    )
    return report


def export_sed_json(
    report: SpectralAnalysisReport,
    output_path: str | None = None,
) -> str:
    """Export spectral energy distributions as JSON for the Tone.js sonifier."""
    import json
    from .config import OUTPUT_DIR

    output_path = output_path or str(OUTPUT_DIR / "spectral_data.json")

    data = {
        "communities": [],
        "shift": report.shift_result.to_dict() if report.shift_result else None,
    }

    for cr in report.community_reports[:20]:  # cap for browser perf
        data["communities"].append({
            "id": cr.community_id,
            "size": cr.size,
            "rayleigh": cr.rayleigh_quotient,
            "anomaly": cr.has_anomaly,
            "eigenvalues": cr.eigenvalues.tolist(),
            "sed": cr.sed.tolist(),
        })

    with open(output_path, "w") as f:
        json.dump(data, f, indent=2)

    logger.info("Exported SED JSON to %s", output_path)
    return output_path
