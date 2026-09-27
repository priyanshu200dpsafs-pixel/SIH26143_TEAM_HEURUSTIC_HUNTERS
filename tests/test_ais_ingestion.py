"""
Unit and Integration Tests for Real AIS Ingestion Architecture (Phase 5).

Deterministic tests covering:
1. AIS observation normalization
2. Malformed observation rejection
3. Duplicate removal
4. Chronological sorting
5. Gap preservation
6. Track reconstruction
7. Spatial filtering
8. Temporal filtering
9. Live provider NOT_CONFIGURED handling
10. Provider authentication error handling
11. Replay provider compatibility
12. Incident-specific candidate extraction
13. Provenance correctness (REAL/LIVE vs SIMULATED/REPLAY)
14. Kinematic engine integration
15. Attribution scoring integration
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import numpy as np
import pandas as pd
import pytest
from shapely.geometry import Polygon

from src.ingestion.ais.models import AISObservation, VesselTrack, ProviderStatus
from src.ingestion.ais.base_provider import AISProvider
from src.ingestion.ais.replay_provider import ReplayAISProvider
from src.ingestion.ais.live_provider import LiveAISProvider
from src.ingestion.ais.live_buffer import LiveAISBuffer
from src.ingestion.ais.quality import generate_quality_report
from src.ais_analysis.track_builder import (
    normalize_raw_observation,
    sort_by_timestamp,
    deduplicate,
    merge_observations,
    build_track,
    interpolate_for_analysis,
)
from src.ais_analysis.traffic_filter import filter_vessels_in_spatiotemporal_window, AISTrafficFilter
from src.ais_analysis.kinematics import AISKinematicEngine
from src.ais_analysis.suspicion_scorer import SuspicionScorer
from src.pipeline.incident_pipeline import run_incident_pipeline
from src.pipeline.models import ProvenanceType


def test_1_ais_observation_normalization():
    """1. Verify normalization of raw dictionary with varied key conventions."""
    raw = {
        "MMSI": "240123000",
        "BaseDateTime": "2024-08-23 09:30:00",
        "LAT": "34.5501",
        "LON": "18.4201",
        "SOG": 12.4,
        "COG": 275.0,
        "Heading": 273,
        "VesselName": "PACIFIC_VOYAGER",
        "VesselType": "80",  # Tanker
        "Draft": 11.2,
    }
    obs = normalize_raw_observation(raw, source="TestFeed", data_status="REAL", mode="LIVE")
    assert obs is not None
    assert obs.mmsi == "240123000"
    assert obs.timestamp == "2024-08-23T09:30:00Z"
    assert np.isclose(obs.latitude, 34.5501)
    assert np.isclose(obs.longitude, 18.4201)
    assert obs.sog == 12.4
    assert obs.cog == 275.0
    assert obs.heading == 273.0
    assert obs.ship_name == "PACIFIC_VOYAGER"
    assert obs.ship_type == "80"
    assert obs.draft == 11.2
    assert obs.source == "TestFeed"
    assert obs.data_status == "REAL"
    assert obs.mode == "LIVE"


def test_2_malformed_observation_rejection():
    """2. Verify rejection of coordinates out of bounds, negative SOG, bad timestamps."""
    # Latitude > 90
    bad_lat = {"mmsi": "123", "timestamp": "2024-08-23T09:00:00Z", "lat": 95.0, "lon": 18.0}
    assert normalize_raw_observation(bad_lat) is None

    # Longitude < -180
    bad_lon = {"mmsi": "123", "timestamp": "2024-08-23T09:00:00Z", "lat": 34.0, "lon": -185.0}
    assert normalize_raw_observation(bad_lon) is None

    # Negative SOG
    bad_sog = {"mmsi": "123", "timestamp": "2024-08-23T09:00:00Z", "lat": 34.0, "lon": 18.0, "sog": -2.5}
    assert normalize_raw_observation(bad_sog) is None

    # Unparseable timestamp
    bad_time = {"mmsi": "123", "timestamp": "invalid-date-string", "lat": 34.0, "lon": 18.0}
    assert normalize_raw_observation(bad_time) is None

    # Missing MMSI
    bad_mmsi = {"timestamp": "2024-08-23T09:00:00Z", "lat": 34.0, "lon": 18.0}
    assert normalize_raw_observation(bad_mmsi) is None


def test_3_duplicate_removal():
    """3. Verify identical observations (same MMSI, timestamp, coords) are deduplicated."""
    obs1 = AISObservation(mmsi="111", timestamp="2024-08-23T10:00:00Z", latitude=34.0, longitude=18.0, sog=10.0)
    obs2 = AISObservation(mmsi="111", timestamp="2024-08-23T10:00:00Z", latitude=34.0, longitude=18.0, sog=10.0)
    obs3 = AISObservation(mmsi="111", timestamp="2024-08-23T10:05:00Z", latitude=34.1, longitude=18.1, sog=10.0)

    deduped = deduplicate([obs1, obs2, obs3])
    assert len(deduped) == 2
    assert deduped[0].timestamp == "2024-08-23T10:00:00Z"
    assert deduped[1].timestamp == "2024-08-23T10:05:00Z"


def test_4_chronological_sorting():
    """4. Verify observation sorting in ascending time order."""
    obs1 = AISObservation(mmsi="111", timestamp="2024-08-23T12:00:00Z", latitude=34.2, longitude=18.2)
    obs2 = AISObservation(mmsi="111", timestamp="2024-08-23T09:00:00Z", latitude=34.0, longitude=18.0)
    obs3 = AISObservation(mmsi="111", timestamp="2024-08-23T10:30:00Z", latitude=34.1, longitude=18.1)

    sorted_obs = sort_by_timestamp([obs1, obs2, obs3])
    assert [o.timestamp for o in sorted_obs] == [
        "2024-08-23T09:00:00Z",
        "2024-08-23T10:30:00Z",
        "2024-08-23T12:00:00Z",
    ]


def test_5_gap_preservation():
    """5. Verify gaps are recorded and interpolation refuses to manufacture positions in large gaps."""
    # 55-minute gap between 10:00 and 10:55
    obs1 = AISObservation(mmsi="999", timestamp="2024-08-23T10:00:00Z", latitude=34.0, longitude=18.0, sog=12.0)
    obs2 = AISObservation(mmsi="999", timestamp="2024-08-23T10:55:00Z", latitude=34.5, longitude=18.5, sog=12.0)

    track = build_track([obs1, obs2], max_gap_minutes=30.0)
    assert len(track.gaps) == 1
    gap = track.gaps[0]
    assert gap.mmsi == "999"
    assert gap.gap_start == "2024-08-23T10:00:00Z"
    assert gap.gap_end == "2024-08-23T10:55:00Z"
    assert gap.gap_duration_minutes == 55.0

    # Attempt interpolation inside the 55-min gap
    interp = interpolate_for_analysis(track, target_timestamps=["2024-08-23T10:30:00Z"], max_gap_minutes=30.0)
    # Must refuse to manufacture coordinates across large gap
    assert len(interp) == 0


def test_6_track_reconstruction():
    """6. Verify VesselTrack construction and conversion to kinematics-ready DataFrame."""
    obs_list = [
        AISObservation(mmsi="222333444", timestamp="2024-08-23T08:00:00Z", latitude=34.0, longitude=18.0, sog=11.0, cog=45.0, ship_name="OCEAN_STAR", ship_type="Cargo"),
        AISObservation(mmsi="222333444", timestamp="2024-08-23T08:15:00Z", latitude=34.1, longitude=18.1, sog=11.5, cog=45.0, ship_name="OCEAN_STAR", ship_type="Cargo"),
    ]
    track = build_track(obs_list)
    assert track.mmsi == "222333444"
    assert track.point_count == 2
    assert track.start_time == "2024-08-23T08:00:00Z"
    assert track.end_time == "2024-08-23T08:15:00Z"

    df = track.to_dataframe()
    assert isinstance(df, pd.DataFrame)
    assert len(df) == 2
    assert set(["MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "VesselName"]).issubset(df.columns)


def test_7_spatial_filtering():
    """7. Verify spatial filtering retains only points inside bounding polygon."""
    poly = Polygon([(18.0, 34.0), (18.5, 34.0), (18.5, 34.5), (18.0, 34.5)])
    df = pd.DataFrame([
        {"MMSI": 1, "BaseDateTime": "2024-08-23T09:00:00Z", "LAT": 34.2, "LON": 18.2, "SOG": 10.0, "COG": 0.0},  # INSIDE
        {"MMSI": 2, "BaseDateTime": "2024-08-23T09:00:00Z", "LAT": 35.5, "LON": 19.5, "SOG": 10.0, "COG": 0.0},  # OUTSIDE
    ])

    filtered = filter_vessels_in_spatiotemporal_window(df, poly, start_utc="", end_utc="")
    assert len(filtered) == 1
    assert filtered["MMSI"].iloc[0] == 1


def test_8_temporal_filtering():
    """8. Verify LiveAISBuffer temporal window querying."""
    buffer = LiveAISBuffer(buffer_hours=48)
    buffer.add_observations([
        AISObservation(mmsi="1", timestamp="2024-08-23T06:00:00Z", latitude=34.0, longitude=18.0),
        AISObservation(mmsi="1", timestamp="2024-08-23T08:00:00Z", latitude=34.1, longitude=18.1),
        AISObservation(mmsi="1", timestamp="2024-08-23T11:00:00Z", latitude=34.2, longitude=18.2),
    ])

    # Window between 07:00 and 09:00
    res = buffer.query_observations(start_time_iso="2024-08-23T07:00:00Z", end_time_iso="2024-08-23T09:00:00Z")
    assert len(res) == 1
    assert res[0].timestamp == "2024-08-23T08:00:00Z"


def test_9_live_provider_not_configured():
    """9. Verify live provider reports NOT_CONFIGURED when credentials are absent."""
    provider = LiveAISProvider(api_url="", api_key="")
    assert provider.get_status() == ProviderStatus.NOT_CONFIGURED
    assert provider.is_configured() is False
    # Must return empty list, never fabricated synthetic data
    assert provider.get_positions() == []


def test_10_provider_authentication_error():
    """10. Verify provider reports AUTH_REQUIRED on HTTP 401/403."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_session.get.return_value = mock_resp

    provider = LiveAISProvider(
        api_url="https://api.example-ais.com/v1",
        api_key="invalid_key_xyz",
        session=mock_session,
    )
    status = provider.get_status()
    assert status == ProviderStatus.AUTH_REQUIRED


