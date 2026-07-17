"""Tests for multi-modal route plausibility.

This scorer shipped untested and was tautological: plausibility was
`best_cost / route_cost`, so the cheapest candidate scored exactly 1.0 in
every query, by construction. Howrah (222 km) and Chennai (3190 km) both
scored 1.000 into Jamtara. These tests pin the properties that make the
number mean something, so the tautology cannot come back unnoticed.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from aegis_supply_trail.engine import _nearest_node_key, load_fir_corpus
from aegis_supply_trail.network import attach_access, build_network
from aegis_supply_trail.routes import plausible_routes

JAMTARA = (23.963, 86.804)
HOWRAH = (22.5839, 88.3424)
CHENNAI = (13.0827, 80.2707)
NEW_DELHI = (28.6432, 77.2194)


def _routes_from(net, fir, src, dst_key, k=4):
    src_key, _ = _nearest_node_key(net, src[0], src[1])
    return plausible_routes(net, src_key, dst_key, k=k, fir_corpus=fir)


def _fixture():
    net = build_network()
    fir = load_fir_corpus()
    dst = attach_access(net, "Jamtara", *JAMTARA)
    return net, fir, dst


class TestPlausibilityIsAbsolute:
    def test_nearby_source_beats_distant_source(self):
        """The regression that started this: Howrah (222 km) and Chennai
        (3190 km) both scored 1.000. Distance must move the number."""
        net, fir, dst = _fixture()
        near = _routes_from(net, fir, HOWRAH, dst)[0]
        far = _routes_from(net, fir, CHENNAI, dst)[0]
        assert near["plausibility"] > far["plausibility"]

    def test_no_route_is_ever_certain(self):
        """A route is a hypothesis about how notes moved — nothing observed
        them moving. Capped at 0.9, and never 1.0 by construction."""
        net, fir, dst = _fixture()
        for src in (HOWRAH, CHENNAI, NEW_DELHI):
            for r in _routes_from(net, fir, src, dst):
                assert r["plausibility"] <= 0.9

    def test_top_route_is_not_automatically_perfect(self):
        """The old scorer made rank-1 score 1.0 every time. The top route must
        earn its number from distance/mode/FIR, not from being rank 1."""
        net, fir, dst = _fixture()
        tops = [
            _routes_from(net, fir, src, dst)[0]["plausibility"]
            for src in (HOWRAH, CHENNAI, NEW_DELHI)
        ]
        assert len(set(tops)) > 1, f"all top routes scored identically: {tops}"

    def test_air_is_penalised_against_rail(self):
        """Rail is the documented primary channel; air is heavily screened
        (BCAS). Same source, so only mode separates them."""
        net, fir, dst = _fixture()
        routes = _routes_from(net, fir, NEW_DELHI, dst)
        air = next((r for r in routes if "air" in r["modes"]), None)
        rail = next((r for r in routes if r["modes"] == ["rail"]), None)
        if air and rail:
            assert air["plausibility"] < rail["plausibility"]

    def test_scores_are_comparable_across_queries(self):
        """Absolute, not relative: the same physical route must score the same
        regardless of which other candidates happened to be found alongside it.
        Howrah and Kolkata are the same origin city, so they must agree."""
        net, fir, dst = _fixture()
        howrah = _routes_from(net, fir, HOWRAH, dst)[0]
        kolkata = _routes_from(net, fir, (22.5726, 88.3639), dst)[0]
        assert howrah["plausibility"] == kolkata["plausibility"]

    def test_plausibility_in_unit_range(self):
        net, fir, dst = _fixture()
        for src in (HOWRAH, CHENNAI, NEW_DELHI):
            for r in _routes_from(net, fir, src, dst):
                assert 0.0 <= r["plausibility"] <= 1.0


class TestRouteEvidence:
    def test_fir_refs_are_real_corpus_entries(self):
        """passes_fir must cite the corpus, never invent a reference."""
        net, fir, dst = _fixture()
        known = {f.ref for f in fir}
        for r in _routes_from(net, fir, HOWRAH, dst):
            for ref in r["passes_fir"]:
                assert ref in known, f"fabricated FIR ref: {ref}"

    def test_legs_are_contiguous(self):
        """Each leg must start where the previous ended — a route with a jump
        in it is not a route."""
        net, fir, dst = _fixture()
        for r in _routes_from(net, fir, NEW_DELHI, dst):
            legs = r["legs"]
            for a, b in zip(legs, legs[1:]):
                assert a["to"] == b["from"], f"gap: {a['to']} -> {b['from']}"
