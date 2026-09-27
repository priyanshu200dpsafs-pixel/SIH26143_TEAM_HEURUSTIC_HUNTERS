"""
Tests for Phase 7B: Core SIH Workflow & Historical AIS Invariants.

Verifies:
1. Historical AIS provider unavailable (returns empty, no fabrication)
2. Historical AIS provider success (with real historical records, e.g. NOAA Marine Cadastre)
3. Historical query uses incident release window timestamp
4. Historical query uses hindcast origin bbox
5. Live AIS is not used as historical fallback
6. Candidate tracks linked to correct MMSI
7. Candidate track timestamps preserved
8. Different vessels produce different map coordinates
9. Scene -> incident -> AIS query identity preserved
"""

import json
from pathlib import Path
import pytest
import pandas as pd
from shapely.geometry import Polygon

from src.ingestion.ais.historical_provider import HistoricalAISProvider
from src.ingestion.ais.live_provider import LiveAISProvider
from src.ingestion.ais.aisstream_provider import AISStreamProvider
from src.ingestion.ais.replay_provider import ReplayAISProvider
from src.ingestion.ais.models import ProviderStatus
from src.pipeline.incident_pipeline import run_incident_pipeline
from src.pipeline.models import ProvenanceType


def test_1_historical_ais_provider_unavailable():
    """Verify that when no historical records cover the bbox/window, provider honestly returns empty."""
    provider = HistoricalAISProvider(data_dir="data/ais/real_reference")
    
    # Query Mediterranean coordinates for 2024 (where only Alaska 2017 is in local archive)
    tracks = provider.get_tracks(
        bbox=(17.0, 33.0, 20.0, 36.0),
        start_time_iso="2024-08-20T00:00:00Z",
        end_time_iso="2024-08-25T00:00:00Z"
    )
    assert tracks == []
    assert provider.has_coverage_for(
        bbox=(17.0, 33.0, 20.0, 36.0),
        start_time="2024-08-20T00:00:00Z",
        end_time="2024-08-25T00:00:00Z"
    ) is False


def test_2_historical_ais_provider_success():
    """Verify provider reconstructs real historical tracks when legitimate data is present."""
    provider = HistoricalAISProvider(data_dir="data/ais/real_reference")
    
    # Query Alaska Zone 01 for January 2017 where real NOAA Cadastre data exists
    tracks = provider.get_tracks(
        bbox=(-176.0, 52.0, -174.0, 53.0),
        start_time_iso="2017-01-01T00:00:00Z",
        end_time_iso="2017-01-05T23:59:59Z"
    )
    assert len(tracks) > 0
    t0 = tracks[0]
    assert t0.data_status == "REAL"
    assert t0.mode == "HISTORICAL"
    assert t0.point_count > 0
    assert t0.mmsi is not None


def test_3_historical_query_uses_incident_timestamp():
    """Verify historical query uses actual incident release window start and end."""
    provider = HistoricalAISProvider(data_dir="data/ais/real_reference")
    
    t_start = "2017-01-04T12:00:00Z"
    t_end = "2017-01-04T15:00:00Z"
    
    positions = provider.get_positions(
        bbox=(-176.0, 52.0, -174.0, 53.0),
        start_time_iso=t_start,
        end_time_iso=t_end
    )
    assert len(positions) > 0
    for p in positions:
        assert p.timestamp >= t_start
        assert p.timestamp <= t_end
        assert p.data_status == "REAL"
        assert p.mode == "HISTORICAL"


def test_4_historical_query_uses_hindcast_bbox():
    """Verify historical query filters precisely within the spatial bounding box."""
    provider = HistoricalAISProvider(data_dir="data/ais/real_reference")
    
    bbox = (-175.5, 52.2, -174.5, 52.6)
    positions = provider.get_positions(
        bbox=bbox,
        start_time_iso="2017-01-01T00:00:00Z",
        end_time_iso="2017-01-10T00:00:00Z"
    )
    assert len(positions) > 0
    for p in positions:
        assert bbox[0] <= p.longitude <= bbox[2]
        assert bbox[1] <= p.latitude <= bbox[3]