def test_11_replay_provider_compatibility():
    """11. Verify ReplayAISProvider preserves SIMULATED/REPLAY provenance and loads fixtures."""
    provider = ReplayAISProvider()
    assert provider.data_status == "SIMULATED"
    assert provider.mode == "REPLAY"
    assert provider.get_status() == ProviderStatus.CONNECTED

    scenarios = provider.get_available_scenarios()
    assert len(scenarios) > 0

    df = provider.load_ais_data(scenario_id=1)
    assert not df.empty
    assert "MMSI" in df.columns

    # Unified interface positions
    positions = provider.get_positions(scenario_id=1)
    assert len(positions) > 0
    assert all(p.data_status == "SIMULATED" for p in positions)
    assert all(p.mode == "REPLAY" for p in positions)


def test_12_incident_specific_candidate_extraction():
    """12. Verify buffer extracts candidate tracks intersecting origin polygon during release window."""
    buffer = LiveAISBuffer(buffer_hours=48, minimum_track_points=2)
    poly = Polygon([(18.1, 34.3), (18.6, 34.3), (18.6, 34.7), (18.1, 34.7)])

    # Vessel A intersects
    vessel_a = [
        AISObservation(mmsi="100", timestamp="2024-08-23T06:00:00Z", latitude=34.4, longitude=18.2),
        AISObservation(mmsi="100", timestamp="2024-08-23T07:00:00Z", latitude=34.5, longitude=18.4),
    ]
    # Vessel B is far away
    vessel_b = [
        AISObservation(mmsi="200", timestamp="2024-08-23T06:00:00Z", latitude=38.0, longitude=22.0),
        AISObservation(mmsi="200", timestamp="2024-08-23T07:00:00Z", latitude=38.1, longitude=22.1),
    ]

    buffer.add_observations(vessel_a + vessel_b)

    candidates = buffer.get_candidate_tracks_for_incident(
        spill_time_iso="2024-08-23T09:41:12Z",
        release_window_start_iso="2024-08-23T05:00:00Z",
        origin_polygon=poly,
    )
    mmsis = [c.mmsi for c in candidates]
    assert "100" in mmsis
    assert "200" not in mmsis


