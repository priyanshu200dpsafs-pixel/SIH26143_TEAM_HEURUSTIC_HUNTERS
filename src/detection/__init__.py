"""
Detection and Characterization Module.

Handles SAR oil slick segmentation (Sentinel-1), optical cross-validation (Sentinel-2),
and geometric/physical property extraction (Fay spreading age, slick area, elongation).
"""

from .sar_segmentation import SARSARSegmentor, preprocess_sar_image, predict_spill_mask
from .optical_fusion import OpticalFusionValidator, calculate_ndwi, filter_false_positives
from .spill_properties import SpillPropertyExtractor, calculate_spill_area, estimate_spill_age_fay

__all__ = [
    "SARSARSegmentor",
    "preprocess_sar_image",
    "predict_spill_mask",
    "OpticalFusionValidator",
    "calculate_ndwi",
    "filter_false_positives",
    "SpillPropertyExtractor",
    "calculate_spill_area",
    "estimate_spill_age_fay",
]
