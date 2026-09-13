"""
Counterfactual Forward Verification Engine.

Simulates forward Lagrangian drift from hypothesized vessel discharge coordinates
and timestamps to the observation epoch. Quantifies physical consistency:
- Centroid offset error (km)
- Footprint Intersection-over-Union (IoU)
- Enclosure fraction (particles arriving within observed slick boundary)
- Physical plausibility score [0.0 - 1.0]
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from shapely.geometry import MultiPoint, Point, Polygon

from src.ais_analysis.kinematics import haversine_distance_meters
from src.drift_model.environmental_interpolator import EnvironmentalInterpolator
from src.drift_model.lagrangian_tracker import LagrangianDriftTracker
from src.drift_model.uncertainty import UncertaintyConeGenerator


class CounterfactualTester:
    """
    Simulates forward drift from candidate release events to verify physical plausibility.
    """

    def __init__(
        self,
        interpolator: EnvironmentalInterpolator,
        windage_factor: float = 0.03,
        horizontal_diffusivity_kh: float = 10.0,
    ):
        self.interpolator = interpolator
        self.tracker = LagrangianDriftTracker(
            interpolator=interpolator,
            windage_factor=windage_factor,
            horizontal_diffusivity_kh=horizontal_diffusivity_kh,
        )
        self.uncertainty_gen = UncertaintyConeGenerator(horizontal_diffusivity_kh=horizontal_diffusivity_kh)

    def test_candidate_release(
        self,
        candidate_release_coord: Tuple[float, float],
        candidate_release_time: Union[str, float],
        observed_spill_geometry: Union[Polygon, Tuple[float, float, float, float], List[Tuple[float, float]]],
        observation_time: Union[str, float],
        num_particles: int = 200,
        random_seed: Optional[int] = 42,
    ) -> Dict[str, Any]:
        """
        Run forward simulation from candidate release event to observation epoch.

        Args:
            candidate_release_coord: (lon, lat) of hypothesized vessel release.
            candidate_release_time: Timestamp of vessel passage.
            observed_spill_geometry: Geometry of detected slick.
            observation_time: Timestamp of satellite imaging.
            num_particles: Number of forward Monte Carlo particles.
            random_seed: Deterministic seed.

        Returns:
            Dictionary with forward arrival coordinates, centroid error, IoU, and verdict.
        """
        t_release = self.interpolator._to_epoch(candidate_release_time)
        t_obs = self.interpolator._to_epoch(observation_time)
        duration_sec = t_obs - t_release

        if duration_sec <= 0:
            return {
                "valid": False,
                "error": "Release time must precede observation time.",
                "physical_plausibility_score": 0.0,
                "counterfactual_verdict": "CHRONOLOGICALLY_IMPOSSIBLE",
            }

        # Convert observed geometry to Shapely Polygon
        if isinstance(observed_spill_geometry, Polygon):
            obs_poly = observed_spill_geometry
        elif isinstance(observed_spill_geometry, (list, tuple)) and len(observed_spill_geometry) == 4 and isinstance(observed_spill_geometry[0], (int, float)):
            min_lon, min_lat, max_lon, max_lat = observed_spill_geometry
            obs_poly = Polygon([(min_lon, min_lat), (max_lon, min_lat), (max_lon, max_lat), (min_lon, max_lat)])
        else:
            obs_poly = Polygon(observed_spill_geometry)

        obs_centroid_lon = obs_poly.centroid.x
        obs_centroid_lat = obs_poly.centroid.y

        # Seed particles around candidate release location
        rel_lon, rel_lat = candidate_release_coord
        seed_pts = [(rel_lon, rel_lat) for _ in range(num_particles)]

        # Simulate forward
        sim_res = self.tracker.simulate(
            seed_positions=seed_pts,
            start_time=candidate_release_time,
            duration_seconds=duration_sec,
            time_step_seconds=600.0,
            direction=1,
            random_seed=random_seed,
        )

        arrival_pts = sim_res["trajectories"][:, -1, :]  # shape: (P, 2) [lon, lat]
        sim_centroid_lon = float(arrival_pts[:, 0].mean())
        sim_centroid_lat = float(arrival_pts[:, 1].mean())

        # Centroid offset error
        centroid_err_m = haversine_distance_meters(
            sim_centroid_lon, sim_centroid_lat,
            obs_centroid_lon, obs_centroid_lat
        )
        centroid_err_km = centroid_err_m / 1000.0
        centroid_err_nm = centroid_err_m / 1852.0

        # Arrival hull
        sim_hull_dict = self.uncertainty_gen.build_confidence_polygon(arrival_pts, confidence_level=0.95, buffer_degrees=0.01)
        sim_poly = sim_hull_dict["shapely_polygon"]

        # Intersection over Union (IoU)
        intersection_area = sim_poly.intersection(obs_poly).area
        union_area = sim_poly.union(obs_poly).area
        iou = float(intersection_area / union_area) if union_area > 0 else 0.0

        # Particles inside or within 2km of observed target
        buffered_target = obs_poly.buffer(0.02)  # ~2.2 km buffer
        inside_count = 0
        for p in arrival_pts:
            if buffered_target.contains(Point(p[0], p[1])):
                inside_count += 1
        inside_fraction = float(inside_count / num_particles)

        # Plausibility score [0.0 - 1.0]
        # Score based on centroid error (decaying with distance) and enclosure fraction
        if centroid_err_km < 2.0:
            dist_score = 1.0
        elif centroid_err_km < 15.0:
            dist_score = float(np.exp(- (centroid_err_km - 2.0) / 4.0))
        else:
            dist_score = 0.0

        plausibility = float(np.clip(0.6 * dist_score + 0.4 * inside_fraction, 0.0, 1.0))

        if plausibility >= 0.70:
            verdict = "HIGH_PHYSICAL_CONSISTENCY"
        elif plausibility >= 0.40:
            verdict = "MODERATE_PHYSICAL_CONSISTENCY"
        else:
            verdict = "PHYSICALLY_INCONSISTENT"

        return {
            "valid": True,
            "candidate_release_coord": [rel_lon, rel_lat],
            "candidate_release_time_iso": pd.to_datetime(t_release, unit="s", utc=True).isoformat(),
            "observation_time_iso": pd.to_datetime(t_obs, unit="s", utc=True).isoformat(),
            "drift_duration_hours": round(duration_sec / 3600.0, 2),
            "simulated_arrival_centroid": [sim_centroid_lon, sim_centroid_lat],
            "observed_spill_centroid": [obs_centroid_lon, obs_centroid_lat],
            "centroid_offset_km": round(centroid_err_km, 2),
            "centroid_offset_nm": round(centroid_err_nm, 2),
            "footprint_iou": round(iou, 3),
            "particles_inside_target_fraction": round(inside_fraction, 3),
            "physical_plausibility_score": round(plausibility, 3),
            "counterfactual_verdict": verdict,
        }
