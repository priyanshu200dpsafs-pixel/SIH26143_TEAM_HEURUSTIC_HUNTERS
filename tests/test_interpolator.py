"""Unit tests for spatial and temporal environmental interpolation."""

import numpy as np
import pytest
from pathlib import Path
from src.drift_model.environmental_interpolator import EnvironmentalInterpolator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ERA5_PATH = PROJECT_ROOT / "data" / "weather" / "era5_wind_mediterranean_case_study.nc"
OSCAR_PATH = PROJECT_ROOT / "data" / "ocean_currents" / "oscar_currents_final_20240823.nc"


@pytest.fixture
def interpolator():
    return EnvironmentalInterpolator(
        era5_path=str(ERA5_PATH),
        oscar_path=str(OSCAR_PATH),
        default_windage=0.03,
    )


def test_exact_grid_point_interpolation(interpolator):
    """Test interpolation at an exact ERA5 grid node."""
    # Exact grid point: lat 34.5, lon 18.0, 2024-08-23 09:00:00 UTC
    u, v = interpolator.interpolate_wind(18.0, 34.5, "2024-08-23T09:00:00Z")
    assert not np.isnan(u) and not np.isnan(v)
    assert -30.0 < u < 30.0
    assert -30.0 < v < 30.0


def test_between_grid_interpolation(interpolator):
    """Test bilinear spatial and linear temporal interpolation between grid points."""
    # Midway between grid cells: lat 34.375, lon 18.125, at 09:30 UTC
    u_mid, v_mid = interpolator.interpolate_wind(18.125, 34.375, "2024-08-23T09:30:00Z")
    assert not np.isnan(u_mid) and not np.isnan(v_mid)

    # Values at surrounding nodes
    u0, v0 = interpolator.interpolate_wind(18.0, 34.25, "2024-08-23T09:00:00Z")
    u1, v1 = interpolator.interpolate_wind(18.25, 34.50, "2024-08-23T10:00:00Z")
    # Midpoint should be bounded within a reasonable envelope of local nodes
    min_u, max_u = min(u0, u1) - 1.5, max(u0, u1) + 1.5
    assert min_u <= u_mid <= max_u


def test_outside_coverage_handling(interpolator):
    """Test query coordinates outside domain (clamped or zero-fallback)."""
    # Well outside Mediterranean ERA5 domain (e.g. Pacific ocean)
    u_out, v_out = interpolator.interpolate_wind(-150.0, 10.0, "2024-08-23T09:00:00Z", fallback_nearest=True)
    assert not np.isnan(u_out) and not np.isnan(v_out)

    # Without fallback
    u_strict, v_strict = interpolator.interpolate_wind(-150.0, 10.0, "2024-08-23T09:00:00Z", fallback_nearest=False)
    assert u_strict == 0.0 and v_strict == 0.0


def test_oscar_current_interpolation(interpolator):
    """Test OSCAR current vector interpolation."""
    # Central Mediterranean coordinates
    u_curr, v_curr = interpolator.interpolate_current(18.3, 34.5)
    assert not np.isnan(u_curr) and not np.isnan(v_curr)
    # Ocean currents in Mediterranean are typically between -1.5 and 1.5 m/s
    assert -2.0 < u_curr < 2.0
    assert -2.0 < v_curr < 2.0


def test_total_advective_velocity(interpolator):
    """Verify combined current + windage * wind advective velocity."""
    u_tot, v_tot = interpolator.get_advective_velocity(
        lon=18.3,
        lat=34.5,
        timestamp="2024-08-23T09:41:12Z",
        windage=0.035,
        deflection_deg=10.0,
    )
    assert not np.isnan(u_tot) and not np.isnan(v_tot)
    # Total drift speed is physically realistic (< 5 m/s)
    speed = np.hypot(u_tot, v_tot)
    assert 0.01 <= speed <= 3.0
