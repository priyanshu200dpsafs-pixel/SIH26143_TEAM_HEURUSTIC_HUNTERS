"""
Detection and Characterization Module.

Handles SAR oil slick segmentation (Sentinel-1), optical cross-validation (Sentinel-2),
and geometric/physical property extraction (Fay spreading age, slick area, elongation).
"""

from .sar_segmentation import SARSARSegmentor, UNetBaseline, preprocess_sar_image, predict_spill_mask
from .optical_fusion import OpticalFusionValidator, calculate_ndwi, calculate_ndvi, filter_false_positives
from .spill_properties import SpillPropertyExtractor, SpillDetection, calculate_spill_area, estimate_spill_age_fay, extract_spill_detections, get_morphological_properties
from .dataset_adapters import KrestenitisDataset, SOSDataset, KRESTENITIS_CLASSES, SOS_CLASSES, decode_krestenitis_rgb_mask, encode_krestenitis_class_mask
from .preprocessing import resize_image_and_mask, normalize_sar_image, TrainingAugmentor
from .metrics import compute_confusion_matrix, evaluate_segmentation_metrics
from .confidence_estimator import ConfidenceEstimator
from .environmental_context import EnvironmentalContextExtractor
