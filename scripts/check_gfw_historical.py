"""
Real Data Smoke Test for Global Fishing Watch (GFW) Historical AIS Integration.

Phase 7B Requirements 12 & 13:
1. Queries a small historical AOI and short historical window for generic verification.
2. Queries the actual 2024 Sentinel-1 scene:
   S1A_IW_GRDH_1SDV_20240823T164734_20240823T164759_055343_06BFAC_153E
   Acquisition: 2024-08-23T16:47:34Z
   Actual scene footprint & pipeline derived release window.
3. Reports authentication, response status, observation counts, track availability,
   and honest coverage status without fabrication.
4. Generates audited report at data/results/ais/gfw_historical_quality_report.json.
"""

import os
import sys
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.ingestion.ais.gfw_historical_provider import GFWHistoricalAISProvider
from src.ingestion.ais.models import ProviderStatus


def run_smoke_test() -> Dict[str, Any]:
    print("=" * 75)
    print("GLOBAL FISHING WATCH (GFW) HISTORICAL AIS SMOKE TEST")
    print("=" * 75)

    token = os.environ.get("GFW_API_TOKEN")
    auth_configured = bool(token)
    token_str = "CONFIGURED (Masked)" if auth_configured else "NOT CONFIGURED"
    print(f"[*] GFW_API_TOKEN in environment: {token_str}")

    provider = GFWHistoricalAISProvider(api_token=token)
    status = provider.get_status()
    print(f"[*] Initial Provider Status: {status.value}")

    # PART 1
    print("\n--- PART 1: GENERIC HISTORICAL AOI SMOKE TEST ---")
    test_bbox = (-5.8, 35.8, -5.2, 36.2)
    test_start = "2024-08-20T00:00:00Z"
    test_end = "2024-08-20T06:00:00Z"

    print(f"Query AOI: {test_bbox}")
    print(f"Query Interval: {test_start} to {test_end}")

    t1_obs = provider.get_positions(
        bbox=test_bbox,
        start_time_iso=test_start,
        end_time_iso=test_end,
    )
    t1_tracks = provider.get_tracks(
        bbox=test_bbox,
        start_time_iso=test_start,
        end_time_iso=test_end,
    )

    t1_status = provider.get_status()
    print(f"API Authentication Status: {t1_status.value}")
    print(f"Observations Returned: {len(t1_obs)}")
    print(f"Unique Vessels Identified: {len(t1_tracks)}")
    if t1_obs:
        earliest = min(o.timestamp for o in t1_obs)
        latest = max(o.timestamp for o in t1_obs)
        print(f"Earliest Timestamp: {earliest}")
        print(f"Latest Timestamp: {latest}")
        print(f"Track Availability: {'AVAILABLE' if t1_tracks else 'NOT AVAILABLE'}")
    else:
        print("Earliest Timestamp: None")
        print("Latest Timestamp: None")
        print("Track Availability: NOT AVAILABLE (0 observations returned)")

    # PART 2
    print("\n--- PART 2: REAL SENTINEL-1 SCENE TEST (2024-08-23) ---")
    scene_name = "S1A_IW_GRDH_1SDV_20240823T164734_20240823T164759_055343_06BFAC_153E.SAFE"
    s1_acquisition = "2024-08-23T16:47:34Z"
    s1_scene_bbox = (16.685553, 33.440971, 19.84104, 35.36055)
    derived_release_start = "2024-08-23T04:47:34Z"
    derived_release_end = "2024-08-23T16:47:34Z"
    hindcast_95_bbox = (16.685553, 33.448469, 18.830298, 35.36055)

    print(f"Scene ID: {scene_name}")
    print(f"Acquisition Time: {s1_acquisition}")
    print(f"Scene Footprint Bbox: {s1_scene_bbox}")
    print(f"Derived 95% Origin Bbox: {hindcast_95_bbox}")
    print(f"Derived Release Window: {derived_release_start} to {derived_release_end}")

    s1_obs = provider.get_positions(
        bbox=hindcast_95_bbox,
        start_time_iso=derived_release_start,
        end_time_iso=derived_release_end,
    )
    s1_tracks = provider.get_tracks(
        bbox=hindcast_95_bbox,
        start_time_iso=derived_release_start,
        end_time_iso=derived_release_end,
    )

    hist_available = len(s1_obs) > 0
    tracks_returned = len(s1_tracks) > 0
    coverage_label = "SUFFICIENT" if len(s1_obs) >= 5 else ("LIMITED" if len(s1_obs) > 0 else "INSUFFICIENT")

    print("\n--- REAL SENTINEL-1 SCENE RESULTS ---")
    print(f"Historical AIS Available? {"YES" if hist_available else "NO"}")
    print(f"Historical Vessel Tracks Returned? {"YES" if tracks_returned else "NO"}")
    print(f"Number of Relevant Vessels: {len(s1_tracks)}")
    print(f"Historical AIS Coverage Status: {coverage_label}")

    report = provider.generate_quality_report(
        observations=s1_obs,
        requested_start=derived_release_start,
        requested_end=derived_release_end,
        bbox=hindcast_95_bbox,
        output_path="data/results/ais/gfw_historical_quality_report.json",
    )

    print("\n[*] Quality report generated at: data/results/ais/gfw_historical_quality_report.json")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    run_smoke_test()
