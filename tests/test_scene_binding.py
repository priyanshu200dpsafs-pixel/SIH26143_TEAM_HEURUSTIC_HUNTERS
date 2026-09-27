"""
Regression test suite for Per-Satellite-Scene Result Isolation and Map Data Binding.
Phase 6D verification.
"""

import pytest
from src.api.routes.satellite import (
    get_product_result,
    compute_geometry_hash,
    validate_scene_footprint,
    bbox_to_geojson_polygon,
)


def test_product_a_and_b_have_distinct_result_identity():
    """
    Verify Product A and Product B produce and bind to strictly isolated results,
    distinct footprints, distinct geometry hashes, and distinct acquisition times.
    """
    res_a = get_product_result("S1A_MED_001A")
    res_b = get_product_result("S1A_ION_002B")

    # Product identity isolation
    assert res_a["product_id"] == "S1A_MED_001A"
    assert res_b["product_id"] == "S1A_ION_002B"
    assert res_a["incident_id"] != res_b["incident_id"]

    # Acquisition time isolation
    assert res_a["acquisition_time"] == "2024-08-23T09:41:12Z"
    assert res_b["acquisition_time"] == "2024-08-24T17:22:05Z"
    assert res_a["acquisition_time"] != res_b["acquisition_time"]

    # Footprint isolation
    fp_a = res_a["scene_footprint"]
    fp_b = res_b["scene_footprint"]
    assert fp_a != fp_b
    assert fp_a["coordinates"] != fp_b["coordinates"]

    # Geometry & Hash isolation
    assert res_a["geometry"] is not None
    assert res_b["geometry"] is not None
    assert res_a["geometry_hash"] is not None
    assert res_b["geometry_hash"] is not None
    assert res_a["geometry_hash"] != res_b["geometry_hash"]

    # Centroid & Bbox isolation
    c_a = res_a["geometry_centroid"]
    c_b = res_b["geometry_centroid"]
    assert c_a != c_b
    assert res_a["geometry_bbox"] != res_b["geometry_bbox"]

    # Centroid strictly within respective footprints
    assert res_a["footprint_validation"] == "PASS"
    assert res_b["footprint_validation"] == "PASS"

    # Verify Central Med vs Ionian Sea coordinate ranges
    assert 18.1 <= c_a[0] <= 18.6
    assert 34.3 <= c_a[1] <= 34.7

    assert 19.2 <= c_b[0] <= 19.8
    assert 36.1 <= c_b[1] <= 36.6


def test_clean_scene_yields_no_spill():
    """
    Verify clean scene S1B_AEG_003C evaluates to NO_SPILL with zero artificial geometries.
    """
    res_c = get_product_result("S1B_AEG_003C")

    assert res_c["product_id"] == "S1B_AEG_003C"
    assert res_c["processing_status"] == "NO_SPILL"
    assert res_c["geometry"] is None
    assert res_c["geometry_hash"] is None
    assert res_c["geometry_centroid"] is None
    assert res_c["geometry_bbox"] is None
    assert res_c["footprint_validation"] == "PASS"

    # Scene footprint must be in Aegean Sea
    fp_c = res_c["scene_footprint"]
    coords = fp_c["coordinates"][0]
    min_lon = min(pt[0] for pt in coords)
    max_lon = max(pt[0] for pt in coords)
    assert min_lon == 24.1
    assert max_lon == 24.8


def test_footprint_mismatch_detection():
    """
    Verify footprint validation detects when a spill centroid lies outside the scene footprint.
    """
    scene_bbox = [18.1, 34.3, 18.6, 34.7]

    # Inside scene footprint -> PASS
    inside_centroid = [18.3, 34.5]
    assert validate_scene_footprint(inside_centroid, scene_bbox) == "PASS"

    # Outside scene footprint (e.g. Aegean coordinate in Central Med scene) -> MISMATCH
    outside_centroid = [24.5, 36.0]
    assert validate_scene_footprint(outside_centroid, scene_bbox) == "GEOMETRY_SCENE_MISMATCH"

    # Latitude outside -> MISMATCH
    lat_outside = [18.3, 36.0]
    assert validate_scene_footprint(lat_outside, scene_bbox) == "GEOMETRY_SCENE_MISMATCH"


def test_canonical_geometry_hashing():
    """
    Verify compute_geometry_hash is deterministic, key-order independent, and sensitive to coordinates.
    """
    geom1 = {
        "type": "Polygon",
        "coordinates": [[[18.1, 34.3], [18.6, 34.3], [18.6, 34.7], [18.1, 34.7], [18.1, 34.3]]]
    }
    # Same data, reversed dictionary insertion order
    geom1_alt = {
        "coordinates": [[[18.1, 34.3], [18.6, 34.3], [18.6, 34.7], [18.1, 34.7], [18.1, 34.3]]],
        "type": "Polygon"
    }
    # Different coordinates
    geom2 = {
        "type": "Polygon",
        "coordinates": [[[19.2, 36.1], [19.8, 36.1], [19.8, 36.6], [19.2, 36.6], [19.2, 36.1]]]
    }

    hash1 = compute_geometry_hash(geom1)
    hash1_alt = compute_geometry_hash(geom1_alt)
    hash2 = compute_geometry_hash(geom2)

    assert hash1 is not None
    assert hash1 == hash1_alt
    assert hash1 != hash2
    assert compute_geometry_hash(None) is None
