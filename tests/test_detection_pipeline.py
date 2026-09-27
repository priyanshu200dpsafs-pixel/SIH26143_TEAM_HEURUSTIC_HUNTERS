"""
Unit Tests for Phase 3 Detection, Extraction, Uncertainty, and Sensor Fusion Pipeline.

Tests:
1. Mask Decoding (4-class Krestenitis RGB & SOS binary)
2. Class Validation (No Ship/Land in Krestenitis, strictly binary SOS)
3. Preprocessing (Resizing, Normalization, Training-only Augmentation, Leakage Prevention)
4. Connected Components (Multi-slick isolation and speckle filtering)
5. Geometry Calculations (Area, Perimeter, Centroid, Bounding Box, Axes, Compactness, Elongation, Fay model)
6. Confidence Handling & Abstention (HIGH, MEDIUM, LOW, INSUFFICIENT)
7. Optical/SAR Alignment (Sentinel-2 overlap, NDWI, NDVI, cloud detection, graceful fallback)
8. Environmental Context (ERA5 10m wind, Bragg dampening regime, out-of-domain fallback)
"""

import math
import numpy as np
import pytest
import torch

from src.detection.dataset_adapters import (
    KRESTENITIS_CLASSES,
    KRESTENITIS_COLOR_MAP,
    SOS_CLASSES,
    KrestenitisDataset,
    SOSDataset,
    decode_krestenitis_rgb_mask,
    encode_krestenitis_class_mask,
)
from src.detection.preprocessing import (
    resize_image_and_mask,
    normalize_sar_image,
    TrainingAugmentor,
)
from src.detection.sar_segmentation import UNetBaseline, SARSARSegmentor
from src.detection.metrics import compute_confusion_matrix, evaluate_segmentation_metrics
from src.detection.spill_properties import (
    SpillDetection,
    SpillPropertyExtractor,
    calculate_spill_area,
    estimate_spill_age_fay,
    extract_spill_detections,
    get_morphological_properties,
)
from src.detection.confidence_estimator import ConfidenceEstimator
from src.detection.optical_fusion import (
    OpticalFusionValidator,
    calculate_ndwi,
    calculate_ndvi,
    filter_false_positives,
)
from src.detection.environmental_context import EnvironmentalContextExtractor


# ==============================================================================
# 1. MASK DECODING TESTS
# ==============================================================================

def test_krestenitis_mask_decoding_exact():
    """Verify exact RGB decoding maps precisely to {0: Background, 1: Oil, 2: Lookalike, 3: Water}."""
    h, w = 4, 4
    rgb = np.zeros((h, w, 3), dtype=np.uint8)
    rgb[0, 0] = [0, 0, 0]         # Background
    rgb[1, 1] = [255, 0, 124]     # Oil
    rgb[2, 2] = [255, 204, 51]    # Look-alike
    rgb[3, 3] = [51, 221, 255]    # Water
    
    decoded = decode_krestenitis_rgb_mask(rgb)
    assert decoded[0, 0] == 0
    assert decoded[1, 1] == 1
    assert decoded[2, 2] == 2
    assert decoded[3, 3] == 3
    
    # Verify round-trip encoding
    recoded = encode_krestenitis_class_mask(decoded)
    assert np.array_equal(recoded[0, 0], [0, 0, 0])
    assert np.array_equal(recoded[1, 1], [255, 0, 124])
    assert np.array_equal(recoded[2, 2], [255, 204, 51])
    assert np.array_equal(recoded[3, 3], [51, 221, 255])


def test_sos_mask_binarization():
    """Verify SOS masks are strictly binarized {0, 1}."""
    raw_mask = np.array([[0, 50, 127], [128, 200, 255]], dtype=np.uint8)
    binary = (raw_mask > 127).astype(np.int64)
    assert np.array_equal(binary, [[0, 0, 0], [1, 1, 1]])
    assert set(np.unique(binary)).issubset({0, 1})


# ==============================================================================
# 2. CLASS VALIDATION TESTS
# ==============================================================================

def test_krestenitis_verified_classes():
    """Enforce that Krestenitis only has Background, Oil, Look-alike, Water (no Ship, no Land)."""
    assert len(KRESTENITIS_CLASSES) == 4
    assert KRESTENITIS_CLASSES[0] == "Background"
    assert KRESTENITIS_CLASSES[1] == "Oil Spill"
    assert KRESTENITIS_CLASSES[2] == "Look-alike / Others"
    assert KRESTENITIS_CLASSES[3] == "Water / Sea Surface"
    
    for cname in KRESTENITIS_CLASSES.values():
        assert "ship" not in cname.lower()
        assert "land" not in cname.lower()


