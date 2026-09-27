"""
End-to-End Vertical Slice Integration and Failure Recovery Tests.

Verifies:
1. Complete deterministic pipeline execution connecting:
   - SAR Satellite Metadata & Image
   - U-Net Inference & Spill Geometry
   - Environmental Context (ERA5 & Optical)
   - Lagrangian Backward Drift Hindcast
   - Replay AIS Tracking (Simulated Benchmark)
   - Kinematics & Suspicion Attribution Scoring
   - Counterfactual Forward Perturbation Resilience
   - Forward Drift Forecasting
   - Incident State Machine & Provenance Labels
2. Safe failure and abstention handling across degraded input modes:
   - No spill detected
   - Low confidence / CleanSeaNet abstention
   - Environmental forcing data unavailable
   - AIS data unavailable
   - Counterfactual unavailable
3. Ingestion monitor (SatelliteWatcher) catalog polling and duplicate prevention.
4. WatchStateMachine transition auditing.
"""

from pathlib import Path
import json
import pytest
import numpy as np
from PIL import Image

from src.pipeline.models import Incident, ProvenanceType
from src.pipeline.state_machine import WatchState, WatchStateMachine
from src.pipeline.incident_pipeline import run_incident_pipeline
from src.ingestion.satellite_watch import (
    SatelliteWatcher,
    SatelliteWatchStatus,
    FixtureCatalogProvider,
)
from src.ingestion.replay_ais import ReplayAISProvider

SAMPLE_IMAGE = "data/sar_images/krestenitis_dataset/test/images/Oil (1007).jpg"
ERA5_PATH = "data/weather/era5_wind_mediterranean_case_study.nc"
OSCAR_PATH = "data/ocean_currents/oscar_currents_final_20240823.nc"
OPTICAL_PATH = "data/optical_images/sentinel2_l2a_mediterranean_fusion.tif"


@pytest.fixture
def clean_test_image(tmp_path):
    """Create a completely clean ocean SAR image with 0 oil spill pixels."""
    img_path = tmp_path / "clean_water.png"
    arr = np.full((256, 256, 3), 120, dtype=np.uint8)
    Image.fromarray(arr).save(img_path)
    return str(img_path)


