"""
Deterministic Verification Suite for Real Sentinel-1 SAR Processing (Phase 7A).

Validates all 14 mandatory Section 25 invariants:
1. Real product metadata preservation
2. Download validation (SHA-256 & integrity)
3. Raster extraction & nodata masking
4. Preprocessing metadata completeness
5. Real scene identity & deterministic binding
6. U-Net model invocation
7. No-spill result (zero-polygon guarantee)
8. Spill candidate result & morphology
9. Geometry-footprint spatial consistency
10. Incident provenance categorization
11. Real vs Replay UI/API separation
12. Stale geometry prevention
13. Environmental timestamp validation (ERA5 alignment & graceful degradation)
14. AIS provenance separation & non-fabrication
"""

import json
from pathlib import Path
import pytest
import numpy as np

from src.detection.sar_segmentation import SARSARSegmentor
from src.detection.sentinel1_real_preprocessing import (
    Sentinel1RealPreprocessor,
    PreprocessingMetadata,
    RealSARSourceType,
)
from src.detection.spill_properties import extract_spill_detections, estimate_spill_age_fay
from src.detection.confidence_estimator import ConfidenceEstimator
from src.api.routes.satellite import compute_geometry_hash, validate_scene_footprint, get_product_result
from src.api.routes.incidents import list_incidents
from scripts.process_real_sentinel1 import (
    check_environmental_forcing,
    process_real_sentinel1_product,
)


@pytest.fixture
def real_audit_data():
    audit_path = Path("data/results/satellite/real_scene_audit.json")
    assert audit_path.exists(), "real_scene_audit.json must exist"
    with open(audit_path) as f:
        return json.load(f)


def test_1_real_product_metadata_preservation(real_audit_data):
    scenes = real_audit_data.get("scenes", [])
    assert len(scenes) >= 3, "Must audit at least 3 genuine Sentinel-1 products"
    for sc in scenes:
        assert sc["product_id"], "Product ID must be preserved"
        assert sc["product_name"].startswith("S1A_IW_GRDH"), "Must be Sentinel-1 IW GRD"
        assert sc["sensor"] == "C-SAR / Sentinel-1"
        assert "T" in sc["acquisition_time"], "Valid ISO timestamp required"
        assert len(sc["bbox"]) == 4, "Must have valid bounding box (min_lon, min_lat, max_lon, max_lat)"
        assert sc["footprint"] is not None, "Footprint polygon must be preserved"


def test_2_download_validation(real_audit_data):
    for sc in real_audit_data["scenes"]:
        assert sc["download_status"] == "SUCCESS"
        assert sc["file_size"] > 0, "File size must be strictly positive"
        assert len(sc["sha256"]) == 64, "Must have valid SHA-256 checksum"
        structure = sc["structure_verified"]
        assert structure["manifest_safe"] is True
        assert structure["quick_look_png"] is True
        assert structure["annotation_xml"] is True


def test_3_raster_extraction():
    pre = Sentinel1RealPreprocessor()
    res = pre.preprocess_scene("data/satellite/sentinel1_real/3bdfd698-b3bb-47b2-920f-b18bc76643b3")
    assert res.success is True
    assert res.normalized_array is not None
    assert res.normalized_array.ndim == 3
    assert res.normalized_array.shape[-1] == 3
    assert res.metadata.nodata_pixel_count > 0, "Must detect border nodata pixels"


def test_4_preprocessing_metadata():
    pre = Sentinel1RealPreprocessor()
    res = pre.preprocess_scene("data/satellite/sentinel1_real/3bdfd698-b3bb-47b2-920f-b18bc76643b3")
    meta = res.metadata
    assert meta.bands == 3
    assert meta.shape[0] > 0 and meta.shape[1] > 0
    assert 0.0 <= meta.min_value <= meta.max_value <= 1.0
    assert len(meta.processing_steps) >= 4
    assert any("Normalized" in s for s in meta.processing_steps)