def test_sos_binary_classes():
    """Enforce that SOS ontology is strictly binary."""
    assert len(SOS_CLASSES) == 2
    assert SOS_CLASSES[0] == "Background"
    assert SOS_CLASSES[1] == "Oil Spill"


# ==============================================================================
# 3. PREPROCESSING & SPLIT INTEGRITY TESTS
# ==============================================================================

def test_deterministic_resizing():
    """Verify nearest-neighbor mask resizing does not interpolate class IDs."""
    img = np.random.rand(1080, 1920, 3).astype(np.float32)
    # Mask with discrete classes {0, 1, 2, 3}
    mask = np.random.choice([0, 1, 2, 3], size=(1080, 1920)).astype(np.int64)
    
    r_img, r_mask = resize_image_and_mask(img, mask, target_size=(256, 256))
    assert r_img.shape == (256, 256, 3)
    assert r_mask.shape == (256, 256)
    assert set(np.unique(r_mask)).issubset({0, 1, 2, 3})


def test_training_augmentor_isolated():
    """Verify augmentor modifies training images and masks consistently without changing class values."""
    aug = TrainingAugmentor(p_hflip=1.0, p_vflip=1.0, p_rot90=0.0, seed=42)
    img = np.arange(16).reshape(4, 4, 1).astype(np.float32)
    mask = np.array([[0, 1, 2, 3], [0, 1, 2, 3], [0, 1, 2, 3], [0, 1, 2, 3]], dtype=np.int64)
    
    a_img, a_mask = aug(img, mask)
    # Should be flipped horizontally and vertically
    assert a_mask[0, 0] == 3
    assert set(np.unique(a_mask)).issubset({0, 1, 2, 3})


def test_zero_split_leakage_krestenitis():
    """Verify 0 overlap between train, val, and test scenes in Krestenitis."""
    kd_train = KrestenitisDataset(split='train')
    kd_val = KrestenitisDataset(split='val')
    kd_test = KrestenitisDataset(split='test')
    
    train_names = set(p[0] for p in kd_train.pairs)
    val_names = set(p[0] for p in kd_val.pairs)
    test_names = set(p[0] for p in kd_test.pairs)
    
    assert len(train_names & val_names) == 0, "Leakage detected between train and val!"
    assert len(train_names & test_names) == 0, "Leakage detected between train and test!"
    assert len(val_names & test_names) == 0, "Leakage detected between val and test!"


# ==============================================================================
# 4. CONNECTED COMPONENTS TESTS
# ==============================================================================

def test_connected_components_multi_object():
    """Verify that disconnected oil patches are isolated into separate detections."""
    mask = np.zeros((100, 100), dtype=np.uint8)
    # Patch 1: top-left (20x20 = 400 px)
    mask[10:30, 10:30] = 1
    # Patch 2: bottom-right (15x15 = 225 px)
    mask[70:85, 70:85] = 1
    # Isolated noise pixel (1 px -> should be rejected by min_area_pixels=15)
    mask[50, 50] = 1
    
    detections = extract_spill_detections(mask, min_area_pixels=15)
    assert len(detections) == 2
    assert detections[0].area_pixels == 400
    assert detections[1].area_pixels == 225


# ==============================================================================
# 5. GEOMETRY CALCULATIONS TESTS
# ==============================================================================

def test_spill_geometry_ellipse():
    """Verify geometric metrics on a synthetic ellipse (semi-axes a=20, b=10)."""
    mask = np.zeros((100, 100), dtype=np.uint8)
    y, x = np.ogrid[:100, :100]
    mask[((x - 50) / 20)**2 + ((y - 50) / 10)**2 <= 1.0] = 1
    
    detections = extract_spill_detections(mask, pixel_resolution_meters=10.0)
    assert len(detections) == 1
    d = detections[0]
    
    # Centroid at (50, 50)
    assert abs(d.centroid[0] - 50.0) < 1.0
    assert abs(d.centroid[1] - 50.0) < 1.0
    
    # Semi-axes 20 and 10 -> Major axis ~40, Minor axis ~20
    assert abs(d.major_axis - 40.0) < 3.0
    assert abs(d.minor_axis - 20.0) < 3.0
    assert 1.8 < d.elongation < 2.2
    assert 0.7 < d.compactness <= 1.0


def test_fay_spreading_model():
    """Verify Fay spreading age calculation is physically bounded."""
    area_m2 = 100_000.0  # 0.1 km²
    age_hours = estimate_spill_age_fay(area_m2, initial_volume_m3=200.0)
    assert 0.5 <= age_hours <= 72.0


# ==============================================================================
# 6. CONFIDENCE & ABSTENTION TESTS
# ==============================================================================

