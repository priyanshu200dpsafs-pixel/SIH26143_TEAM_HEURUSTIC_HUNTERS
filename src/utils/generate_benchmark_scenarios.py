"""
Benchmark Scenario Generator for Spill Attribution and AIS Kinematics Validation.

Implements the 7 adversarial stress-test scenarios defined in
docs/synthetic_validation_scenarios.md.
Ground-truth culprit identities and release parameters are strictly isolated into
data/ais/synthetic/benchmarks/ground_truth/ (hidden from attribution engine).
"""

import json
from pathlib import Path
from typing import Dict, List, Tuple
import numpy as np
import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
BENCHMARK_DIR = PROJECT_ROOT / "data" / "ais" / "synthetic" / "benchmarks"
HIDDEN_TRUTH_DIR = BENCHMARK_DIR / "ground_truth"


def _generate_vessel_track(
    mmsi: int,
    vessel_name: str,
    vessel_type: float,
    start_time_iso: str,
    start_coord: Tuple[float, float],
    heading_deg: float,
    speed_knots: float,
    duration_hours: float = 18.0,
    interval_minutes: float = 5.0,
    draft: float = 14.0,
    draft_drop: float = 0.0,
    gap_window: Tuple[float, float] = None,  # (start_hr, end_hr)
    kinematic_glitch: bool = False,
    rng: np.random.Generator = None,
) -> pd.DataFrame:
    """Generate a realistic AIS track with optional gaps or kinematic anomalies."""
    if rng is None:
        rng = np.random.default_rng(mmsi)

    t0 = pd.to_datetime(start_time_iso)
    steps = int((duration_hours * 60.0) / interval_minutes)
    records = []

    lon, lat = start_coord
    speed_mps = speed_knots * 0.514444
    dt_sec = interval_minutes * 60.0

    for i in range(steps + 1):
        t_current = t0 + pd.Timedelta(seconds=i * dt_sec)
        elapsed_hr = (i * interval_minutes) / 60.0

        # Check for gap window
        if gap_window is not None and (gap_window[0] <= elapsed_hr <= gap_window[1]):
            # Advance position during blackout without recording broadcast
            rad = np.radians(heading_deg)
            dist_m = speed_mps * dt_sec
            dlat = (dist_m * np.cos(rad)) / 111139.0
            dlon = (dist_m * np.sin(rad)) / (111139.0 * np.cos(np.radians(lat)))
            lat += dlat
            lon += dlon
            continue

        cur_draft = draft - draft_drop if elapsed_hr >= 7.25 else draft
        cur_sog = speed_knots
        cur_cog = heading_deg

        if kinematic_glitch and (7.0 <= elapsed_hr <= 7.5):
            # Impossible kinematic spike (speed > 55 knots, coordinate jump)
            cur_sog = 68.5
            lon += 0.45
            lat += 0.35

        records.append({
            "MMSI": mmsi,
            "BaseDateTime": t_current.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "LAT": round(lat, 5),
            "LON": round(lon, 5),
            "SOG": round(cur_sog + rng.normal(0, 0.1), 1),
            "COG": round(cur_cog + rng.normal(0, 0.5), 1),
            "Heading": round(cur_cog),
            "VesselName": vessel_name,
            "IMO": 9000000 + (mmsi % 100000),
            "CallSign": f"CALL{mmsi % 1000}",
            "VesselType": vessel_type,
            "Status": 0,
            "Length": 240.0 if vessel_type == 1004.0 else 180.0,
            "Width": 38.0 if vessel_type == 1004.0 else 28.0,
            "Draft": round(cur_draft, 1),
            "Cargo": int(vessel_type),
        })

        # Advance position along heading
        rad = np.radians(heading_deg)
        dist_m = speed_mps * dt_sec
        dlat = (dist_m * np.cos(rad)) / 111139.0
        dlon = (dist_m * np.sin(rad)) / (111139.0 * np.cos(np.radians(lat)))
        lat += dlat
        lon += dlon

    return pd.DataFrame(records)


