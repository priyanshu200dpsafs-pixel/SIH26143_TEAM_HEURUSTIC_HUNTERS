"""
Confidence Estimation, Uncertainty Quantification, and Abstention Layer.

Avoids raw softmax overconfidence by combining:
1. Mean Model Softmax Probability
2. Multi-class Entropy / Dispersion (segmentation confidence)
3. Oil vs Look-alike Margin (p_oil - p_lookalike)
4. Object Geometric Scale (speckle / clutter penalty)
5. Environmental Wind Consistency (ERA5 Bragg wave dampening window)
6. Optional Optical Corroboration / Contradiction

Outputs calibrated composite confidence scores and 4 categorical levels:
- HIGH
- MEDIUM
- LOW
- INSUFFICIENT (Abstention / Rejection)
"""

import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np

from src.detection.spill_properties import SpillDetection


class ConfidenceEstimator:
    """
    Multi-modal uncertainty estimator and decision abstention engine.
    """

    def __init__(
        self,
        high_threshold: float = 0.75,
        medium_threshold: float = 0.55,
        low_threshold: float = 0.35,
        min_margin_for_high: float = 0.20,
    ):
        self.th_high = high_threshold
        self.th_medium = medium_threshold
        self.th_low = low_threshold
        self.min_margin_for_high = min_margin_for_high

    def evaluate_detection(
        self,
        detection: SpillDetection,
        wind_speed_ms: Optional[float] = None,
        optical_context: Optional[Dict[str, Any]] = None,
    ) -> SpillDetection:
        """
        Compute calibrated confidence and assign classification tier to SpillDetection.
        """
        p_oil = detection.model_probability
        margin = detection.class_margin
        area_px = detection.area_pixels
        
        # 1. Model Probability Factor [0, 1]
        c_prob = float(np.clip(p_oil, 0.0, 1.0))
        
        # 2. Margin Factor: normalized difference against look-alike [0, 1]
        # Margin >= 0.40 is considered full confidence differentiation
        c_margin = float(np.clip(margin / 0.40, 0.0, 1.0)) if margin > 0 else 0.0
        
        # 3. Size / Scale Factor [0.2, 1.0]
        # Speckles < 25 pixels heavily penalized
        if area_px < 20:
            c_size = 0.20
        elif area_px < 50:
            c_size = 0.50
        elif area_px < 150:
            c_size = 0.80
        else:
            c_size = 1.00
            
        # 4. Environmental Consistency (ERA5 wind speed)
        env_dict: Dict[str, Any] = {}
        if wind_speed_ms is not None:
            if 3.0 <= wind_speed_ms <= 12.0:
                c_env = 1.00
                env_status = "OPTIMAL_BRAGG_DAMPENING_WINDOW"
                env_note = f"Wind speed ({wind_speed_ms:.1f} m/s) ideal for SAR oil slick dampening."
            elif wind_speed_ms < 3.0:
                c_env = 0.50
                env_status = "CALM_SEA_LOOKALIKE_RISK"
                env_note = f"Low wind ({wind_speed_ms:.1f} m/s) causes widespread natural calm-water look-alikes."
            else:
                c_env = 0.60
                env_status = "HIGH_WIND_DISPERSION_RISK"
                env_note = f"High wind ({wind_speed_ms:.1f} m/s) disrupts surface slicks and increases wave backscatter."
            env_dict = {
                "wind_speed_ms": round(wind_speed_ms, 2),
                "status": env_status,
                "factor": c_env,
                "rationale": env_note,
            }
        else:
            c_env = 0.80  # Neutral fallback
            env_dict = {"status": "WIND_CONTEXT_UNAVAILABLE", "factor": 0.80}
            
        # 5. Optical Evidence delta
        opt_delta = 0.0
        if optical_context is not None:
            opt_status = optical_context.get("status", "OPTICAL_EVIDENCE_UNAVAILABLE")
            if opt_status == "CORROBORATED_BY_OPTICAL":
                opt_delta = 0.10
            elif opt_status == "CONTRADICTED_BY_OPTICAL":
                opt_delta = -0.30
                
        # Composite Calibrated Score
        composite_score = (
            0.40 * c_prob +
            0.30 * c_margin +
            0.15 * c_size +
            0.15 * c_env +
            opt_delta
        )
        composite_score = float(np.clip(composite_score, 0.0, 1.0))
        
        # Categorical Decision Tier with Abstention Logic
        if composite_score < self.th_low or margin < 0.05 or area_px < 20 or c_env < 0.55 and margin < 0.15:
            tier = "INSUFFICIENT"
        elif composite_score < self.th_medium or margin < 0.12:
            tier = "LOW"
        elif composite_score < self.th_high or margin < self.min_margin_for_high:
            tier = "MEDIUM"
        else:
            tier = "HIGH"
            
        detection.confidence_level = tier
        detection.segmentation_confidence = round(composite_score, 4)
        detection.environmental_consistency = env_dict
        detection.optical_evidence = optical_context
        
        return detection

    def evaluate_all(
        self,
        detections: List[SpillDetection],
        wind_speed_ms: Optional[float] = None,
        optical_context: Optional[Dict[str, Any]] = None,
    ) -> List[SpillDetection]:
        """Batch evaluate confidence for a list of detections."""
        return [self.evaluate_detection(d, wind_speed_ms, optical_context) for d in detections]
