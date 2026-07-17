"""Ghost Ring privacy layer — differential privacy on embeddings.

Before boundary embeddings are shared with the central matcher, calibrated
Gaussian noise is added to satisfy (ε, δ)-differential privacy.  This means
a single node's participation (or absence) in the local training set changes
each published embedding coordinate by at most a bounded amount, with high
probability.

Phase 1: Gaussian mechanism on the raw 64-dim embedding vector.
Phase 2 (deferred): SMPC via CrypTen for secure matching without a trusted
central matcher.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class PrivacyReport:
    """Privacy-utility tradeoff results."""
    epsilon: float
    delta: float
    noise_scale: float
    original_matching_precision: float
    noisy_matching_precision: float
    precision_degradation: float

    def to_dict(self) -> dict:
        return {
            "epsilon": self.epsilon,
            "delta": self.delta,
            "noise_scale": round(self.noise_scale, 6),
            "original_matching_precision": round(self.original_matching_precision, 4),
            "noisy_matching_precision": round(self.noisy_matching_precision, 4),
            "precision_degradation": round(self.precision_degradation, 4),
        }


def _l2_sensitivity(embedding_dim: int = 64) -> float:
    """L2 sensitivity of the GraphSAGE embedding function.

    Conservative bound: the embedding is the output of a ReLU network with
    bounded input features (normalized to [0,1]).  The final layer's L2 norm
    is bounded by the product of spectral norms of the weight matrices.
    In practice we clip embeddings to unit norm before publishing, so
    sensitivity = 2 (worst case: one node flips from +1 to -1 in every dim
    after normalization ⇒ ‖e₁ - e₂‖₂ ≤ 2).
    """
    return 2.0


def _gaussian_noise_scale(
    sensitivity: float,
    epsilon: float,
    delta: float,
) -> float:
    """Compute σ for the Gaussian mechanism: σ = sensitivity × √(2 ln(1.25/δ)) / ε."""
    return sensitivity * np.sqrt(2.0 * np.log(1.25 / delta)) / epsilon


def add_dp_noise(
    embedding: np.ndarray,
    epsilon: float = 1.0,
    delta: float = 1e-5,
    rng: np.random.Generator | None = None,
) -> np.ndarray:
    """Add calibrated Gaussian noise to a single embedding vector.

    The embedding is first L2-normalized (clipped to the unit ball) so the
    sensitivity bound holds, then noise is drawn from N(0, σ²I) where σ is
    set by the Gaussian mechanism.

    Args:
        embedding: raw 64-dim embedding from GraphSAGE.
        epsilon: privacy budget (smaller = more private, noisier).
        delta: failure probability.
        rng: numpy random generator for reproducibility.

    Returns:
        Noisy embedding (same shape).
    """
    rng = rng or np.random.default_rng()
    # Clip to unit ball (ensures sensitivity bound)
    norm = np.linalg.norm(embedding)
    if norm > 1.0:
        embedding = embedding / norm

    sigma = _gaussian_noise_scale(_l2_sensitivity(), epsilon, delta)
    noise = rng.normal(0, sigma, size=embedding.shape)
    return embedding + noise


def add_dp_noise_to_boundary_infos(
    boundary_infos: list,
    epsilon: float = 1.0,
    delta: float = 1e-5,
    seed: int = 42,
) -> list:
    """Apply DP noise to all boundary info embeddings in-place.

    Args:
        boundary_infos: list of BoundaryInfo objects (from ghost_ring.py).
        epsilon: privacy budget.
        delta: failure probability.
        seed: random seed for reproducibility.

    Returns:
        The same list with noisy embeddings.
    """
    rng = np.random.default_rng(seed)
    for info in boundary_infos:
        info.embedding = add_dp_noise(info.embedding, epsilon, delta, rng)

    logger.info(
        "Applied (%.1f, %.0e)-DP noise to %d boundary embeddings",
        epsilon, delta, len(boundary_infos),
    )
    return boundary_infos


def sweep_privacy_utility(
    run_matching_fn,
    all_boundary_infos: list[list],
    ground_truth_cross_edges: set[tuple[str, str]],
    epsilons: list[float] | None = None,
    delta: float = 1e-5,
) -> list[PrivacyReport]:
    """Sweep ε values and report matching precision degradation.

    Args:
        run_matching_fn: callable(boundary_infos) → list[MatchedEdge]
        all_boundary_infos: original (clean) boundary infos per bank
        ground_truth_cross_edges: set of (src, dst) true cross-partition edges
        epsilons: list of ε values to test (default: [0.1, 0.5, 1.0, 2.0, 5.0, 10.0])
        delta: DP delta parameter

    Returns:
        List of PrivacyReport for each ε.
    """
    import copy

    epsilons = epsilons or [0.1, 0.5, 1.0, 2.0, 5.0, 10.0]

    # Baseline: matching without noise
    original_matched = run_matching_fn(all_boundary_infos)
    original_precision = _matching_precision(original_matched, ground_truth_cross_edges)

    reports: list[PrivacyReport] = []
    for eps in epsilons:
        # Deep copy boundary infos and add noise
        noisy_infos = copy.deepcopy(all_boundary_infos)
        for bank_infos in noisy_infos:
            add_dp_noise_to_boundary_infos(bank_infos, epsilon=eps, delta=delta)

        noisy_matched = run_matching_fn(noisy_infos)
        noisy_precision = _matching_precision(noisy_matched, ground_truth_cross_edges)

        reports.append(PrivacyReport(
            epsilon=eps,
            delta=delta,
            noise_scale=_gaussian_noise_scale(_l2_sensitivity(), eps, delta),
            original_matching_precision=original_precision,
            noisy_matching_precision=noisy_precision,
            precision_degradation=original_precision - noisy_precision,
        ))

        logger.info(
            "ε=%.1f: matching precision %.4f → %.4f (degradation: %.4f)",
            eps, original_precision, noisy_precision,
            original_precision - noisy_precision,
        )

    return reports


def _matching_precision(
    matched_edges: list,
    ground_truth: set[tuple[str, str]],
) -> float:
    """Of matched edges, fraction that are real cross-partition edges."""
    if not matched_edges:
        return 0.0
    hits = sum(
        1 for m in matched_edges
        if (m.source_account, m.target_account) in ground_truth
        or (m.target_account, m.source_account) in ground_truth
    )
    return hits / len(matched_edges)
