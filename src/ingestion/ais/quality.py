"""
Real AIS Data Quality & Integrity Auditing.

Generates structured schema validation and data health reports when real AIS providers
are queried. Quantifies:
- Observation and unique vessel counts
- Spatial and temporal bounding
- Missing field rates (MMSI, position, SOG, COG)
- Duplicate message rates
- Coordinate, timestamp, and kinematic anomalies
Outputs reports to data/results/ais/live_quality_report.json.
"""

from datetime import datetime, timezone
import json
import math
from pathlib import Path
from typing import Any, Dict, List, Optional
import numpy as np

from src.ingestion.ais.models import AISObservation
from src.ais_analysis.track_builder import build_track


def generate_quality_report(
    observations: List[AISObservation],
    provider_name: str = "UNKNOWN",
    output_path: Optional[str] = "data/results/ais/live_quality_report.json",
    invalid_coord_count: int = 0,
    invalid_time_count: int = 0,
) -> Dict[str, Any]:
    """
    Audit incoming real AIS stream and generate validation metrics conforming to Phase 5B specifications.
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    total_obs = len(observations)

    if total_obs == 0:
        report = {
            "provider": provider_name,
            "query_timestamp": now_utc,
            "observation_count": 0,
            "unique_vessels": 0,
            "earliest_timestamp": None,
            "latest_timestamp": None,
            "spatial_extent": None,
            "duplicate_rate": 0.0,
            "missing_mmsi_rate": 0.0,
            "missing_position_rate": 0.0,
            "missing_sog_rate": 0.0,
            "missing_cog_rate": 0.0,
            "invalid_coordinate_count": invalid_coord_count,
            "invalid_timestamp_count": invalid_time_count,
            "large_gap_count": 0,
            "kinematic_anomaly_count": 0,
            "status": "EMPTY_OR_UNCONFIGURED",
        }
    else:
        mmsis = set(o.mmsi for o in observations if o.mmsi)
        timestamps = [o.timestamp for o in observations if o.timestamp]
        earliest_ts = min(timestamps) if timestamps else None
        latest_ts = max(timestamps) if timestamps else None

        lats = [o.latitude for o in observations if o.latitude is not None]
        lons = [o.longitude for o in observations if o.longitude is not None]
        spatial_extent = {
            "min_lat": round(min(lats), 4) if lats else 0.0,
            "max_lat": round(max(lats), 4) if lats else 0.0,
            "min_lon": round(min(lons), 4) if lons else 0.0,
            "max_lon": round(max(lons), 4) if lons else 0.0,
        } if lats and lons else None

        # Missing field rates
        missing_mmsi = sum(1 for o in observations if not o.mmsi)
        missing_pos = sum(1 for o in observations if o.latitude is None or o.longitude is None)
        missing_sog = sum(1 for o in observations if o.sog is None)
        missing_cog = sum(1 for o in observations if o.cog is None)

        # Duplicate detection
        seen = set()
        duplicates = 0
        for o in observations:
            key = (o.mmsi, o.timestamp, round(o.latitude, 5), round(o.longitude, 5))
            if key in seen:
                duplicates += 1
            else:
                seen.add(key)
        dup_rate = round(duplicates / total_obs, 4)

        # Kinematic anomalies & track gaps
        excessive_speed = sum(1 for o in observations if o.sog is not None and o.sog > 45.0)

        # Group by MMSI to detect gaps
        by_mmsi: Dict[str, List[AISObservation]] = {}
        for o in observations:
            by_mmsi.setdefault(o.mmsi, []).append(o)

        large_gaps = 0
        for m, m_obs in by_mmsi.items():
            if len(m_obs) >= 2:
                track = build_track(m_obs, max_gap_minutes=30.0)
                large_gaps += len(track.gaps)

        report = {
            "provider": provider_name,
            "query_timestamp": now_utc,
            "observation_count": total_obs,
            "unique_vessels": len(mmsis),
            "earliest_timestamp": earliest_ts,
            "latest_timestamp": latest_ts,
            "spatial_extent": spatial_extent,
            "duplicate_rate": dup_rate,
            "missing_mmsi_rate": round(missing_mmsi / total_obs, 4),
            "missing_position_rate": round(missing_pos / total_obs, 4),
            "missing_sog_rate": round(missing_sog / total_obs, 4),
            "missing_cog_rate": round(missing_cog / total_obs, 4),
            "invalid_coordinate_count": invalid_coord_count,
            "invalid_timestamp_count": invalid_time_count,
            "large_gap_count": large_gaps,
            "kinematic_anomaly_count": excessive_speed,
            "status": "VALIDATED",
        }

    if output_path:
        out_file = Path(output_path)
        out_file.parent.mkdir(parents=True, exist_ok=True)
        with open(out_file, "w") as f:
            json.dump(report, f, indent=2)

    return report
