"""
Spill Object Extraction, Morphological Profiling, and Spreading Dynamics.

Extracts connected components from predicted oil segmentation masks and computes:
- Surface Area (pixels and km²)
- Perimeter (pixels and km)
- Centroid (pixel and normalized coordinates)
- Bounding Box (min_x, min_y, max_x, max_y)
- Major & Minor Axis lengths (via second central moments / inertia tensor)
- Principal Orientation angle (radians and degrees)
- Compactness (isoperimetric quotient: 4 * pi * Area / Perimeter²)
- Elongation (Major Axis / Minor Axis)

Encapsulates individual slicks in the canonical SpillDetection schema.
Also provides Fay spreading model estimations for temporal release age.
"""

from dataclasses import asdict, dataclass, field
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
from scipy import ndimage


@dataclass
class SpillDetection:
    """
    Canonical schema for an extracted SAR oil spill detection object.
    """
    spill_id: str
    area_pixels: int
    area_km2: float
    perimeter_pixels: float
    perimeter_km: float
    centroid: Tuple[float, float]            # (x, y) = (column, row)
    bounding_box: Tuple[int, int, int, int]  # (min_x, min_y, max_x, max_y)
    major_axis: float
    minor_axis: float
    orientation_degrees: float
    orientation_radians: float
    compactness: float                       # 4 * pi * Area / Perimeter²
    elongation: float                        # Major Axis / Minor Axis
    confidence_level: str = "MEDIUM"         # HIGH, MEDIUM, LOW, INSUFFICIENT
    model_probability: float = 0.0
    segmentation_confidence: float = 0.0
    class_margin: float = 0.0
    environmental_consistency: Dict[str, Any] = field(default_factory=dict)
    optical_evidence: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


def calculate_spill_area(
    binary_mask: np.ndarray,
    pixel_resolution_m: float = 10.0,
) -> float:
    """
    Calculate total surface area of spill in square kilometers.
    
    Args:
        binary_mask: 2D binary segmentation mask.
        pixel_resolution_m: Pixel ground sampling distance in meters.
        
    Returns:
        Surface area in square kilometers (km²).
    """
    pixel_count = int(np.sum(binary_mask > 0))
    area_m2 = pixel_count * (pixel_resolution_m ** 2)
    return float(area_m2 / 1e6)


def estimate_spill_age_fay(
    area_m2: float,
    initial_volume_m3: float = 100.0,
    kinematic_viscosity: float = 1e-5,
    density_ratio_delta: float = 0.15,
) -> float:
    """
    Estimate spill elapsed time using Fay's spreading model.
    
    Phases:
    1. Gravity-Inertial phase: r ~ (Delta * g * V * t²)^(1/4)
    2. Gravity-Viscous phase:  r ~ (Delta * g * V² * t^(3/2) / nu^(1/2))^(1/6)
    3. Surface Tension-Viscous: r ~ (sigma² * t³ / (rho_w² * nu))^(1/4)
    
    Using the gravity-viscous spreading regime (most representative for hours 1 to 24):
    r(t) = k_2 * (Delta * g * V² / sqrt(nu))^(1/6) * t^(1/4)
    where k_2 ~ 1.14.
    
    Args:
        area_m2: Measured surface area in square meters.
        initial_volume_m3: Estimated discharge volume in cubic meters.
        kinematic_viscosity: Kinematic viscosity of seawater (~1e-6 to 1e-5 m²/s).
        density_ratio_delta: (rho_water - rho_oil) / rho_water (~0.10 to 0.20).
        
    Returns:
        Estimated elapsed release age in hours.
    """
    if area_m2 <= 0:
        return 0.0
        
    g = 9.81
    k2 = 1.14
    radius = math.sqrt(area_m2 / math.pi)
    
    # Invert r(t) = k2 * [ (Delta * g * V^2) / sqrt(nu) ]^(1/6) * t^(1/4)
    c_factor = (density_ratio_delta * g * (initial_volume_m3 ** 2) / math.sqrt(kinematic_viscosity)) ** (1.0 / 6.0)
    if c_factor <= 0:
        return 0.0
        
    t_seconds = (radius / (k2 * c_factor)) ** 4.0
    # Bound to physically plausible window [0.1, 72.0] hours
    t_hours = float(np.clip(t_seconds / 3600.0, 0.1, 72.0))
    return t_hours