def test_13_provenance_correctness(tmp_path):
    """13. Verify automatic provenance assignment: REAL/LIVE for live provider vs SIMULATED for replay."""
    # Mock Live Provider
    class MockLiveProvider(AISProvider):
        @property
        def data_status(self) -> str:
            return "REAL"
        @property
        def mode(self) -> str:
            return "LIVE"
        def get_status(self) -> ProviderStatus:
            return ProviderStatus.CONNECTED
        def get_positions(self, **kwargs):
            return [
                AISObservation(mmsi="999888", timestamp="2024-08-23T07:00:00Z", latitude=34.45, longitude=18.35, sog=12.0, cog=45.0, ship_name="REAL_VESSEL", ship_type="Tanker", source="LiveFeed", data_status="REAL", mode="LIVE"),
                AISObservation(mmsi="999888", timestamp="2024-08-23T08:00:00Z", latitude=34.50, longitude=18.40, sog=12.0, cog=45.0, ship_name="REAL_VESSEL", ship_type="Tanker", source="LiveFeed", data_status="REAL", mode="LIVE"),
            ]
        def get_track(self, mmsi, **kwargs):
            return None
        def get_tracks(self, **kwargs):
            # Return real-labeled track with 2 points
            obs = [
                AISObservation(mmsi="999888", timestamp="2024-08-23T07:00:00Z", latitude=34.45, longitude=18.35, sog=12.0, cog=45.0, ship_name="REAL_VESSEL", ship_type="Tanker", source="LiveFeed", data_status="REAL", mode="LIVE"),
                AISObservation(mmsi="999888", timestamp="2024-08-23T08:00:00Z", latitude=34.50, longitude=18.40, sog=12.0, cog=45.0, ship_name="REAL_VESSEL", ship_type="Tanker", source="LiveFeed", data_status="REAL", mode="LIVE"),
            ]
            return [build_track(obs)]
        def get_vessel_static_data(self, mmsi):
            return {"mmsi": str(mmsi), "data_status": "REAL", "mode": "LIVE"}

    live_prov = MockLiveProvider()
    assert live_prov.data_status == "REAL"
    assert live_prov.mode == "LIVE"

    # Execute incident pipeline with mock live provider
    sample_chip = "data/sar_images/krestenitis_dataset/test/images/Oil (1007).jpg"
    scene_meta = {
        "incident_id": "INC_LIVE_AIS_TEST",
        "product_id": "S1_LIVE_AIS",
        "image_path": sample_chip,
        "acquisition_time": "2024-08-23T09:41:12Z",
        "bounding_box": [18.1, 34.3, 18.6, 34.7],
    }

    inc = run_incident_pipeline(
        scene_metadata=scene_meta,
        ais_provider=live_prov,
        output_dir=str(tmp_path),
        allow_low_confidence=True,
    )

    assert inc.reality_labels["AIS"] == "REAL LIVE (Maritime Transponder Stream)"
    assert len(inc.candidates) > 0
    candidate = inc.candidates[0]
    assert candidate.provenance == ProvenanceType.REAL.value
    assert candidate.consistency_tier in ("HIGH-CONSISTENCY CANDIDATE", "MODERATE-CONSISTENCY CANDIDATE", "LOW-CONSISTENCY CANDIDATE")


