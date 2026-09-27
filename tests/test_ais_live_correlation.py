"""
Deterministic Unit & Integration Tests for Phase 5B: Live AIS Correlation & Provider Switching.

Tests:
1. Live provider successful normalization
2. Real provenance assignment (REAL / LIVE)
3. Live buffer insertion
4. Live buffer expiration
5. Live candidate extraction
6. AIS coverage insufficiency (AIS_COVERAGE_INSUFFICIENT)
7. Provider rate limit (HTTP 429)
8. Provider timeout handling
9. Malformed live observation handling
10. Missing vessel metadata handling
11. Live-to-attribution integration
12. Replay/live provider configuration switching
Zero external network dependencies during pytest.
"""

from datetime import datetime, timezone, timedelta
from unittest.mock import MagicMock
import numpy as np
import pandas as pd
import pytest
import requests
from shapely.geometry import Polygon

from src.ingestion.ais.models import AISObservation, VesselTrack, ProviderStatus
from src.ingestion.ais.base_provider import AISProvider
from src.ingestion.ais.replay_provider import ReplayAISProvider
from src.ingestion.ais.live_provider import LiveAISProvider
from src.ingestion.ais.live_buffer import LiveAISBuffer
from src.ais_analysis.track_builder import normalize_raw_observation, build_track
from src.ais_analysis.suspicion_scorer import SuspicionScorer
from src.pipeline.incident_pipeline import run_incident_pipeline
from src.pipeline.models import ProvenanceType
from src.pipeline.state_machine import WatchState