def test_complete_vertical_slice_execution(tmp_path):
    """
    Test 1: Full deterministic vertical slice connecting all scientific modules end-to-end.
    """
    output_dir = str(tmp_path / "incidents")
    metadata = {
        "incident_id": "TEST_SLICE_001",
        "region_name": "Central Mediterranean Testbed",
        "product_id": "S1A_IW_GRDH_1SDV_20240823T094112_TEST",
        "acquisition_time": "2024-08-23T09:41:12Z",
        "image_path": SAMPLE_IMAGE,
        "bounding_box": [18.1, 34.3, 18.6, 34.7],
        "provenance": "REAL",
    }

    incident = run_incident_pipeline(
        scene_metadata=metadata,
        era5_path=ERA5_PATH,
        oscar_path=OSCAR_PATH,
        optical_path=OPTICAL_PATH,
        ais_scenario_id=1,
        output_dir=output_dir,
        device="cpu",
        confidence_threshold=0.3,
        allow_low_confidence=True,
    )

    # 1. Incident Identity & State
    assert incident.incident_id == "TEST_SLICE_001"
    assert incident.status == WatchState.INCIDENT_READY.value
    assert len(incident.execution_log) >= 8

    # 2. Satellite Observation
    assert incident.satellite_observation is not None
    assert incident.satellite_observation.product_id == metadata["product_id"]
    assert incident.satellite_observation.provenance == "REAL"
    assert incident.satellite_observation.acquisition_time == "2024-08-23T09:41:12Z"

    # 3. Spill Observation & Morphology
    assert incident.spill_observation is not None
    assert incident.spill_observation.detected is True
    assert incident.spill_observation.area_pixels > 0
    assert incident.spill_observation.area_km2 > 0.0
    assert incident.spill_observation.centroid is not None
    assert incident.spill_observation.polygon_geojson is not None
    assert incident.spill_observation.provenance == ProvenanceType.INFERRED.value

    # 4. Environmental Context & Optical Fusion
    assert incident.environmental_evidence is not None
    assert incident.environmental_evidence.provenance == ProvenanceType.REAL.value
    assert incident.environmental_evidence.bragg_regime in (
        "OPTIMAL_BRAGG_DAMPENING",
        "CALM_SEA_LOOKALIKE_RISK",
        "HIGH_WIND_DISPERSION_RISK",
    )
    assert incident.environmental_evidence.optical_checked is True

    # 5. Lagrangian Backward Drift Hindcast
    assert incident.hindcast_result is not None
    assert incident.hindcast_result.lookback_hours >= 3.0
    assert incident.hindcast_result.origin_centroid is not None
    assert incident.hindcast_result.confidence_95_polygon is not None
    assert incident.hindcast_result.provenance == ProvenanceType.INFERRED.value

    # 6. AIS Replay & Kinematics
    assert len(incident.candidates) > 0
    for cand in incident.candidates:
        assert cand.provenance == ProvenanceType.SIMULATED.value
        assert cand.mmsi > 0
        assert 0.0 <= cand.composite_score <= 1.0

    # 7. Attribution Decision
    assert incident.top_candidate is not None
    assert incident.top_candidate.attribution_decision in (
        "PRIMARY_SUSPECT",
        "PLAUSIBLE_CANDIDATE",
        "EXONERATED_SPATIALLY_DISJOINT",
        "EXONERATED_TEMPORALLY_INCOMPATIBLE",
    )

    # 8. Counterfactual Resilience
    assert incident.counterfactual_result is not None
    assert incident.counterfactual_result.tested is True
    assert incident.counterfactual_result.verdict in (
        "HIGH_PHYSICAL_CONSISTENCY",
        "MODERATE_PHYSICAL_CONSISTENCY",
        "SENSITIVE_TO_FORCING",
        "INCONSISTENT_HYPOTHESIS",
    )
    assert incident.counterfactual_result.provenance == ProvenanceType.INFERRED.value

    # 9. Forward Forecast
    assert incident.forecast_result is not None
    assert incident.forecast_result.forecast_hours == 12.0
    assert incident.forecast_result.future_centroid is not None
    assert incident.forecast_result.future_envelope_polygon is not None
    assert incident.forecast_result.provenance == ProvenanceType.INFERRED.value

    # 10. Reality Labels
    assert incident.reality_labels["Satellite"] == "REAL ARCHIVED (Sentinel-1 SAR)"
    assert incident.reality_labels["AIS"] == "SIMULATED REPLAY (Controlled Benchmark)"
    assert incident.reality_labels["Hindcast"] == "INFERRED (RK4 Backward Advection-Diffusion)"
    assert incident.reality_labels["Attribution"] == "MODEL-DERIVED (5-Factor Normalized)"

    # 11. Persistence Verification
    incident_file = Path(output_dir) / "TEST_SLICE_001.json"
    geojson_file = Path(output_dir) / "TEST_SLICE_001_layers.geojson"
    assert incident_file.exists()
    assert geojson_file.exists()

    with open(incident_file) as f:
        saved_doc = json.load(f)
    assert saved_doc["incident_id"] == "TEST_SLICE_001"
    assert saved_doc["status"] == "INCIDENT_READY"


def test_failure_path_no_spill(clean_test_image, tmp_path):
    """
    Test 2: Safe handling when zero spill pixels are detected.
    """
    metadata = {
        "incident_id": "TEST_NO_SPILL",
        "image_path": clean_test_image,
        "acquisition_time": "2024-08-23T09:41:12Z",
        "bounding_box": [18.1, 34.3, 18.6, 34.7],
    }
    incident = run_incident_pipeline(
        scene_metadata=metadata,
        output_dir=str(tmp_path),
        confidence_threshold=0.8,
    )
    assert incident.status == WatchState.NO_SPILL.value
    assert incident.spill_observation is not None
    assert incident.spill_observation.detected is False
    assert incident.hindcast_result is None
    assert len(incident.candidates) == 0


def test_failure_path_low_confidence_abstention(tmp_path):
    """
    Test 3: CleanSeaNet abstention when candidate confidence is INSUFFICIENT.
    """
    metadata = {
        "incident_id": "TEST_ABSTAIN",
        "image_path": SAMPLE_IMAGE,
        "acquisition_time": "2024-08-23T09:41:12Z",
        "bounding_box": [18.1, 34.3, 18.6, 34.7],
    }
    # Optical contradiction and calm sea specular reflection triggers CleanSeaNet abstention
    incident = run_incident_pipeline(
        scene_metadata=metadata,
        output_dir=str(tmp_path),
        allow_low_confidence=False,
        wind_speed_override=1.5,
        optical_eval_override={"status": "CONTRADICTED_BY_OPTICAL"},
    )
    assert incident.status == WatchState.FAILED.value
    assert incident.failure_reason is not None
    assert "Abstention" in incident.failure_reason or "confidence" in incident.failure_reason.lower()


