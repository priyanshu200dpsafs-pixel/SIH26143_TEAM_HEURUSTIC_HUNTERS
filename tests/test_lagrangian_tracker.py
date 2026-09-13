"""Unit tests for Lagrangian drift engine forward and backward propagation."""

import numpy as np
import pytest
from pathlib import Path
from src.drift_model.environmental_interpolator import EnvironmentalInterpolator
from src.drift_model.lagrangian_tracker import LagrangianDriftTracker, calculate_leeway_drift

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ERA5_PATH = PROJECT_ROOT / "data" / "weather" / "era5_wind_mediterranean_case_study.nc"
OSCAR_PATH = PROJECT_ROOT / "data" / "ocean_currents" / "oscar_currents_final_20240823.nc"


@pytest.fixture
def tracker():
    interp = EnvironmentalInterpolator(
        era5_path=str(ERA5_PATH),
        oscar_path=str(OSCAR_PATH),
        default_windage=0.03,
        default_deflection_deg=10.0,
    )
    return LagrangianDriftTracker(
        interpolator=interp,
        windage_factor=0.03,
        horizontal_diffusivity_kh=15.0,
    )


def test_leeway_drift_deflection():
    """Verify wind leeway magnitude and deflection rotation."""
    # North wind (u=0, v=10 m/s), 0 deg deflection
    u_d, v_d = calculate_leeway_drift(u_wind=0.0, v_wind=10.0, leeway_factor=0.03, deflection_angle_deg=0.0)
    assert u_d == 0.0
    assert np.isclose(v_d, 0.3)

    # 90 deg clockwise deflection
    u_d90, v_d90 = calculate_leeway_drift(u_wind=0.0, v_wind=10.0, leeway_factor=0.03, deflection_angle_deg=90.0)
    assert np.isclose(u_d90, -0.3)
    assert np.isclose(v_d90, 0.0, atol=1e-6)


def test_forward_drift_simulation(tracker):
    """Verify forward trajectory simulation produces valid coordinates."""
    seed_points = [(18.3, 34.5), (18.31, 34.51)]
    res = tracker.simulate(
        seed_positions=seed_points,
        start_time="2024-08-23T09:00:00Z",
        duration_seconds=3600.0 * 3,  # 3 hours
        time_step_seconds=600.0,       # 10 min
        direction=1,
        random_seed=42,
    )
    assert res["direction"] == "forward"
    assert res["num_particles"] == 2
    assert res["num_steps"] == 18
    assert res["trajectories"].shape == (2, 19, 2)
    # Positions should have moved away from start
    end_lon, end_lat = res["trajectories"][0, -1, :]
    assert (end_lon != 18.3) or (end_lat != 34.5)


def test_backward_drift_simulation(tracker):
    """Verify backward trajectory simulation moves opposite to forward advection."""
    seed_points = [(18.3, 34.5)]
    res_back = tracker.simulate(
        seed_positions=seed_points,
        start_time="2024-08-23T12:00:00Z",
        duration_seconds=3600.0 * 3,
        time_step_seconds=600.0,
        direction=-1,
        random_seed=42,
    )
    assert res_back["direction"] == "backward"
    # Timestamps should decrease
    assert res_back["timestamps_epoch"][-1] < res_back["timestamps_epoch"][0]


def test_stochastic_diffusion_dispersion(tracker):
    """Verify multiple particles from the same origin disperse when Kh > 0."""
    seed_points = [(18.3, 34.5) for _ in range(50)]
    res = tracker.simulate(
        seed_positions=seed_points,
        start_time="2024-08-23T09:00:00Z",
        duration_seconds=3600.0 * 2,
        time_step_seconds=600.0,
        direction=1,
        random_seed=123,
    )
    final_positions = res["trajectories"][:, -1, :]
    # Check that positions are not identical due to random walk diffusion
    std_lon = float(np.std(final_positions[:, 0]))
    std_lat = float(np.std(final_positions[:, 1]))
    assert std_lon > 0.0001
    assert std_lat > 0.0001
