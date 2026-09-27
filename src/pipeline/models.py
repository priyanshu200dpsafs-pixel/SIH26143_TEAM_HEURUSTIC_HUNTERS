"""
Canonical Incident and Evidence Data Models.

Defines standardized, machine-readable structures for:
- Incident
- EvidenceRecord
- SatelliteObservation
- SpillObservation
- EnvironmentalEvidence
- HindcastResult
- AISCandidate
- CounterfactualResult
- ForecastResult

Enforces explicit provenance tagging ('REAL', 'SIMULATED', 'INFERRED', 'UNAVAILABLE')
and reality labels across all intelligence outputs.
"""

from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import json
import numpy as np


class ProvenanceType(str, Enum):
    REAL = "REAL"
    SIMULATED = "SIMULATED"
    INFERRED = "INFERRED"
    UNAVAILABLE = "UNAVAILABLE"


def sanitize_for_json(obj: Any) -> Any:
    """Recursively convert numpy types, tuples, and shapely objects for JSON serialization."""
    if obj is None:
        return None
    if isinstance(obj, (int, float, str, bool)):
        return obj
    if isinstance(obj, (np.integer, np.int64, np.int32)):
        return int(obj)
    if isinstance(obj, (np.floating, np.float64, np.float32)):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return [sanitize_for_json(x) for x in obj.tolist()]
    if isinstance(obj, (list, tuple)):
        return [sanitize_for_json(x) for x in obj]
    if isinstance(obj, dict):
        return {str(k): sanitize_for_json(v) for k, v in obj.items()}
    if hasattr(obj, "__geo_interface__"):
        return sanitize_for_json(obj.__geo_interface__)
    if hasattr(obj, "to_dict"):
        return sanitize_for_json(obj.to_dict())
    return str(obj)


@dataclass
class EvidenceRecord:
    """Generic evidentiary container for tracking source provenance and hashes."""
    evidence_id: str
    evidence_type: str
    provenance: str  # REAL, SIMULATED, INFERRED, UNAVAILABLE
    source_identifier: str
    timestamp_utc: str
    metadata: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        return sanitize_for_json(asdict(self))


@dataclass
class SatelliteObservation:
    """Satellite earth observation metadata and image chip references."""
    product_id: str
    satellite_name: str  # e.g., Sentinel-1
    sensor_type: str  # SAR C-Band
    acquisition_time: str  # ISO UTC
    bounding_box: Tuple[float, float, float, float]  # (min_lon, min_lat, max_lon, max_lat)
    image_path: str
    polarization: str = "VV"
    pixel_resolution_meters: float = 10.0
    provenance: str = ProvenanceType.REAL.value  # REAL / REPLAY / SIMULATED
    source_identifier: str = "ESA Copernicus / Local Catalog"

    def to_dict(self) -> Dict[str, Any]:
        return sanitize_for_json(asdict(self))


@dataclass
class SpillObservation:
    """Segmented spill properties and morphological characterization."""
    detected: bool
    spill_id: Optional[str] = None
    area_pixels: int = 0
    area_km2: float = 0.0
    perimeter_km: float = 0.0
    centroid: Optional[Tuple[float, float]] = None  # (lon, lat)
    bounding_box: Optional[Tuple[float, float, float, float]] = None
    major_axis_km: float = 0.0
    minor_axis_km: float = 0.0
    orientation_deg: float = 0.0
    compactness: float = 0.0
    elongation: float = 0.0
    model_confidence: float = 0.0
    confidence_tier: str = "INSUFFICIENT"  # HIGH, MEDIUM, LOW, INSUFFICIENT
    estimated_age_hours_fay: float = 0.0
    polygon_geojson: Optional[Dict[str, Any]] = None
    raw_detections_count: int = 0
    provenance: str = ProvenanceType.INFERRED.value
    source_identifier: str = "SAR U-Net Model + Morphology Extractor"

    def to_dict(self) -> Dict[str, Any]:
        return sanitize_for_json(asdict(self))


@dataclass
class EnvironmentalEvidence:
    """Environmental atmospheric and hydrodynamic conditions."""
    observation_time: str
    wind_speed_mps: float = 0.0
    wind_direction_deg: float = 0.0
    bragg_regime: str = "UNKNOWN"  # OPTIMAL, CALM, HIGH_WIND, UNKNOWN
    wind_u: float = 0.0
    wind_v: float = 0.0
    current_u: float = 0.0
    current_v: float = 0.0
    era5_source: str = "data/weather/era5_wind_mediterranean_case_study.nc"
    oscar_source: str = "data/ocean_currents/oscar_currents_final_20240823.nc"
    optical_checked: bool = False
    optical_result: Optional[Dict[str, Any]] = None
    provenance: str = ProvenanceType.REAL.value  # REAL ARCHIVED
    source_identifier: str = "ECMWF ERA5 + NASA OSCAR"

    def to_dict(self) -> Dict[str, Any]:
        return sanitize_for_json(asdict(self))


