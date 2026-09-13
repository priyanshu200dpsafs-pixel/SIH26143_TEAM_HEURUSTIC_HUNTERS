"""
Spatio-Temporal Trajectory Intersection Engine.

Evaluates geometric and temporal intersections between candidate vessel AIS tracks
and backwards-hindcasted source confidence regions.
Calculates:
- Direct polygon containment (points inside region)
- Segment crossing (line segments cutting through region, including across transponder blackouts)
- Temporal concurrence with the hindcast release window
- Minimum distance to source region boundary
- Estimated residence time inside the source region
"""

from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd
from shapely.geometry import LineString, Point, Polygon

from src.ais_analysis.kinematics import haversine_distance_meters, series_to_epoch_seconds


class TrajectoryIntersectionEngine:
    """
    Computes spatial-temporal intersection metrics between vessel trajectories
    and oil spill source envelopes.
    """

    def __init__(self, temporal_tolerance_seconds: float = 3600.0):
        """
        Args:
            temporal_tolerance_seconds: Buffer in seconds around target release time window.
        """
        self.temporal_tolerance = temporal_tolerance_seconds

    def evaluate_intersection(
        self,
        vessel_df: pd.DataFrame,
        source_polygon: Polygon,
        source_time_window: Tuple[float, float],
    ) -> Dict[str, Any]:
        """
        Analyze whether and how a vessel track intersects the source probability region.

        Args:
            vessel_df: DataFrame of vessel AIS records with columns:
                       ['MMSI', 'VesselName', 'BaseDateTime', 'LAT', 'LON', 'SOG', 'COG'].
            source_polygon: Shapely Polygon of source confidence region (e.g. 95% hull).
            source_time_window: (t_min_epoch, t_max_epoch) of estimated release window.

        Returns:
            Structured dictionary with intersection metrics.
        """
        if len(vessel_df) == 0:
            return {
                "intersects": False,
                "spatial_overlap": False,
                "temporal_overlap": False,
                "min_distance_nm": 999.0,
                "residence_time_minutes": 0.0,
                "crossing_type": "NONE",
            }

        df = vessel_df.sort_values("BaseDateTime").reset_index(drop=True)
        times = series_to_epoch_seconds(df["BaseDateTime"])

        t_win_min, t_win_max = source_time_window
        buffered_t_min = t_win_min - self.temporal_tolerance
        buffered_t_max = t_win_max + self.temporal_tolerance

        min_dist_m = float("inf")
        contained_indices = []
        crossing_segments = []
        concurrent_points = 0
        total_time_inside_sec = 0.0

        for i in range(len(df)):
            t_curr = float(times[i])
            lon = float(df.at[i, "LON"])
            lat = float(df.at[i, "LAT"])
            pt = Point(lon, lat)

            # Check distance to polygon
            dist_deg = source_polygon.distance(pt)
            if dist_deg == 0.0 or source_polygon.contains(pt):
                dist_m = 0.0
                contained_indices.append(i)
            else:
                dist_m = dist_deg * 111139.0

            if dist_m < min_dist_m:
                min_dist_m = dist_m

            # Check temporal concurrence
            if buffered_t_min <= t_curr <= buffered_t_max:
                concurrent_points += 1

        # Check line segment crossings
        for i in range(len(df) - 1):
            t1, t2 = float(times[i]), float(times[i + 1])
            p1 = Point(float(df.at[i, "LON"]), float(df.at[i, "LAT"]))
            p2 = Point(float(df.at[i + 1, "LON"]), float(df.at[i + 1, "LAT"]))
            seg = LineString([p1, p2])

            # Check if segment temporal span intersects release window
            seg_t_min, seg_t_max = min(t1, t2), max(t1, t2)
            seg_in_window = (seg_t_min <= buffered_t_max) and (seg_t_max >= buffered_t_min)

            if seg.intersects(source_polygon):
                crossing_segments.append({
                    "start_idx": i,
                    "end_idx": i + 1,
                    "start_time": df.at[i, "BaseDateTime"],
                    "end_time": df.at[i + 1, "BaseDateTime"],
                    "duration_sec": t2 - t1,
                    "in_temporal_window": seg_in_window,
                })
                if seg_in_window:
                    inter = seg.intersection(source_polygon)
                    frac = inter.length / seg.length if seg.length > 0 else 1.0
                    total_time_inside_sec += (t2 - t1) * frac

        spatial_overlap = len(contained_indices) > 0 or len(crossing_segments) > 0
        temporal_overlap = concurrent_points > 0 or any(c["in_temporal_window"] for c in crossing_segments)
        full_intersection = spatial_overlap and temporal_overlap

        # Crossing classification
        if len(contained_indices) > 0:
            crossing_type = "DIRECT_BROADCAST_CONTAINMENT"
        elif len(crossing_segments) > 0:
            crossing_type = "TRANSIT_SEGMENT_INTERSECTION"
        elif min_dist_m < 5000.0:
            crossing_type = "NEAR_MISS_WITHIN_5KM"
        else:
            crossing_type = "NONE"

        min_dist_nm = min_dist_m / 1852.0

        return {
            "mmsi": int(df.at[0, "MMSI"]),
            "vessel_name": str(df.at[0, "VesselName"]),
            "intersects": full_intersection,
            "spatial_overlap": spatial_overlap,
            "temporal_overlap": temporal_overlap,
            "min_distance_nm": round(min_dist_nm, 2),
            "min_distance_meters": round(min_dist_m, 1),
            "contained_point_count": len(contained_indices),
            "crossing_segment_count": len(crossing_segments),
            "residence_time_minutes": round(total_time_inside_sec / 60.0, 1),
            "crossing_type": crossing_type,
        }
