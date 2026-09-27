"""
AIS Traffic Spatiotemporal Filter.

Filters raw or cleaned AIS messages and trajectories against the hindcasted
oil spill dispersion cone and discharge time window.
Optimizes query throughput so that only spatio-temporally compatible vessels
are dispatched to the attribution scoring engine.
"""

from datetime import datetime, timezone, timedelta
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from shapely.geometry import Point, Polygon, shape

from src.ingestion.ais.models import AISObservation, VesselTrack
from src.ais_analysis.track_builder import build_track, normalize_raw_observation


class AISTrafficFilter:
    """
    Filters maritime AIS trajectories within target spatial-temporal corridors.
    """

    def __init__(self, ais_data_path: Optional[str] = None):
        self.ais_data_path = ais_data_path

    def filter_candidates(
        self,
        bounding_polygon: Union[Dict[str, Any], Polygon],
        time_window: Dict[str, str],
        vessel_types: Optional[List[int]] = None,
        dataframe: Optional[pd.DataFrame] = None,
    ) -> List[Dict[str, Any]]:
        """
        Identify vessels present inside the candidate release polygon during time_window.

        Args:
            bounding_polygon: GeoJSON polygon or Shapely Polygon of hindcast dispersion cone.
            time_window: Dict with 'start_time' and 'end_time' ISO timestamps.
            vessel_types: Optional list of AIS ship type codes.
            dataframe: Optional pre-loaded DataFrame.

        Returns:
            List of candidate vessel trajectory records grouped by MMSI.
        """
        df = dataframe
        if df is None and self.ais_data_path:
            df = pd.read_csv(self.ais_data_path)

        if df is None or df.empty:
            return []

        poly = shape(bounding_polygon) if isinstance(bounding_polygon, dict) else bounding_polygon
        start_t = time_window.get("start_time", "")
        end_t = time_window.get("end_time", "")

        filtered_df = filter_vessels_in_spatiotemporal_window(
            ais_dataframe=df,
            polygon_coords=poly,
            start_utc=start_t,
            end_utc=end_t,
        )

        if filtered_df.empty:
            return []

        if vessel_types is not None and "VesselType" in filtered_df.columns:
            filtered_df = filtered_df[filtered_df["VesselType"].isin(vessel_types)]

        candidates = []
        for mmsi, v_df in filtered_df.groupby("MMSI"):
            candidates.append({
                "mmsi": int(mmsi),
                "vessel_name": str(v_df["VesselName"].iloc[0]) if "VesselName" in v_df else "UNKNOWN",
                "vessel_type": float(v_df["VesselType"].iloc[0]) if "VesselType" in v_df else 1001.0,
                "points_count": len(v_df),
                "records": v_df.to_dict(orient="records"),
            })

        return candidates


def filter_vessels_in_spatiotemporal_window(
    ais_dataframe: pd.DataFrame,
    polygon_coords: Union[Polygon, List[Tuple[float, float]]],
    start_utc: str,
    end_utc: str,
) -> pd.DataFrame:
    """
    Vectorized filter across bounding coordinates and timestamps.
    """
    if ais_dataframe.empty:
        return ais_dataframe.copy()

    df = ais_dataframe.copy()

    # Temporal filter
    time_col = "BaseDateTime" if "BaseDateTime" in df.columns else "timestamp"
    if time_col in df.columns:
        if start_utc:
            df = df[df[time_col] >= start_utc]
        if end_utc:
            df = df[df[time_col] <= end_utc]

    if df.empty:
        return df

    # Spatial filter
    poly = polygon_coords if isinstance(polygon_coords, Polygon) else Polygon(polygon_coords)
    min_x, min_y, max_x, max_y = poly.bounds

    lon_col = "LON" if "LON" in df.columns else "longitude"
    lat_col = "LAT" if "LAT" in df.columns else "latitude"

    # Fast bbox filter first
    bbox_mask = (
        (df[lon_col] >= min_x) & (df[lon_col] <= max_x) &
        (df[lat_col] >= min_y) & (df[lat_col] <= max_y)
    )
    candidate_subset = df[bbox_mask]
    if candidate_subset.empty:
        return candidate_subset

    # Fine polygon check
    contains_mask = [
        poly.contains(Point(lon, lat))
        for lon, lat in zip(candidate_subset[lon_col], candidate_subset[lat_col])
    ]

    return candidate_subset[contains_mask].reset_index(drop=True)
