"""
Download and verify OSCAR Surface Ocean Current vectors from NASA PO.DAAC / Earthdata.

Accepts NASA Earthdata credentials via environment variables:
- EARTHDATA_TOKEN (or EARTHDATA_USERNAME & EARTHDATA_PASSWORD)

Queries NASA CMR for OSCAR 0.25-degree final surface current vectors,
downloads the NetCDF granule for the case study date, and validates integrity with xarray.
"""

import os
import sys
import json
import urllib.request
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "ocean_currents"

CMR_GRANULES_URL = "https://cmr.earthdata.nasa.gov/search/granules.json"
COLLECTION_SHORT_NAME = "OSCAR_L4_OC_FINAL_V2.0"
TARGET_DATE = "2024-08-23"


def get_auth_token():
    """Retrieve Earthdata token from environment or ~/.netrc."""
    token = os.environ.get("EARTHDATA_TOKEN")
    if token:
        return token.strip()
    
    # Check ~/.netrc
    netrc_path = Path.home() / ".netrc"
    if netrc_path.exists():
        import netrc
        try:
            n = netrc.netrc(str(netrc_path))
            auth = n.authenticators("urs.earthdata.nasa.gov")
            if auth:
                # In Earthdata, password can be the bearer token
                return auth[2]
        except Exception:
            pass

    print("\n" + "=" * 70)
    print("MISSING CREDENTIALS: NASA Earthdata (OSCAR Ocean Currents)")
    print("=" * 70)
    print("Please export your Earthdata Bearer Token before running:")
    print("  export EARTHDATA_TOKEN=\"your_token_here\"")
    print("=" * 70 + "\n")
    return None


def query_granule(token: str, date_str: str):
    """Find OSCAR NetCDF download link for target date via CMR."""
    url = f"{CMR_GRANULES_URL}?short_name={COLLECTION_SHORT_NAME}&temporal={date_str}T00:00:00Z,{date_str}T23:59:59Z"
    print(f"[*] Querying NASA CMR for OSCAR granule ({date_str})...")
    req = urllib.request.Request(url, headers={"Authorization": f"Bearer {token}"})
    
    with urllib.request.urlopen(req) as resp:
        data = json.loads(resp.read().decode("utf-8"))
        entries = data.get("feed", {}).get("entry", [])
        assert len(entries) > 0, f"No OSCAR granules found for date {date_str}"
        
        granule = entries[0]
        title = granule.get("title")
        for link in granule.get("links", []):
            if link.get("rel") == "http://esipfed.org/ns/fedsearch/1.1/data#":
                return title, link.get("href")
        
        raise RuntimeError("No direct data download link found in granule metadata")


def download_oscar_nc(token: str, download_url: str, dest_path: Path):
    """Download NetCDF file handling Cumulus / S3 pre-signed redirects."""
    import requests
    print(f"[*] Requesting OSCAR data from PO.DAAC: {download_url}")
    session = requests.Session()
    
    # Request without following redirects initially
    resp = session.get(download_url, headers={"Authorization": f"Bearer {token}"}, allow_redirects=False)
    
    if resp.status_code in [301, 302, 303, 307]:
        redirect_url = resp.headers.get("Location")
        print(f"[*] Following pre-signed S3 redirect...")
        # Strip authorization header on S3 redirect
        r_data = session.get(redirect_url, stream=True)
        r_data.raise_for_status()
        
        total_size = int(r_data.headers.get("Content-Length", 0))
        downloaded = 0
        with open(dest_path, "wb") as f:
            for chunk in r_data.iter_content(chunk_size=1024 * 128):
                f.write(chunk)
                downloaded += len(chunk)
                if total_size > 0:
                    pct = (downloaded / total_size) * 100
                    sys.stdout.write(f"\r    Downloaded: {downloaded / (1024*1024):.2f} MB / {total_size / (1024*1024):.2f} MB ({pct:.1f}%)")
                    sys.stdout.flush()
        print(f"\n[+] Successfully saved {dest_path.name} ({dest_path.stat().st_size / (1024*1024):.2f} MB)")
    else:
        raise RuntimeError(f"Unexpected response from PO.DAAC: HTTP {resp.status_code}")


