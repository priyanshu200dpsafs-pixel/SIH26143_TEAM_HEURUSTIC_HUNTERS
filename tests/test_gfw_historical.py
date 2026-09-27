"""
Deterministic Unit and Integration Tests for Global Fishing Watch (GFW) Historical AIS Provider.

Phase 7B Requirement 21:
Deterministic mocked tests covering:
1. GFW authentication failure
2. Successful response
3. Response normalization
4. Identity mapping
5. Historical timestamp filtering
6. Spatial filtering
7. Duplicate removal
8. Gap preservation
9. Provider errors
10. Rate limiting
11. No historical coverage
12. Incident-specific historical query
13. Provenance
14. Attribution integration
Does NOT depend on internet access.
"""

import json
from unittest.mock import MagicMock, patch
import pytest
import pandas as pd
from shapely.geometry import Polygon

from src.ingestion.ais.gfw_historical_provider import GFWHistoricalAISProvider
from src.ingestion.ais.models import AISObservation, ProviderStatus, VesselTrack
from src.pipeline.incident_pipeline import run_incident_pipeline
from src.pipeline.models import ProvenanceType


@pytest.fixture
def mock_gfw_entries():
    return [
        {
            "id": "ev_001",
            "type": "fishing",
            "start": "2024-08-23T08:15:00Z",
            "end": "2024-08-23T09:00:00Z",
            "position": {"lat": 34.2500, "lon": 17.5000},
            "sog": 10.5,
            "cog": 180.0,
            "heading": 179.0,
            "vessel": {
                "id": "gfw_vessel_991",
                "ssvid": "240123000",
                "name": "AEGEAN_STAR",
                "type": "tanker",
                "imo": "9876543",
            },
        },
        {
            "id": "ev_002",
            "type": "fishing",
            "start": "2024-08-23T09:30:00Z",
            "end": "2024-08-23T10:00:00Z",
            "position": {"lat": 34.4000, "lon": 17.6500},
            "sog": 11.2,
            "cog": 185.0,
            "heading": 184.0,
            "vessel": {
                "id": "gfw_vessel_991",
                "ssvid": "240123000",
                "name": "AEGEAN_STAR",
                "type": "tanker",
                "imo": "9876543",
            },
        },
        {
            "id": "ev_003",
            "type": "encounter",
            "start": "2024-08-23T11:00:00Z",
            "end": "2024-08-23T11:45:00Z",
            "position": {"lat": 34.5500, "lon": 17.8000},
            "sog": 12.0,
            "cog": 190.0,
            "heading": 189.0,
            "vessel": {
                "id": "gfw_vessel_991",
                "ssvid": "240123000",
                "name": "AEGEAN_STAR",
                "type": "tanker",
                "imo": "9876543",
            },
        },
    ]


def test_1_gfw_authentication_failure():
    """1. Verify 401/403 response transitions provider to AUTH_REQUIRED and returns empty list."""
    provider = GFWHistoricalAISProvider(api_token="invalid_token")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 401
        mock_resp.text = json.dumps({"error": "invalid token"})
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        obs = provider.get_positions(
            bbox=(16.0, 33.0, 19.0, 36.0),
            start_time_iso="2024-08-23T00:00:00Z",
            end_time_iso="2024-08-23T23:59:59Z",
        )

        assert obs == []
        assert provider.get_status() == ProviderStatus.AUTH_REQUIRED


def test_2_gfw_successful_response(mock_gfw_entries):
    """2. Verify successful 200 response parses observations and maintains CONNECTED status."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"entries": mock_gfw_entries}
        mock_resp.headers = {"x-ratelimit-daily-remaining-requests": "950"}
        mock_post.return_value = mock_resp

        obs = provider.get_positions(
            bbox=(16.0, 33.0, 19.0, 36.0),
            start_time_iso="2024-08-23T00:00:00Z",
            end_time_iso="2024-08-23T23:59:59Z",
        )

        assert len(obs) == 3
        assert provider.get_status() == ProviderStatus.CONNECTED


def test_3_gfw_response_normalization(mock_gfw_entries):
    """3. Verify response maps into canonical AISObservation with correct data types."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"entries": [mock_gfw_entries[0]]}
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        obs = provider.get_positions(bbox=(16.0, 33.0, 19.0, 36.0))[0]

        assert obs.mmsi == "240123000"
        assert obs.timestamp == "2024-08-23T08:15:00Z"
        assert obs.latitude == 34.2500
        assert obs.longitude == 17.5000
        assert obs.sog == 10.5
        assert obs.cog == 180.0
        assert obs.heading == 179.0
        assert obs.ship_name == "AEGEAN_STAR"
        assert obs.ship_type == "tanker"
        assert obs.imo == "9876543"
        assert obs.source == "Global Fishing Watch"
        assert obs.data_status == "REAL"
        assert obs.mode == "HISTORICAL"


def test_4_gfw_identity_mapping(mock_gfw_entries):
    """4. Verify GFW persistent vessel_id is preserved."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"entries": [mock_gfw_entries[0]]}
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        tracks = provider.get_tracks(bbox=(16.0, 33.0, 19.0, 36.0))
        assert len(tracks) == 1
        assert tracks[0].vessel_id == "gfw_vessel_991"
        assert tracks[0].mmsi == "240123000"


def test_5_gfw_historical_timestamp_filtering(mock_gfw_entries):
    """5. Verify temporal bounds filter out-of-range observations."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"entries": mock_gfw_entries}
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        # Query only up to 09:00:00 (excludes 09:30 and 11:00)
        obs = provider.get_positions(
            bbox=(16.0, 33.0, 19.0, 36.0),
            start_time_iso="2024-08-23T08:00:00Z",
            end_time_iso="2024-08-23T09:00:00Z",
        )

        assert len(obs) == 1
        assert obs[0].timestamp == "2024-08-23T08:15:00Z"


