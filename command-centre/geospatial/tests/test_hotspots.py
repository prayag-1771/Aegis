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
