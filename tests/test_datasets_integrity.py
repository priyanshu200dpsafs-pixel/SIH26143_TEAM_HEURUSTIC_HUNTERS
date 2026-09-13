"""
Automated integrity test suite for all 7 downloaded real & synthetic datasets.
Ensures zero mock/fabricated data and validates dimensions, CRS, schemas, and values.
"""

from pathlib import Path
import pytest
import pandas as pd
import numpy as np
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DATA_DIR = PROJECT_ROOT / "data"


def test_coastlines_dataset():
    """Verify Natural Earth Coastlines and Land shapefiles."""
    import geopandas as gpd

    coast_shp = DATA_DIR / "coastlines" / "ne_10m_coastline.shp"
    land_shp = DATA_DIR / "coastlines" / "ne_10m_land.shp"

    assert coast_shp.exists(), "Coastline shapefile missing"
    assert land_shp.exists(), "Land shapefile missing"

    gdf_coast = gpd.read_file(coast_shp)
    gdf_land = gpd.read_file(land_shp)

    assert len(gdf_coast) > 1000, f"Expected >1000 coastline features, got {len(gdf_coast)}"
    assert len(gdf_land) > 5, f"Expected >5 land features, got {len(gdf_land)}"
    assert gdf_coast.crs.to_string() == "EPSG:4326"
    assert gdf_land.crs.to_string() == "EPSG:4326"


def test_marinecadastre_ais_dataset():
    """Verify MarineCadastre AIS CSV dataset schema and row count."""
    ais_file = DATA_DIR / "ais" / "real_reference" / "AIS_2017_01_Zone01.csv"
    assert ais_file.exists(), "MarineCadastre AIS file missing"
    assert ais_file.stat().st_size > 500_000, "MarineCadastre AIS file too small"

    df = pd.read_csv(ais_file, nrows=100)
    expected_cols = {"MMSI", "BaseDateTime", "LAT", "LON", "SOG", "COG", "Heading", "VesselName", "VesselType"}
    assert expected_cols.issubset(set(df.columns)), f"Missing columns in AIS data: {expected_cols - set(df.columns)}"


def test_synthetic_ais_scenario():
    """Verify synthetic scenario has 9 vessels including 1 suspect tanker with AIS blackout."""
    scenario_file = DATA_DIR / "ais" / "synthetic" / "synthetic_ais_spill_scenario.csv"
    assert scenario_file.exists(), "Synthetic AIS scenario missing"

    df = pd.read_csv(scenario_file)
    assert len(df) > 2000, f"Expected >2000 rows, got {len(df)}"

    vessels = df["VesselName"].unique()
    assert len(vessels) == 9, f"Expected 9 vessels, got {len(vessels)}"
    assert "ATLANTIC CARRIER" in vessels, "Suspect tanker missing"

    # Verify suspect tanker draft reduction
    suspect_df = df[df["VesselName"] == "ATLANTIC CARRIER"].sort_values("BaseDateTime")
    first_draft = suspect_df["Draft"].iloc[0]
    last_draft = suspect_df["Draft"].iloc[-1]
    assert first_draft > last_draft, f"Expected draft drop, got {first_draft} -> {last_draft}"


def test_sentinel2_optical():
    """Verify Sentinel-2 L2A optical GeoTIFF has 4 bands and valid spatial metadata."""
    import rasterio

    tif_file = DATA_DIR / "optical_images" / "sentinel2_l2a_mediterranean_fusion.tif"
    assert tif_file.exists(), "Sentinel-2 GeoTIFF missing"
    assert tif_file.stat().st_size > 500_000, "GeoTIFF file too small"

    with rasterio.open(tif_file) as src:
        assert src.count == 4, f"Expected 4 bands, got {src.count}"
        assert src.width > 200 and src.height > 200
        assert src.crs is not None
        b2 = src.read(1)
        assert b2.dtype == np.float32 or b2.dtype == np.uint16 or b2.dtype == np.uint8


def test_era5_wind():
    """Verify ERA5 Hourly 10m Wind NetCDF contains u10/v10 and valid coordinates."""
    import xarray as xr

    nc_file = DATA_DIR / "weather" / "era5_wind_mediterranean_case_study.nc"
    assert nc_file.exists(), "ERA5 NetCDF missing"
    assert nc_file.stat().st_size > 10_000, "ERA5 NetCDF too small"

    ds = xr.open_dataset(nc_file)
    assert "u10" in ds.data_vars, "u10 variable missing"
    assert "v10" in ds.data_vars, "v10 variable missing"
    assert "valid_time" in ds.coords or "time" in ds.coords
    ds.close()


def test_oscar_ocean_currents():
    """Verify NASA OSCAR Surface Ocean Currents NetCDF."""
    import xarray as xr

    nc_file = DATA_DIR / "ocean_currents" / "oscar_currents_final_20240823.nc"
    assert nc_file.exists(), "OSCAR NetCDF missing"
    assert nc_file.stat().st_size > 10_000_000, "OSCAR NetCDF too small"

    ds = xr.open_dataset(nc_file)
    assert "u" in ds.data_vars, "u current variable missing"
    assert "v" in ds.data_vars, "v current variable missing"
    assert "latitude" in ds.coords or "lat" in ds.coords
    assert "longitude" in ds.coords or "lon" in ds.coords
    ds.close()


def test_krestenitis_sar_dataset():
    """Verify Krestenitis et al. CERTH SAR Oil Spill dataset (Option B)."""
    krest_dir = DATA_DIR / "sar_images" / "krestenitis_dataset"
    assert krest_dir.exists(), "Krestenitis directory missing"

    for split, exp_imgs, exp_masks in [("train", 672, 672), ("val", 160, 160), ("test", 208, 208)]:
        img_dir = krest_dir / split / "images"
        mask_dir = krest_dir / split / "masks"
        assert img_dir.exists(), f"{split}/images directory missing"
        assert mask_dir.exists(), f"{split}/masks directory missing"

        imgs = list(img_dir.glob("*.jpg"))
        masks = list(mask_dir.glob("*.png"))
        assert len(imgs) == exp_imgs, f"Expected {exp_imgs} {split} images, got {len(imgs)}"
        assert len(masks) == exp_masks, f"Expected {exp_masks} {split} masks, got {len(masks)}"

    # Check a sample image & mask resolution
    sample_img = Image.open(krest_dir / "train" / "images" / "Oil (1).jpg")
    sample_mask = Image.open(krest_dir / "train" / "masks" / "Oil (1).png")
    assert sample_img.size == (1920, 1080)
    assert sample_mask.size == (1920, 1080)


def test_zenodo_sos_dataset_masks():
    """Verify Zenodo SOS Refined Dataset masks (Option A)."""
    sos_dir = DATA_DIR / "sar_images" / "sos_dataset" / "masks"
    assert sos_dir.exists(), "SOS masks directory missing"

    train_masks = list((sos_dir / "train").glob("*.png"))
    val_masks = list((sos_dir / "val").glob("*.png"))

    assert len(train_masks) == 6455, f"Expected 6455 train masks, got {len(train_masks)}"
    assert len(val_masks) == 1615, f"Expected 1615 val masks, got {len(val_masks)}"