def get_morphological_properties(binary_mask: np.ndarray) -> Dict[str, float]:
    """
    Extract aggregate morphological shape factors from a binary mask.
    """
    if np.sum(binary_mask > 0) == 0:
        return {
            "area_pixels": 0,
            "perimeter_pixels": 0.0,
            "compactness": 0.0,
            "elongation": 1.0,
            "major_axis": 0.0,
            "minor_axis": 0.0,
            "orientation_degrees": 0.0,
        }
        
    # Boundary extraction via morphological gradient
    eroded = ndimage.binary_erosion(binary_mask)
    boundary = (binary_mask.astype(bool) ^ eroded)
    perimeter = float(np.sum(boundary))
    area = float(np.sum(binary_mask > 0))
    
    # Compactness (isoperimetric quotient)
    compactness = float(4.0 * math.pi * area / (perimeter ** 2)) if perimeter > 0 else 0.0
    compactness = float(np.clip(compactness, 0.0, 1.0))
    
    # Moments of inertia for major/minor axis and orientation
    y_indices, x_indices = np.where(binary_mask > 0)
    x_mean = float(np.mean(x_indices))
    y_mean = float(np.mean(y_indices))
    
    x_c = x_indices - x_mean
    y_c = y_indices - y_mean
    
    mu20 = float(np.mean(x_c ** 2))
    mu02 = float(np.mean(y_c ** 2))
    mu11 = float(np.mean(x_c * y_c))
    
    # Eigenvalues of 2D covariance
    common = math.sqrt((mu20 - mu02) ** 2 + 4.0 * (mu11 ** 2))
    lambda1 = (mu20 + mu02 + common) / 2.0
    lambda2 = max(0.0, (mu20 + mu02 - common) / 2.0)
    
    major_axis = float(4.0 * math.sqrt(max(0.0, lambda1)))
    minor_axis = float(4.0 * math.sqrt(max(0.0, lambda2)))
    elongation = float(major_axis / max(minor_axis, 1e-3))
    
    # Orientation
    angle_rad = 0.5 * math.atan2(2.0 * mu11, mu20 - mu02)
    angle_deg = float(math.degrees(angle_rad))
    
    return {
        "area_pixels": int(area),
        "perimeter_pixels": round(perimeter, 2),
        "compactness": round(compactness, 4),
        "elongation": round(elongation, 4),
        "major_axis": round(major_axis, 2),
        "minor_axis": round(minor_axis, 2),
        "orientation_degrees": round(angle_deg, 2),
    }


