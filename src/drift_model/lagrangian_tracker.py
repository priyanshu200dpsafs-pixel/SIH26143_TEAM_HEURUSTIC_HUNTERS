"""
Lagrangian Particle Drift Tracker.

Simulates forward (forecasting) and backward (hindcasting) advective-diffusive
transport of oil spill particles across oceanic surface forcing fields.
Integrates hydrodynamic currents (OSCAR), atmospheric winds (ERA5 10m vectors),
and turbulent stochastic diffusion.
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from src.drift_model.environmental_interpolator import EnvironmentalInterpolator

EARTH_RADIUS_METERS = 6371000.0


def rk4_step(
    pos: Tuple[float, float],
    t: float,
    dt: float,
    interpolator: EnvironmentalInterpolator,
    windage: float = 0.03,
    deflection_deg: float = 0.0,
    kh: float = 10.0,
    rng: Optional[np.random.Generator] = None,
) -> Tuple[float, float]:
    """
    Execute a single 4th-order Runge-Kutta numerical integration step for Lagrangian drift,
    with stochastic turbulent diffusion.

    Args:
        pos: (longitude, latitude) coordinates in degrees.
        t: Current epoch time in seconds.
        dt: Signed timestep in seconds (positive for forward, negative for backward).
        interpolator: EnvironmentalInterpolator providing wind and current fields.
        windage: Wind leeway coefficient.
        deflection_deg: Wind deflection angle.
        kh: Horizontal eddy diffusivity (m²/s).
        rng: NumPy random generator.

    Returns:
        Updated (longitude, latitude) coordinates.
    """
    lon, lat = pos

    def get_velocity_m_per_s(lon_q: float, lat_q: float, t_q: float) -> Tuple[float, float]:
        return interpolator.get_advective_velocity(
            lon=lon_q,
            lat=lat_q,
            timestamp=t_q,
            windage=windage,
            deflection_deg=deflection_deg,
        )

    def uv_to_dlat_dlon(u: float, v: float, lat_ref: float) -> Tuple[float, float]:
        lat_rad = np.radians(lat_ref)
        cos_lat = max(np.cos(lat_rad), 0.01)
        dlat = (v / EARTH_RADIUS_METERS) * (180.0 / np.pi)
        dlon = (u / (EARTH_RADIUS_METERS * cos_lat)) * (180.0 / np.pi)
        return dlon, dlat

    # k1
    u1, v1 = get_velocity_m_per_s(lon, lat, t)
    dlon1, dlat1 = uv_to_dlat_dlon(u1, v1, lat)

    # k2
    t2 = t + 0.5 * dt
    lon2 = lon + 0.5 * dt * dlon1
    lat2 = lat + 0.5 * dt * dlat1
    u2, v2 = get_velocity_m_per_s(lon2, lat2, t2)
    dlon2, dlat2 = uv_to_dlat_dlon(u2, v2, lat2)

    # k3
    t3 = t + 0.5 * dt
    lon3 = lon + 0.5 * dt * dlon2
    lat3 = lat + 0.5 * dt * dlat2
    u3, v3 = get_velocity_m_per_s(lon3, lat3, t3)
    dlon3, dlat3 = uv_to_dlat_dlon(u3, v3, lat3)

    # k4
    t4 = t + dt
    lon4 = lon + dt * dlon3
    lat4 = lat + dt * dlat3
    u4, v4 = get_velocity_m_per_s(lon4, lat4, t4)
    dlon4, dlat4 = uv_to_dlat_dlon(u4, v4, lat4)

    # RK4 Advective Displacement
    dlon_adv = (dt / 6.0) * (dlon1 + 2.0 * dlon2 + 2.0 * dlon3 + dlon4)
    dlat_adv = (dt / 6.0) * (dlat1 + 2.0 * dlat2 + 2.0 * dlat3 + dlat4)

    # Stochastic Turbulent Diffusion (Random Walk)
    dlon_diff = 0.0
    dlat_diff = 0.0
    if kh > 0.0 and abs(dt) > 0.0:
        if rng is None:
            rng = np.random.default_rng()
        sigma_m = np.sqrt(2.0 * kh * abs(dt))
        dx_m = rng.normal(0.0, sigma_m)
        dy_m = rng.normal(0.0, sigma_m)
        cos_lat = max(np.cos(np.radians(lat)), 0.01)
        dlon_diff = (dx_m / (EARTH_RADIUS_METERS * cos_lat)) * (180.0 / np.pi)
        dlat_diff = (dy_m / EARTH_RADIUS_METERS) * (180.0 / np.pi)

    new_lon = lon + dlon_adv + dlon_diff
    new_lat = lat + dlat_adv + dlat_diff

    # Coordinate safety clipping
    new_lat = float(np.clip(new_lat, -89.9, 89.9))
    new_lon = float((new_lon + 180.0) % 360.0 - 180.0)

    return new_lon, new_lat


class LagrangianDriftTracker:
    """
    Simulates Lagrangian trajectory backtracking and forward tracking
    of oil spill particles subject to ocean current, wind, and turbulent diffusion.
    """

    def __init__(
        self,
        current_data_path: Optional[str] = None,
        wind_data_path: Optional[str] = None,
        interpolator: Optional[EnvironmentalInterpolator] = None,
        windage_factor: float = 0.03,
        deflection_angle_deg: float = 0.0,
        horizontal_diffusivity_kh: float = 10.0,
    ):
        self.current_data_path = current_data_path
        self.wind_data_path = wind_data_path
        self.windage_factor = windage_factor
        self.deflection_angle_deg = deflection_angle_deg
        self.kh = horizontal_diffusivity_kh

        if interpolator is not None:
            self.interpolator = interpolator
        elif current_data_path and wind_data_path:
            self.interpolator = EnvironmentalInterpolator(
                era5_path=wind_data_path,
                oscar_path=current_data_path,
                default_windage=windage_factor,
                default_deflection_deg=deflection_angle_deg,
            )
        else:
            self.interpolator = None

    def simulate(
        self,
        seed_positions: List[Tuple[float, float]],
        start_time: Union[str, float],
        duration_seconds: float,
        time_step_seconds: float = 600.0,
        direction: int = 1,
        random_seed: Optional[int] = None,
    ) -> Dict[str, Any]:
        """
        Simulate Lagrangian particle ensemble forward (direction=1) or backward (direction=-1).

        Args:
            seed_positions: List of initial (longitude, latitude) coordinates.
            start_time: ISO timestamp or epoch seconds of observation.
            duration_seconds: Duration of trajectory propagation in seconds.
            time_step_seconds: Integration timestep magnitude in seconds.
            direction: +1 for forward forecast, -1 for backward hindcast.
            random_seed: Seed for stochastic diffusion reproducibility.

        Returns:
            Dictionary containing timestamps, trajectories array (particles, steps, 2),
            and summary trajectory metrics.
        """
        if self.interpolator is None:
            raise NotImplementedError("Environmental forcing data must be provided for tracking simulation.")

        t_start = self.interpolator._to_epoch(start_time)
        dt = float(direction * abs(time_step_seconds))
        num_steps = int(abs(duration_seconds) / abs(time_step_seconds))
        num_particles = len(seed_positions)

        rng = np.random.default_rng(random_seed)

        # Preallocate trajectory array: (num_particles, num_steps + 1, 2) [lon, lat]
        trajectories = np.zeros((num_particles, num_steps + 1, 2), dtype=float)
        timestamps = np.zeros(num_steps + 1, dtype=float)

        for p_idx, (lon0, lat0) in enumerate(seed_positions):
            trajectories[p_idx, 0, :] = [lon0, lat0]
        timestamps[0] = t_start

        current_positions = [tuple(p) for p in trajectories[:, 0, :]]
        current_time = t_start

        for step in range(1, num_steps + 1):
            next_positions = []
            for p_idx, pos in enumerate(current_positions):
                next_pos = rk4_step(
                    pos=pos,
                    t=current_time,
                    dt=dt,
                    interpolator=self.interpolator,
                    windage=self.windage_factor,
                    deflection_deg=self.deflection_angle_deg,
                    kh=self.kh,
                    rng=rng,
                )
                trajectories[p_idx, step, :] = next_pos
                next_positions.append(next_pos)

            current_time += dt
            timestamps[step] = current_time
            current_positions = next_positions

        return {
            "num_particles": num_particles,
            "num_steps": num_steps,
            "direction": "forward" if direction > 0 else "backward",
            "start_time_iso": pd.to_datetime(t_start, unit="s", utc=True).isoformat(),
            "end_time_iso": pd.to_datetime(current_time, unit="s", utc=True).isoformat(),
            "timestamps_epoch": timestamps,
            "trajectories": trajectories,  # shape: (P, S+1, 2) [lon, lat]
        }

    def run_hindcast(
        self,
        origin_coords: Tuple[float, float],
        detection_time: str,
        lookback_hours: int = 24,
        time_step_seconds: int = 600,
        num_particles: int = 500,
        random_seed: Optional[int] = 42,
    ) -> Dict[str, Any]:
        """
        Perform backward trajectory integration to pinpoint original release point.
        """
        if self.interpolator is None:
            raise NotImplementedError("Hindcasting simulation not yet implemented without environmental forcing data.")

        # If origin_coords is (lat, lon), convert to (lon, lat)
        lat, lon = origin_coords
        seed_positions = [(lon, lat) for _ in range(num_particles)]

        return self.simulate(
            seed_positions=seed_positions,
            start_time=detection_time,
            duration_seconds=lookback_hours * 3600.0,
            time_step_seconds=time_step_seconds,
            direction=-1,
            random_seed=random_seed,
        )


def calculate_leeway_drift(
    u_wind: float,
    v_wind: float,
    leeway_factor: float = 0.03,
    deflection_angle_deg: float = 0.0,
) -> Tuple[float, float]:
    """
    Calculate wind-induced surface leeway drift vector with Coriolis deflection.

    Args:
        u_wind: Zonal wind velocity (m/s).
        v_wind: Meridional wind velocity (m/s).
        leeway_factor: Leeway multiplier (typically 0.03).
        deflection_angle_deg: Angle offset clockwise (North) / counter-clockwise (South).

    Returns:
        (u_drift, v_drift) velocity components.
    """
    theta_rad = np.radians(deflection_angle_deg)
    cos_t = np.cos(theta_rad)
    sin_t = np.sin(theta_rad)
    u_def = u_wind * cos_t - v_wind * sin_t
    v_def = u_wind * sin_t + v_wind * cos_t
    return float(leeway_factor * u_def), float(leeway_factor * v_def)