def test_failure_path_missing_environmental_data(tmp_path):
    """
    Test 4: Safe failure when environmental forcing NetCDF files are missing.
    """
    metadata = {
        "incident_id": "TEST_MISSING_ENV",
        "image_path": SAMPLE_IMAGE,
        "acquisition_time": "2024-08-23T09:41:12Z",
        "bounding_box": [18.1, 34.3, 18.6, 34.7],
    }
    incident = run_incident_pipeline(
        scene_metadata=metadata,
        era5_path="nonexistent_era5.nc",
        oscar_path="nonexistent_oscar.nc",
        output_dir=str(tmp_path),
        allow_low_confidence=True,
    )
    assert incident.status == WatchState.FAILED.value
    assert incident.failure_reason is not None
    assert "Environmental" in incident.failure_reason


def test_failure_path_missing_ais_data(tmp_path):
    """
    Test 5: Safe failure when candidate AIS data is unavailable.
    """
    metadata = {
        "incident_id": "TEST_MISSING_AIS",
        "image_path": SAMPLE_IMAGE,
        "acquisition_time": "2024-08-23T09:41:12Z",
        "bounding_box": [18.1, 34.3, 18.6, 34.7],
    }
    incident = run_incident_pipeline(
        scene_metadata=metadata,
        ais_scenario_id=9999,
        ais_csv_path="nonexistent_ais.csv",
        output_dir=str(tmp_path),
        allow_low_confidence=True,
    )
    assert incident.status == WatchState.FAILED.value
    assert incident.failure_reason is not None
    assert "AIS" in incident.failure_reason or "unavailable" in incident.failure_reason.lower()


def test_failure_path_counterfactual_unavailable(tmp_path):
    """
    Test 6: Safe handling when counterfactual is bypassed (e.g. no suspect intersects).
    Scenario 05 represents a dark fleet where all broadcasting vessels are exonerated.
    """
    metadata = {
        "incident_id": "TEST_CF_BYPASS",
        "image_path": SAMPLE_IMAGE,
        "acquisition_time": "2024-08-23T09:41:12Z",
        "bounding_box": [18.1, 34.3, 18.6, 34.7],
    }
    incident = run_incident_pipeline(
        scene_metadata=metadata,
        ais_scenario_id=5,  # scenario 5: no candidate intersects release zone
        output_dir=str(tmp_path),
        allow_low_confidence=True,
    )
    assert incident.status == WatchState.INCIDENT_READY.value
    assert incident.counterfactual_result is not None
    assert incident.counterfactual_result.tested is False
    assert incident.counterfactual_result.verdict == "NOT_RUN"


def test_satellite_watch_deterministic_catalog():
    """
    Test 7: Satellite watcher catalog queries and ledger state tracking.
    """
    provider = FixtureCatalogProvider(fixtures=[
        {
            "product_id": "S1A_TEST_001",
            "acquisition_time": "2024-08-23T09:41:12Z",
            "bounding_box": [18.1, 34.3, 18.6, 34.7],
        },
        {
            "product_id": "S1A_TEST_002",
            "acquisition_time": "2024-08-24T09:41:12Z",
            "bounding_box": [18.1, 34.3, 18.6, 34.7],
        },
    ])

    watcher = SatelliteWatcher(catalog_provider=provider)

    # First poll -> NEW_PRODUCT (S1A_TEST_001)
    status1, prod1 = watcher.check_for_new_products()
    assert status1 == SatelliteWatchStatus.NEW_PRODUCT
    assert prod1["product_id"] == "S1A_TEST_001"

    # Second poll -> NEW_PRODUCT (S1A_TEST_002)
    status2, prod2 = watcher.check_for_new_products()
    assert status2 == SatelliteWatchStatus.NEW_PRODUCT
    assert prod2["product_id"] == "S1A_TEST_002"

    # Third poll -> DUPLICATE_PRODUCT (all seen)
    status3, prod3 = watcher.check_for_new_products()
    assert status3 == SatelliteWatchStatus.DUPLICATE_PRODUCT


def test_state_machine_transition_logging():
    """
    Test 8: Verification of transition audit logging across state machine.
    """
    sm = WatchStateMachine(initial_state=WatchState.MONITORING)
    assert sm.current_state == WatchState.MONITORING

    sm.transition(WatchState.NEW_PRODUCT, reason="Discovered S1 observation")
    assert sm.current_state == WatchState.NEW_PRODUCT

    sm.transition(WatchState.PROCESSING, reason="Model inference start")
    sm.transition(WatchState.SPILL_CONFIRMED, reason="High confidence slick")

    log = sm.get_log()
    assert len(log) == 4
    assert log[1]["from_state"] == "MONITORING"
    assert log[1]["to_state"] == "NEW_PRODUCT"
    assert log[1]["reason"] == "Discovered S1 observation"
