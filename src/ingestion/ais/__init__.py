"""
AIS Ingestion Package.

Provides provider abstraction, canonical observations, replay and live streaming adapters,
in-memory buffering, and quality reporting for maritime vessel surveillance.
"""

from src.ingestion.ais.models import (
    AISObservation,
    AISGap,
    VesselTrack,
    ProviderStatus,
)
from src.ingestion.ais.base_provider import AISProvider
from src.ingestion.ais.replay_provider import ReplayAISProvider
from src.ingestion.ais.live_provider import LiveAISProvider
from src.ingestion.ais.aisstream_provider import AISStreamProvider, convert_bbox_to_aisstream
from src.ingestion.ais.live_buffer import LiveAISBuffer
from src.ingestion.ais.quality import generate_quality_report
from src.ais_analysis.track_builder import (
    build_track,
    normalize_raw_observation,
    sort_by_timestamp,
    deduplicate,
    merge_observations,
    interpolate_for_analysis,
)

from src.ingestion.ais.historical_provider import HistoricalAISProvider
from src.ingestion.ais.gfw_historical_provider import GFWHistoricalAISProvider
__all__ = [
    "HistoricalAISProvider",
    "GFWHistoricalAISProvider",
    "AISObservation",
    "AISGap",
    "VesselTrack",
    "ProviderStatus",
    "AISProvider",
    "ReplayAISProvider",
    "LiveAISProvider",
    "AISStreamProvider",
    "convert_bbox_to_aisstream",
    "LiveAISBuffer",
    "generate_quality_report",
    "build_track",
    "normalize_raw_observation",
    "sort_by_timestamp",
    "deduplicate",
    "merge_observations",
    "interpolate_for_analysis",
]
