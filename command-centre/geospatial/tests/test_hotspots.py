"""Hotspot clustering tests — the cross-domain hub detection must be exact."""

from aegis_geospatial import cluster_hotspots


def test_cross_domain_hub_detected():
    """Scam + counterfeit within 25km -> one cross-domain hub."""
    points = [
        {"type": "scam", "lat": 23.795, "lon": 86.803, "weight": 0.97, "district": "Jamtara"},
        {"type": "counterfeit", "lat": 23.79, "lon": 86.81, "weight": 0.91, "district": "Jamtara"},
    ]
    hubs = cluster_hotspots(points)
    assert len(hubs) == 1
    assert hubs[0].cross_domain is True
    assert hubs[0].domains == ["counterfeit", "scam"]
    assert hubs[0].district == "Jamtara"


def test_distant_points_do_not_cluster():
    """Chennai and Mumbai are ~1000km apart -> no hub."""
    points = [
        {"type": "scam", "lat": 13.08, "lon": 80.27},
        {"type": "counterfeit", "lat": 18.93, "lon": 72.83},
    ]
    assert cluster_hotspots(points) == []


def test_single_domain_cluster_not_flagged_cross_domain():
    points = [
        {"type": "scam", "lat": 23.79, "lon": 86.80},
        {"type": "scam", "lat": 23.80, "lon": 86.81},
        {"type": "scam", "lat": 23.81, "lon": 86.79},
    ]
    hubs = cluster_hotspots(points)
    assert len(hubs) == 1
    assert hubs[0].cross_domain is False


def test_cross_domain_hubs_sort_first():
    points = [
        # big single-domain cluster (higher intensity)
        {"type": "scam", "lat": 28.6, "lon": 77.2, "weight": 1.0},
        {"type": "scam", "lat": 28.61, "lon": 77.21, "weight": 1.0},
        {"type": "scam", "lat": 28.62, "lon": 77.22, "weight": 1.0},
        # small cross-domain cluster far away
        {"type": "scam", "lat": 23.79, "lon": 86.80, "weight": 0.5},
        {"type": "counterfeit", "lat": 23.80, "lon": 86.81, "weight": 0.5},
    ]
    hubs = cluster_hotspots(points)
    assert len(hubs) == 2
    assert hubs[0].cross_domain is True  # cross-domain outranks raw intensity


def test_tier_coordinated_requires_all_three_domains():
    """Only scam + counterfeit + fraud_ring together = a 'coordinated' hub."""
    points = [
        {"type": "scam", "lat": 23.79, "lon": 86.80, "weight": 0.9},
        {"type": "counterfeit", "lat": 23.80, "lon": 86.81, "weight": 0.9},
        {"type": "fraud_ring", "lat": 23.81, "lon": 86.79, "weight": 0.9},
    ]
    hubs = cluster_hotspots(points)
    assert len(hubs) == 1
    assert hubs[0].tier == "coordinated"


def test_tier_two_domains_is_multi_signal_not_coordinated():
    """A 2-domain overlap (scam + ring) is 'multi_signal', NOT 'coordinated' —
    accuracy over drama: the badge must not overstate what is present."""
    points = [
        {"type": "scam", "lat": 27.55, "lon": 76.63, "weight": 0.9},
        {"type": "fraud_ring", "lat": 27.56, "lon": 76.64, "weight": 0.9},
    ]
    hubs = cluster_hotspots(points)
    assert len(hubs) == 1
    assert hubs[0].cross_domain is True  # still cross-domain (legacy field)
    assert hubs[0].tier == "multi_signal"


def test_tier_single_domain_is_none():
    points = [
        {"type": "fraud_ring", "lat": 27.22, "lon": 77.49},
        {"type": "fraud_ring", "lat": 27.23, "lon": 77.50},
    ]
    hubs = cluster_hotspots(points)
    assert hubs[0].tier is None


def test_coordinated_outranks_bigger_multi_signal():
    """A fully coordinated (3-domain) hub sorts ahead of a larger 2-domain hub."""
    points = [
        # large 2-domain cluster (higher intensity)
        {"type": "scam", "lat": 28.6, "lon": 77.2, "weight": 1.0},
        {"type": "scam", "lat": 28.61, "lon": 77.21, "weight": 1.0},
        {"type": "fraud_ring", "lat": 28.62, "lon": 77.22, "weight": 1.0},
        # smaller 3-domain (coordinated) cluster far away
        {"type": "scam", "lat": 23.79, "lon": 86.80, "weight": 0.4},
        {"type": "counterfeit", "lat": 23.80, "lon": 86.81, "weight": 0.4},
        {"type": "fraud_ring", "lat": 23.81, "lon": 86.79, "weight": 0.4},
    ]
    hubs = cluster_hotspots(points)
    assert hubs[0].tier == "coordinated"  # coordinated leads despite lower intensity
