"""
AIS Track Construction, Normalization & Continuity Engine.

Transforms unstructured or stream-based AISObservation records into chronological,
deduplicated, gap-aware vessel trajectories (VesselTrack).
Enforces physical plausibility bounds during normalization without deleting valid
tactical maneuvers.
"""

from datetime import datetime, timezone
import math
from typing import Any, Dict, List, Optional, Tuple, Union
import numpy as np
import pandas as pd

from src.ingestion.ais.models import AISObservation, AISGap, VesselTrack


def normalize_timestamp_to_iso(val: Any) -> Optional[str]:
    """Convert various datetime/string/epoch representations to ISO 8601 UTC string."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return None
    try:
        # Numeric epoch (seconds or milliseconds)
        if isinstance(val, (int, float)):
            if val > 1e11:  # milliseconds
                val = val / 1000.0
            dt = datetime.fromtimestamp(val, tz=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        
        # String parsing via pandas for maximum flexibility
        ts = pd.to_datetime(val, utc=True)
        if pd.isna(ts):
            return None
        return ts.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def normalize_raw_observation(
    raw: Dict[str, Any],
    source: str = "UNKNOWN",
    data_status: str = "REAL",
    mode: str = "LIVE",
) -> Optional[AISObservation]:
    """
    Normalize arbitrary raw provider message or dict into a canonical AISObservation.
    Rejects malformed positions (out-of-bound coords, invalid timestamps, negative SOG).
    Preserves unusual kinematics for kinematic engine evaluation.
    """
    if not isinstance(raw, dict):
        return None

    # 1. MMSI Extraction & Validation
    mmsi_val = (
        raw.get("mmsi")
        or raw.get("MMSI")
        or raw.get("vessel_mmsi")
        or raw.get("mmsi_number")
        or raw.get("UserID")
    )
    if mmsi_val is None:
        return None
    mmsi_str = str(mmsi_val).strip()
    if not mmsi_str or mmsi_str == "0" or mmsi_str.lower() == "none":
        return None

    # 2. Timestamp Validation
    time_raw = (
        raw.get("timestamp")
        or raw.get("BaseDateTime")
        or raw.get("time")
        or raw.get("msg_time")
        or raw.get("dateTime")
        or raw.get("Timestamp")
    )
    iso_time = normalize_timestamp_to_iso(time_raw)
    if not iso_time:
        return None

    # 3. Coordinate Validation
    lat_val = raw.get("latitude") or raw.get("LAT") or raw.get("lat") or raw.get("Latitude")
    lon_val = raw.get("longitude") or raw.get("LON") or raw.get("lon") or raw.get("Longitude")
    if lat_val is None or lon_val is None:
        return None
    try:
        lat = float(lat_val)
        lon = float(lon_val)
    except (ValueError, TypeError):
        return None

    # Strict physical boundary checks
    if math.isnan(lat) or math.isnan(lon):
        return None
    if lat < -90.0 or lat > 90.0:
        return None
    if lon < -180.0 or lon > 180.0:
        return None
    # Filter common uninitialized GPS defaults (e.g. 91.0, 181.0, 0.0 & 0.0 off Null Island if marked default)
    if lat == 0.0 and lon == 0.0 and raw.get("filter_null_island", False):
        return None

    # 4. Navigational Values (SOG, COG, Heading)
    sog_val = raw.get("sog") or raw.get("SOG") or raw.get("speed") or raw.get("Speed")
    sog: Optional[float] = None
    if sog_val is not None:
        try:
            s_f = float(sog_val)
            if not math.isnan(s_f):
                if s_f < 0.0:
                    return None  # Negative speed is physically impossible
                # 102.3 is standard AIS code for unavailable SOG
                sog = s_f if s_f < 102.2 else None
        except (ValueError, TypeError):
            sog = None

    cog_val = raw.get("cog") or raw.get("COG") or raw.get("course") or raw.get("Course")
    cog: Optional[float] = None
    if cog_val is not None:
        try:
            c_f = float(cog_val)
            if not math.isnan(c_f) and 0.0 <= c_f <= 360.0:
                cog = c_f
        except (ValueError, TypeError):
            cog = None

    hdg_val = raw.get("heading") or raw.get("Heading") or raw.get("true_heading")
    heading: Optional[float] = None
    if hdg_val is not None:
        try:
            h_f = float(hdg_val)
            if not math.isnan(h_f) and 0.0 <= h_f <= 359.0:
                heading = h_f
            elif h_f == 511.0:  # 511 is AIS standard for not available
                heading = None
        except (ValueError, TypeError):
            heading = None

    # 5. Metadata (vessel name, type, IMO, draft, dimensions)
    ship_name = (
        raw.get("ship_name")
        or raw.get("VesselName")
        or raw.get("vessel_name")
        or raw.get("name")
    )
    if ship_name:
        ship_name = str(ship_name).strip()

    ship_type = (
        raw.get("ship_type")
        or raw.get("VesselType")
        or raw.get("vessel_type")
        or raw.get("type")
    )
    if ship_type is not None:
        ship_type = str(ship_type).strip()

    imo = raw.get("imo") or raw.get("IMO") or raw.get("imo_number")
    if imo is not None:
        imo = str(imo).strip()

    draft_val = raw.get("draft") or raw.get("Draft") or raw.get("draught")
    draft: Optional[float] = None
    if draft_val is not None:
        try:
            d_f = float(draft_val)
            if not math.isnan(d_f) and 0.0 <= d_f <= 35.0:  # Physical limits of largest tankers
                draft = d_f
        except (ValueError, TypeError):
            draft = None

    length_val = raw.get("length") or raw.get("Length")
    length = float(length_val) if length_val is not None and not math.isnan(float(length_val)) else None

    beam_val = raw.get("beam") or raw.get("Beam") or raw.get("width")
    beam = float(beam_val) if beam_val is not None and not math.isnan(float(beam_val)) else None

    nav_stat = raw.get("navigation_status") or raw.get("NavigationalStatus") or raw.get("status")
    if nav_stat is not None:
        nav_stat = str(nav_stat).strip()

    return AISObservation(
        mmsi=mmsi_str,
        timestamp=iso_time,
        latitude=lat,
        longitude=lon,
        sog=sog,
        cog=cog,
        heading=heading,
        navigation_status=nav_stat,
        imo=imo,
        ship_name=ship_name,
        ship_type=ship_type,
        length=length,
        beam=beam,
        draft=draft,
        source=raw.get("source", source),
        data_status=raw.get("data_status", data_status),
        mode=raw.get("mode", mode),
    )


def sort_by_timestamp(observations: List[AISObservation]) -> List[AISObservation]:
    """Sort observation list chronologically."""
    return sorted(observations, key=lambda obs: obs.timestamp)


def deduplicate(observations: List[AISObservation]) -> List[AISObservation]:
    """
    Remove duplicate observations having identical MMSI, timestamp, and coordinates.
    """
    seen = set()
    deduped = []
    for obs in observations:
        # Precision rounding to avoid micro-float duplicate differences
        key = (obs.mmsi, obs.timestamp, round(obs.latitude, 5), round(obs.longitude, 5))
        if key not in seen:
            seen.add(key)
            deduped.append(obs)
    return deduped


def merge_observations(
    obs_list1: List[AISObservation],
    obs_list2: List[AISObservation],
) -> List[AISObservation]:
    """Merge two observation lists, deduplicating and sorting chronologically."""
    combined = list(obs_list1) + list(obs_list2)
    deduped = deduplicate(combined)
    return sort_by_timestamp(deduped)


def detect_track_gaps(
    sorted_observations: List[AISObservation],
    max_gap_minutes: float = 30.0,
) -> List[AISGap]:
    """
    Scan sorted track for gaps exceeding max_gap_minutes.
    AIS Gap != Guilt. Gaps are preserved as factual trajectory anomalies.
    """
    gaps: List[AISGap] = []
    if len(sorted_observations) < 2:
        return gaps

    for i in range(len(sorted_observations) - 1):
        obs1 = sorted_observations[i]
        obs2 = sorted_observations[i + 1]

        t1 = obs1.epoch_seconds
        t2 = obs2.epoch_seconds
        dt_minutes = (t2 - t1) / 60.0

        if dt_minutes > max_gap_minutes:
            gap = AISGap(
                mmsi=obs1.mmsi,
                gap_start=obs1.timestamp,
                gap_end=obs2.timestamp,
                gap_duration_minutes=dt_minutes,
                location_before=(obs1.longitude, obs1.latitude),
                location_after=(obs2.longitude, obs2.latitude),
                kinematic_context={
                    "sog_before": obs1.sog,
                    "sog_after": obs2.sog,
                    "cog_before": obs1.cog,
                    "cog_after": obs2.cog,
                },
                source=obs1.source,
            )
            gaps.append(gap)

    return gaps


def build_track(
    observations: List[AISObservation],
    max_gap_minutes: float = 30.0,
) -> VesselTrack:
    """
    Construct a clean, chronologically sorted, gap-aware VesselTrack from observations.
    """
    if not observations:
        return VesselTrack(mmsi="UNKNOWN", observations=[], gaps=[])

    mmsi = observations[0].mmsi
    name = next((o.ship_name for o in observations if o.ship_name), None)
    vtype = next((o.ship_type for o in observations if o.ship_type), None)
    imo = next((o.imo for o in observations if o.imo), None)
    source = observations[0].source
    data_status = observations[0].data_status
    mode = observations[0].mode

    # Sort & deduplicate
    sorted_obs = sort_by_timestamp(deduplicate(observations))
    gaps = detect_track_gaps(sorted_obs, max_gap_minutes=max_gap_minutes)

    return VesselTrack(
        mmsi=mmsi,
        ship_name=name,
        ship_type=vtype,
        imo=imo,
        observations=sorted_obs,
        gaps=gaps,
        source=source,
        data_status=data_status,
        mode=mode,
    )


def interpolate_for_analysis(
    track: VesselTrack,
    target_timestamps: List[str],
    max_gap_minutes: float = 30.0,
) -> List[AISObservation]:
    """
    Interpolate vessel positions strictly for small continuous intervals.
    CRITICAL RULE:
    Do NOT interpolate across large transponder gaps (> max_gap_minutes).
    Intermediate vessel positions are NEVER manufactured across large hiatuses.
    """
    if not track.observations or not target_timestamps:
        return []

    obs = track.observations
    times = [o.epoch_seconds for o in obs]
    lats = [o.latitude for o in obs]
    lons = [o.longitude for o in obs]

    interpolated = []

    for t_str in target_timestamps:
        t_iso = normalize_timestamp_to_iso(t_str)
        if not t_iso:
            continue
        dt_target = pd.to_datetime(t_iso, utc=True).timestamp()

        # Check bounds
        if dt_target < times[0] or dt_target > times[-1]:
            continue

        # Find enclosing interval [i, i+1]
        idx = np.searchsorted(times, dt_target)
        if idx == 0:
            interpolated.append(obs[0])
            continue
        if idx >= len(times):
            interpolated.append(obs[-1])
            continue

        t_prev = times[idx - 1]
        t_next = times[idx]
        gap_min = (t_next - t_prev) / 60.0

        # Refuse to manufacture coordinates across large broadcast gaps
        if gap_min > max_gap_minutes:
            continue

        if t_next == t_prev:
            interpolated.append(obs[idx])
            continue

        alpha = (dt_target - t_prev) / (t_next - t_prev)
        interp_lat = lats[idx - 1] + alpha * (lats[idx] - lats[idx - 1])
        interp_lon = lons[idx - 1] + alpha * (lons[idx] - lons[idx - 1])

        # Interpolate SOG if available
        sog_prev = obs[idx - 1].sog
        sog_next = obs[idx].sog
        interp_sog = None
        if sog_prev is not None and sog_next is not None:
            interp_sog = sog_prev + alpha * (sog_next - sog_prev)

        # Course over ground
        interp_cog = obs[idx - 1].cog

        interp_obs = AISObservation(
            mmsi=track.mmsi,
            timestamp=t_iso,
            latitude=float(interp_lat),
            longitude=float(interp_lon),
            sog=interp_sog,
            cog=interp_cog,
            heading=obs[idx - 1].heading,
            ship_name=track.ship_name,
            ship_type=track.ship_type,
            imo=track.imo,
            source=f"{track.source}_INTERPOLATED",
            data_status=track.data_status,
            mode=track.mode,
        )
        interpolated.append(interp_obs)

    return interpolated
