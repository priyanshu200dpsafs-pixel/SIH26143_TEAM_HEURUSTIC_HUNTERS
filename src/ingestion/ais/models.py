"""
Canonical AIS Data Models & Observation Schemas.

Defines standardized data representations for normalized maritime AIS observations,
vessel tracks, gap records, and provider connection statuses.
Guarantees strict provenance tracking without fabricating missing values.
"""

from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd


class ProviderStatus(str, Enum):
    CONNECTED = "CONNECTED"
    CONNECTING = "CONNECTING"
    DISCONNECTED = "DISCONNECTED"
    RECONNECTING = "RECONNECTING"
    AUTH_REQUIRED = "AUTH_REQUIRED"
    NOT_CONFIGURED = "NOT_CONFIGURED"
    PROVIDER_ERROR = "PROVIDER_ERROR"
    NETWORK_ERROR = "NETWORK_ERROR"
    RATE_LIMITED = "RATE_LIMITED"


@dataclass
class AISObservation:
    """
    Canonical normalized AIS observation.
    Fields may be None when upstream provider does not supply them.
    Never fabricates missing values.
    """
    mmsi: str
    timestamp: str  # ISO 8601 UTC (e.g., '2024-08-23T09:41:12Z')
    latitude: float
    longitude: float
    sog: Optional[float] = None  # Speed Over Ground in knots
    cog: Optional[float] = None  # Course Over Ground in degrees [0, 360)
    heading: Optional[float] = None  # True heading in degrees [0, 359] or 511 if unavailable
    navigation_status: Optional[str] = None  # Under way using engine, at anchor, moored, etc.
    imo: Optional[str] = None  # IMO number if available
    ship_name: Optional[str] = None
    ship_type: Optional[str] = None  # e.g., 'Tanker', 'Cargo', 'Fishing', or numeric code string
    length: Optional[float] = None  # Length in meters
    beam: Optional[float] = None  # Beam in meters
    draft: Optional[float] = None  # Current maximum present static draught in meters
    source: str = "UNKNOWN"  # Provider identifier (e.g. 'AISStream', 'Spire', 'ReplayFixture')
    data_status: str = "REAL"  # 'REAL' or 'SIMULATED'
    mode: str = "LIVE"  # 'LIVE' or 'REPLAY'
    vessel_id: Optional[str] = None  # Persistent provider vessel identity (e.g., GFW vessel_id)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @property
    def epoch_seconds(self) -> float:
        """Convert ISO timestamp to UTC epoch seconds."""
        dt = pd.to_datetime(self.timestamp, utc=True)
        return dt.timestamp()

    @property
    def vessel_name(self) -> Optional[str]:
        return self.ship_name

    @property
    def vessel_type(self) -> Optional[str]:
        return self.ship_type

    @property
    def speed_over_ground(self) -> float:
        return self.sog or 0.0

    @property
    def course_over_ground(self) -> float:
        return self.cog or 0.0


@dataclass
class AISGap:
    """
    Structured record of a detected broadcast hiatus between two consecutive observations.
    AIS Gap != Guilt. Gaps are recorded as objective temporal integrity features.
    """
    mmsi: str
    gap_start: str  # ISO 8601 UTC timestamp of last observation before gap
    gap_end: str  # ISO 8601 UTC timestamp of first observation after gap
    gap_duration_minutes: float
    location_before: Tuple[float, float]  # (lon, lat)
    location_after: Tuple[float, float]  # (lon, lat)
    kinematic_context: Dict[str, Any] = field(default_factory=dict)
    source: str = "UNKNOWN"

    def to_dict(self) -> Dict[str, Any]:
        return {
            "mmsi": self.mmsi,
            "gap_start": self.gap_start,
            "gap_end": self.gap_end,
            "gap_duration_minutes": round(self.gap_duration_minutes, 2),
            "location_before": list(self.location_before),
            "location_after": list(self.location_after),
            "kinematic_context": self.kinematic_context,
            "source": self.source,
        }


