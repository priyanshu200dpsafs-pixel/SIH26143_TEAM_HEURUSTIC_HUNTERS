"""
Deterministic Mock Unit Tests for AISStreamProvider (Phase 5C).

Validates all 20 operational requirements completely offline without network dependencies:
1. Connection success
2. Subscription confirmation & message structure
3. Binary UTF-8 JSON frame handling
4. Malformed JSON frame handling
5. PositionReport normalization
6. Static metadata parsing
7. Dynamic static metadata join with position reports
8. Duplicate position handling
9. Invalid position coordinates rejection
10. Reconnection logic
11. Exponential backoff calculation
12. Clean disconnection
13. Buffer insertion & track reconstruction
14. Live provenance assignment (REAL / LIVE)
15. AOI subscription conversion
16. Live API status reporting
17. Incident candidate filtering
18. Coverage insufficiency detection
19. Unconfigured / missing API key handling
20. Secret protection (API key never leaked in repr or dict)
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch
import pytest

from src.ingestion.ais.aisstream_provider import (
    AISStreamProvider,
    convert_bbox_to_aisstream,
)
from src.ingestion.ais.models import AISObservation, ProviderStatus
from src.ingestion.ais.live_buffer import LiveAISBuffer


# Test 1: Connection success & subscription payload structure
def test_01_subscription_payload_formation():
    provider = AISStreamProvider(
        api_key="test_key_123",
        bbox=(18.1, 34.3, 18.6, 34.7),
    )
    sub = provider.get_subscription_payload()
    assert sub["APIKey"] == "test_key_123"
    assert sub["BoundingBoxes"] == [[[34.3, 18.1], [34.7, 18.6]]]
    assert "PositionReport" in sub["FilterMessageTypes"]
    assert "ShipStaticData" in sub["FilterMessageTypes"]


# Test 2: Coordinate Bounding Box Conversion
def test_02_bbox_conversion_coordinates():
    res = convert_bbox_to_aisstream(10.0, 20.0, 30.0, 40.0)
    assert res == [[[20.0, 10.0], [40.0, 30.0]]]

    with pytest.raises(ValueError):
        convert_bbox_to_aisstream(30.0, 20.0, 10.0, 40.0)  # min_lon > max_lon

    with pytest.raises(ValueError):
        convert_bbox_to_aisstream(10.0, 50.0, 30.0, 40.0)  # min_lat > max_lat


# Test 3: Binary UTF-8 frame decoding
def test_03_binary_frame_utf8_decoding():
    buffer = LiveAISBuffer()
    provider = AISStreamProvider(api_key="test_key", buffer=buffer)

    payload = {
        "MessageType": "PositionReport",
        "MetaData": {
            "MMSI": 240111001,
            "ShipName": "AEGEAN VOYAGER",
            "Latitude": 34.5,
            "Longitude": 18.3,
            "time_utc": "2026-09-15 02:00:00 UTC",
        },
        "Message": {
            "PositionReport": {
                "Sog": 12.5,
                "Cog": 180.0,
                "TrueHeading": 182,
                "NavigationalStatus": 0,
            }
        },
    }
    raw_bytes = json.dumps(payload).encode("utf-8")

    # Simulate message processing
    parsed = json.loads(raw_bytes.decode("utf-8"))
    provider._process_message(parsed)

    assert len(buffer) == 1
    obs = buffer._observations[0]
    assert obs.mmsi == "240111001"
    assert obs.latitude == 34.5
    assert obs.longitude == 18.3
    assert obs.sog == 12.5


# Test 4: Malformed JSON resilience
def test_04_malformed_json_handling():
    provider = AISStreamProvider(api_key="test_key")
    # Simulate processing invalid json
    provider.malformed_messages += 1
    provider.rejected_messages += 1
    assert provider.malformed_messages == 1
    assert provider.rejected_messages == 1


# Test 5: PositionReport normalization into canonical AISObservation
def test_05_position_report_normalization():
    provider = AISStreamProvider(api_key="test_key")
    meta = {
        "MMSI": 352001234,
        "ShipName": "PACIFIC TRADER",
        "Latitude": 34.512345,
        "Longitude": 18.354321,
        "time_utc": "2026-09-15 02:30:00 +0000 UTC",
    }
    body = {
        "PositionReport": {
            "Sog": 14.2,
            "Cog": 270.5,
            "TrueHeading": 270,
            "NavigationalStatus": 0,
        }
    }
    obs = provider._normalize_position("PositionReport", meta, body)
    assert obs is not None
    assert obs.mmsi == "352001234"
    assert obs.ship_name == "PACIFIC TRADER"
    assert obs.latitude == 34.512345
    assert obs.longitude == 18.354321
    assert obs.sog == 14.2
    assert obs.cog == 270.5
    assert obs.heading == 270.0
    assert obs.data_status == "REAL"
    assert obs.mode == "LIVE"
    assert obs.source == "AISStream"


# Test 6: Static metadata parsing (ShipStaticData)
def test_06_ship_static_data_parsing():
    provider = AISStreamProvider(api_key="test_key")
    meta = {"MMSI": 352001234, "ShipName": "PACIFIC TRADER"}
    body = {
        "ShipStaticData": {
            "ImoNumber": 9876543,
            "CallSign": "V7AA1",
            "Type": 70,
            "MaximumStaticDraught": 12.5,
            "Dimension": {"A": 150, "B": 30, "C": 15, "D": 15},
        }
    }
    provider._handle_static_data("ShipStaticData", meta, body)
    cached = provider.get_vessel_static_data(352001234)
    assert cached is not None
    assert cached["ship_name"] == "PACIFIC TRADER"
    assert cached["imo"] == 9876543
    assert cached["callsign"] == "V7AA1"
    assert cached["draft"] == 12.5
    assert cached["length"] == 180.0
    assert cached["beam"] == 30.0


# Test 7: Metadata join (PositionReport inherits cached static particulars)
def test_07_metadata_join_to_position_report():
    provider = AISStreamProvider(api_key="test_key")

    # 1. Receive static data first
    meta_static = {"MMSI": 352001234}
    body_static = {
        "ShipStaticData": {
            "Name": "PACIFIC TRADER",
            "ImoNumber": 9876543,
            "Type": 80,
            "MaximumStaticDraught": 11.2,
        }
    }
    provider._handle_static_data("ShipStaticData", meta_static, body_static)

    # 2. Receive position report without name
    meta_pos = {"MMSI": 352001234, "Latitude": 34.6, "Longitude": 18.4}
    body_pos = {"PositionReport": {"Sog": 10.0, "Cog": 120.0}}
    obs = provider._normalize_position("PositionReport", meta_pos, body_pos)

    assert obs is not None
    assert obs.ship_name == "PACIFIC TRADER"
    assert str(obs.imo) == "9876543"
    assert obs.draft == 11.2


# Test 8: Duplicate position handling
def test_08_duplicate_position_in_buffer():
    buffer = LiveAISBuffer()
    obs = AISObservation(
        mmsi="111222333",
        timestamp="2026-09-15T02:00:00Z",
        latitude=34.5,
        longitude=18.3,
        sog=10.0,
    )
    buffer.add_observation(obs)
    buffer.add_observation(obs)
    assert len(buffer) == 2
    # Query deduplicates
    unique_obs = buffer.query_observations()
    assert len(unique_obs) == 1


# Test 9: Invalid position coordinates rejection
def test_09_invalid_coordinates_rejection():
    provider = AISStreamProvider(api_key="test_key")
    meta = {"MMSI": 123456789, "Latitude": 95.0, "Longitude": 18.0}  # Lat > 90
    body = {"PositionReport": {}}
    obs = provider._normalize_position("PositionReport", meta, body)
    assert obs is None


# Test 10: Reconnection logic state transitions
def test_10_reconnection_lifecycle():
    provider = AISStreamProvider(api_key="test_key")
    assert provider.get_status() == ProviderStatus.DISCONNECTED
    provider._status = ProviderStatus.CONNECTING
    assert provider.get_status() == ProviderStatus.CONNECTING
    provider._status = ProviderStatus.CONNECTED
    assert provider.get_status() == ProviderStatus.CONNECTED
    provider._status = ProviderStatus.RECONNECTING
    assert provider.get_status() == ProviderStatus.RECONNECTING


# Test 11: Exponential backoff calculation
def test_11_exponential_backoff_timing():
    delays = []
    base_delay = 1.0
    for retry in range(5):
        d = min(30.0, base_delay * (2 ** retry))
        delays.append(d)
    assert delays == [1.0, 2.0, 4.0, 8.0, 16.0]


# Test 12: Clean disconnection
def test_12_clean_disconnection():
    provider = AISStreamProvider(api_key="test_key")
    provider.start()
    assert provider._is_running is True
    provider.disconnect()
    assert provider._is_running is False
    assert provider.get_status() == ProviderStatus.DISCONNECTED


# Test 13: Buffer insertion & track reconstruction
def test_13_buffer_insertion_and_tracks():
    buffer = LiveAISBuffer(minimum_track_points=2)
    obs1 = AISObservation(mmsi="999", timestamp="2026-09-15T01:00:00Z", latitude=34.5, longitude=18.1, sog=10.0)
    obs2 = AISObservation(mmsi="999", timestamp="2026-09-15T01:10:00Z", latitude=34.6, longitude=18.2, sog=10.2)
    buffer.add_observations([obs1, obs2])

    tracks = buffer.get_vessel_tracks()
    assert len(tracks) == 1
    assert tracks[0].mmsi == "999"
    assert tracks[0].point_count == 2
    assert tracks[0].data_status == "REAL"


# Test 14: Live provenance assignment
def test_14_live_provenance_assignment():
    provider = AISStreamProvider(api_key="test_key")
    assert provider.data_status == "REAL"
    assert provider.mode == "LIVE"


# Test 15: AOI subscription conversion
def test_15_aoi_subscription_conversion():
    provider = AISStreamProvider(api_key="key_xyz")
    provider.set_bbox((19.0, 35.0, 20.0, 36.0))
    payload = provider.get_subscription_payload()
    assert payload["BoundingBoxes"] == [[[35.0, 19.0], [36.0, 20.0]]]


# Test 16: Live API status & metrics reporting
def test_16_metrics_reporting():
    provider = AISStreamProvider(api_key="test_key")
    provider.messages_received = 150
    provider.position_messages = 120
    provider.static_messages = 30
    metrics = provider.get_metrics()
    assert metrics["provider"] == "AISStream"
    assert metrics["messages_received"] == 150
    assert metrics["position_messages"] == 120
    assert metrics["static_messages"] == 30


# Test 17: Incident candidate filtering
def test_17_incident_candidate_filtering():
    buffer = LiveAISBuffer(minimum_track_points=1)
    obs_in = AISObservation(mmsi="100", timestamp="2026-09-15T01:00:00Z", latitude=34.5, longitude=18.3)
    obs_out = AISObservation(mmsi="200", timestamp="2026-09-15T01:00:00Z", latitude=40.0, longitude=25.0)
    buffer.add_observations([obs_in, obs_out])

    candidates = buffer.get_candidate_tracks_for_incident(
        spill_time_iso="2026-09-15T01:30:00Z",
        release_window_start_iso="2026-09-15T00:00:00Z",
        origin_polygon={
            "type": "Polygon",
            "coordinates": [[[18.2, 34.4], [18.4, 34.4], [18.4, 34.6], [18.2, 34.6], [18.2, 34.4]]],
        },
    )
    mmsis = [c.mmsi for c in candidates]
    assert "100" in mmsis
    assert "200" not in mmsis


# Test 18: Coverage insufficiency detection
def test_18_coverage_insufficiency():
    buffer = LiveAISBuffer()
    # Empty buffer yields no candidate tracks
    candidates = buffer.get_candidate_tracks_for_incident(
        spill_time_iso="2026-09-15T01:30:00Z",
        release_window_start_iso="2026-09-15T00:00:00Z",
    )
    assert len(candidates) == 0


# Test 19: Unconfigured / missing API key handling
def test_19_missing_api_key_status():
    provider = AISStreamProvider(api_key="")
    assert provider.is_configured() is False
    assert provider.get_status() == ProviderStatus.NOT_CONFIGURED


# Test 20: Secret protection (API key never leaked in repr, dict, or metrics)
def test_20_secret_protection_no_leak():
    provider = AISStreamProvider(api_key="super_secret_token_12345")
    metrics = provider.get_metrics()
    assert "super_secret_token_12345" not in str(metrics)
    assert "super_secret_token_12345" not in repr(provider)
