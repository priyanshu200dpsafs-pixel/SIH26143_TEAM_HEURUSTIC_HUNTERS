"""
Deterministic Unit & Integration Tests for Sentinel-1 Ingestion & Watch Service.

Covers all 14 Phase 4B test requirements using deterministic mocked responses:
1. Real-provider normalization with fixture response
2. No products returned
3. New product discovery
4. Duplicate product rejection
5. Authentication error handling
6. Network error handling
7. Ingestion ledger persistence & reload
8. Download collision & safe non-overwrite
9. Unsupported raster handling (raw SAFE / ZIP)
10. Valid preprocessing metadata extraction
11. Clean no-spill incident flow
12. New spill incident trigger
13. Clean graceful service shutdown
14. Replay mode unchanged
"""

import json
from pathlib import Path
import threading
import time
from unittest.mock import patch, MagicMock
import pytest
import numpy as np
from PIL import Image
import requests

from src.ingestion.sentinel1_provider import (
    CopernicusSentinel1Provider,
    ProviderStatus,
    DownloadStatus,
    Sentinel1ProductMetadata,
)
from src.ingestion.ledger import IngestionLedger, IngestionStatus
from src.ingestion.satellite_watch import (
    SatelliteWatcher,
    SatelliteWatchStatus,
    WatchEvent,
    FixtureCatalogProvider,
)
from src.ingestion.watch_service import WatchService
from src.ingestion.replay_ais import ReplayAISProvider
from src.detection.sentinel1_preprocessing import (
    Sentinel1Preprocessor,
    PreprocessingState,
)
from src.pipeline.models import Incident, ProvenanceType
from src.pipeline.state_machine import WatchState


RAW_ODATA_FIXTURE = {
    "value": [
        {
            "Id": "a21ac162-6574-4b85-80f4-612a9ebe2ec7",
            "Name": "S1C_IW_GRDH_1SDV_20260908T044827_20260908T044852_009351_012992_57DC.SAFE",
            "ContentDate": {
                "Start": "2026-09-08T04:48:27.960Z",
                "End": "2026-09-08T04:48:52.957Z",
            },
            "OriginDate": "2026-09-08T06:12:00.000Z",
            "ContentLength": 856281000,
            "GeoFootprint": {
                "type": "Polygon",
                "coordinates": [
                    [
                        [18.1, 34.3],
                        [18.6, 34.3],
                        [18.6, 34.7],
                        [18.1, 34.7],
                        [18.1, 34.3],
                    ]
                ],
            },
            "Attributes": [
                {"Name": "orbitNumber", "Value": 9351},
                {"Name": "relativeOrbitNumber", "Value": 136},
                {"Name": "polarisationChannels", "Value": "VV&VH"},
                {"Name": "productType", "Value": "GRD"},
            ],
        }
    ]
}


@pytest.fixture
def sample_sar_chip(tmp_path):
    """Create sample SAR image chip for test inference."""
    p = tmp_path / "sample_sar.jpg"
    # Copy real sample image if exists, else create test array
    src_real = Path("data/sar_images/krestenitis_dataset/test/images/Oil (1007).jpg")
    if src_real.exists():
        import shutil
        shutil.copy(src_real, p)
    else:
        arr = np.full((256, 256, 3), 120, dtype=np.uint8)
        Image.fromarray(arr).save(p)
    return str(p)


def test_real_provider_normalization_fixture():
    """1. Test real-provider normalization with OData response fixture."""
    provider = CopernicusSentinel1Provider()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = RAW_ODATA_FIXTURE

    with patch("requests.get", return_value=mock_resp):
        status, products, err = provider.search_products(bbox=(18.1, 34.3, 18.6, 34.7))

    assert status == ProviderStatus.SUCCESS
    assert len(products) == 1
    prod = products[0]
    assert prod.product_id == "a21ac162-6574-4b85-80f4-612a9ebe2ec7"
    assert "S1C_IW_GRDH" in prod.product_name
    assert prod.sensor == "C-SAR / Sentinel-1"
    assert prod.acquisition_start == "2026-09-08T04:48:27.960Z"
    assert prod.orbit == 9351
    assert prod.relative_orbit == 136
    assert prod.polarization == "VV&VH"
    assert prod.product_type == "GRD"
    assert prod.bbox == (18.1, 34.3, 18.6, 34.7)


def test_no_products_handling():
    """2. Test handling when catalog returns zero products."""
    provider = CopernicusSentinel1Provider()

    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"value": []}

    with patch("requests.get", return_value=mock_resp):
        status, products, err = provider.search_products(bbox=(18.1, 34.3, 18.6, 34.7))

    assert status == ProviderStatus.NO_RESULTS
    assert len(products) == 0