def test_6_gfw_spatial_filtering(mock_gfw_entries):
    """6. Verify spatial bbox bounds filter out-of-range observations."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"entries": mock_gfw_entries}
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        # Restrict longitude to [17.4, 17.6] (excludes ev_002 at 17.65 and ev_003 at 17.80)
        obs = provider.get_positions(
            bbox=(17.4, 34.0, 17.6, 35.0),
            start_time_iso="2024-08-23T00:00:00Z",
            end_time_iso="2024-08-23T23:59:59Z",
        )

        assert len(obs) == 1
        assert obs[0].longitude == 17.5000


def test_7_gfw_duplicate_removal(mock_gfw_entries):
    """7. Verify exact duplicates are filtered out."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    # Duplicate the first entry
    duplicate_payload = [mock_gfw_entries[0], mock_gfw_entries[0], mock_gfw_entries[1]]
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"entries": duplicate_payload}
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        obs = provider.get_positions(bbox=(16.0, 33.0, 19.0, 36.0))
        assert len(obs) == 2


def test_8_gfw_gap_preservation(mock_gfw_entries):
    """8. Verify broadcast hiatus > 30 mins generates structured AISGap record."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"entries": mock_gfw_entries}
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        tracks = provider.get_tracks(bbox=(16.0, 33.0, 19.0, 36.0))
        assert len(tracks) == 1
        track = tracks[0]
        # From 08:15 to 09:30 is 75 minutes gap (>30m)
        # From 09:30 to 11:00 is 90 minutes gap (>30m)
        assert len(track.gaps) >= 1
        assert track.gaps[0].gap_duration_minutes > 30.0


def test_9_gfw_provider_errors():
    """9. Verify 500 error sets PROVIDER_ERROR status and returns empty."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 503
        mock_resp.text = "Service Unavailable"
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        obs = provider.get_positions(bbox=(16.0, 33.0, 19.0, 36.0))
        assert obs == []
        assert provider.get_status() == ProviderStatus.PROVIDER_ERROR


def test_10_gfw_rate_limiting():
    """10. Verify 429 response transitions provider to RATE_LIMITED."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 429
        mock_resp.text = "Too Many Requests"
        mock_resp.headers = {"x-ratelimit-daily-remaining-requests": "0"}
        mock_post.return_value = mock_resp

        obs = provider.get_positions(bbox=(16.0, 33.0, 19.0, 36.0))
        assert obs == []
        assert provider.get_status() == ProviderStatus.RATE_LIMITED


def test_11_gfw_no_historical_coverage():
    """11. Verify empty provider response reports coverage as absent without errors."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"entries": []}
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        assert provider.has_coverage_for(bbox=(16.0, 33.0, 19.0, 36.0)) is False
        tracks = provider.get_tracks(bbox=(16.0, 33.0, 19.0, 36.0))
        assert tracks == []


def test_12_gfw_incident_specific_query(mock_gfw_entries):
    """12. Verify query accurately takes derived release window and 95% bbox."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    incident_release_start = "2024-08-23T04:47:34Z"
    incident_release_end = "2024-08-23T16:47:34Z"
    hindcast_95_bbox = (16.685553, 33.448469, 18.830298, 35.36055)

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"entries": mock_gfw_entries}
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        tracks = provider.get_tracks(
            bbox=hindcast_95_bbox,
            start_time_iso=incident_release_start,
            end_time_iso=incident_release_end,
        )

        assert mock_post.called
        call_json = mock_post.call_args[1]["json"]
        assert call_json["startDate"] == "2024-08-23"
        assert call_json["endDate"] == "2024-08-23"
        assert call_json["geometry"]["type"] == "Polygon"
        assert len(tracks) == 1


def test_13_gfw_provenance(mock_gfw_entries):
    """13. Verify provenance guarantees REAL and HISTORICAL status."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"entries": mock_gfw_entries}
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        tracks = provider.get_tracks(bbox=(16.0, 33.0, 19.0, 36.0))
        assert tracks[0].data_status == "REAL"
        assert tracks[0].mode == "HISTORICAL"
        assert tracks[0].source == "Global Fishing Watch"


def test_14_gfw_attribution_integration(mock_gfw_entries):
    """14. Verify full incident pipeline executes with GFWHistoricalAISProvider without fabricating."""
    provider = GFWHistoricalAISProvider(api_token="valid_test_token")
    scene_meta = {
        "scene_id": "S1A_IW_GRDH_1SDV_20240823T164734_20240823T164759_055343_06BFAC_153E",
        "acquisition_time": "2024-08-23T16:47:34Z",
        "bbox": [16.685553, 33.440971, 19.84104, 35.36055],
        "mode": "HISTORICAL",
    }

    with patch("requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"entries": mock_gfw_entries}
        mock_resp.headers = {}
        mock_post.return_value = mock_resp

        incident = run_incident_pipeline(
            scene_metadata=scene_meta,
            ais_provider=provider,
            output_dir="data/results/incidents",
        )

        assert incident is not None
        assert incident.reality_labels["AIS"].startswith("REAL HISTORICAL")
