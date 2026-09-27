"""Ingestion package for Continuous Maritime Watch."""

from src.ingestion.replay_ais import ReplayAISProvider
from src.ingestion.ais import (
    AISProvider,
    AISObservation,
    VesselTrack,
    LiveAISProvider,
    LiveAISBuffer,
)
from src.ingestion.ledger import IngestionLedger, IngestionStatus, LedgerEntry
from src.ingestion.sentinel1_provider import (
    CopernicusSentinel1Provider,
    ProviderStatus,
    DownloadStatus,
    Sentinel1ProductMetadata,
)
from src.ingestion.satellite_watch import (
    SatelliteWatcher,
    SatelliteWatchStatus,
    WatchEvent,
    SatelliteCatalogProvider,
    FixtureCatalogProvider,
)
from src.ingestion.watch_service import WatchService

__all__ = [
    "ReplayAISProvider",
    "AISProvider",
    "AISObservation",
    "VesselTrack",
    "LiveAISProvider",
    "LiveAISBuffer",
    "IngestionLedger",
    "IngestionStatus",
    "LedgerEntry",
    "CopernicusSentinel1Provider",
    "ProviderStatus",
    "DownloadStatus",
    "Sentinel1ProductMetadata",
    "SatelliteWatcher",
    "SatelliteWatchStatus",
    "WatchEvent",
    "SatelliteCatalogProvider",
    "FixtureCatalogProvider",
    "WatchService",
]
