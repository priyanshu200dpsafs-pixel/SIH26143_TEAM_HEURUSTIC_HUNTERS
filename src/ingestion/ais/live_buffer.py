"""
Rolling In-Memory Buffer for Live Maritime AIS Feeds.

Maintains a sliding temporal window (e.g., 48 hours) of normalized AISObservation records.
Enables rapid spatial-temporal slice queries to identify which commercial vessels
were in or near the inferred oil spill discharge zone during the estimated release window.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
import pandas as pd
from shapely.geometry import Point, Polygon, shape

from src.ingestion.ais.models import AISObservation, VesselTrack
from src.ais_analysis.track_builder import build_track, sort_by_timestamp, deduplicate


class LiveAISBuffer:
    """
    Thread-safe sliding buffer for real-time AIS observation streams.
    """

    def __init__(
        self,
        buffer_hours: float = 48.0,
        minimum_track_points: int = 3,
        maximum_gap_minutes: float = 30.0,
    ):
        self.buffer_hours = buffer_hours
        self.minimum_track_points = minimum_track_points
        self.maximum_gap_minutes = maximum_gap_minutes
        self._observations: List[AISObservation] = []

    def __len__(self) -> int:
        return len(self._observations)

    def add_observation(self, obs: AISObservation) -> None:
        """Insert a single normalized observation."""
        if obs:
            self._observations.append(obs)

    def add_observations(self, obs_list: List[AISObservation]) -> None:
        """Bulk ingest multiple observations."""
        valid = [o for o in obs_list if o]
        self._observations.extend(valid)

    def prune_older_than(self, cutoff_time_iso: str) -> int:
        """Remove all observations timestamped strictly before cutoff_time_iso."""
        initial_len = len(self._observations)
        self._observations = [o for o in self._observations if o.timestamp >= cutoff_time_iso]
        return initial_len - len(self._observations)

    def prune_rolling_window(self, current_time_iso: Optional[str] = None) -> int:
        """Prune records older than buffer_hours relative to current time."""
        if not self._observations and not current_time_iso:
            return 0

        if current_time_iso:
            now_dt = pd.to_datetime(current_time_iso, utc=True)
        else:
            now_dt = max(pd.to_datetime(o.timestamp, utc=True) for o in self._observations)

        cutoff_dt = now_dt - timedelta(hours=self.buffer_hours)
        cutoff_iso = cutoff_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        return self.prune_older_than(cutoff_iso)

    def query_observations(
        self,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
        mmsi: Optional[Union[str, int]] = None,
    ) -> List[AISObservation]:
        """
        Filter buffered observations by time window, spatial bounding box, and optional MMSI.
        bbox format: (min_lon, min_lat, max_lon, max_lat)
        """
        results = self._observations

        if mmsi is not None:
            m_str = str(mmsi)
            results = [o for o in results if o.mmsi == m_str]

        if start_time_iso is not None:
            results = [o for o in results if o.timestamp >= start_time_iso]

        if end_time_iso is not None:
            results = [o for o in results if o.timestamp <= end_time_iso]

        if bbox is not None:
            min_lon, min_lat, max_lon, max_lat = bbox
            results = [
                o for o in results
                if min_lon <= o.longitude <= max_lon and min_lat <= o.latitude <= max_lat
            ]

        return sort_by_timestamp(deduplicate(results))

    def get_vessel_tracks(
        self,
        start_time_iso: Optional[str] = None,
        end_time_iso: Optional[str] = None,
        bbox: Optional[Tuple[float, float, float, float]] = None,
    ) -> List[VesselTrack]:
        """
        Reconstruct tracks for vessels having at least minimum_track_points within criteria.
        """
        obs_list = self.query_observations(
            start_time_iso=start_time_iso,
            end_time_iso=end_time_iso,
            bbox=bbox,
        )
        if not obs_list:
            return []

        by_mmsi: Dict[str, List[AISObservation]] = {}
        for o in obs_list:
            by_mmsi.setdefault(o.mmsi, []).append(o)

        tracks: List[VesselTrack] = []
        for mmsi, m_obs in by_mmsi.items():
            if len(m_obs) >= self.minimum_track_points:
                track = build_track(m_obs, max_gap_minutes=self.maximum_gap_minutes)
                tracks.append(track)

        return tracks

    def get_candidate_tracks_for_incident(
        self,
        spill_time_iso: str,
        release_window_start_iso: str,
        origin_polygon: Optional[Any] = None,
        spatial_buffer_deg: float = 0.5,
        temporal_buffer_hours: float = 4.0,
    ) -> List[VesselTrack]:
        """
        Incident-specific query extracting only candidate tracks relevant to the spill.
        Steps:
        1. Temporal envelope: [release_window_start - buffer, spill_time + buffer]
        2. Spatial bounding box: origin polygon bounds + spatial_buffer_deg
        3. Track reconstruction and polygon intersection check
        """
        # Expand temporal window
        t_start_dt = pd.to_datetime(release_window_start_iso, utc=True) - timedelta(hours=temporal_buffer_hours)
        t_end_dt = pd.to_datetime(spill_time_iso, utc=True) + timedelta(hours=temporal_buffer_hours)
        query_start = t_start_dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        query_end = t_end_dt.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Derive spatial bounding box
        bbox = None
        poly_geom = None
        if origin_polygon is not None:
            if isinstance(origin_polygon, dict):
                poly_geom = shape(origin_polygon)
            elif hasattr(origin_polygon, "bounds"):
                poly_geom = origin_polygon

            if poly_geom is not None:
                min_x, min_y, max_x, max_y = poly_geom.bounds
                bbox = (
                    min_x - spatial_buffer_deg,
                    min_y - spatial_buffer_deg,
                    max_x + spatial_buffer_deg,
                    max_y + spatial_buffer_deg,
                )

        candidate_tracks = self.get_vessel_tracks(
            start_time_iso=query_start,
            end_time_iso=query_end,
            bbox=bbox,
        )

        # If an origin polygon is provided, refine candidates
        if poly_geom is not None and candidate_tracks:
            buffered_poly = poly_geom.buffer(spatial_buffer_deg)
            filtered = []
            for track in candidate_tracks:
                # Keep track if any observation point falls inside buffered polygon
                has_point = any(buffered_poly.contains(Point(o.longitude, o.latitude)) for o in track.observations)
                if has_point:
                    filtered.append(track)
            return filtered

        return candidate_tracks