@dataclass
class HindcastResult:
    """Lagrangian backward trajectory simulation results."""
    lookback_hours: float
    time_step_seconds: float
    num_particles: int
    release_window_start: str  # ISO UTC
    release_window_end: str    # ISO UTC
    origin_centroid: Tuple[float, float]  # (lon, lat)
    confidence_95_polygon: Optional[Dict[str, Any]] = None  # GeoJSON
    confidence_50_polygon: Optional[Dict[str, Any]] = None  # GeoJSON
    probability_raster: Optional[Dict[str, Any]] = None
    provenance: str = ProvenanceType.INFERRED.value
    source_identifier: str = "LagrangianDriftTracker (RK4 Backward)"

    def to_dict(self) -> Dict[str, Any]:
        return sanitize_for_json(asdict(self))


@dataclass
class AISCandidate:
    """Candidate vessel scored for attribution."""
    mmsi: int
    vessel_name: str
    vessel_type: float
    composite_score: float
    attribution_decision: str  # PRIMARY_SUSPECT, PLAUSIBLE_CANDIDATE, EXONERATED_...
    spatial_score: float = 0.0
    temporal_score: float = 0.0
    trajectory_score: float = 0.0
    gap_score: float = 0.0
    type_score: float = 0.0
    draft_score: float = 0.0
    min_distance_nm: float = 999.0
    residence_time_minutes: float = 0.0
    anomalies: List[Dict[str, Any]] = field(default_factory=list)
    track_geojson: Optional[Dict[str, Any]] = None
    consistency_tier: Optional[str] = None  # HIGH-CONSISTENCY CANDIDATE, MODERATE-CONSISTENCY CANDIDATE, LOW-CONSISTENCY CANDIDATE
    provenance: str = ProvenanceType.SIMULATED.value  # SIMULATED REPLAY
    source_identifier: str = "ReplayAISProvider (Adversarial Benchmark)"

    def to_dict(self) -> Dict[str, Any]:
        return sanitize_for_json(asdict(self))


@dataclass
class CounterfactualResult:
    """Counterfactual verification of candidate discharge hypothesis."""
    candidate_mmsi: Optional[int] = None
    candidate_name: Optional[str] = None
    tested: bool = False
    verdict: str = "NOT_RUN"  # ROBUST_MATCH, SENSITIVE_TO_FORCING, INCONSISTENT_HYPOTHESIS, NOT_RUN
    plausibility_score: float = 0.0
    centroid_offset_km: float = 0.0
    footprint_iou: float = 0.0
    provenance: str = ProvenanceType.INFERRED.value
    source_identifier: str = "CounterfactualTester (Forward Perturbation)"

    def to_dict(self) -> Dict[str, Any]:
        return sanitize_for_json(asdict(self))


@dataclass
class ForecastResult:
    """Forward spill propagation projection."""
    forecast_hours: float
    time_step_seconds: float
    num_particles: int
    future_window_end: str  # ISO UTC
    future_centroid: Tuple[float, float]  # (lon, lat)
    future_envelope_polygon: Optional[Dict[str, Any]] = None  # GeoJSON
    provenance: str = ProvenanceType.INFERRED.value
    source_identifier: str = "LagrangianDriftTracker (RK4 Forward Forecast)"

    def to_dict(self) -> Dict[str, Any]:
        return sanitize_for_json(asdict(self))


@dataclass
class Incident:
    """Canonical maritime spill intelligence incident dossier."""
    incident_id: str
    status: str
    created_at: str
    updated_at: str
    region_name: str
    satellite_observation: Optional[SatelliteObservation] = None
    spill_observation: Optional[SpillObservation] = None
    environmental_evidence: Optional[EnvironmentalEvidence] = None
    hindcast_result: Optional[HindcastResult] = None
    candidates: List[AISCandidate] = field(default_factory=list)
    top_candidate: Optional[AISCandidate] = None
    counterfactual_result: Optional[CounterfactualResult] = None
    forecast_result: Optional[ForecastResult] = None
    reality_labels: Dict[str, str] = field(default_factory=dict)
    execution_log: List[Dict[str, Any]] = field(default_factory=list)
    failure_reason: Optional[str] = None
    attribution_status: Optional[str] = None
    provenance_category: str = "REAL"

    def to_dict(self) -> Dict[str, Any]:
        return sanitize_for_json(asdict(self))

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent)

    def save(self, filepath: str) -> None:
        with open(filepath, "w") as f:
            json.dump(self.to_dict(), f, indent=2)
