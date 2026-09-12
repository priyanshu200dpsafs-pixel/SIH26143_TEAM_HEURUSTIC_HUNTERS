"""
AIS Trajectory Analysis and Vessel Attribution Module.

Filters marine traffic against hindcast uncertainty cones, detects spoofing
and transponder blackout anomalies, and calculates multi-factor suspicion scores.
"""

from .traffic_filter import AISTrafficFilter, filter_vessels_in_spatiotemporal_window
from .spoofing_detector import SpoofingDetector, check_kinematic_plausibility
from .suspicion_scorer import SuspicionScorer, rank_suspect_vessels

__all__ = [
    "AISTrafficFilter",
    "filter_vessels_in_spatiotemporal_window",
    "SpoofingDetector",
    "check_kinematic_plausibility",
    "SuspicionScorer",
    "rank_suspect_vessels",
]