def verify_oscar(nc_path: Path):
    """Validate NetCDF integrity with xarray and plot regional current vectors."""
    import xarray as xr
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    print("[*] Validating OSCAR NetCDF with xarray...")
    ds = xr.open_dataset(nc_path)
    
    assert "u" in ds.data_vars and "v" in ds.data_vars, "Missing u/v ocean current components"
    
    u = ds["u"].squeeze()
    v = ds["v"].squeeze()
    lats = ds["lat"].values
    lons = ds["lon"].values

    # Subset to Mediterranean / case study region (Lat 30-40N, Lon 10-30E)
    lat_mask = (lats >= 30.0) & (lats <= 40.0)
    lon_mask = (lons >= 10.0) & (lons <= 30.0)
    
    sub_lats = lats[lat_mask]
    sub_lons = lons[lon_mask]
    
    # Slice u and v
    sub_u = u.values[np.ix_(lat_mask, lon_mask)] if u.shape == (len(lats), len(lons)) else u.values.T[np.ix_(lat_mask, lon_mask)]
    sub_v = v.values[np.ix_(lat_mask, lon_mask)] if v.shape == (len(lats), len(lons)) else v.values.T[np.ix_(lat_mask, lon_mask)]
    
    sub_speed = np.sqrt(sub_u**2 + sub_v**2)

    # Plot
    fig, ax = plt.subplots(figsize=(11, 6))
    lon_grid, lat_grid = np.meshgrid(sub_lons, sub_lats)
    
    im = ax.contourf(lon_grid, lat_grid, sub_speed, cmap="PuBuGn", levels=15)
    plt.colorbar(im, ax=ax, label="Current Speed (m/s)")
    ax.quiver(lon_grid[::2, ::2], lat_grid[::2, ::2], sub_u[::2, ::2], sub_v[::2, ::2], color="#0f172a", scale=8)
    ax.set_title(f"OSCAR Ocean Surface Current Vectors - {TARGET_DATE} (m/s)", fontsize=13)
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")
    ax.grid(True, linestyle="--", alpha=0.4)

    plot_path = nc_path.parent / "oscar_currents_verification_plot.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()

    return {
        "dimensions": dict(ds.sizes),
        "variables": list(ds.data_vars.keys()),
        "time": str(ds["time"].values[0]),
        "global_lat_range": [float(lats.min()), float(lats.max())],
        "global_lon_range": [float(lons.min()), float(lons.max())],
        "regional_speed_mean": float(np.nanmean(sub_speed)),
        "regional_speed_max": float(np.nanmax(sub_speed)),
        "plot_path": str(plot_path),
    }


def main():
    token = get_auth_token()
    if not token:
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target_nc = OUTPUT_DIR / f"oscar_currents_final_{TARGET_DATE.replace('-', '')}.nc"

    if not target_nc.exists() or target_nc.stat().st_size == 0:
        title, download_url = query_granule(token, TARGET_DATE)
        print(f"[+] Found Granule: {title}")
        download_oscar_nc(token, download_url, target_nc)
    else:
        print(f"[+] Existing file found: {target_nc.name} ({target_nc.stat().st_size / (1024*1024):.2f} MB)")

    info = verify_oscar(target_nc)

    print("\n" + "=" * 65)
    print("NASA OSCAR OCEAN CURRENTS VERIFICATION REPORT")
    print("=" * 65)
    print(f"File Path:            {target_nc}")
    print(f"File Size:            {target_nc.stat().st_size / (1024*1024):.2f} MB")
    print(f"Data Format:          NetCDF4 (xarray)")
    print(f"Dimensions:           {info['dimensions']}")
    print(f"Key Variables:        {info['variables']}")
    print(f"Observation Date:     {info['time'][:10]}")
    print(f"Global Coverage:      Lat [{info['global_lat_range'][0]:.1f}, {info['global_lat_range'][1]:.1f}], Lon [{info['global_lon_range'][0]:.1f}, {info['global_lon_range'][1]:.1f}]")
    print(f"Regional Mean Speed:  {info['regional_speed_mean']:.3f} m/s ({info['regional_speed_mean']*1.94384:.2f} knots)")
    print(f"Regional Max Speed:   {info['regional_speed_max']:.3f} m/s ({info['regional_speed_max']*1.94384:.2f} knots)")
    print(f"Verification Plot:    {info['plot_path']}")
    print("=" * 65)


if __name__ == "__main__":
    main()
