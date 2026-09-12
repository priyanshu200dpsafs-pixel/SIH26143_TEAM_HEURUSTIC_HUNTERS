"""
Download and verify MarineCadastre AIS reference dataset.

Downloads a monthly zone AIS CSV zip from NOAA MarineCadastre
(https://coast.noaa.gov/htdata/CMSP/AISDataHandler/), saves to
data/ais/real_reference/, and inspects schema, bounds, and date ranges.
"""

import sys
import zipfile
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "ais" / "real_reference"

# NOAA MarineCadastre monthly zone archive
# Using Zone 01 (176 KB) as pristine reference schema sample
NOAA_AIS_URL = "https://coast.noaa.gov/htdata/CMSP/AISDataHandler/2017/AIS_2017_01_Zone01.zip"
ZIP_NAME = "AIS_2017_01_Zone01.zip"


def download_ais():
    """Download NOAA MarineCadastre AIS monthly zone file."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    dest_zip = OUTPUT_DIR / ZIP_NAME

    if not dest_zip.exists() or dest_zip.stat().st_size == 0:
        print(f"[*] Downloading MarineCadastre AIS: {NOAA_AIS_URL} -> {dest_zip.name}")
        cmd = ["curl", "-L", "--progress-bar", "-o", str(dest_zip), NOAA_AIS_URL]
        subprocess.run(cmd, check=True)
    else:
        print(f"[+] Zip already exists: {dest_zip.name}")

    size_mb = dest_zip.stat().st_size / (1024 * 1024)
    assert dest_zip.stat().st_size > 0, "Downloaded zip file is empty!"
    print(f"[+] Verified zip file size: {size_mb:.2f} MB")

    # Unpack CSV
    print(f"[*] Extracting {dest_zip.name} into {OUTPUT_DIR}...")
    with zipfile.ZipFile(dest_zip, "r") as zf:
        zf.extractall(OUTPUT_DIR)

    csv_files = list(OUTPUT_DIR.rglob("*.csv"))
    assert len(csv_files) > 0, "No CSV found after extraction!"
    target_csv = csv_files[0]
    print(f"[+] Extracted CSV: {target_csv.name} ({target_csv.stat().st_size / (1024 * 1024):.2f} MB)")

    # Read and inspect with pandas
    import pandas as pd
    print(f"[*] Loading and verifying with Pandas: {target_csv.name}...")
    df = pd.read_csv(target_csv)
    
    assert len(df) > 0, "Extracted CSV is empty!"
    
    # Analyze schema and fields
    cols = list(df.columns)
    lat_col = [c for c in cols if "lat" in c.lower()][0]
    lon_col = [c for c in cols if "lon" in c.lower()][0]
    time_col = [c for c in cols if "time" in c.lower() or "date" in c.lower()][0]

    min_lat, max_lat = df[lat_col].min(), df[lat_col].max()
    min_lon, max_lon = df[lon_col].min(), df[lon_col].max()
    min_time = df[time_col].min()
    max_time = df[time_col].max()
    unique_vessels = df["MMSI"].nunique() if "MMSI" in df.columns else len(df)

    print("\n" + "=" * 65)
    print("MARINECADASTRE AIS REFERENCE DATASET VERIFICATION REPORT")
    print("=" * 65)
    print(f"Target Directory:      {OUTPUT_DIR}")
    print(f"Extracted File:        {target_csv.name}")
    print(f"Total Rows:            {len(df):,}")
    print(f"Unique Vessels (MMSI): {unique_vessels:,}")
    print(f"Date Range:            {min_time} to {max_time}")
    print(f"Coordinate Bounds:     Lat [{min_lat:.4f}, {max_lat:.4f}], Lon [{min_lon:.4f}, {max_lon:.4f}]")
    print(f"Schema Columns ({len(cols)}):")
    for i, c in enumerate(cols, 1):
        print(f"  {i:2d}. {c} ({df[c].dtype})")
    print("=" * 65)


if __name__ == "__main__":
    download_ais()
