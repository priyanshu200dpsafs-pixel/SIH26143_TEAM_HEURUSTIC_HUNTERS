"""Unit tests for detection and property extraction module."""

import pytest
from src.detection.sar_segmentation import SARSARSegmentor
from src.detection.optical_fusion import OpticalFusionValidator
from src.detection.spill_properties import SpillPropertyExtractor


def test_sar_segmentor_initialization():
    """Verify SARSARSegmentor instantiates with defaults."""
    segmentor = SARSARSegmentor(device="cpu")
    assert segmentor.device == "cpu"
    assert segmentor.model is None


def test_optical_validator_initialization():
    """Verify OpticalFusionValidator instantiates."""
    validator = OpticalFusionValidator()
    assert validator.optical_data_dir is None


def test_spill_property_extractor_initialization():
    """Verify SpillPropertyExtractor resolution configuration."""
    extractor = SpillPropertyExtractor(pixel_resolution_meters=12.5)
    assert extractor.pixel_res == 12.5


def test_unimplemented_stubs_raise_not_implemented():
    """Verify scaffold functions raise NotImplementedError until implemented."""
    segmentor = SARSARSegmentor()
    with pytest.raises(NotImplementedError):
        segmentor.segment("dummy.tif")
