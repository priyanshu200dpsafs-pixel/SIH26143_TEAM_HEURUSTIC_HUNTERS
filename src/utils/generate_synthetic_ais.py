"""
Synthetic Maritime AIS Trajectory Generator.

Produces synthetic AIS trajectory datasets adhering to the exact 16-column
NOAA MarineCadastre CSV schema for controlled forensic evaluation.

Scenario:
- 8 innocent vessels (cargo, container, ferry, patrol) with continuous pings.
- 1 guilty crude oil tanker ('ATLANTIC CARRIER') with:
    - Direct transit through hindcast spill origin.
    - 45-minute transponder blackout (dark vessel window).
    - Draft reduction indicating illicit discharge.
"""

import math
import random
import datetime
from pathlib import Path
from typing import Dict, List, Any
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "ais" / "synthetic"

# Exact NOAA MarineCadastre schema columns
SCHEMA_COLUMNS = [
    "MMSI",
    "BaseDateTime",
    "LAT",
    "LON",
    "SOG",
    "COG",
    "Heading",
    "VesselName",
    "IMO",
    "CallSign",
    "VesselType",
    "Status",
    "Length",
    "Width",
    "Draft",
    "Cargo",
]

# Scenario Parameters (Mediterranean Spill Scenario)
SPILL_ORIGIN_LAT = 34.6180
SPILL_ORIGIN_LON = 18.1050
SCENARIO_START = datetime.datetime(2026, 9, 11, 12, 0, 0, tzinfo=datetime.timezone.utc)
SCENARIO_DURATION_HOURS = 24
PING_INTERVAL_MINUTES = 5


def calculate_lat_lon(start_lat: float, start_lon: float, speed_knots: float, heading_deg: float, elapsed_hours: float):
    """Displace coordinates based on speed, course, and elapsed time."""
    # 1 knot = 1.852 km/h; 1 deg lat ~= 111.0 km; 1 deg lon ~= 111.0 * cos(lat)
    distance_km = speed_knots * 1.852 * elapsed_hours
    heading_rad = math.radians(heading_deg)
    
    delta_lat = (distance_km * math.cos(heading_rad)) / 111.0
    mean_lat = start_lat + delta_lat / 2.0
    delta_lon = (distance_km * math.sin(heading_rad)) / (111.0 * math.cos(math.radians(mean_lat)))
    
    return start_lat + delta_lat, start_lon + delta_lon


