"""Unit tests for evidentiary report generation."""

import pytest
from src.reporting.generate_report import ProsecutorBriefGenerator


def test_brief_generator_initialization():
    """Verify report compiler output directory configuration."""
    generator = ProsecutorBriefGenerator(output_dir="test_reports")
    assert generator.output_dir == "test_reports"


def test_brief_assembly_stub_raises():
    """Verify report assembly raises NotImplementedError."""
    generator = ProsecutorBriefGenerator()
    with pytest.raises(NotImplementedError):
        generator.build_brief(
            incident_id="TEST-001",
            detection_data={},
            hindcast_data={},
            suspect_vessels=[],
        )
