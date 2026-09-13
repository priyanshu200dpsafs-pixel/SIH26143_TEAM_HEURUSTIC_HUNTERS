"""Unit tests for backward drift hindcasting and ensemble uncertainty quantification."""

import numpy as np
import pytest
from pathlib import Path
from shapely.geometry import Polygon

from src.drift_model.environmental_interpolator import EnvironmentalInterpolator
from src.drift_model.hindcast import BackwardDriftHindcaster, sample_particles_in_geometry
from src.drift_model.uncertainty import UncertaintyConeGenerator

PROJECT_ROOT = Path(__file__).resolve().parent.parent
ERA5_PATH = PROJECT_ROOT / "data" / "weather" / "era5_wind_mediterranean_case_study.nc"
OSCAR_PATH = PROJECT_ROOT / "data" / "ocean_currents" / "oscar_currents_final_20240823.nc"


@pytest.fixture
def hindcaster():
    interp = EnvironmentalInterpolator(
        era5_path=str(ERA5_PATH),
        oscar_path=str(OSCAR_PATH),
        default_windage=0.03,
    )
    return BackwardDriftHindcaster(
        interpolator=interp,
        default_windage_range=(0.025, 0.035),
        horizontal_diffusivity_kh=10.0,
    )


def test_particle_sampling_in_polygon():
    """Verify uniform particle sampling inside a spill bounding polygon."""
    poly = Polygon([(18.2, 34.4), (18.4, 34.4), (18.4, 34.6), (18.2, 34.6)])
    pts = sample_particles_in_geometry(poly, num_particles=100, rng=np.random.default_rng(42))
    assert len(pts) == 100
    for lon, lat in pts:
        assert 18.2 <= lon <= 18.4
        assert 34.4 <= lat <= 34.6


def test_uncertainty_cone_confidence_regions():
    """Verify 50%, 80%, and 95% confidence polygon hierarchies."""
    rng = np.random.default_rng(42)
    # Gaussian particle cluster around (18.0, 34.0)
    pts = rng.normal(loc=[18.0, 34.0], scale=[0.05, 0.05], size=(200, 2))
    ugen = UncertaintyConeGenerator(horizontal_diffusivity_kh=10.0)

    p50 = ugen.build_confidence_polygon(pts, confidence_level=0.50)
    p80 = ugen.build_confidence_polygon(pts, confidence_level=0.80)
    p95 = ugen.build_confidence_polygon(pts, confidence_level=0.95)

    assert p50["shapely_polygon"].area < p80["shapely_polygon"].area
    assert p80["shapely_polygon"].area < p95["shapely_polygon"].area
    assert p95["particle_count"] > p50["particle_count"]


def test_backward_hindcast_execution(hindcaster):
    """Verify backward hindcast generates probability densities and time envelopes."""
    spill_box = (18.25, 34.45, 18.35, 34.55)
    result = hindcaster.run_hindcast(
        spill_geometry=spill_box,
        observation_time="2024-08-23T09:41:12Z",
        lookback_hours=6.0,
        time_step_seconds=1200.0,  # 20 min
        num_particles=50,
        random_seed=42,
    )

    assert result["num_particles"] == 50
    assert len(result["time_envelopes"]) > 0
    assert "origin_probability_raster" in result

    # Check probability raster normalizes to 1.0
    prob_grid = result["origin_probability_raster"]["probability_grid"]
    assert np.isclose(prob_grid.sum(), 1.0)

    # Check confidence regions are valid polygons
    for conf_key in ["p50", "p80", "p95"]:
        conf_poly = result["origin_confidence_regions"][conf_key]
        assert conf_poly["shapely_polygon"].is_valid
        assert conf_poly["shapely_polygon"].area > 0.0
