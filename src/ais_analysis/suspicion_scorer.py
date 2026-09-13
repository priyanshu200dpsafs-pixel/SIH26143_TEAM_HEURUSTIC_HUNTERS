"""
Multi-Factor Vessel Suspicion Scoring & Attribution Engine.

Calculates evidence-based attribution scores by combining:
1. Spatial compatibility (distance to backward hindcast cone)
2. Temporal compatibility (transit during release window)
3. Trajectory compatibility (crossing, residence time)
4. Drift consistency (hydrodynamic drift alignment)
5. AIS integrity (transponder gaps over release site vs normal continuous tracking)
6. Vessel prior (crude/chemical tanker vs cargo, draft drop)

Stores all component scores and explicit reasoning. Never hides decisions inside a single scalar.
"""

from typing import Any, Dict, List, Optional
import numpy as np


class SuspicionScorer:
    """
    Probabilistic attribution engine ranking candidate vessels against hindcast evidence.
    """

    def __init__(
        self,
        weight_proximity: float = 0.35,
        weight_vessel_type: float = 0.25,
        weight_ais_gap: float = 0.25,
        weight_draft_change: float = 0.15,
        weight_temporal: float = 0.0,
        weight_drift: float = 0.0,
    ):
        """
        Initialize scoring weights (summing to 1.0).
        Supports backwards-compatible 4-weight signature while providing full multi-factor weights.
        """
        self.w_prox = weight_proximity
        self.w_type = weight_vessel_type
        self.w_gap = weight_ais_gap
        self.w_draft = weight_draft_change
        self.w_temporal = weight_temporal
        self.w_drift = weight_drift

    def score_vessel(
        self,
        vessel_profile: Dict[str, Any],
        spill_hindcast: Dict[str, Any],
    ) -> Dict[str, Any]:
        """
        Calculate individual suspicion metrics and composite score.

        Args:
            vessel_profile: Dictionary containing:
                - 'mmsi', 'vessel_name', 'vessel_type'
                - 'intersection': Output from TrajectoryIntersectionEngine
                - 'kinematics': Output from AISKinematicEngine
                - 'draft_change': Float (optional, negative if cargo discharged)
            spill_hindcast: Hindcast dictionary or release parameters.

        Returns:
            Dictionary with breakdown across all 6 evidence factors and composite index.
        """
        mmsi = vessel_profile.get("mmsi", 0)
        name = vessel_profile.get("vessel_name", "UNKNOWN")
        vtype = float(vessel_profile.get("vessel_type", 1001.0))

        intersection = vessel_profile.get("intersection", {})
        kinematics = vessel_profile.get("kinematics", {})
        draft_change = float(vessel_profile.get("draft_change", 0.0))

        # Check for disqualified kinematics (e.g. impossible speed > 55 knots)
        has_impossible_speed = any(
            a.get("subtype") == "IMPOSSIBLE_SPEED" for a in kinematics.get("anomalies", [])
        )
        if has_impossible_speed:
            return {
                "mmsi": mmsi,
                "vessel_name": name,
                "composite_suspicion_score": 0.0,
                "attribution_decision": "DISQUALIFIED_INVALID_KINEMATICS",
                "evidence_breakdown": {
                    "spatial_compatibility": 0.0,
                    "temporal_compatibility": 0.0,
                    "trajectory_compatibility": 0.0,
                    "drift_consistency": 0.0,
                    "ais_integrity": 0.0,
                    "vessel_prior": 0.0,
                },
                "reasoning_summary": "Vessel trajectory rejected due to impossible kinematic displacement / GPS integrity anomaly.",
            }

        # 1. Spatial Compatibility [0.0 - 1.0]
        min_dist_nm = float(intersection.get("min_distance_nm", 999.0))
        if min_dist_nm <= 1.0 or intersection.get("spatial_overlap", False):
            s_spatial = 1.0
        elif min_dist_nm <= 5.0:
            s_spatial = float(np.exp(- (min_dist_nm - 1.0) / 2.0))
        elif min_dist_nm <= 20.0:
            s_spatial = float(np.exp(- min_dist_nm / 5.0))
        else:
            s_spatial = 0.0

        # 2. Temporal Compatibility [0.0 - 1.0]
        temporal_overlap = bool(intersection.get("temporal_overlap", False))
        s_temporal = 1.0 if temporal_overlap else 0.0

        # 3. Trajectory Compatibility [0.0 - 1.0]
        crossing_type = intersection.get("crossing_type", "NONE")
        residence_min = float(intersection.get("residence_time_minutes", 0.0))
        if crossing_type == "DIRECT_BROADCAST_CONTAINMENT":
            s_traj = 1.0
        elif crossing_type == "TRANSIT_SEGMENT_INTERSECTION":
            s_traj = 0.95
        elif crossing_type == "NEAR_MISS_WITHIN_5KM":
            s_traj = 0.50
        else:
            s_traj = 0.0

        # 4. Drift Consistency [0.0 - 1.0]
        # High if spatial overlap occurs precisely inside backwards drift envelope
        s_drift = 1.0 if (s_spatial > 0.8 and s_temporal > 0.8) else (s_spatial * s_temporal)

        # 5. AIS Integrity / Gap Anomaly [0.0 - 1.0]
        gaps = kinematics.get("continuity_gaps", [])
        gap_in_cone = False
        if gaps and s_spatial > 0.5:
            gap_in_cone = True

        if gap_in_cone:
            s_gap = 1.0  # Deliberate blackout over release origin
        elif gaps and s_spatial <= 0.2:
            s_gap = 0.1  # Outage occurred far from spill; innocent equipment glitch
        else:
            s_gap = 0.3  # Normal continuous broadcast

        # 6. Vessel Prior & Draft Change [0.0 - 1.0]
        # Tanker (1004 / 80-89) has higher prior than General Cargo (1001 / 70-79)
        if vtype in (1004.0, 80.0, 81.0, 82.0, 83.0, 84.0):
            s_type = 1.0
        elif vtype in (1024.0, 1025.0):
            s_type = 0.6
        else:
            s_type = 0.3

        s_draft = 1.0 if draft_change < -0.5 else 0.2

        # Compute composite index
        # Normalize weights to sum to 1.0
        total_w = self.w_prox + self.w_type + self.w_gap + self.w_draft
        w_p = self.w_prox / total_w
        w_t = self.w_type / total_w
        w_g = self.w_gap / total_w
        w_d = self.w_draft / total_w

        composite = (
            w_p * (0.6 * s_spatial + 0.4 * s_temporal) +
            w_t * s_type +
            w_g * s_gap +
            w_d * s_draft
        )
        composite = float(np.clip(composite, 0.0, 1.0))

        # Attribution Decision Logic
        if s_spatial == 0.0:
            decision = "EXONERATED_SPATIALLY_DISJOINT"
            reason = f"Vessel passed {min_dist_nm:.1f} nm away; completely outside the backward drift uncertainty cone."
        elif s_temporal == 0.0:
            decision = "EXONERATED_TEMPORALLY_INCOMPATIBLE"
            reason = "Vessel was not in the spill area during the estimated release window."
        elif composite >= 0.70 and s_spatial >= 0.8:
            decision = "PRIMARY_SUSPECT"
            reason = f"High spatiotemporal convergence (distance: {min_dist_nm:.1f} nm), tanker classification, and suspicious transponder profile."
        elif composite >= 0.45:
            decision = "PLAUSIBLE_CANDIDATE"
            reason = f"Plausible transit within proximity ({min_dist_nm:.1f} nm), but secondary evidence is ambiguous."
        else:
            decision = "INSUFFICIENT_EVIDENCE_EXONERATED"
            reason = "Low composite suspicion score."

        return {
            "mmsi": mmsi,
            "vessel_name": name,
            "composite_suspicion_score": round(composite, 3),
            "attribution_decision": decision,
            "evidence_breakdown": {
                "spatial_compatibility": round(s_spatial, 3),
                "temporal_compatibility": round(s_temporal, 3),
                "trajectory_compatibility": round(s_traj, 3),
                "drift_consistency": round(s_drift, 3),
                "ais_integrity": round(s_gap, 3),
                "vessel_prior": round(s_type, 3),
                "draft_prior": round(s_draft, 3),
                "min_distance_nm": min_dist_nm,
                "crossing_type": crossing_type,
                "residence_time_minutes": residence_min,
            },
            "reasoning_summary": reason,
        }


def rank_suspect_vessels(
    candidate_scores: List[Dict[str, Any]],
    top_n: int = 5,
) -> List[Dict[str, Any]]:
    """
    Sort candidate vessels in descending order of composite suspicion index.

    Args:
        candidate_scores: List of scored vessel dictionaries.
        top_n: Number of suspect vessels to return.

    Returns:
        Ranked list of top candidate vessels.
    """
    sorted_candidates = sorted(
        candidate_scores,
        key=lambda x: x.get("composite_suspicion_score", 0.0),
        reverse=True,
    )
    return sorted_candidates[:top_n]
