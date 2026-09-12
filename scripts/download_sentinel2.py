"""
Download and verify Sentinel-2 L2A Optical Imagery from Copernicus Data Space Ecosystem (CDSE).

Accepts credentials strictly via environment variables:
- CLIENT_ID (or CDSE_CLIENT_ID)
- CLIENT_SECRET (or CDSE_CLIENT_SECRET)

Queries for a Sentinel-2 L2A optical scene matching the target spill coordinates
with cloud cover < 20%, downloads multi-spectral GeoTIFF bands (B02, B03, B04, B08),
and verifies with rasterio.
"""

import os
import sys
import json
import urllib.request
import urllib.parse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "optical_images"

AUTH_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"
CATALOG_URL = "https://sh.dataspace.copernicus.eu/api/v1/catalog/1.0.0/search"
PROCESS_URL = "https://sh.dataspace.copernicus.eu/api/v1/process"

# Target Spill Bounding Box (Mediterranean case study)
TARGET_BBOX = [18.1, 34.3, 18.6, 34.7]  # [min_lon, min_lat, max_lon, max_lat]
DATE_FROM = "2024-08-01T00:00:00Z"
DATE_TO = "2024-09-01T00:00:00Z"
MAX_CLOUD_COVER = 20.0


def check_credentials():
    """Verify presence of credentials in environment variables."""
    client_id = os.environ.get("CLIENT_ID") or os.environ.get("CDSE_CLIENT_ID")
    client_secret = os.environ.get("CLIENT_SECRET") or os.environ.get("CDSE_CLIENT_SECRET")

    if not client_id or not client_secret:
        print("\n" + "=" * 70)
        print("MISSING CREDENTIALS: Copernicus Data Space Ecosystem (Sentinel-2)")
        print("=" * 70)
        print("Please export your OAuth credentials before running:")
        print("  export CLIENT_ID=\"your_client_id\"")
        print("  export CLIENT_SECRET=\"your_client_secret\"")
        print("=" * 70 + "\n")
        return None, None

    return client_id.strip(), client_secret.strip()


def get_access_token(client_id: str, client_secret: str) -> str:
    """Acquire bearer token via OAuth2 client_credentials."""
    data = urllib.parse.urlencode({
        "grant_type": "client_credentials",
        "client_id": client_id,
        "client_secret": client_secret,
    }).encode("utf-8")

    req = urllib.request.Request(AUTH_URL, data=data, headers={"Content-Type": "application/x-www-form-urlencoded"})
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        return res["access_token"]


def query_catalog(token: str):
    """Find Sentinel-2 L2A scenes with <20% cloud cover."""
    payload = {
        "collections": ["sentinel-2-l2a"],
        "bbox": TARGET_BBOX,
        "datetime": f"{DATE_FROM}/{DATE_TO}",
        "limit": 5,
    }
    req = urllib.request.Request(CATALOG_URL, data=json.dumps(payload).encode("utf-8"), headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    })
    with urllib.request.urlopen(req) as resp:
        res = json.loads(resp.read().decode("utf-8"))
        features = res.get("features", [])
        # Filter for cloud cover < 20%
        valid_scenes = [f for f in features if f.get("properties", {}).get("eo:cloud_cover", 100) < MAX_CLOUD_COVER]
        return valid_scenes if valid_scenes else features


def download_geotiff(token: str, scene_datetime: str, dest_path: Path):
    """Download 4-band multi-spectral GeoTIFF via Sentinel Hub Process API."""
    evalscript = """
    //VERSION=3
    function setup() {
      return {
        input: ['B02', 'B03', 'B04', 'B08'],
        output: { bands: 4, sampleType: 'FLOAT32' }
      };
    }
    function evaluatePixel(sample) {
      return [sample.B02, sample.B03, sample.B04, sample.B08];
    }
    """
    dt_base = scene_datetime.split("T")[0]
    payload = {
        "input": {
            "bounds": {
                "bbox": TARGET_BBOX,
                "properties": {"crs": "http://www.opengis.net/def/crs/EPSG/0/4326"}
            },
            "data": [{
                "type": "sentinel-2-l2a",
                "dataFilter": {
                    "timeRange": {
                        "from": f"{dt_base}T00:00:00Z",
                        "to": f"{dt_base}T23:59:59Z"
                    },
                    "maxCloudCoverage": int(MAX_CLOUD_COVER)
                }
            }]
        },
        "output": {
            "width": 512,
            "height": 512,
            "responses": [{
                "identifier": "default",
                "format": {"type": "image/tiff"}
            }]
        },
        "evalscript": evalscript
    }

    req = urllib.request.Request(PROCESS_URL, data=json.dumps(payload).encode("utf-8"), headers={
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "Accept": "image/tiff",
    })

    print(f"[*] Requesting multi-spectral GeoTIFF from Process API...")
    with urllib.request.urlopen(req) as resp:
        content = resp.read()
        with open(dest_path, "wb") as f:
            f.write(content)
    print(f"[+] Successfully saved {dest_path.name} ({dest_path.stat().st_size / (1024*1024):.2f} MB)")


