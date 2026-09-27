"""
Deterministic Replay AIS Provider.

Ingests recorded / synthetic AIS benchmark scenario files for deterministic replay.
Explicitly labels all emitted trajectories as SIMULATED / REPLAY.
Does NOT expose hidden ground-truth culprit identities to downstream attribution engines.
"""

# Re-export from canonical ais ingestion package for backward compatibility
from src.ingestion.ais.replay_provider import ReplayAISProvider

__all__ = ["ReplayAISProvider"]