def generate_scenario_data() -> pd.DataFrame:
    """Generate synthetic AIS records matching MarineCadastre schema."""
    random.seed(42)
    records: List[Dict[str, Any]] = []

    # 1. Guilty Vessel: ATLANTIC CARRIER (Crude Oil Tanker)
    guilty_mmsi = 636018992
    guilty_start_lat = 34.2000
    guilty_start_lon = 17.7000
    guilty_speed = 13.5  # knots
    guilty_heading = 38.0  # degrees NE

    current_time = SCENARIO_START
    elapsed = 0.0

    while elapsed <= SCENARIO_DURATION_HOURS:
        # Check for intentional AIS dark window: 2026-09-11 19:15 to 20:00 (7.25h to 8.0h from start)
        in_dark_window = 7.25 <= elapsed <= 8.00

        lat, lon = calculate_lat_lon(guilty_start_lat, guilty_start_lon, guilty_speed, guilty_heading, elapsed)
        
        # Draft drop after discharge: 14.2m -> 12.4m
        current_draft = 14.2 if elapsed < 7.5 else 12.4

        if not in_dark_window:
            records.append({
                "MMSI": guilty_mmsi,
                "BaseDateTime": current_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "LAT": round(lat + random.gauss(0, 0.0002), 6),
                "LON": round(lon + random.gauss(0, 0.0002), 6),
                "SOG": round(guilty_speed + random.uniform(-0.3, 0.3), 1),
                "COG": round(guilty_heading + random.uniform(-1.0, 1.0), 1),
                "Heading": round(guilty_heading),
                "VesselName": "ATLANTIC CARRIER",
                "IMO": "IMO9348123",
                "CallSign": "D5XY8",
                "VesselType": 80.0,  # Tanker
                "Status": "under way using engine",
                "Length": 274.0,
                "Width": 48.0,
                "Draft": round(current_draft, 1),
                "Cargo": 80.0,
            })

        current_time += datetime.timedelta(minutes=PING_INTERVAL_MINUTES)
        elapsed += PING_INTERVAL_MINUTES / 60.0

    # 2. Innocent Vessels: 8 vessels navigating parallel/divergent tracks without anomalies
    innocent_profiles = [
        {"name": "PACIFIC TITAN", "mmsi": 352002140, "type": 82.0, "len": 182, "wid": 32, "draft": 9.5, "s_lat": 34.0, "s_lon": 18.8, "spd": 14.0, "hdg": 330.0},
        {"name": "AEGEAN BREEZE", "mmsi": 240889000, "type": 71.0, "len": 294, "wid": 40, "draft": 13.0, "s_lat": 35.1, "s_lon": 17.5, "spd": 18.5, "hdg": 115.0},
        {"name": "MED EXPRESS", "mmsi": 247120300, "type": 60.0, "len": 145, "wid": 24, "draft": 6.2, "s_lat": 34.8, "s_lon": 19.2, "spd": 22.0, "hdg": 260.0},
        {"name": "BLUE HORIZON", "mmsi": 239100450, "type": 70.0, "len": 225, "wid": 32, "draft": 11.8, "s_lat": 33.9, "s_lon": 18.2, "spd": 12.0, "hdg": 45.0},
        {"name": "COASTAL DEFENDER", "mmsi": 247000999, "type": 55.0, "len": 65, "wid": 11, "draft": 3.8, "s_lat": 34.3, "s_lon": 18.5, "spd": 16.0, "hdg": 20.0},
        {"name": "SEA STAR", "mmsi": 636015522, "type": 37.0, "len": 42, "wid": 9, "draft": 2.5, "s_lat": 34.9, "s_lon": 17.9, "spd": 9.5, "hdg": 180.0},
        {"name": "GLOBAL TRADER", "mmsi": 255806000, "type": 79.0, "len": 260, "wid": 36, "draft": 12.5, "s_lat": 34.1, "s_lon": 17.2, "spd": 15.0, "hdg": 70.0},
        {"name": "NORTHERN LIGHT", "mmsi": 311000888, "type": 81.0, "len": 190, "wid": 30, "draft": 10.1, "s_lat": 35.3, "s_lon": 18.6, "spd": 13.0, "hdg": 210.0},
    ]

    for p in innocent_profiles:
        curr_time = SCENARIO_START
        curr_elapsed = 0.0
        while curr_elapsed <= SCENARIO_DURATION_HOURS:
            lat, lon = calculate_lat_lon(p["s_lat"], p["s_lon"], p["spd"], p["hdg"], curr_elapsed)
            records.append({
                "MMSI": p["mmsi"],
                "BaseDateTime": curr_time.strftime("%Y-%m-%dT%H:%M:%SZ"),
                "LAT": round(lat + random.gauss(0, 0.0002), 6),
                "LON": round(lon + random.gauss(0, 0.0002), 6),
                "SOG": round(p["spd"] + random.uniform(-0.2, 0.2), 1),
                "COG": round(p["hdg"] + random.uniform(-0.8, 0.8), 1),
                "Heading": round(p["hdg"]),
                "VesselName": p["name"],
                "IMO": f"IMO{random.randint(9100000, 9999999)}",
                "CallSign": f"CALL{p['mmsi'] % 1000}",
                "VesselType": p["type"],
                "Status": "under way using engine",
                "Length": float(p["len"]),
                "Width": float(p["wid"]),
                "Draft": float(p["draft"]),
                "Cargo": float(p["type"]),
            })
            curr_time += datetime.timedelta(minutes=PING_INTERVAL_MINUTES)
            curr_elapsed += PING_INTERVAL_MINUTES / 60.0

    df = pd.DataFrame(records, columns=SCHEMA_COLUMNS)
    df.sort_values(by=["BaseDateTime", "MMSI"], inplace=True)
    return df


def main():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dest_file = OUTPUT_DIR / "synthetic_ais_spill_scenario.csv"
    
    print("[*] Generating synthetic AIS traffic adhering to NOAA MarineCadastre schema...")
    df = generate_scenario_data()
    
    df.to_csv(dest_file, index=False)
    size_mb = dest_file.stat().st_size / (1024 * 1024)
    
    # Verification stats
    min_lat, max_lat = df["LAT"].min(), df["LAT"].max()
    min_lon, max_lon = df["LON"].min(), df["LON"].max()
    start_time = df["BaseDateTime"].min()
    end_time = df["BaseDateTime"].max()
    vessels = df["VesselName"].unique()

    print("\n" + "=" * 65)
    print("SYNTHETIC AIS SCENARIO GENERATION VERIFICATION REPORT")
    print("=" * 65)
    print(f"Destination:           {dest_file}")
    print(f"File Size:             {size_mb:.2f} MB")
    print(f"Total Rows:            {len(df):,}")
    print(f"Unique Vessels:        {len(vessels)} (1 suspect + {len(vessels)-1} background vessels)")
    print(f"Time Range:            {start_time} to {end_time}")
    print(f"Spatial Envelope:      Lat [{min_lat:.4f}, {max_lat:.4f}], Lon [{min_lon:.4f}, {max_lon:.4f}]")
    print(f"Schema Compliance:     16/16 NOAA MarineCadastre columns")
    print("\nVessel Breakdown:")
    for v in vessels:
        v_df = df[df["VesselName"] == v]
        is_suspect = "🚨 SUSPECT (Transponder gap + Draft drop)" if v == "ATLANTIC CARRIER" else "Innocent transit"
        print(f"  - {v:18s} (MMSI: {v_df['MMSI'].iloc[0]}) | {len(v_df):3d} pings | {is_suspect}")
    print("=" * 65)


if __name__ == "__main__":
    main()
