"""Unit tests for AIS kinematics, trajectory intersection, attribution scoring, and counterfactuals."""

import numpy as np
import pandas as pd
import pytest
from pathlib import Path
from shapely.geometry import Polygon

from src.ais_analysis.kinematics import AISKinematicEngine, haversine_distance_meters, compute_turn_rate_deg_per_min
from src.ais_analysis.trajectory_intersection import TrajectoryIntersectionEngine
from src.ais_analysis.suspicion_scorer import SuspicionScorer, rank_suspect_vessels
from src.drift_model.environmental_interpolator import EnvironmentalInterpolator
from src.drift_model.counterfactual import CounterfactualTester

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ERA5_PATH = PROJECT_ROOT / "data" / "weather" / "era5_wind_mediterranean_case_study.nc"
OSCAR_PATH = PROJECT_ROOT / "data" / "ocean_currents" / "oscar_currents_final_20240823.nc"


def test_haversine_distance():
    """Verify haversine distance calculation."""
    # 1 degree of latitude at equator is ~111.19 km
    dist = haversine_distance_meters(0.0, 0.0, 0.0, 1.0)
    assert np.isclose(dist, 111195.0, rtol=0.01)


def test_turn_rate_calculation():
    """Verify angular turn rate in degrees per minute."""
    # Turn from 10 to 40 deg in 60 sec -> 30 deg/min
    rate = compute_turn_rate_deg_per_min(10.0, 40.0, 60.0)
    assert np.isclose(rate, 30.0)


def test_kinematic_engine_impossible_speed_flag():
    """Verify kinematic engine flags impossible speed as AIS INTEGRITY ANOMALY."""
    engine = AISKinematicEngine(max_speed_knots=45.0)
    df = pd.DataFrame([
        {"MMSI": 111, "BaseDateTime": "2024-08-23T01:00:00Z", "LAT": 34.0, "LON": 18.0, "SOG": 12.0, "COG": 45.0, "VesselName": "TEST"},
        {"MMSI": 111, "BaseDateTime": "2024-08-23T01:05:00Z", "LAT": 35.0, "LON": 19.0, "SOG": 75.0, "COG": 45.0, "VesselName": "TEST"},  # ~140 km in 5 min
    ])
    res = engine.analyze_trajectory(df)
    assert res["has_integrity_anomaly"] is True
    subtypes = [a["subtype"] for a in res["anomalies"]]
    assert "IMPOSSIBLE_SPEED" in subtypes


def test_trajectory_intersection():
    """Verify trajectory intersection engine detects segment crossing."""
    poly = Polygon([(18.0, 34.0), (18.5, 34.0), (18.5, 34.5), (18.0, 34.5)])
    df = pd.DataFrame([
        {"MMSI": 222, "BaseDateTime": "2024-08-23T00:00:00Z", "LAT": 33.8, "LON": 17.8, "SOG": 12.0, "COG": 45.0, "VesselName": "SHIP_A"},
        {"MMSI": 222, "BaseDateTime": "2024-08-23T02:00:00Z", "LAT": 34.7, "LON": 18.7, "SOG": 12.0, "COG": 45.0, "VesselName": "SHIP_A"},
    ])
    engine = TrajectoryIntersectionEngine(temporal_tolerance_seconds=3600.0)
    t_min = pd.to_datetime("2024-08-23T00:30:00Z").timestamp()
    t_max = pd.to_datetime("2024-08-23T01:30:00Z").timestamp()
    res = engine.evaluate_intersection(df, poly, (t_min, t_max))

    assert res["spatial_overlap"] is True
    assert res["temporal_overlap"] is True
    assert res["intersects"] is True


def test_attribution_scoring_multi_factor():
    """Verify multi-factor suspicion scoring returns components and explicit reasoning."""
    scorer = SuspicionScorer()
    profile = {
        "mmsi": 333,
        "vessel_name": "SUSPECT_TANKER",
        "vessel_type": 1004.0,  # Tanker
        "draft_change": -1.5,
        "intersection": {
            "spatial_overlap": True,
            "temporal_overlap": True,
            "min_distance_nm": 0.2,
            "crossing_type": "DIRECT_BROADCAST_CONTAINMENT",
            "residence_time_minutes": 25.0,
        },
        "kinematics": {"anomalies": []},
    }
    score_res = scorer.score_vessel(profile, {})
    assert score_res["composite_suspicion_score"] > 0.75
    assert score_res["attribution_decision"] == "PRIMARY_SUSPECT"
    assert "reasoning_summary" in score_res
    assert "spatial_compatibility" in score_res["evidence_breakdown"]


def test_counterfactual_tester():
    """Verify counterfactual forward simulation evaluates physical plausibility."""
    interp = EnvironmentalInterpolator(
        era5_path=str(ERA5_PATH),
        oscar_path=str(OSCAR_PATH),
        default_windage=0.03,
    )
    tester = CounterfactualTester(interpolator=interp, windage_factor=0.03)
    res = tester.test_candidate_release(
        candidate_release_coord=(18.35, 34.50),
        candidate_release_time="2024-08-23T06:00:00Z",
        observed_spill_geometry=(18.30, 34.45, 18.40, 34.55),
        observation_time="2024-08-23T09:41:12Z",
        num_particles=20,
    )
    assert res["valid"] is True
    assert res["centroid_offset_km"] < 10.0
    assert res["physical_plausibility_score"] > 0.5
    assert res["counterfactual_verdict"] in ("HIGH_PHYSICAL_CONSISTENCY", "MODERATE_PHYSICAL_CONSISTENCY")
