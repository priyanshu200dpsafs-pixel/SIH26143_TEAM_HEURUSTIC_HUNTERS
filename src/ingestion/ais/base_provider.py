"""
Abstract Base Provider for Maritime AIS Ingestion.

Defines the contract for querying raw positions, reconstructed tracks, and static ship data
from both simulated replay engines and live maritime transponder feeds.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Tuple, Union
from src.ingestion.ais.models import AISObservation, VesselTrack, ProviderStatus


class AISProvider(ABC):
    """
    Abstract base class for all AIS data providers.
    """

    @property
    @abstractmethod
    def data_status(self) -> str:
        """Return 'REAL' or 'SIMULATED'."""
        pass

    @property
    @abstractmethod
    def mode(self) -> str:
        """Return 'LIVE' or 'REPLAY'."""
        pass

    @abstractmethod
    def get_status(self) -> ProviderStatus:
        """Return current operational status of the provider."""
        pass

    @abstractmethod
    def get_positions(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
        mmsi: Optional[Union[str, int]] = None,
    ) -> List[AISObservation]:
        """
        Query raw normalized AIS observations matching spatial/temporal/vessel filters.
        bbox format: (min_lon, min_lat, max_lon, max_lat)
        """
        pass

    @abstractmethod
    def get_track(
        self,
        mmsi: Union[str, int],
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
    ) -> Optional[VesselTrack]:
        """
        Retrieve a reconstructed, chronologically sorted, gap-aware track for a single vessel.
        """
        pass

    @abstractmethod
    def get_tracks(
        self,
        mmsis: Optional[List[Union[str, int]]] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
    ) -> List[VesselTrack]:
        """
        Retrieve reconstructed tracks for all vessels matching query criteria.
        """
        pass

    @abstractmethod
    def get_vessel_static_data(self, mmsi: Union[str, int]) -> Optional[Dict[str, Any]]:
        """
        Retrieve static vessel particulars (name, IMO, callsign, dimensions).
        """
        pass