def extract_spill_detections(
    oil_binary_mask: np.ndarray,
    pixel_resolution_meters: float = 10.0,
    min_area_pixels: int = 15,
    probabilities: Optional[np.ndarray] = None,
    lookalike_probabilities: Optional[np.ndarray] = None,
) -> List[SpillDetection]:
    """
    Decompose predicted oil mask into discrete connected component objects
    and calculate complete geometric and morphological attributes.
    
    Args:
        oil_binary_mask: 2D binary array where 1 = Oil.
        pixel_resolution_meters: Spatial pixel resolution (GSD) in meters.
        min_area_pixels: Minimum pixel threshold to reject speckle noise.
        probabilities: Optional predicted oil probability map (H, W).
        lookalike_probabilities: Optional predicted look-alike probability map (H, W).
        
    Returns:
        List of canonical SpillDetection objects.
    """
    # 8-connectivity structuring element
    struct = np.ones((3, 3), dtype=bool)
    labeled_mask, num_features = ndimage.label(oil_binary_mask > 0, structure=struct)
    
    detections: List[SpillDetection] = []
    
    for obj_id in range(1, num_features + 1):
        obj_mask = (labeled_mask == obj_id)
        area_px = int(np.sum(obj_mask))
        if area_px < min_area_pixels:
            continue
            
        area_km2 = float(area_px * (pixel_resolution_meters ** 2) / 1e6)
        
        # Perimeter via boundary pixels
        eroded = ndimage.binary_erosion(obj_mask)
        boundary = (obj_mask ^ eroded)
        perim_px = float(np.sum(boundary))
        perim_km = float(perim_px * pixel_resolution_meters / 1000.0)
        
        # Centroid
        y_coords, x_coords = np.where(obj_mask)
        cx = float(np.mean(x_coords))
        cy = float(np.mean(y_coords))
        
        # Bounding box
        min_x = int(np.min(x_coords))
        max_x = int(np.max(x_coords))
        min_y = int(np.min(y_coords))
        max_y = int(np.max(y_coords))
        
        # Inertia moments for axis and orientation
        xc = x_coords - cx
        yc = y_coords - cy
        mu20 = float(np.mean(xc ** 2))
        mu02 = float(np.mean(yc ** 2))
        mu11 = float(np.mean(xc * yc))
        
        common = math.sqrt((mu20 - mu02) ** 2 + 4.0 * (mu11 ** 2))
        lambda1 = (mu20 + mu02 + common) / 2.0
        lambda2 = max(0.0, (mu20 + mu02 - common) / 2.0)
        
        major_axis = float(4.0 * math.sqrt(max(0.0, lambda1)))
        minor_axis = float(4.0 * math.sqrt(max(0.0, lambda2)))
        elongation = float(major_axis / max(minor_axis, 1e-3))
        
        angle_rad = 0.5 * math.atan2(2.0 * mu11, mu20 - mu02)
        angle_deg = float(math.degrees(angle_rad))
        
        compactness = float(4.0 * math.pi * area_px / (perim_px ** 2)) if perim_px > 0 else 0.0
        compactness = float(np.clip(compactness, 0.0, 1.0))
        
        # Probability & Margin extraction if provided
        mean_p = float(np.mean(probabilities[obj_mask])) if probabilities is not None else 0.85
        margin = 0.5
        if probabilities is not None and lookalike_probabilities is not None:
            mean_la = float(np.mean(lookalike_probabilities[obj_mask]))
            margin = mean_p - mean_la
            
        spill = SpillDetection(
            spill_id=f"SPILL_{obj_id:03d}",
            area_pixels=area_px,
            area_km2=round(area_km2, 6),
            perimeter_pixels=round(perim_px, 2),
            perimeter_km=round(perim_km, 4),
            centroid=(round(cx, 2), round(cy, 2)),
            bounding_box=(min_x, min_y, max_x, max_y),
            major_axis=round(major_axis, 2),
            minor_axis=round(minor_axis, 2),
            orientation_degrees=round(angle_deg, 2),
            orientation_radians=round(angle_rad, 4),
            compactness=round(compactness, 4),
            elongation=round(elongation, 4),
            model_probability=round(mean_p, 4),
            class_margin=round(margin, 4),
        )
        detections.append(spill)
        
    return detections


class SpillPropertyExtractor:
    """
    Extracts geometric, physical, and temporal properties from segmented oil slicks.
    """

    def __init__(self, pixel_resolution_meters: float = 10.0):
        self.pixel_res = pixel_resolution_meters

    def extract_all(self, binary_mask: np.ndarray) -> Dict[str, Any]:
        """
        Extract complete geometric profile and detections from binary mask.
        """
        detections = extract_spill_detections(binary_mask, self.pixel_res)
        morph = get_morphological_properties(binary_mask)
        total_area_km2 = calculate_spill_area(binary_mask, self.pixel_res)
        
        return {
            "total_area_km2": round(total_area_km2, 6),
            "detected_objects_count": len(detections),
            "detections": [d.to_dict() for d in detections],
            "aggregate_morphology": morph,
        }