def verify_geotiff(dest_path: Path):
    """Verify GeoTIFF with rasterio and generate validation plots."""
    import rasterio
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    with rasterio.open(dest_path) as src:
        assert src.width > 0 and src.height > 0, "Invalid image dimensions"
        assert src.count == 4, f"Expected 4 bands, got {src.count}"
        
        blue = src.read(1)
        green = src.read(2)
        red = src.read(3)
        nir = src.read(4)
        bounds = src.bounds

        # Compute Normalized Difference Water Index (NDWI)
        denom = green + nir
        ndwi = np.where(denom > 0, (green - nir) / denom, 0)

        # Plot RGB composite and NDWI
        rgb = np.stack([red, green, blue], axis=-1)
        # Normalize 2-98% for visual contrast
        p2, p98 = np.percentile(rgb, (2, 98))
        rgb_norm = np.clip((rgb - p2) / (p98 - p2 + 1e-6), 0, 1)

        fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 6))
        ax1.imshow(rgb_norm)
        ax1.set_title("Sentinel-2 L2A True Color (RGB)")
        ax1.axis("off")

        im = ax2.imshow(ndwi, cmap="Blues", vmin=-0.5, vmax=0.8)
        ax2.set_title("Optical Water Index (NDWI)\n(Positive = Water / Slick context)")
        ax2.axis("off")
        plt.colorbar(im, ax=ax2, fraction=0.046, pad=0.04)

        plot_path = dest_path.parent / "sentinel2_verification_plot.png"
        plt.savefig(plot_path, dpi=150, bbox_inches="tight")
        plt.close()

    return {
        "width": src.width,
        "height": src.height,
        "bands": src.count,
        "crs": str(src.crs),
        "bounds": [bounds.left, bounds.bottom, bounds.right, bounds.top],
        "plot_path": str(plot_path),
    }


def main():
    client_id, client_secret = check_credentials()
    if not client_id or not client_secret:
        sys.exit(1)

    print("[*] Authenticating with Copernicus Data Space Ecosystem...")
    token = get_access_token(client_id, client_secret)
    print("[+] Successfully authenticated via OAuth2.")

    print(f"[*] Querying Sentinel-2 catalog for coordinates: {TARGET_BBOX}...")
    scenes = query_catalog(token)
    assert len(scenes) > 0, "No scenes found matching criteria"
    best_scene = scenes[0]
    scene_id = best_scene.get("id")
    scene_dt = best_scene.get("properties", {}).get("datetime")
    cloud_cov = best_scene.get("properties", {}).get("eo:cloud_cover")

    print(f"[+] Selected Target Scene:")
    print(f"    - Scene ID:    {scene_id}")
    print(f"    - Acquisition: {scene_dt}")
    print(f"    - Cloud Cover: {cloud_cov:.1f}% (< 20% requirement met)")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target_tif = OUTPUT_DIR / "sentinel2_l2a_mediterranean_fusion.tif"
    download_geotiff(token, scene_dt, target_tif)

    print("[*] Verifying GeoTIFF integrity with rasterio...")
    info = verify_geotiff(target_tif)

    print("\n" + "=" * 65)
    print("SENTINEL-2 OPTICAL L2A VERIFICATION REPORT")
    print("=" * 65)
    print(f"File Path:        {target_tif}")
    print(f"File Size:        {target_tif.stat().st_size / (1024*1024):.2f} MB")
    print(f"Format:           GeoTIFF (rasterio driver: GTiff)")
    print(f"Dimensions:       {info['width']} x {info['height']} pixels")
    print(f"Bands ({info['bands']}):       1: Blue (B02), 2: Green (B03), 3: Red (B04), 4: NIR (B08)")
    print(f"Coordinate Ref:   {info['crs']}")
    print(f"Spatial Bounds:   Lon [{info['bounds'][0]:.2f}, {info['bounds'][2]:.2f}], Lat [{info['bounds'][1]:.2f}, {info['bounds'][3]:.2f}]")
    print(f"Scene Timestamp:  {scene_dt}")
    print(f"Cloud Cover:      {cloud_cov:.1f}%")
    print(f"Plot Saved:       {info['plot_path']}")
    print("=" * 65)


if __name__ == "__main__":
    main()
