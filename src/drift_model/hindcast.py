"""
Backward Drift Hindcasting Engine.

Backtracks observed oil spill geometries in time using multi-parameter Lagrangian
ensembles to reconstruct:
- Time-dependent source envelopes
- Source probability density fields
- Multi-tier confidence regions (50%, 80%, 95%)
- Potential vessel encounter windows
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from shapely.geometry import Point, Polygon

from src.drift_model.environmental_interpolator import EnvironmentalInterpolator
from src.drift_model.lagrangian_tracker import LagrangianDriftTracker
from src.drift_model.uncertainty import UncertaintyConeGenerator


def sample_particles_in_geometry(
    spill_geometry: Union[Polygon, List[Tuple[float, float]], Tuple[float, float, float, float]],
    num_particles: int = 500,
    rng: Optional[np.random.Generator] = None,
) -> List[Tuple[float, float]]:
    """
    Uniformly sample particle starting coordinates inside or along a spill geometry.

    Args:
        spill_geometry: Shapely Polygon, list of (lon, lat) boundary vertices,
                        or (min_lon, min_lat, max_lon, max_lat) bounding box.
        num_particles: Number of seed particles.
        rng: NumPy random generator.

    Returns:
        List of (lon, lat) particle seed coordinates.
    """
    if rng is None:
        rng = np.random.default_rng()

    if isinstance(spill_geometry, (list, tuple)) and len(spill_geometry) == 4 and isinstance(spill_geometry[0], (int, float)):
        min_lon, min_lat, max_lon, max_lat = spill_geometry
        poly = Polygon([
            (min_lon, min_lat),
            (max_lon, min_lat),
            (max_lon, max_lat),
            (min_lon, max_lat),
        ])
    elif isinstance(spill_geometry, list):
        poly = Polygon(spill_geometry)
    elif isinstance(spill_geometry, Polygon):
        poly = spill_geometry
    else:
        raise ValueError("Unsupported spill_geometry format")

    min_x, min_y, max_x, max_y = poly.bounds
    points = []
    attempts = 0
    max_attempts = num_particles * 25

    while len(points) < num_particles and attempts < max_attempts:
        rx = rng.uniform(min_x, max_x)
        ry = rng.uniform(min_y, max_y)
        pt = Point(rx, ry)
        if poly.contains(pt) or poly.touches(pt):
            points.append((float(rx), float(ry)))
        attempts += 1

    # If shape is very thin or degenerate, sample along boundary
    if len(points) < num_particles:
        for _ in range(num_particles - len(points)):
            ratio = rng.uniform(0.0, 1.0)
            pt = poly.exterior.interpolate(ratio, normalized=True)
            points.append((float(pt.x), float(pt.y)))

    return points


class BackwardDriftHindcaster:
    """
    Executes ensemble-based backward drift hindcasting to infer release origins.
    """

    def __init__(
        self,
        interpolator: EnvironmentalInterpolator,
        default_windage_range: Tuple[float, float] = (0.025, 0.035),
        default_deflection_range: Tuple[float, float] = (0.0, 15.0),
        horizontal_diffusivity_kh: float = 12.0,
    ):
        self.interpolator = interpolator
        self.windage_range = default_windage_range
        self.deflection_range = default_deflection_range
        self.kh = horizontal_diffusivity_kh
        self.uncertainty_gen = UncertaintyConeGenerator(horizontal_diffusivity_kh=self.kh)

    def run_hindcast(
        self,
        spill_geometry: Union[Polygon, List[Tuple[float, float]], Tuple[float, float, float, float]],
        observation_time: Union[str, float],
        lookback_hours: float = 24.0,
        time_step_seconds: float = 600.0,
        num_particles: int = 500,
        random_seed: Optional[int] = 42,
    ) -> Dict[str, Any]:
        """
        Run multi-parameter Monte Carlo backward trajectory hindcast.
        """
        rng = np.random.default_rng(random_seed)

        # 1. Sample seed particles across observed spill shape
        seed_positions = sample_particles_in_geometry(spill_geometry, num_particles=num_particles, rng=rng)

        # 2. Draw parameter variation across ensemble
        windage_samples = rng.uniform(self.windage_range[0], self.windage_range[1], num_particles)
        deflection_samples = rng.uniform(self.deflection_range[0], self.deflection_range[1], num_particles)

        t_obs = self.interpolator._to_epoch(observation_time)
        dt = -float(abs(time_step_seconds))
        num_steps = int((lookback_hours * 3600.0) / abs(time_step_seconds))

        # Trajectory array: (P, S+1, 2)
        trajectories = np.zeros((num_particles, num_steps + 1, 2), dtype=float)
        timestamps = np.zeros(num_steps + 1, dtype=float)

        for p_idx, pos0 in enumerate(seed_positions):
            trajectories[p_idx, 0, :] = pos0
        timestamps[0] = t_obs

        current_positions = [tuple(p) for p in trajectories[:, 0, :]]
        current_t = t_obs

        from src.drift_model.lagrangian_tracker import rk4_step

        for step in range(1, num_steps + 1):
            next_positions = []
            for p_idx, pos in enumerate(current_positions):
                next_pos = rk4_step(
                    pos=pos,
                    t=current_t,
                    dt=dt,
                    interpolator=self.interpolator,
                    windage=float(windage_samples[p_idx]),
                    deflection_deg=float(deflection_samples[p_idx]),
                    kh=self.kh,
                    rng=rng,
                )
                trajectories[p_idx, step, :] = next_pos
                next_positions.append(next_pos)

            current_t += dt
            timestamps[step] = current_t
            current_positions = next_positions

        # 3. Compute time-dependent uncertainty envelopes (e.g. at each hour)
        hourly_indices = [
            i for i in range(0, num_steps + 1, max(1, int(3600.0 / abs(time_step_seconds))))
        ]
        if hourly_indices[-1] != num_steps:
            hourly_indices.append(num_steps)

        time_envelopes = []
        for h_idx in hourly_indices:
            pts_at_t = trajectories[:, h_idx, :]
            poly_95 = self.uncertainty_gen.build_confidence_polygon(pts_at_t, confidence_level=0.95)
            poly_80 = self.uncertainty_gen.build_confidence_polygon(pts_at_t, confidence_level=0.80)
            poly_50 = self.uncertainty_gen.build_confidence_polygon(pts_at_t, confidence_level=0.50)
            t_epoch = float(timestamps[h_idx])
            time_envelopes.append({
                "step_index": h_idx,
                "timestamp_epoch": t_epoch,
                "timestamp_iso": pd.to_datetime(t_epoch, unit="s", utc=True).isoformat(),
                "hours_before_observation": (t_obs - t_epoch) / 3600.0,
                "confidence_95": poly_95,
                "confidence_80": poly_80,
                "confidence_50": poly_50,
                "centroid": [float(pts_at_t[:, 0].mean()), float(pts_at_t[:, 1].mean())],
                "spread_radius_km": float(np.std(pts_at_t, axis=0).mean() * 111.0),
            })

        # 4. Final origin probability raster (at max lookback)
        final_pts = trajectories[:, -1, :]
        prob_raster = self.uncertainty_gen.compute_probability_raster(final_pts, grid_resolution_deg=0.015)
        final_conf_95 = self.uncertainty_gen.build_confidence_polygon(final_pts, confidence_level=0.95)
        final_conf_80 = self.uncertainty_gen.build_confidence_polygon(final_pts, confidence_level=0.80)
        final_conf_50 = self.uncertainty_gen.build_confidence_polygon(final_pts, confidence_level=0.50)

        return {
            "observation_time_iso": pd.to_datetime(t_obs, unit="s", utc=True).isoformat(),
            "lookback_hours": lookback_hours,
            "num_particles": num_particles,
            "timestamps_epoch": timestamps,
            "trajectories": trajectories,
            "time_envelopes": time_envelopes,
            "origin_probability_raster": prob_raster,
            "origin_confidence_regions": {
                "p95": final_conf_95,
                "p80": final_conf_80,
                "p50": final_conf_50,
            },
        }
