"""
Download and verify ERA5 10m u/v surface wind components from Copernicus Climate Data Store (CDS).

Requires CDS account credentials configured in ~/.cdsapirc.
Downloads hourly u10 and v10 wind vectors as NetCDF for the case study region/dates,
and validates integrity using xarray.
"""

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "data" / "weather"
CDSAPIRC_PATH = Path.home() / ".cdsapirc"

# Target spatial bounding box [North, West, South, East] and date
AREA_BOUNDS = [36.0, 17.0, 33.0, 20.0]
YEAR = "2024"
MONTH = "08"
DAYS = ["22", "23", "24"]
TIMES = [f"{h:02d}:00" for h in range(24)]


def check_cds_config():
    """Verify presence of ~/.cdsapirc."""
    if not CDSAPIRC_PATH.exists() or CDSAPIRC_PATH.stat().st_size == 0:
        print("\n" + "=" * 70)
        print("MISSING CONFIGURATION: Copernicus Climate Data Store (ERA5)")
        print("=" * 70)
        print("ERA5 wind data requires an active CDS account and API key in ~/.cdsapirc.")
        print("1. Register a free account at: https://cds.climate.copernicus.eu")
        print("2. Copy your Personal Access Token from your user profile.")
        print("3. Add it to ~/.cdsapirc with:")
        print("     url: https://cds.climate.copernicus.eu/api")
        print("     key: <YOUR_PERSONAL_ACCESS_TOKEN>")
        print("=" * 70 + "\n")
        return False
    return True


def download_era5(dest_nc_path: Path):
    """Retrieve ERA5 single levels 10m u/v wind components."""
    import cdsapi
    c = cdsapi.Client()

    request = {
        "product_type": ["reanalysis"],
        "variable": [
            "10m_u_component_of_wind",
            "10m_v_component_of_wind",
        ],
        "year": [YEAR],
        "month": [MONTH],
        "day": DAYS,
        "time": TIMES,
        "data_format": "netcdf",
        "download_format": "unarchived",
        "area": AREA_BOUNDS,
    }

    print(f"[*] Submitting ERA5 wind request to Copernicus Climate Data Store...")
    print(f"    - Variable: 10m u/v wind components (u10, v10)")
    print(f"    - Date Range: {YEAR}-{MONTH}-{DAYS[0]} to {YEAR}-{MONTH}-{DAYS[-1]} (hourly)")
    print(f"    - Bounding Box: [North: {AREA_BOUNDS[0]}, West: {AREA_BOUNDS[1]}, South: {AREA_BOUNDS[2]}, East: {AREA_BOUNDS[3]}]")
    
    try:
        c.retrieve("reanalysis-era5-single-levels", request, str(dest_nc_path))
        print(f"[+] Download complete: {dest_nc_path.name} ({dest_nc_path.stat().st_size / (1024*1024):.2f} MB)")
    except Exception as e:
        err_str = str(e)
        if "licence" in err_str.lower():
            print("\n" + "!" * 70)
            print("LICENCE ACCEPTANCE REQUIRED")
            print("!" * 70)
            print("You must accept the ERA5 licence terms once on the CDS portal:")
            print("👉 https://cds.climate.copernicus.eu/datasets/reanalysis-era5-single-levels?tab=download#manage-licences")
            print("Scroll to the bottom of that page, check the terms box, click 'Accept', then rerun this script.")
            print("!" * 70 + "\n")
            sys.exit(2)
        else:
            raise e