def test_14_kinematic_integration():
    """14. Verify reconstructed track DataFrame seamlessly feeds into AISKinematicEngine."""
    engine = AISKinematicEngine()
    obs = [
        AISObservation(mmsi="555", timestamp="2024-08-23T01:00:00Z", latitude=34.0, longitude=18.0, sog=10.0, cog=45.0),
        AISObservation(mmsi="555", timestamp="2024-08-23T01:10:00Z", latitude=34.05, longitude=18.05, sog=10.2, cog=45.0),
    ]
    track = build_track(obs)
    df = track.to_dataframe()

    res = engine.analyze_trajectory(df)
    assert "max_speed_knots" in res
    assert "total_records" in res
    assert "anomalies" in res
    assert res["has_integrity_anomaly"] is False


def test_15_attribution_scoring_integration():
    """15. Verify candidate scored from VesselTrack receives explainable multi-factor attribution."""
    scorer = SuspicionScorer()
    obs = [
        AISObservation(mmsi="777", timestamp="2024-08-23T06:00:00Z", latitude=34.45, longitude=18.35, sog=12.0, cog=45.0, ship_name="SUSPECT_CRUDE", ship_type="Tanker"),
        AISObservation(mmsi="777", timestamp="2024-08-23T07:00:00Z", latitude=34.50, longitude=18.40, sog=12.0, cog=45.0, ship_name="SUSPECT_CRUDE", ship_type="Tanker"),
    ]
    track = build_track(obs)
    df = track.to_dataframe()

    profile = {
        "mmsi": 777,
        "vessel_name": "SUSPECT_CRUDE",
        "vessel_type": 1004.0,
        "draft_change": 0.0,
        "intersection": {
            "spatial_overlap": True,
            "temporal_overlap": True,
            "min_distance_nm": 0.4,
            "crossing_type": "INTERSECTING_VOYAGE",
            "residence_time_minutes": 40.0,
        },
        "kinematics": {"anomalies": []},
    }

    score_res = scorer.score_vessel(profile, {})
    assert score_res["composite_suspicion_score"] >= 0.5
    assert score_res["attribution_decision"] in ("PRIMARY_SUSPECT", "PLAUSIBLE_CANDIDATE")
    assert "evidence_breakdown" in score_res