def build_all_scenarios():
    BENCHMARK_DIR.mkdir(parents=True, exist_ok=True)
    HIDDEN_TRUTH_DIR.mkdir(parents=True, exist_ok=True)

    base_time = "2024-08-22T18:00:00Z"
    release_time_target = "2024-08-23T01:15:00Z"  # 7.25 hrs after base_time
    origin_coord_target = (18.353, 34.532)        # (lon, lat)

    # Calculated start coordinate to arrive exactly at origin_coord_target at 01:15 UTC
    # heading 45 deg, speed 13.5 knots, elapsed 7.25 hours:
    culprit_start_coord = (16.955, 33.379)

    scenarios = [
        {
            "id": 1,
            "name": "true_source_continuous_ais",
            "desc": "True culprit vessel sails directly across spill origin with full continuous AIS broadcasting.",
            "target_culprit_mmsi": 240111001,
            "target_culprit_name": "AEGEAN VOYAGER",
            "culprit_config": {
                "mmsi": 240111001,
                "name": "AEGEAN VOYAGER",
                "type": 1004.0,  # Tanker
                "start_coord": culprit_start_coord,
                "heading": 45.0,
                "speed": 13.5,
                "draft_drop": 1.8,
                "gap": None,
                "glitch": False,
            },
            "background_vessels": [
                (240111002, "CARGO PIONEER", 1001.0, (18.60, 33.80), 315.0, 14.0, 0.0, None, False),
                (240111003, "BLUE HORIZON", 1001.0, (17.80, 35.10), 90.0, 12.0, 0.0, None, False),
                (240111004, "GAS TRADER", 1024.0, (19.10, 34.80), 225.0, 15.0, 0.0, None, False),
            ]
        },
        {
            "id": 2,
            "name": "true_source_ais_gap",
            "desc": "True culprit intentionally turns off AIS for 90 minutes while transiting the spill release location.",
            "target_culprit_mmsi": 240222002,
            "target_culprit_name": "MEDITERRANEAN STAR",
            "culprit_config": {
                "mmsi": 240222002,
                "name": "MEDITERRANEAN STAR",
                "type": 1004.0,  # Tanker
                "start_coord": culprit_start_coord,
                "heading": 45.0,
                "speed": 13.5,
                "draft_drop": 1.8,
                "gap": (6.5, 8.0),  # Blackout covering 01:15 UTC
                "glitch": False,
            },
            "background_vessels": [
                (240222003, "CONTAINER EXP", 1001.0, (18.80, 34.00), 300.0, 16.0, 0.0, None, False),
                (240222004, "SEA RUNNER", 1001.0, (17.50, 34.90), 110.0, 11.5, 0.0, None, False),
            ]
        },
        {
            "id": 3,
            "name": "innocent_vessel_ais_gap",
            "desc": "Innocent vessel experiences an AIS transponder outage, but is located 40 nm outside the backward drift cone.",
            "target_culprit_mmsi": None,
            "target_culprit_name": "UNKNOWN_VESSEL",
            "culprit_config": None,
            "background_vessels": [
                (240333001, "PACIFIC TRADER", 1001.0, (17.50, 32.50), 45.0, 13.0, 0.0, (6.0, 8.0), False),  # Far south
                (240333002, "NORDIC STAR", 1001.0, (18.90, 35.50), 240.0, 14.0, 0.0, None, False),
                (240333003, "HELLAS LEADER", 1004.0, (19.80, 34.20), 270.0, 12.5, 0.0, None, False),
            ]
        },
        {
            "id": 4,
            "name": "two_plausible_vessels",
            "desc": "Two vessels transit near the release cone; one tanker with cargo draft drop vs one container ship.",
            "target_culprit_mmsi": 240444001,
            "target_culprit_name": "OLYMPIC PIONEER",
            "culprit_config": {
                "mmsi": 240444001,
                "name": "OLYMPIC PIONEER",
                "type": 1004.0,  # Tanker
                "start_coord": culprit_start_coord,
                "heading": 45.0,
                "speed": 13.5,
                "draft_drop": 1.8,
                "gap": None,
                "glitch": False,
            },
            "background_vessels": [
                # Parallel innocent container ship passing 5 nm away with no draft drop
                (240444002, "MSC ADRIATIC", 1001.0, (culprit_start_coord[0] + 0.08, culprit_start_coord[1] - 0.06), 45.0, 15.0, 0.0, None, False),
                (240444003, "BALTIC EXPRESS", 1001.0, (18.60, 35.20), 200.0, 13.0, 0.0, None, False),
            ]
        },
        {
            "id": 5,
            "name": "no_compatible_vessel_dark_fleet",
            "desc": "Spill caused by an unflagged non-broadcasting dark vessel; zero legitimate AIS tracks enter the cone.",
            "target_culprit_mmsi": None,
            "target_culprit_name": "DARK_FLEET_NON_BROADCASTING",
            "culprit_config": None,
            "background_vessels": [
                (240555001, "GLOBAL HOPE", 1001.0, (18.80, 35.50), 260.0, 13.0, 0.0, None, False),
                (240555002, "ISLAND TRADER", 1001.0, (17.20, 33.20), 80.0, 11.0, 0.0, None, False),
                (240555003, "CMA CGM MED", 1001.0, (19.50, 34.10), 310.0, 17.0, 0.0, None, False),
            ]
        },
        {
            "id": 6,
            "name": "impossible_kinematics",
            "desc": "A vessel presents spoofed or corrupted GPS data (>60 knots, teleportation jump).",
            "target_culprit_mmsi": None,
            "target_culprit_name": "UNKNOWN_VESSEL",
            "culprit_config": None,
            "background_vessels": [
                (240666001, "PHANTOM V", 1004.0, (17.30, 33.50), 45.0, 13.0, 0.0, None, True),  # Kinematic glitch
                (240666002, "STELLA MARIS", 1001.0, (18.80, 35.30), 220.0, 12.0, 0.0, None, False),
            ]
        },
        {
            "id": 7,
            "name": "nearby_but_temporally_incompatible",
            "desc": "Vessel passes directly over the observed slick coordinates at observation time, but oil was released 8h prior upstream.",
            "target_culprit_mmsi": None,
            "target_culprit_name": "HISTORICAL_SPILL_UPSTREAM",
            "culprit_config": None,
            "background_vessels": [
                # Arrives at slick position (18.35, 34.50) at elapsed 15.5 hr (09:30 UTC), but release was at 01:15 UTC upstream
                (240777001, "IONIAN SEA", 1004.0, (17.65, 33.80), 45.0, 14.0, 0.0, None, False),
                (240777002, "ALEXANDRIA V", 1001.0, (18.90, 35.40), 210.0, 13.5, 0.0, None, False),
            ]
        },
    ]

    manifest = []

    for scn in scenarios:
        scn_id = scn["id"]
        scn_name = scn["name"]
        prefix = f"scenario_{scn_id:02d}_{scn_name}"

        dfs = []
        if scn["culprit_config"] is not None:
            c = scn["culprit_config"]
            df_culprit = _generate_vessel_track(
                mmsi=c["mmsi"],
                vessel_name=c["name"],
                vessel_type=c["type"],
                start_time_iso=base_time,
                start_coord=c["start_coord"],
                heading_deg=c["heading"],
                speed_knots=c["speed"],
                draft_drop=c["draft_drop"],
                gap_window=c["gap"],
                kinematic_glitch=c["glitch"],
                rng=np.random.default_rng(scn_id * 1000 + 1),
            )
            dfs.append(df_culprit)

        for b_idx, b in enumerate(scn["background_vessels"]):
            b_mmsi, b_name, b_type, b_start, b_head, b_spd, b_drop, b_gap, b_glitch = b
            df_b = _generate_vessel_track(
                mmsi=b_mmsi,
                vessel_name=b_name,
                vessel_type=b_type,
                start_time_iso=base_time,
                start_coord=b_start,
                heading_deg=b_head,
                speed_knots=b_spd,
                draft_drop=b_drop,
                gap_window=b_gap,
                kinematic_glitch=b_glitch,
                rng=np.random.default_rng(scn_id * 1000 + 10 + b_idx),
            )
            dfs.append(df_b)

        combined_df = pd.concat(dfs, ignore_index=True)
        combined_df = combined_df.sort_values("BaseDateTime").reset_index(drop=True)

        # 1. Save AIS input CSV
        csv_path = BENCHMARK_DIR / f"{prefix}_ais.csv"
        combined_df.to_csv(csv_path, index=False)

        # 2. Save public scenario metadata (NO ground truth leak)
        meta_path = BENCHMARK_DIR / f"{prefix}_meta.json"
        public_meta = {
            "scenario_id": scn_id,
            "scenario_name": scn_name,
            "description": scn["desc"],
            "vessel_count": int(combined_df["MMSI"].nunique()),
            "total_records": len(combined_df),
            "start_time": combined_df["BaseDateTime"].min(),
            "end_time": combined_df["BaseDateTime"].max(),
            "ais_file": csv_path.name,
            "spill_observation": {
                "observed_slick_centroid": [18.35, 34.50],
                "observation_time_iso": "2024-08-23T09:41:12Z",
                "estimated_lookback_hours": 8.5,
            }
        }
        with open(meta_path, "w") as f:
            json.dump(public_meta, f, indent=2)

        # 3. Save hidden ground truth separately
        truth_path = HIDDEN_TRUTH_DIR / f"{prefix}_truth.json"
        hidden_truth = {
            "scenario_id": scn_id,
            "scenario_name": scn_name,
            "has_culprit_in_ais": scn["target_culprit_mmsi"] is not None,
            "ground_truth_culprit_mmsi": scn["target_culprit_mmsi"],
            "ground_truth_culprit_name": scn["target_culprit_name"],
            "release_time_iso": release_time_target,
            "release_coord": list(origin_coord_target),
            "target_expected_outcome": "ATTRIBUTED_TO_CULPRIT" if scn["target_culprit_mmsi"] else "EXONERATED_ALL_OR_UNATTRIBUTED",
        }
        with open(truth_path, "w") as f:
            json.dump(hidden_truth, f, indent=2)

        manifest.append({
            "scenario_id": scn_id,
            "name": scn_name,
            "ais_file": csv_path.name,
            "meta_file": meta_path.name,
            "truth_file": truth_path.name,
        })

    manifest_path = BENCHMARK_DIR / "benchmark_manifest.json"
    with open(manifest_path, "w") as f:
        json.dump(manifest, f, indent=2)

    print(f"[✓] Successfully re-generated all 7 validation scenarios in {BENCHMARK_DIR}")


if __name__ == "__main__":
    build_all_scenarios()