def test_1_live_provider_successful_normalization():
    """1. Verify live provider normalizes incoming JSON payload into canonical AISObservation."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "data": [
            {
                "mmsi": "636018000",
                "timestamp": "2024-08-23T08:30:00Z",
                "lat": 34.450,
                "lon": 18.350,
                "speed": 11.5,
                "course": 280.0,
                "name": "MED_LIBRA",
                "type": "Tanker",
            }
        ]
    }
    mock_session.get.return_value = mock_resp

    provider = LiveAISProvider(
        api_url="https://api.test-maritime.org/v1",
        api_key="test_token_123",
        session=mock_session,
    )
    positions = provider.get_positions(bbox=(18.0, 34.0, 19.0, 35.0))
    assert len(positions) == 1
    obs = positions[0]
    assert obs.mmsi == "636018000"
    assert obs.ship_name == "MED_LIBRA"
    assert obs.sog == 11.5
    assert obs.data_status == "REAL"
    assert obs.mode == "LIVE"


def test_2_real_provenance_assignment():
    """2. Verify live provider strictly enforces REAL / LIVE provenance."""
    provider = LiveAISProvider(api_url="https://api.test.org", api_key="key")
    assert provider.data_status == "REAL"
    assert provider.mode == "LIVE"

    obs = normalize_raw_observation(
        {"mmsi": "123", "timestamp": "2024-08-23T08:00:00Z", "lat": 34.0, "lon": 18.0},
        source="LiveFeed",
        data_status="REAL",
        mode="LIVE",
    )
    assert obs.data_status == "REAL"
    assert obs.mode == "LIVE"


def test_3_live_buffer_insertion():
    """3. Verify inserting observations into LiveAISBuffer."""
    buffer = LiveAISBuffer(buffer_hours=48.0)
    assert len(buffer) == 0
    buffer.add_observation(AISObservation(mmsi="1", timestamp="2024-08-23T08:00:00Z", latitude=34.0, longitude=18.0))
    assert len(buffer) == 1
    buffer.add_observations([
        AISObservation(mmsi="2", timestamp="2024-08-23T08:05:00Z", latitude=34.1, longitude=18.1),
        AISObservation(mmsi="3", timestamp="2024-08-23T08:10:00Z", latitude=34.2, longitude=18.2),
    ])
    assert len(buffer) == 3


def test_4_live_buffer_expiration():
    """4. Verify buffer pruning drops records older than buffer_hours."""
    buffer = LiveAISBuffer(buffer_hours=24.0)
    # 3 days ago vs now
    buffer.add_observations([
        AISObservation(mmsi="OLD", timestamp="2024-08-20T00:00:00Z", latitude=34.0, longitude=18.0),
        AISObservation(mmsi="NEW", timestamp="2024-08-23T00:00:00Z", latitude=34.0, longitude=18.0),
    ])
    pruned = buffer.prune_rolling_window(current_time_iso="2024-08-23T01:00:00Z")
    assert pruned == 1
    assert len(buffer) == 1
    assert buffer._observations[0].mmsi == "NEW"


def test_5_live_candidate_extraction():
    """5. Verify candidate track extraction based on release window and origin envelope."""
    buffer = LiveAISBuffer(buffer_hours=48.0, minimum_track_points=2)
    poly = Polygon([(18.2, 34.4), (18.5, 34.4), (18.5, 34.6), (18.2, 34.6)])

    # Intersecting track
    buffer.add_observations([
        AISObservation(mmsi="IN_1", timestamp="2024-08-23T06:00:00Z", latitude=34.45, longitude=18.30),
        AISObservation(mmsi="IN_1", timestamp="2024-08-23T07:00:00Z", latitude=34.50, longitude=18.35),
        # Disjoint track
        AISObservation(mmsi="OUT_1", timestamp="2024-08-23T06:00:00Z", latitude=37.00, longitude=20.00),
        AISObservation(mmsi="OUT_1", timestamp="2024-08-23T07:00:00Z", latitude=37.05, longitude=20.05),
    ])

    candidates = buffer.get_candidate_tracks_for_incident(
        spill_time_iso="2024-08-23T09:41:12Z",
        release_window_start_iso="2024-08-23T05:00:00Z",
        origin_polygon=poly,
    )
    assert len(candidates) == 1
    assert candidates[0].mmsi == "IN_1"


def test_6_ais_coverage_insufficiency(tmp_path):
    """6. Verify pipeline handles zero coverage honestly (AIS_COVERAGE_INSUFFICIENT)."""
    class EmptyLiveProvider(AISProvider):
        @property
        def data_status(self) -> str:
            return "REAL"
        @property
        def mode(self) -> str:
            return "LIVE"
        def get_status(self) -> ProviderStatus:
            return ProviderStatus.CONNECTED
        def get_positions(self, **kwargs):
            return []
        def get_track(self, mmsi, **kwargs):
            return None
        def get_tracks(self, **kwargs):
            return []
        def get_vessel_static_data(self, mmsi):
            return None

    scene_meta = {
        "incident_id": "INC_ZERO_COV_TEST",
        "product_id": "S1_ZERO_COV",
        "image_path": "data/sar_images/krestenitis_dataset/test/images/Oil (1007).jpg",
        "acquisition_time": "2024-08-23T09:41:12Z",
        "bounding_box": [18.1, 34.3, 18.6, 34.7],
    }

    inc = run_incident_pipeline(
        scene_metadata=scene_meta,
        ais_provider=EmptyLiveProvider(),
        output_dir=str(tmp_path),
        allow_low_confidence=True,
    )

    assert inc.status == WatchState.AIS_COVERAGE_INSUFFICIENT.value
    assert inc.attribution_status == "INSUFFICIENT AIS COVERAGE"
    assert len(inc.candidates) == 0
    assert inc.top_candidate is None


def test_7_provider_rate_limit():
    """7. Verify HTTP 429 returns RATE_LIMITED."""
    mock_session = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 429
    mock_session.get.return_value = mock_resp

    provider = LiveAISProvider(
        api_url="https://api.test.org",
        api_key="key",
        session=mock_session,
    )
    assert provider.get_status() == ProviderStatus.RATE_LIMITED


def test_8_provider_timeout():
    """8. Verify network timeout maps to NETWORK_ERROR."""
    mock_session = MagicMock()
    mock_session.get.side_effect = requests.exceptions.Timeout("Connection timed out")

    provider = LiveAISProvider(
        api_url="https://api.test.org",
        api_key="key",
        session=mock_session,
    )
    assert provider.get_status() == ProviderStatus.NETWORK_ERROR


def test_9_malformed_live_observation_rejection():
    """9. Verify rejection of corrupted live coordinates and negative SOG."""
    assert normalize_raw_observation({"mmsi": "1", "lat": float('nan'), "lon": 18.0, "timestamp": "2024-08-23T00:00:00Z"}) is None
    assert normalize_raw_observation({"mmsi": "1", "lat": 34.0, "lon": 18.0, "sog": -10.0, "timestamp": "2024-08-23T00:00:00Z"}) is None


def test_10_missing_vessel_metadata_handling():
    """10. Verify observation created cleanly when ship name/IMO/draft are missing."""
    obs = normalize_raw_observation({
        "mmsi": "987654321",
        "timestamp": "2024-08-23T08:00:00Z",
        "lat": 34.5,
        "lon": 18.5,
    })
    assert obs is not None
    assert obs.ship_name is None
    assert obs.imo is None
    assert obs.draft is None

    track = build_track([obs])
    df = track.to_dataframe()
    assert len(df) == 1
    assert df["VesselName"].iloc[0] == "UNKNOWN"


def test_11_live_to_attribution_integration():
    """11. Verify live track processed into candidate score with explainable consistency tier."""
    scorer = SuspicionScorer()
    obs = [
        AISObservation(mmsi="444", timestamp="2024-08-23T06:00:00Z", latitude=34.45, longitude=18.35, sog=12.0, cog=45.0, ship_name="LIVE_TANKER", ship_type="Tanker"),
        AISObservation(mmsi="444", timestamp="2024-08-23T07:00:00Z", latitude=34.50, longitude=18.40, sog=12.0, cog=45.0, ship_name="LIVE_TANKER", ship_type="Tanker"),
    ]
    track = build_track(obs)
    df = track.to_dataframe()
    assert not df.empty

    profile = {
        "mmsi": 444,
        "vessel_name": "LIVE_TANKER",
        "vessel_type": 1004.0,
        "draft_change": 0.0,
        "intersection": {
            "spatial_overlap": True,
            "temporal_overlap": True,
            "min_distance_nm": 0.3,
            "crossing_type": "CONTAINED",
            "residence_time_minutes": 30.0,
        },
        "kinematics": {"anomalies": []},
    }
    score_res = scorer.score_vessel(profile, {})
    assert score_res["composite_suspicion_score"] >= 0.5
    assert "attribution_decision" in score_res


def test_12_replay_live_provider_switching(tmp_path):
    """12. Verify clean provider switching between Replay and Live without state leakage."""
    sample_chip = "data/sar_images/krestenitis_dataset/test/images/Oil (1007).jpg"
    scene_meta = {
        "incident_id": "INC_SWITCH_TEST",
        "product_id": "S1_SWITCH",
        "image_path": sample_chip,
        "acquisition_time": "2024-08-23T09:41:12Z",
        "bounding_box": [18.1, 34.3, 18.6, 34.7],
    }

    # Run 1: Replay Mode
    inc_replay = run_incident_pipeline(
        scene_metadata=scene_meta,
        ais_provider=ReplayAISProvider(default_scenario=1),
        output_dir=str(tmp_path / "replay"),
        allow_low_confidence=True,
    )
    assert inc_replay.reality_labels["AIS"] == "SIMULATED REPLAY (Controlled Benchmark)"
    assert inc_replay.candidates[0].provenance == ProvenanceType.SIMULATED.value

    # Run 2: Mock Live Provider
    class MockLive(AISProvider):
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
                AISObservation(mmsi="888", timestamp="2024-08-23T07:00:00Z", latitude=34.45, longitude=18.35, sog=10.0, cog=45.0, ship_name="LIVE_SHIP", ship_type="Tanker", source="LiveTest", data_status="REAL", mode="LIVE"),
                AISObservation(mmsi="888", timestamp="2024-08-23T08:00:00Z", latitude=34.50, longitude=18.40, sog=10.0, cog=45.0, ship_name="LIVE_SHIP", ship_type="Tanker", source="LiveTest", data_status="REAL", mode="LIVE"),
            ]
        def get_track(self, mmsi, **kwargs):
            return None
        def get_tracks(self, **kwargs):
            return [build_track(self.get_positions())]
        def get_vessel_static_data(self, mmsi):
            return {"mmsi": str(mmsi), "data_status": "REAL", "mode": "LIVE"}

    inc_live = run_incident_pipeline(
        scene_metadata=scene_meta,
        ais_provider=MockLive(),
        output_dir=str(tmp_path / "live"),
        allow_low_confidence=True,
    )
    assert inc_live.reality_labels["AIS"] == "REAL LIVE (Maritime Transponder Stream)"
    assert inc_live.candidates[0].provenance == ProvenanceType.REAL.value