@dataclass
class VesselTrack:
    """
    Chronologically ordered trajectory for a single vessel.
    """
    mmsi: str
    ship_name: Optional[str] = None
    ship_type: Optional[str] = None
    imo: Optional[str] = None
    observations: List[AISObservation] = field(default_factory=list)
    gaps: List[AISGap] = field(default_factory=list)
    source: str = "UNKNOWN"
    data_status: str = "REAL"
    mode: str = "LIVE"
    vessel_id: Optional[str] = None
    track_resolution: str = "VARIABLE"

    @property
    def point_count(self) -> int:
        return len(self.observations)

    @property
    def start_time(self) -> Optional[str]:
        return self.observations[0].timestamp if self.observations else None

    @property
    def end_time(self) -> Optional[str]:
        return self.observations[-1].timestamp if self.observations else None

    def to_dataframe(self) -> pd.DataFrame:
        """
        Convert track into standardized DataFrame compatible with existing kinematics
        and trajectory intersection engines (BaseDateTime, LAT, LON, SOG, COG, etc.).
        """
        if not self.observations:
            return pd.DataFrame(columns=[
                "MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG",
                "Heading", "VesselName", "VesselType", "Draft", "IMO"
            ])

        rows = []
        for obs in self.observations:
            # Map ship_type to numeric code if available, or default code
            vtype_num = 1001.0
            if obs.ship_type:
                try:
                    vtype_num = float(obs.ship_type)
                except ValueError:
                    st_lower = str(obs.ship_type).lower()
                    if 'tanker' in st_lower:
                        vtype_num = 1004.0
                    elif 'cargo' in st_lower:
                        vtype_num = 1003.0
                    elif 'fishing' in st_lower:
                        vtype_num = 1002.0
                    elif 'tug' in st_lower:
                        vtype_num = 1006.0
                    else:
                        vtype_num = 1001.0

            rows.append({
                "MMSI": int(obs.mmsi) if str(obs.mmsi).isdigit() else obs.mmsi,
                "BaseDateTime": obs.timestamp,
                "LAT": float(obs.latitude),
                "LON": float(obs.longitude),
                "SOG": float(obs.sog) if obs.sog is not None else 0.0,
                "COG": float(obs.cog) if obs.cog is not None else 0.0,
                "Heading": float(obs.heading) if obs.heading is not None else 511.0,
                "VesselName": obs.ship_name or self.ship_name or "UNKNOWN",
                "VesselType": vtype_num,
                "Draft": float(obs.draft) if obs.draft is not None else 0.0,
                "IMO": obs.imo or self.imo or "UNKNOWN",
                "Source": obs.source,
                "DataStatus": obs.data_status,
                "Mode": obs.mode,
            })

        df = pd.DataFrame(rows)
        df = df.sort_values("BaseDateTime").reset_index(drop=True)
        return df

    @property
    def vessel_name(self) -> Optional[str]:
        return self.ship_name

    @property
    def vessel_type(self) -> Optional[str]:
        return self.ship_type

    @property
    def source_provider(self) -> str:
        return self.source

    @property
    def anomalies(self) -> List[Any]:
        return []

    @property
    def callsign(self) -> Optional[str]:
        return None

    @property
    def length_m(self) -> Optional[float]:
        return None

    @property
    def width_m(self) -> Optional[float]:
        return None

    @property
    def draft_m(self) -> Optional[float]:
        return None

    def to_geojson(self) -> Dict[str, Any]:
        coords = [[float(o.longitude), float(o.latitude)] for o in self.observations]
        return {
            "type": "Feature",
            "geometry": {
                "type": "LineString",
                "coordinates": coords,
            },
            "properties": {
                "mmsi": self.mmsi,
                "vessel_name": self.ship_name or "Unknown",
                "vessel_type": self.ship_type or "Unknown",
                "imo": self.imo,
                "point_count": len(coords),
                "start_time": self.start_time,
                "end_time": self.end_time,
                "source": self.source,
                "data_status": self.data_status,
                "mode": self.mode,
            }
        }