def test_5_live_ais_is_not_used_as_historical_fallback():
    """Verify historical investigations never substitute live AIS or fake candidates."""
    provider = HistoricalAISProvider(data_dir="data/ais/real_reference")
    
    # Query for historical scene with no data
    tracks = provider.get_tracks(
        bbox=(18.1, 34.3, 18.6, 34.7),
        start_time_iso="2024-08-23T00:00:00Z",
        end_time_iso="2024-08-23T12:00:00Z"
    )
    assert len(tracks) == 0
    assert provider.mode == "HISTORICAL"
    assert provider.data_status == "REAL"


def test_6_candidate_tracks_linked_to_correct_mmsi():
    """Verify candidate tracks are grouped and indexed strictly by their transponder MMSI."""
    provider = HistoricalAISProvider(data_dir="data/ais/real_reference")
    
    tracks = provider.get_tracks(
        bbox=(-176.0, 52.0, -174.0, 53.0),
        start_time_iso="2017-01-01T00:00:00Z",
        end_time_iso="2017-01-05T23:59:59Z"
    )
    for tr in tracks:
        for obs in tr.observations:
            assert str(obs.mmsi) == str(tr.mmsi)


def test_7_candidate_track_timestamps_preserved():
    """Verify all timestamps are strictly chronological and preserved without distortion."""
    provider = HistoricalAISProvider(data_dir="data/ais/real_reference")
    
    tracks = provider.get_tracks(
        bbox=(-176.0, 52.0, -174.0, 53.0),
        start_time_iso="2017-01-01T00:00:00Z",
        end_time_iso="2017-01-05T23:59:59Z"
    )
    for tr in tracks:
        timestamps = [o.timestamp for o in tr.observations]
        assert timestamps == sorted(timestamps)


def test_8_different_vessels_produce_different_map_targets():
    """Verify each candidate vessel resolves to its own distinct coordinates, never a shared fallback."""
    provider = HistoricalAISProvider(data_dir="data/ais/real_reference")
    
    tracks = provider.get_tracks(
        bbox=(-176.0, 52.0, -174.0, 53.0),
        start_time_iso="2017-01-01T00:00:00Z",
        end_time_iso="2017-01-05T23:59:59Z"
    )
    assert len(tracks) >= 2
    coord1 = (tracks[0].observations[0].longitude, tracks[0].observations[0].latitude)
    coord2 = tracks[1].observations[0].longitude, tracks[1].observations[0].latitude
    assert coord1 != coord2


def test_9_scene_incident_ais_query_identity_preserved(tmp_path):
    """Verify scene metadata flows faithfully into incident record and queries historical provider."""
    from scripts.process_real_sentinel1 import process_real_sentinel1_product
    
    # Process real scene 3bdfd698...
    res = process_real_sentinel1_product(
        product_id="3bdfd698-b3bb-47b2-920f-b18bc76643b3",
        output_dir=str(tmp_path / "incidents")
    )
    
    assert res["product_id"] == "3bdfd698-b3bb-47b2-920f-b18bc76643b3"
    assert res["incident_id"] == "INC_3BDFD698"
    assert res["footprint_validation"] == "PASS"
    assert res["hindcast_available"] is True
    assert res["forecast_available"] is True
    
    # Check that because this Mediterranean scene has no historical AIS locally, candidates is 0
    assert res["candidate_count"] == 0
    
    # Inspect persisted incident file
    with open(res["incident_file"]) as f:
        inc_data = json.load(f)
    assert inc_data["provenance_category"] == "REAL"
    assert inc_data["hindcast_result"] is not None
    assert "HISTORICAL AIS UNAVAILABLE" in inc_data["reality_labels"]["AIS"]