def test_new_product_discovery(tmp_path):
    """3. Test new product discovery and ledger registration."""
    ledger = IngestionLedger(tmp_path / "test_ledger.json")
    provider = FixtureCatalogProvider(fixtures=[
        {
            "product_id": "S1_NEW_001",
            "product_name": "S1A_IW_GRD_NEW_001",
            "acquisition_start": "2026-09-08T04:48:27Z",
        }
    ])
    watcher = SatelliteWatcher(catalog_provider=provider, ledger=ledger)

    event, prod = watcher.poll_and_emit_event()
    assert event == WatchEvent.NEW_SATELLITE_PRODUCT
    assert prod["product_id"] == "S1_NEW_001"
    assert ledger.is_seen("S1_NEW_001") is True

    entry = ledger.get_entry("S1_NEW_001")
    assert entry is not None
    assert entry.processing_status == IngestionStatus.DISCOVERED.value


def test_duplicate_product_rejection(tmp_path):
    """4. Test that already processed/seen products emit DUPLICATE event."""
    ledger = IngestionLedger(tmp_path / "test_ledger.json")
    provider = FixtureCatalogProvider(fixtures=[
        {"product_id": "S1_DUP_001", "product_name": "S1A_IW_GRD_DUP_001"}
    ])
    watcher = SatelliteWatcher(catalog_provider=provider, ledger=ledger)

    # First poll -> NEW
    e1, p1 = watcher.poll_and_emit_event()
    assert e1 == WatchEvent.NEW_SATELLITE_PRODUCT

    # Second poll -> DUPLICATE
    e2, p2 = watcher.poll_and_emit_event()
    assert e2 == WatchEvent.DUPLICATE_SATELLITE_PRODUCT
    assert p2["product_id"] == "S1_DUP_001"


def test_auth_error_handling():
    """5. Test clean AUTH_ERROR propagation without printing secrets."""
    provider = CopernicusSentinel1Provider()

    mock_resp = MagicMock()
    mock_resp.status_code = 401
    mock_resp.text = "Unauthorized"

    with patch("requests.get", return_value=mock_resp):
        status, products, err = provider.search_products(bbox=(18.1, 34.3, 18.6, 34.7))

    assert status == ProviderStatus.AUTH_ERROR
    assert "authentication failed" in err.lower()


def test_network_error_handling():
    """6. Test clean NETWORK_ERROR handling when API is unreachable."""
    provider = CopernicusSentinel1Provider()

    with patch("requests.get", side_effect=requests.ConnectionError("DNS failure")):
        status, products, err = provider.search_products(bbox=(18.1, 34.3, 18.6, 34.7))

    assert status == ProviderStatus.NETWORK_ERROR
    assert "connectivity error" in err.lower()


def test_ledger_persistence(tmp_path):
    """7. Test ledger atomic persistence and reload."""
    ledger_path = tmp_path / "sub" / "persistent_ledger.json"
    ledger1 = IngestionLedger(ledger_path)

    ledger1.record_discovery("PROD_100", "Sentinel-1 Product 100", spatial_bbox=(18.1, 34.3, 18.6, 34.7))
    ledger1.update_status("PROD_100", IngestionStatus.DOWNLOADED, product_hash="abcdef123456")

    assert ledger_path.exists()

    # Reload fresh instance
    ledger2 = IngestionLedger(ledger_path)
    entry = ledger2.get_entry("PROD_100")
    assert entry is not None
    assert entry.product_name == "Sentinel-1 Product 100"
    assert entry.processing_status == IngestionStatus.DOWNLOADED.value
    assert entry.product_hash == "abcdef123456"
    assert entry.spatial_bbox == (18.1, 34.3, 18.6, 34.7)


def test_download_collision(tmp_path):
    """8. Test download safe non-overwrite on existing product file."""
    provider = CopernicusSentinel1Provider()
    dest_dir = tmp_path / "storage"
    dest_dir.mkdir(parents=True, exist_ok=True)

    test_file = dest_dir / "COLLISION_001.zip"
    test_file.write_bytes(b"EXISTING_SENTINEL1_DATA")

    meta = Sentinel1ProductMetadata(
        product_id="COLLISION_001",
        product_name="S1A_COLLISION_001",
    )

    status, dl_path, hash_val = provider.download_product(meta, destination_dir=dest_dir)
    assert status == DownloadStatus.SUCCESS
    assert dl_path == str(test_file)
    assert hash_val is not None
    # Ensure file content was not overwritten
    assert test_file.read_bytes() == b"EXISTING_SENTINEL1_DATA"