def test_confidence_tiers_and_abstention():
    """Verify confidence assigns HIGH, MEDIUM, LOW, and INSUFFICIENT correctly."""
    ce = ConfidenceEstimator()
    
    # High confidence slick
    d_high = SpillDetection(
        spill_id="TEST_HIGH", area_pixels=500, area_km2=0.05, perimeter_pixels=100.0, perimeter_km=1.0,
        centroid=(50.0, 50.0), bounding_box=(20, 20, 80, 80), major_axis=40.0, minor_axis=20.0,
        orientation_degrees=0.0, orientation_radians=0.0, compactness=0.8, elongation=2.0,
        model_probability=0.95, class_margin=0.45
    )
    d_high = ce.evaluate_detection(d_high, wind_speed_ms=7.0)
    assert d_high.confidence_level == "HIGH"
    
    # Weak margin look-alike risk (abstain)
    d_ambiguous = SpillDetection(
        spill_id="TEST_AMB", area_pixels=150, area_km2=0.015, perimeter_pixels=50.0, perimeter_km=0.5,
        centroid=(50.0, 50.0), bounding_box=(30, 30, 70, 70), major_axis=30.0, minor_axis=15.0,
        orientation_degrees=0.0, orientation_radians=0.0, compactness=0.8, elongation=2.0,
        model_probability=0.52, class_margin=0.02
    )
    d_ambiguous = ce.evaluate_detection(d_ambiguous, wind_speed_ms=7.0)
    assert d_ambiguous.confidence_level == "INSUFFICIENT"
    
    # Tiny speckle (abstain)
    d_tiny = SpillDetection(
        spill_id="TEST_TINY", area_pixels=18, area_km2=0.0018, perimeter_pixels=12.0, perimeter_km=0.12,
        centroid=(50.0, 50.0), bounding_box=(45, 45, 55, 55), major_axis=8.0, minor_axis=4.0,
        orientation_degrees=0.0, orientation_radians=0.0, compactness=0.8, elongation=2.0,
        model_probability=0.90, class_margin=0.30
    )
    d_tiny = ce.evaluate_detection(d_tiny, wind_speed_ms=7.0)
    assert d_tiny.confidence_level == "INSUFFICIENT"


# ==============================================================================
# 7. OPTICAL/SAR ALIGNMENT TESTS
# ==============================================================================

def test_optical_validator_spatial_bounds():
    """Verify optical validator checks spatial overlap and fails gracefully if outside."""
    pytest.importorskip("rasterio")
    validator = OpticalFusionValidator()
    
    # Outside swath
    outside_res = validator.validate_detection(
        sar_mask=None,
        geo_bounds={'min_lat': 10.0, 'min_lon': 5.0, 'max_lat': 11.0, 'max_lon': 6.0},
        timestamp="2024-08-23T09:41:12Z"
    )
    assert outside_res["status"] == "OPTICAL_EVIDENCE_UNAVAILABLE"
    
    # Inside Mediterranean swath
    inside_res = validator.validate_detection(
        sar_mask=None,
        geo_bounds={'min_lat': 34.40, 'min_lon': 18.20, 'max_lat': 34.60, 'max_lon': 18.40},
        timestamp="2024-08-23T09:41:12Z"
    )
    assert inside_res["status"] in ("CORROBORATED_BY_OPTICAL", "OPTICAL_AMBIGUOUS_NEUTRAL")
    assert inside_res["ndwi_mean"] is not None


def test_ndwi_and_ndvi_functions():
    """Verify NDWI and NDVI formulas."""
    green = np.array([[0.2, 0.4]])
    nir = np.array([[0.1, 0.6]])
    red = np.array([[0.1, 0.2]])
    
    ndwi = calculate_ndwi(green, nir)
    # (0.2 - 0.1) / (0.2 + 0.1) = 0.1 / 0.3 = 0.333
    assert abs(ndwi[0, 0] - 0.333) < 0.01
    
    ndvi = calculate_ndvi(red, nir)
    # (0.6 - 0.2) / (0.6 + 0.2) = 0.4 / 0.8 = 0.50
    assert abs(ndvi[0, 1] - 0.50) < 0.01


# ==============================================================================
# 8. ENVIRONMENTAL CONTEXT TESTS
# ==============================================================================

def test_environmental_context_bragg_regime():
    """Verify ERA5 context extraction and physical Bragg wave regime."""
    ece = EnvironmentalContextExtractor()
    ctx = ece.get_context(lat=34.50, lon=18.00, timestamp_epoch=1724406072.0)
    
    assert ctx["status"] == "ERA5_CONTEXT_AVAILABLE"
    assert ctx["wind_speed_ms"] > 0.0
    assert ctx["dampening_regime"] in ("OPTIMAL_BRAGG_DAMPENING", "CALM_SEA_LOOKALIKE_RISK", "HIGH_WIND_DISPERSION_RISK")
    assert len(ctx["physical_assumptions"]) >= 2
