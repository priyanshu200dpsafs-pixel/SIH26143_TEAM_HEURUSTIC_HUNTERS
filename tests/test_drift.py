"""Unit tests for Lagrangian drift hindcasting and uncertainty modules."""

import pytest
from src.drift_model.lagrangian_tracker import LagrangianDriftTracker
from src.drift_model.uncertainty import UncertaintyConeGenerator


def test_drift_tracker_initialization():
    """Verify tracker initialization with physical leeway parameters."""
    tracker = LagrangianDriftTracker(windage_factor=0.035, deflection_angle_deg=15.0)
    assert tracker.windage_factor == 0.035
    assert tracker.deflection_angle_deg == 15.0


def test_uncertainty_cone_generator_initialization():
    """Verify turbulent diffusivity parameter setting."""
    cone_gen = UncertaintyConeGenerator(horizontal_diffusivity_kh=25.0)
    assert cone_gen.kh == 25.0


def test_hindcast_stub_raises():
    """Verify hindcast execution raises NotImplementedError."""
    tracker = LagrangianDriftTracker()
    with pytest.raises(NotImplementedError):
        tracker.run_hindcast(origin_coords=(35.0, 18.0), detection_time="2026-09-12T12:00:00Z")