def verify_netcdf(nc_path: Path):
    """Verify NetCDF integrity with xarray and generate wind vector plot."""
    import xarray as xr
    import numpy as np
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    print(f"[*] Verifying NetCDF dataset integrity with xarray...")
    ds = xr.open_dataset(nc_path)
    
    assert "u10" in ds.variables or "10m_u_component_of_wind" in ds.variables, "Missing u-component variable"
    assert "v10" in ds.variables or "10m_v_component_of_wind" in ds.variables, "Missing v-component variable"

    u_var = "u10" if "u10" in ds.variables else "10m_u_component_of_wind"
    v_var = "v10" if "v10" in ds.variables else "10m_v_component_of_wind"

    u = ds[u_var].values
    v = ds[v_var].values
    times = ds["valid_time"].values if "valid_time" in ds.coords else ds["time"].values
    lats = ds["latitude"].values
    lons = ds["longitude"].values

    wind_speed = np.sqrt(u**2 + v**2)
    mean_speed = float(np.nanmean(wind_speed))
    max_speed = float(np.nanmax(wind_speed))

    # Generate wind vector plot for first timestamp
    fig, ax = plt.subplots(figsize=(10, 7))
    lon_grid, lat_grid = np.meshgrid(lons, lats)
    u_slice = u[0, :, :]
    v_slice = v[0, :, :]
    spd_slice = wind_speed[0, :, :]

    im = ax.contourf(lon_grid, lat_grid, spd_slice, cmap="YlGnBu", levels=15)
    plt.colorbar(im, ax=ax, label="Wind Speed (m/s)")
    ax.quiver(lon_grid, lat_grid, u_slice, v_slice, color="#1e293b", scale=120)
    ax.set_title(f"ERA5 10m Wind Vectors (m/s) - {str(times[0])[:19]}", fontsize=13)
    ax.set_xlabel("Longitude (°E)")
    ax.set_ylabel("Latitude (°N)")
    ax.grid(True, linestyle="--", alpha=0.4)

    plot_path = nc_path.parent / "era5_wind_verification_plot.png"
    plt.savefig(plot_path, dpi=150, bbox_inches="tight")
    plt.close()

    return {
        "dimensions": dict(ds.sizes),
        "variables": list(ds.data_vars.keys()),
        "time_count": len(times),
        "time_range": [str(times[0]), str(times[-1])],
        "lat_range": [float(lats.min()), float(lats.max())],
        "lon_range": [float(lons.min()), float(lons.max())],
        "mean_speed_mps": mean_speed,
        "max_speed_mps": max_speed,
        "plot_path": str(plot_path),
    }


def main():
    if not check_cds_config():
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    target_nc = OUTPUT_DIR / "era5_wind_mediterranean_case_study.nc"

    if not target_nc.exists() or target_nc.stat().st_size == 0:
        download_era5(target_nc)
    else:
        print(f"[+] Existing file found: {target_nc.name} ({target_nc.stat().st_size / (1024*1024):.2f} MB)")

    info = verify_netcdf(target_nc)

    print("\n" + "=" * 65)
    print("ERA5 HOURLY WIND (10M) VERIFICATION REPORT")
    print("=" * 65)
    print(f"File Path:       {target_nc}")
    print(f"File Size:       {target_nc.stat().st_size / (1024*1024):.2f} MB")
    print(f"Data Format:     NetCDF4 (xarray)")
    print(f"Dimensions:      {info['dimensions']}")
    print(f"Variables:       {info['variables']}")
    print(f"Hourly Steps:    {info['time_count']} timesteps")
    print(f"Date Range:      {info['time_range'][0][:16]} to {info['time_range'][1][:16]}")
    print(f"Spatial Bounds:  Lat [{info['lat_range'][0]:.2f}, {info['lat_range'][1]:.2f}], Lon [{info['lon_range'][0]:.2f}, {info['lon_range'][1]:.2f}]")
    print(f"Mean Wind Speed: {info['mean_speed_mps']:.2f} m/s ({info['mean_speed_mps']*1.94384:.1f} knots)")
    print(f"Max Wind Speed:  {info['max_speed_mps']:.2f} m/s ({info['max_speed_mps']*1.94384:.1f} knots)")
    print(f"Plot Saved:      {info['plot_path']}")
    print("=" * 65)


if __name__ == "__main__":
    main()
