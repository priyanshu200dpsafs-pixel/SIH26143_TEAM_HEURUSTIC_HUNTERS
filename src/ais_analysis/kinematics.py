"""
AIS Kinematic Verification & Integrity Anomaly Engine.

Computes physical navigation parameters across AIS vessel trajectories:
- Haversine geodesic displacement
- Implied speed over ground
- Tangential acceleration
- Rate of turn and heading continuity
- Temporal broadcast gaps

Flags:
- Impossible speed (> 45 knots for commercial ships)
- Excessive acceleration (> 1.5 m/s²)
- Abrupt impossible turn rate (> 60°/min)
- AIS continuity anomaly (transponder gaps > 30 minutes)
Designation: 'AIS INTEGRITY ANOMALY' (strictly avoiding unverified 'SPOOFING CONFIRMED').
"""

from typing import Any, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd

EARTH_RADIUS_METERS = 6371000.0


def haversine_distance_meters(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Calculate Great Circle distance between two points in meters."""
    phi1, phi2 = np.radians(lat1), np.radians(lat2)
    dphi = np.radians(lat2 - lat1)
    dlambda = np.radians(lon2 - lon1)

    a = np.sin(dphi / 2.0) ** 2 + np.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2.0) ** 2
    c = 2.0 * np.arctan2(np.sqrt(a), np.sqrt(1.0 - a))
    return float(EARTH_RADIUS_METERS * c)


def compute_turn_rate_deg_per_min(heading1: float, heading2: float, dt_seconds: float) -> float:
    """Calculate shortest angular turn rate in degrees per minute."""
    if dt_seconds <= 0.0:
        return 0.0
    d_deg = (heading2 - heading1 + 180.0) % 360.0 - 180.0
    return float(abs(d_deg) / (dt_seconds / 60.0))


def series_to_epoch_seconds(s: pd.Series) -> np.ndarray:
    """Convert pandas datetime series to epoch seconds safely across all pandas versions."""
    t = pd.to_datetime(s, utc=True)
    divisor = 10**6 if "us" in str(t.dtype) else 10**9
    return t.astype("int64").values // divisor


class AISKinematicEngine:
    """
    Evaluates kinematic validity and transponder continuity across an AIS track.
    """

    def __init__(
        self,
        max_speed_knots: float = 45.0,
        max_acceleration_mps2: float = 1.5,
        max_turn_rate_deg_per_min: float = 60.0,
        max_gap_minutes: float = 30.0,
    ):
        self.max_speed_knots = max_speed_knots
        self.max_acceleration_mps2 = max_acceleration_mps2
        self.max_turn_rate_deg_per_min = max_turn_rate_deg_per_min
        self.max_gap_minutes = max_gap_minutes

    def analyze_trajectory(self, vessel_df: pd.DataFrame) -> Dict[str, Any]:
        """
        Analyze a single vessel's AIS records sorted chronologically.

        Returns:
            Dictionary with kinematic metrics, detected anomalies, and continuity flags.
        """
        if len(vessel_df) < 2:
            return {
                "valid": True,
                "record_count": len(vessel_df),
                "anomalies": [],
                "has_integrity_anomaly": False,
                "continuity_gaps": [],
            }

        df = vessel_df.sort_values("BaseDateTime").reset_index(drop=True)
        times = series_to_epoch_seconds(df["BaseDateTime"])

        anomalies = []
        continuity_gaps = []
        speeds_knots = []
        accelerations_mps2 = []
        turn_rates_deg_min = []

        for i in range(len(df) - 1):
            t1, t2 = times[i], times[i + 1]
            dt = float(t2 - t1)
            if dt <= 0.0:
                continue

            lon1, lat1 = float(df.at[i, "LON"]), float(df.at[i, "LAT"])
            lon2, lat2 = float(df.at[i + 1, "LON"]), float(df.at[i + 1, "LAT"])
            sog1 = float(df.at[i, "SOG"])
            sog2 = float(df.at[i + 1, "SOG"])
            cog1 = float(df.at[i, "COG"])
            cog2 = float(df.at[i + 1, "COG"])

            # Distance and implied speed
            dist_m = haversine_distance_meters(lon1, lat1, lon2, lat2)
            implied_speed_mps = dist_m / dt
            implied_speed_knots = implied_speed_mps / 0.514444
            speeds_knots.append(implied_speed_knots)

            # Acceleration
            accel_mps2 = abs(sog2 * 0.514444 - sog1 * 0.514444) / dt
            accelerations_mps2.append(accel_mps2)

            # Turn rate
            turn_rate = compute_turn_rate_deg_per_min(cog1, cog2, dt)
            turn_rates_deg_min.append(turn_rate)

            # Check for temporal gap (continuity anomaly)
            dt_min = dt / 60.0
            if dt_min > self.max_gap_minutes:
                gap_record = {
                    "type": "AIS INTEGRITY ANOMALY",
                    "subtype": "TEMPORAL_TRANSPONDER_GAP",
                    "start_time": df.at[i, "BaseDateTime"],
                    "end_time": df.at[i + 1, "BaseDateTime"],
                    "duration_minutes": round(dt_min, 1),
                    "start_coord": [lon1, lat1],
                    "end_coord": [lon2, lat2],
                    "gap_distance_nm": round(dist_m / 1852.0, 2),
                }
                continuity_gaps.append(gap_record)
                anomalies.append(gap_record)

            # Check for impossible speed
            if implied_speed_knots > self.max_speed_knots or sog2 > self.max_speed_knots:
                anomalies.append({
                    "type": "AIS INTEGRITY ANOMALY",
                    "subtype": "IMPOSSIBLE_SPEED",
                    "timestamp": df.at[i + 1, "BaseDateTime"],
                    "speed_knots": round(max(implied_speed_knots, sog2), 1),
                    "threshold_knots": self.max_speed_knots,
                    "coord": [lon2, lat2],
                })

            # Check for excessive acceleration
            if accel_mps2 > self.max_acceleration_mps2:
                anomalies.append({
                    "type": "AIS INTEGRITY ANOMALY",
                    "subtype": "EXCESSIVE_ACCELERATION",
                    "timestamp": df.at[i + 1, "BaseDateTime"],
                    "acceleration_mps2": round(accel_mps2, 2),
                    "threshold_mps2": self.max_acceleration_mps2,
                })

            # Check for abrupt impossible turn
            if turn_rate > self.max_turn_rate_deg_per_min and dt_min < 5.0:
                anomalies.append({
                    "type": "AIS INTEGRITY ANOMALY",
                    "subtype": "IMPOSSIBLE_TURN_RATE",
                    "timestamp": df.at[i + 1, "BaseDateTime"],
                    "turn_rate_deg_per_min": round(turn_rate, 1),
                    "threshold_deg_per_min": self.max_turn_rate_deg_per_min,
                })

        has_integrity_anomaly = len(anomalies) > 0

        return {
            "mmsi": int(df.at[0, "MMSI"]),
            "vessel_name": str(df.at[0, "VesselName"]),
            "total_records": len(df),
            "max_speed_knots": round(float(np.max(speeds_knots)), 1) if speeds_knots else 0.0,
            "max_acceleration_mps2": round(float(np.max(accelerations_mps2)), 2) if accelerations_mps2 else 0.0,
            "max_turn_rate_deg_min": round(float(np.max(turn_rates_deg_min)), 1) if turn_rates_deg_min else 0.0,
            "continuity_gaps": continuity_gaps,
            "anomalies": anomalies,
            "has_integrity_anomaly": has_integrity_anomaly,
        }
