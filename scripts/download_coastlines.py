"""
Download and verify Natural Earth 10m Coastlines and Land Shapefiles.

Downloads:
- ne_10m_coastline.zip
- ne_10m_land.zip
from Natural Earth CDN, unzips to data/coastlines/, verifies with GeoPandas,
and generates a verification plot and statistics report.
"""

import os
import sys
import zipfile
import urllib.request
from pathlib import Path

# Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "coastlines"

FILES_TO_DOWNLOAD = [
    {
        "name": "ne_10m_coastline",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_coastline.zip",
        "zip_file": "ne_10m_coastline.zip",
        "shp_file": "ne_10m_coastline.shp",
    },
    {
        "name": "ne_10m_land",
        "url": "https://naciscdn.org/naturalearth/10m/physical/ne_10m_land.zip",
        "zip_file": "ne_10m_land.zip",
        "shp_file": "ne_10m_land.shp",
    },
]


def download_file(url: str, dest_path: Path) -> None:
    """Stream download file with progress reporting."""
    print(f"[*] Downloading {url} -> {dest_path.name}...")
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    
    with urllib.request.urlopen(req) as resp, open(dest_path, "wb") as out_file:
        total_size = int(resp.headers.get("Content-Length", 0))
        downloaded = 0
        chunk_size = 1024 * 64
        
        while True:
            chunk = resp.read(chunk_size)
            if not chunk:
                break
            out_file.write(chunk)
            downloaded += len(chunk)
            if total_size > 0:
                percent = (downloaded / total_size) * 100
                sys.stdout.write(f"\r    Progress: {downloaded / (1024*1024):.2f} MB / {total_size / (1024*1024):.2f} MB ({percent:.1f}%)")
                sys.stdout.flush()
    print("\n[+] Download completed successfully.")


def verify_and_extract() -> None:
    """Download, extract, and inspect with GeoPandas."""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    
    import geopandas as gpd
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    report = {}

    for item in FILES_TO_DOWNLOAD:
        zip_path = OUTPUT_DIR / item["zip_file"]
        shp_path = OUTPUT_DIR / item["shp_file"]

        # Download if zip does not exist
        if not zip_path.exists() or zip_path.stat().st_size == 0:
            download_file(item["url"], zip_path)

        # Check zip size
        size_bytes = zip_path.stat().st_size
        assert size_bytes > 0, f"Error: {zip_path.name} is empty (0 bytes)!"
        print(f"[+] Verified zip file {zip_path.name}: {size_bytes / (1024*1024):.2f} MB")

        # Unzip
        print(f"[*] Unpacking {zip_path.name} into {OUTPUT_DIR}...")
        with zipfile.ZipFile(zip_path, "r") as zf:
            zf.extractall(OUTPUT_DIR)

        # Check shapefile exists
        assert shp_path.exists(), f"Error: expected shapefile {shp_path} not found after extract!"

        # Open and verify with GeoPandas
        print(f"[*] Reading and validating {shp_path.name} with GeoPandas...")
        gdf = gpd.read_file(shp_path)
        
        assert len(gdf) > 0, f"Error: GeoDataFrame {shp_path.name} has 0 records!"
        bounds = gdf.total_bounds  # [minx, miny, maxx, maxy]

        report[item["name"]] = {
            "records": len(gdf),
            "crs": str(gdf.crs),
            "bounds": {
                "min_lon": float(bounds[0]),
                "min_lat": float(bounds[1]),
                "max_lon": float(bounds[2]),
                "max_lat": float(bounds[3]),
            },
        }

    # Generate quick verification plot of Mediterranean / Global coastlines
    print("[*] Generating verification plot...")
    land_gdf = gpd.read_file(OUTPUT_DIR / "ne_10m_land.shp")
    coast_gdf = gpd.read_file(OUTPUT_DIR / "ne_10m_coastline.shp")

    fig, ax = plt.subplots(figsize=(12, 6))
    land_gdf.plot(ax=ax, color="#e0e0d8", edgecolor="#b0b0a8", linewidth=0.5)
    coast_gdf.plot(ax=ax, color="#1e5f8a", linewidth=0.8)
    ax.set_title("Natural Earth 10m Coastlines & Land Verification Plot", fontsize=14)
    ax.set_xlim(-20, 45)  # Focus on Mediterranean / Atlantic maritime area
    ax.set_ylim(25, 60)
    ax.grid(True, linestyle="--", alpha=0.5)

    plot_path = OUTPUT_DIR / "coastlines_verification_plot.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()
    print(f"[+] Verification plot saved to {plot_path}")

    # File inventory in directory
    all_files = list(OUTPUT_DIR.glob("*.*"))
    total_size_mb = sum(f.stat().st_size for f in all_files) / (1024 * 1024)

    print("\n" + "=" * 60)
    print("NATURAL EARTH COASTLINES VERIFICATION REPORT")
    print("=" * 60)
    print(f"Target Directory: {OUTPUT_DIR}")
    print(f"Total File Count: {len(all_files)}")
    print(f"Total Size:       {total_size_mb:.2f} MB")
    for name, info in report.items():
        print(f"\nLayer: {name}")
        print(f"  - Record Count: {info['records']}")
        print(f"  - CRS:          {info['crs']}")
        print(f"  - Bounding Box: Lon [{info['bounds']['min_lon']:.2f}, {info['bounds']['max_lon']:.2f}], Lat [{info['bounds']['min_lat']:.2f}, {info['bounds']['max_lat']:.2f}]")
    print("=" * 60)


if __name__ == "__main__":
    verify_and_extract()
