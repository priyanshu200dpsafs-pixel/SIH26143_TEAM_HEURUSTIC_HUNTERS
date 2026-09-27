#!/usr/bin/env python3
"""
Sentinel-1 Live Connectivity & Catalog Verification Smoke Test.

Queries the live Copernicus Data Space Ecosystem (CDSE) OData catalog over a configured
spatial bounding box and time window.
Reports product counts and normalized metadata without logging secrets.
"""

import argparse
from datetime import datetime, timedelta, timezone
import json
import os
import sys
from pathlib import Path

# Ensure project root in sys.path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from src.ingestion.sentinel1_provider import (
    CopernicusSentinel1Provider,
    ProviderStatus,
)


def main():
    parser = argparse.ArgumentParser(description="Sentinel-1 Live Catalog Connectivity Smoke Test")
    parser.add_argument("--bbox", nargs=4, type=float, default=[18.1, 34.3, 18.6, 34.7],
                        help="Bounding box min_lon min_lat max_lon max_lat (default: Central Mediterranean)")
    parser.add_argument("--days", type=int, default=14, help="Time window lookback in days (default: 14)")
    parser.add_argument("--max-results", type=int, default=5, help="Maximum products to print (default: 5)")
    args = parser.parse_args()

    min_lon, min_lat, max_lon, max_lat = args.bbox
    now = datetime.now(timezone.utc)
    start_time = (now - timedelta(days=args.days)).strftime("%Y-%m-%dT00:00:00.000Z")
    end_time = now.strftime("%Y-%m-%dT23:59:59.999Z")

    print("=" * 65)
    print("SENTINEL-1 LIVE CONNECTIVITY CHECK")
    print("=" * 65)
    print("Provider:       Copernicus Data Space Ecosystem (CDSE)")

    provider = CopernicusSentinel1Provider()

    # Check authentication
    if provider.has_credentials():
        auth_status, token = provider.get_auth_token()
        if auth_status == ProviderStatus.SUCCESS:
            print("Authentication: SUCCESS (OAuth2 Token Acquired)")
        else:
            print(f"Authentication: {auth_status.value} (Check COPERNICUS_CLIENT_ID / SECRET)")
    else:
        print("Authentication: ANONYMOUS / PUBLIC ODATA (Search Active, Download requires credentials)")

    print(f"AOI Bounding Box: [{min_lon:.2f}°E, {min_lat:.2f}°N, {max_lon:.2f}°E, {max_lat:.2f}°N]")
    print(f"Time Window:      {start_time[:10]} to {end_time[:10]} ({args.days} days)")
    print("-" * 65)

    print("[*] Querying live Copernicus OData catalog...")
    status, products, err_msg = provider.search_products(
        bbox=(min_lon, min_lat, max_lon, max_lat),
        start_time_iso=start_time,
        end_time_iso=end_time,
        product_type="GRD",
        max_results=args.max_results,
    )

    if status == ProviderStatus.SUCCESS:
        print(f"[✓] Query Success: {len(products)} Sentinel-1 products found.")
        print("-" * 65)
        for i, prod in enumerate(products, 1):
            print(f"Product {i}:")
            print(f"  ID:           {prod.product_id}")
            print(f"  Name:         {prod.product_name}")
            print(f"  Sensor:       {prod.sensor}")
            print(f"  Type:         {prod.product_type}")
            print(f"  Acquisition:  {prod.acquisition_start} -> {prod.acquisition_end}")
            print(f"  Orbit:        {prod.orbit} (Relative: {prod.relative_orbit})")
            print(f"  Polarization: {prod.polarization}")
            if prod.content_length:
                size_mb = prod.content_length / (1024 * 1024)
                print(f"  Archive Size: {size_mb:.1f} MB")
            print()
    elif status == ProviderStatus.NO_RESULTS:
        print(f"[i] Query Success: No Sentinel-1 products found in AOI over the last {args.days} days.")
    else:
        print(f"[✗] Query Failed: {status.value}")
        if err_msg:
            print(f"    Details: {err_msg}")

    print("=" * 65)
    print("Smoke test complete.")


if __name__ == "__main__":
    main()