def test_unsupported_raster_detection(tmp_path):
    """9. Test that raw SAFE / ZIP / directory is flagged UNSUPPORTED_PRODUCT."""
    preprocessor = Sentinel1Preprocessor()

    # Raw SAFE archive directory
    safe_dir = tmp_path / "S1A_IW_GRDH.SAFE"
    safe_dir.mkdir()

    report = preprocessor.validate_raster(safe_dir)
    assert report.is_valid is False
    assert report.state == PreprocessingState.UNSUPPORTED_PRODUCT.value
    assert "SAFE" in report.unsupported_reason


def test_valid_preprocessing_metadata(sample_sar_chip):
    """10. Test valid preprocessing report on real image chip."""
    preprocessor = Sentinel1Preprocessor()
    report = preprocessor.validate_raster(sample_sar_chip)

    assert report.is_valid is True
    assert report.state == PreprocessingState.READY_FOR_PROCESSING.value
    assert report.dimensions == (256, 256) or report.dimensions == (1920, 1080)
    assert report.band_count == 3
    assert len(report.transformation_steps) >= 2


def test_clean_no_spill_incident(tmp_path):
    """11. Test clean no-spill watch cycle."""
    clean_chip = tmp_path / "clean_chip.png"
    Image.fromarray(np.full((256, 256, 3), 0, dtype=np.uint8)).save(clean_chip)

    ledger = IngestionLedger(tmp_path / "ledger.json")
    provider = FixtureCatalogProvider(fixtures=[
        {
            "product_id": "S1_CLEAN_001",
            "product_name": "S1A_IW_GRD_CLEAN",
            "image_path": str(clean_chip),
            "acquisition_start": "2024-08-23T09:41:12Z",
            "bbox": [18.1, 34.3, 18.6, 34.7],
        }
    ])
    watcher = SatelliteWatcher(catalog_provider=provider, ledger=ledger)
    service = WatchService(watcher=watcher, ledger=ledger)

    res = service.run_once()
    assert res["status"] == "PROCESSED"
    assert res["incident_status"] == WatchState.NO_SPILL.value
    assert res["spill_detected"] is False

    entry = ledger.get_entry("S1_CLEAN_001")
    assert entry.processing_status == IngestionStatus.PROCESSED.value


def test_new_spill_incident_trigger(sample_sar_chip, tmp_path):
    """12. Test new spill incident trigger and pipeline completion."""
    ledger = IngestionLedger(tmp_path / "ledger.json")
    provider = FixtureCatalogProvider(fixtures=[
        {
            "product_id": "S1_SPILL_TRIGGER",
            "product_name": "S1A_IW_GRD_SPILL",
            "image_path": sample_sar_chip,
            "acquisition_start": "2024-08-23T09:41:12Z",
            "bbox": [18.1, 34.3, 18.6, 34.7],
        }
    ])
    watcher = SatelliteWatcher(catalog_provider=provider, ledger=ledger)
    service = WatchService(watcher=watcher, ledger=ledger)

    res = service.run_once()
    assert res["status"] == "PROCESSED"
    assert res["incident_status"] == WatchState.INCIDENT_READY.value
    assert res["spill_detected"] is True
    assert res["incident_id"] is not None

    entry = ledger.get_entry("S1_SPILL_TRIGGER")
    assert entry.incident_id == res["incident_id"]
    assert entry.processing_status == IngestionStatus.PROCESSED.value


def test_graceful_shutdown(tmp_path):
    """13. Test graceful shutdown of watch loop."""
    ledger = IngestionLedger(tmp_path / "ledger.json")
    provider = FixtureCatalogProvider(fixtures=[])
    watcher = SatelliteWatcher(catalog_provider=provider, ledger=ledger)
    service = WatchService(watcher=watcher, ledger=ledger)
    assert service.is_running() is True

    # Start loop in background thread with 1-second interval
    t = threading.Thread(target=service.run_loop, kwargs={"poll_interval_seconds": 1})
    t.start()

    time.sleep(0.1)
    service.stop()
    t.join(timeout=2.0)

    assert not t.is_alive()
    assert service.is_running() is False


def test_replay_mode_unchanged():
    """14. Test that ReplayAISProvider and replay mode preserve SIMULATED/REPLAY provenance."""
    provider = ReplayAISProvider()
    assert provider.data_status == "SIMULATED"
    assert provider.mode == "REPLAY"

    df = provider.load_ais_data(scenario_id=1)
    assert len(df) > 0
    assert "MMSI" in df.columns
    assert "BaseDateTime" in df.columns
    # Ensure ground truth is not in returned dataframe
    assert "ground_truth_culprit" not in df.columns
