"""Unit tests for AIS trajectory analysis, spoofing, and suspicion scoring."""

import pytest
from src.ais_analysis.traffic_filter import AISTrafficFilter
from src.ais_analysis.spoofing_detector import SpoofingDetector
from src.ais_analysis.suspicion_scorer import SuspicionScorer
from src.utils.geo_helpers import haversine_distance_km, calculate_bearing_deg


def test_ais_filter_initialization():
    """Verify AISTrafficFilter instantiates."""
    filter_engine = AISTrafficFilter()
    assert filter_engine.ais_data_path is None


def test_spoofing_detector_speed_threshold():
    """Verify max plausible speed parameter."""
    detector = SpoofingDetector(max_realistic_speed_knots=35.0)
    assert detector.max_speed == 35.0


def test_suspicion_scorer_weights_sum_to_one():
    """Verify attribution scoring weights normalize correctly."""
    scorer = SuspicionScorer()
    total_weight = scorer.w_prox + scorer.w_type + scorer.w_gap + scorer.w_draft
    assert abs(total_weight - 1.0) < 1e-6


def test_geo_helpers():
    """Verify basic geodesic calculations."""
    # Distance between London (51.5074, -0.1278) and Paris (48.8566, 2.3522) ~ 343 km
    dist = haversine_distance_km(51.5074, -0.1278, 48.8566, 2.3522)
    assert 340.0 < dist < 350.0

    # Bearing due north
    bearing = calculate_bearing_deg(0.0, 0.0, 1.0, 0.0)
    assert abs(bearing - 0.0) < 1e-3
