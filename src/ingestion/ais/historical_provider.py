"""
Historical Maritime AIS Provider Interface.

Provides legitimate historical AIS voyage reconstruction for forensic satellite SAR
attribution investigations. Strict scientific and legal constraints:
- Genuinely sourced from historical maritime transponder records (e.g., NOAA Marine Cadastre,
  national maritime authorities, or verified historical transponder databases).
- Emitted records strictly labeled: data_status='REAL', mode='HISTORICAL'.
- NEVER substitutes real-time / live AIS (e.g. AISStream) for historical acquisitions.
- NEVER substitutes synthetic benchmark replays and labels them real.
- When no legitimate historical provider or data covers the requested spatiotemporal window,
  honestly returns empty tracks and reports HISTORICAL AIS UNAVAILABLE.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd

from src.ingestion.ais.base_provider import AISProvider
from src.ingestion.ais.models import AISObservation, VesselTrack, ProviderStatus
from src.ais_analysis.track_builder import normalize_raw_observation, build_track

logger = logging.getLogger(__name__)


class HistoricalAISProvider(AISProvider):
    """
    Legitimate Historical AIS Provider for retrospective SAR incident attribution.
    """

    def __init__(
        self,
        data_dir: Optional[Union[str, Path]] = None,
        file_patterns: Optional[List[str]] = None,
        source_label: str = "NOAA_MarineCadastre",
    ):
        env_dir = os.getenv("HISTORICAL_AIS_DIR")
        if data_dir is not None:
            self.data_dir = Path(data_dir)
        elif env_dir:
            self.data_dir = Path(env_dir)
        else:
            self.data_dir = Path("data/ais/real_reference")

        self.file_patterns = file_patterns or ["*.csv", "*.parquet"]
        self.source_label = source_label
        self._data_status = "REAL"
        self._mode = "HISTORICAL"
        self._indexed_files: List[Path] = []
        self._refresh_index()

    @property
    def data_status(self) -> str:
        return self._data_status

    @property
    def mode(self) -> str:
        return self._mode

    def get_status(self) -> ProviderStatus:
        if not self.data_dir.exists():
            return ProviderStatus.NOT_CONFIGURED
        if not self._indexed_files:
            return ProviderStatus.NOT_CONFIGURED
        return ProviderStatus.CONNECTED

    def _refresh_index(self) -> None:
        self._indexed_files = []
        if self.data_dir.exists():
            for pat in self.file_patterns:
                self._indexed_files.extend(list(self.data_dir.glob(pat)))

    def has_coverage_for(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
    ) -> bool:
        if not self._indexed_files:
            return False
        if bbox is None and start_time is None and end_time is None:
            return True

        positions = self.get_positions(
            bbox=bbox,
            start_time_iso=start_time,
            end_time_iso=end_time,
            limit=1,
        )
        return len(positions) > 0

    def get_positions(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
        mmsi: Optional[Union[str, int]] = None,
        limit: Optional[int] = None,
        **kwargs: Any,
    ) -> List[AISObservation]:
        start_iso = start_time_iso or kwargs.get("start_time")
        end_iso = end_time_iso or kwargs.get("end_time")

        if not self._indexed_files:
            return []

        observations: List[AISObservation] = []

        for fpath in self._indexed_files:
            try:
                if fpath.suffix.lower() == ".parquet":
                    df = pd.read_parquet(fpath)
                else:
                    df = pd.read_csv(fpath)

                if df.empty:
                    continue

                col_map = {
                    "lat": "LAT", "latitude": "LAT",
                    "lon": "LON", "longitude": "LON",
                    "basedatetime": "BaseDateTime", "timestamp": "BaseDateTime",
                    "vesselname": "VesselName", "ship_name": "VesselName",
                    "vesseltype": "VesselType", "ship_type": "VesselType",
                    "mmsi": "MMSI",
                    "sog": "SOG", "speed": "SOG",
                    "cog": "COG", "course": "COG",
                    "heading": "Heading",
                    "imo": "IMO",
                    "draft": "Draft",
                }
                rename_dict = {}
                for c in df.columns:
                    clow = c.strip().lower()
                    if clow in col_map:
                        rename_dict[c] = col_map[clow]
                df = df.rename(columns=rename_dict)

                if "BaseDateTime" not in df.columns or "LAT" not in df.columns or "LON" not in df.columns:
                    continue

                if mmsi is not None:
                    m_str = str(mmsi).strip()
                    df = df[df["MMSI"].astype(str).str.strip() == m_str]
                    if df.empty:
                        continue

                if bbox is not None:
                    min_lon, min_lat, max_lon, max_lat = bbox
                    df = df[
                        (df["LON"] >= min_lon) & (df["LON"] <= max_lon) &
                        (df["LAT"] >= min_lat) & (df["LAT"] <= max_lat)
                    ]
                    if df.empty:
                        continue

                if start_iso is not None:
                    df = df[df["BaseDateTime"].astype(str) >= str(start_iso)]
                    if df.empty:
                        continue
                if end_iso is not None:
                    df = df[df["BaseDateTime"].astype(str) <= str(end_iso)]
                    if df.empty:
                        continue

                for _, row in df.iterrows():
                    obs = normalize_raw_observation(
                        raw=row.to_dict(),
                        source=self.source_label,
                        data_status=self.data_status,
                        mode=self.mode,
                    )
                    if obs:
                        observations.append(obs)
                        if limit and len(observations) >= limit:
                            return observations

            except Exception as e:
                logger.warning(f"Error reading historical AIS file {fpath}: {e}")
                continue

        return observations

    def get_tracks(
        self,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
        mmsis: Optional[List[Union[str, int]]] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        **kwargs: Any,
    ) -> List[VesselTrack]:
        start_iso = start_time or start_time_iso or kwargs.get("start_time")
        end_iso = end_time or end_time_iso or kwargs.get("end_time")
        q_bbox = bbox or kwargs.get("bbox")

        # Handle positional swap: get_tracks(start_time, end_time, bbox)
        if isinstance(q_bbox, str) and (start_iso is None or isinstance(start_iso, str)):
            temp_start = q_bbox
            temp_end = start_iso
            temp_bbox = end_iso if isinstance(end_iso, (tuple, list)) else kwargs.get("bbox")
            start_iso = temp_start
            end_iso = temp_end
            q_bbox = temp_bbox

        obs_list = self.get_positions(
            bbox=q_bbox,
            start_time_iso=start_iso,
            end_time_iso=end_iso,
        )

        if not obs_list:
            return []

        by_mmsi: Dict[str, List[AISObservation]] = {}
        for o in obs_list:
            if mmsis is not None:
                if str(o.mmsi) not in [str(m) for m in mmsis]:
                    continue
            by_mmsi.setdefault(o.mmsi, []).append(o)

        tracks: List[VesselTrack] = []
        for mmsi_key, v_obs in by_mmsi.items():
            t = build_track(v_obs)
            t.data_status = self.data_status
            t.mode = self.mode
            t.source = self.source_label
            tracks.append(t)

        return tracks

    def get_track(
        self,
        mmsi: Union[str, int],
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
        start_time: Optional[str] = None,
        end_time: Optional[str] = None,
        **kwargs: Any,
    ) -> Optional[VesselTrack]:
        start_iso = start_time or start_time_iso or kwargs.get("start_time")
        end_iso = end_time or end_time_iso or kwargs.get("end_time")

        obs = self.get_positions(
            mmsi=mmsi,
            start_time_iso=start_iso,
            end_time_iso=end_iso,
        )
        if not obs:
            return None
        t = build_track(obs)
        t.data_status = self.data_status
        t.mode = self.mode
        t.source = self.source_label
        return t

    def get_vessel_static_data(self, mmsi: Union[str, int]) -> Optional[Dict[str, Any]]:
        track = self.get_track(mmsi=mmsi)
        if not track or not track.observations:
            return None
        obs = track.observations[0]
        return {
            "mmsi": obs.mmsi,
            "ship_name": track.ship_name or obs.ship_name or "UNKNOWN",
            "ship_type": track.ship_type or obs.ship_type or "UNKNOWN",
            "imo": track.imo or obs.imo,
            "length": obs.length,
            "beam": obs.beam,
            "draft": obs.draft,
            "source": self.source_label,
            "data_status": self.data_status,
            "mode": self.mode,
        }
