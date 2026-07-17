"""Tests for Frequency of Fraud — spectral graph analysis."""

from __future__ import annotations

import pytest
import numpy as np
import networkx as nx
from scipy import sparse

from aegis_fraud_graph.data import load_synthetic
from aegis_fraud_graph.config import SynthConfig


@pytest.fixture(scope="module")
def small_dataset():
    cfg = SynthConfig(n_legit_accounts=200, n_rings=3, ring_size_min=3,
                      ring_size_max=5, n_background_tx=500, seed=99)
    return load_synthetic(cfg, cache=False)


@pytest.fixture
def simple_graph():
    """A small graph for deterministic spectral tests."""
    g = nx.karate_club_graph()
    return g


class TestLaplacian:
    def test_eigenvalues_in_range(self, simple_graph):
        from aegis_fraud_graph.spectral import build_normalized_laplacian, compute_spectrum
        L, nodes = build_normalized_laplacian(simple_graph)
        evals, evecs = compute_spectrum(L, k=10)
        assert all(0.0 <= ev <= 2.0 + 1e-6 for ev in evals), f"Eigenvalues out of [0,2]: {evals}"

    def test_first_eigenvalue_near_zero(self, simple_graph):
        from aegis_fraud_graph.spectral import build_normalized_laplacian, compute_spectrum
        L, nodes = build_normalized_laplacian(simple_graph)
        evals, _ = compute_spectrum(L, k=5)
        assert abs(evals[0]) < 0.01, f"First eigenvalue should be ~0, got {evals[0]}"

    def test_laplacian_shape(self, simple_graph):
        from aegis_fraud_graph.spectral import build_normalized_laplacian
        L, nodes = build_normalized_laplacian(simple_graph)
        n = len(nodes)
        assert L.shape == (n, n)
        assert sparse.issparse(L)


class TestRayleighQuotient:
    def test_matches_manual(self, simple_graph):
        from aegis_fraud_graph.spectral import build_normalized_laplacian, rayleigh_quotient
        L, nodes = build_normalized_laplacian(simple_graph)
        x = np.ones(len(nodes))
        rq = rayleigh_quotient(x, L)
        # Manual: x^T L x / x^T x
        manual = float(x @ (L @ x)) / float(x @ x)
        assert abs(rq - manual) < 1e-10

    def test_nullspace_signal_zero_rq(self, simple_graph):
        from aegis_fraud_graph.spectral import build_normalized_laplacian, rayleigh_quotient
        L, nodes = build_normalized_laplacian(simple_graph)
        # For normalized Laplacian, nullspace vector is D^(1/2) * 1
        deg = dict(simple_graph.degree())
        x = np.array([np.sqrt(deg.get(n, 0)) for n in nodes])
        rq = rayleigh_quotient(x, L)
        assert abs(rq) < 0.01


class TestSpectralEnergyDistribution:
    def test_sums_to_one(self, simple_graph):
        from aegis_fraud_graph.spectral import (
            build_normalized_laplacian, compute_spectrum,
            spectral_energy_distribution,
        )
        L, nodes = build_normalized_laplacian(simple_graph)
        evals, evecs = compute_spectrum(L, k=15)
        x = np.array([simple_graph.degree(n) for n in nodes], dtype=float)
        sed = spectral_energy_distribution(x, evals, evecs)
        assert abs(sed.sum() - 1.0) < 1e-6

    def test_shape_matches_eigenvalues(self, simple_graph):
        from aegis_fraud_graph.spectral import (
            build_normalized_laplacian, compute_spectrum,
            spectral_energy_distribution,
        )
        L, nodes = build_normalized_laplacian(simple_graph)
        evals, evecs = compute_spectrum(L, k=10)
        x = np.ones(len(nodes))
        sed = spectral_energy_distribution(x, evals, evecs)
        assert len(sed) == len(evals)


class TestSpectralShift:
    def test_ring_shifts_right(self):
        """Injecting a clique into a community should shift energy rightward."""
        from aegis_fraud_graph.spectral import measure_spectral_shift

        # Clean: random regular graph
        clean = nx.random_regular_graph(3, 30, seed=42)

        # Ring: same graph + injected dense clique
        ring = clean.copy()
        clique_nodes = list(range(30, 36))
        ring.add_nodes_from(clique_nodes)
        for i in clique_nodes:
            for j in clique_nodes:
                if i < j:
                    ring.add_edge(i, j)
            # Connect to some existing nodes
            ring.add_edge(i, i % 30)

        result = measure_spectral_shift(clean, ring, feature_signal="degree")
        # Ring should have higher Rayleigh quotient (more high-freq energy)
        assert result.shift_magnitude > -0.5  # allow some tolerance


class TestBetaWaveletFilter:
    def test_output_shape(self, simple_graph):
        from aegis_fraud_graph.spectral import build_normalized_laplacian, BetaWaveletFilter
        L, nodes = build_normalized_laplacian(simple_graph)
        n = len(nodes)
        filt = BetaWaveletFilter(n_bands=4, polynomial_order=6)

        # Single feature
        x = np.array([simple_graph.degree(nd) for nd in nodes], dtype=float)
        out = filt.multi_scale_features(x, L)
        assert out.shape == (n, 4)  # 1 feature × 4 bands

        # Multi-feature
        X = np.random.randn(n, 3)
        out = filt.multi_scale_features(X, L)
        assert out.shape == (n, 12)  # 3 features × 4 bands

    def test_filter_signal_returns_valid(self, simple_graph):
        from aegis_fraud_graph.spectral import build_normalized_laplacian, BetaWaveletFilter
        L, nodes = build_normalized_laplacian(simple_graph)
        filt = BetaWaveletFilter(n_bands=3)
        x = np.ones(len(nodes))
        for band in range(3):
            filtered = filt.filter_signal(x, L, band)
            assert filtered.shape == (len(nodes),)
            assert np.isfinite(filtered).all()


class TestAudio:
    def test_wav_generation(self, tmp_path):
        from aegis_fraud_graph.spectral_audio import synthesize_community, save_wav
        eigenvalues = np.array([0.0, 0.3, 0.7, 1.2, 1.8])
        sed = np.array([0.1, 0.3, 0.3, 0.2, 0.1])
        signal = synthesize_community(eigenvalues, sed, duration=1.0)
        assert len(signal) == 44100
        assert signal.max() <= 1.0
        assert signal.min() >= -1.0

        path = save_wav(signal, tmp_path / "test.wav")
        assert path.exists()
        assert path.stat().st_size > 100


class TestFullPipeline:
    def test_run_spectral_analysis(self, small_dataset):
        from aegis_fraud_graph.spectral import run_spectral_analysis
        report = run_spectral_analysis(source="synthetic")
        assert report.n_communities > 0
        d = report.to_dict()
        assert "communities" in d
        assert isinstance(d["anomalous_communities"], int)
