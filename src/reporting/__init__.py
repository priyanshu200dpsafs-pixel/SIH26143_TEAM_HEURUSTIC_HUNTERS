"""
Reporting and Evidentiary Brief Generation Module.

Generates legally defensible, standardized PDF "Prosecutor's Briefs"
incorporating satellite imagery chips, drift trajectories, AIS track overlays,
and chain-of-custody verification metadata.
"""

from .generate_report import ProsecutorBriefGenerator, compile_evidentiary_brief

__all__ = [
    "ProsecutorBriefGenerator",
    "compile_evidentiary_brief",
]