def test_5_real_scene_identity():
    hash1 = compute_geometry_hash({"type": "Polygon", "coordinates": [[[10, 20], [11, 20], [11, 21], [10, 20]]]})
    hash2 = compute_geometry_hash({"type": "Polygon", "coordinates": [[[10, 20], [11, 20], [11, 21], [10, 20]]]})
    hash3 = compute_geometry_hash({"type": "Polygon", "coordinates": [[[15, 25], [16, 25], [16, 26], [15, 25]]]})
    assert hash1 == hash2, "Identical geometries must produce identical hashes"
    assert hash1 != hash3, "Different geometries must produce distinct hashes"


def test_6_unet_invocation():
    segmentor = SARSARSegmentor("models/sar_unet_baseline_best.pt")
    dummy_chip = np.zeros((256, 256, 3), dtype=np.float32)
    dummy_chip[50:100, 50:100, :] = 0.8
    out = segmentor.segment(dummy_chip)
    assert "class_mask" in out
    assert "oil_mask" in out
    assert "probabilities" in out
    assert out["oil_mask"].shape == (256, 256)


def test_7_no_spill_result():
    oil_mask = np.zeros((256, 256), dtype=np.uint8)
    dets = extract_spill_detections(oil_mask, pixel_resolution_meters=50.0)
    assert len(dets) == 0, "No spill detections should be extracted from zero mask"


def test_8_spill_candidate_result():
    oil_mask = np.zeros((256, 256), dtype=np.uint8)
    oil_mask[40:80, 50:110] = 1
    dets = extract_spill_detections(oil_mask, pixel_resolution_meters=50.0, min_area_pixels=25)
    assert len(dets) == 1
    d = dets[0]
    assert d.area_pixels == 2400
    assert d.area_km2 > 0.0
    age = estimate_spill_age_fay(d.area_km2 * 1e6)
    assert age > 0.0


def test_9_geometry_footprint_consistency():
    bbox = [16.0, 33.0, 19.0, 36.0]
    pass_res = validate_scene_footprint(centroid=[17.5, 34.5], bbox=bbox)
    assert pass_res == "PASS"

    fail_res = validate_scene_footprint(centroid=[25.0, 40.0], bbox=bbox)
    assert fail_res == "GEOMETRY_SCENE_MISMATCH"


def test_10_incident_provenance():
    inc_dir = Path("data/results/incidents")
    real_inc = inc_dir / "INC_3BDFD698.json"
    assert real_inc.exists()
    with open(real_inc) as f:
        data = json.load(f)
    assert data.get("provenance_category") == "REAL"
    assert "REAL OBSERVATION" in data.get("reality_labels", {}).get("Satellite", "")


def test_11_real_vs_replay_separation():
    res_real = list_incidents(provenance_category="REAL")
    for inc in res_real["incidents"]:
        assert inc["provenance_category"] == "REAL"

    res_bench = list_incidents(provenance_category="BENCHMARK")
    for inc in res_bench["incidents"]:
        assert inc["provenance_category"] in ("BENCHMARK", "TEST")


def test_12_stale_geometry_prevention():
    res1 = get_product_result("3bdfd698-b3bb-47b2-920f-b18bc76643b3")
    res2 = get_product_result("5847827e-1714-4492-ab36-39c2913c7f79")
    assert res1["product_id"] != res2["product_id"]
    assert res1["incident_id"] != res2["incident_id"]
    assert res1["geometry_hash"] != res2["geometry_hash"], "Different scenes must not share geometry hashes"


def test_13_environmental_timestamp_validation():
    aligned_status, wind, meta = check_environmental_forcing("2024-08-23T16:47:34Z", [17.0, 33.5, 19.5, 35.0])
    assert aligned_status == "ALIGNED"
    assert wind is not None and wind > 0

    unavail_status, wind2, meta2 = check_environmental_forcing("2022-01-01T00:00:00Z", [17.0, 33.5, 19.5, 35.0])
    assert unavail_status == "ENVIRONMENTAL DATA UNAVAILABLE"
    assert wind2 is None


def test_14_ais_provenance_separation():
    real_inc = Path("data/results/incidents/INC_3BDFD698.json")
    with open(real_inc) as f:
        data = json.load(f)
    ais_label = data.get("reality_labels", {}).get("AIS", "")
    assert "SIMULATED" not in data.get("satellite_observation", {}).get("provenance", "")
    assert "REAL LIVE" in ais_label or "INSUFFICIENT" in ais_label or "HISTORICAL" in ais_label
