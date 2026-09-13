# Comprehensive Data Readiness Matrix

This matrix evaluates all assets in the repository across five scientific criteria.
**Rule**: No dataset may be marked READY merely because its file opens without error.

| Dataset Asset | Exists | Structurally Valid | Scientifically Validated | Case Linked | Ready Status & Role |
| :--- | :---: | :---: | :---: | :---: | :--- |
| **Krestenitis SAR Benchmark (Option B)** | ✅ Yes | ✅ Yes (1,040 images/masks, 0 corrupt, 100% paired) | ✅ Yes (4 verified classes: Water, Oil, Look-alike, Background; Ship & Land absent) | ❌ No (Global historical patch dataset 2015–2018) | **READY (ML Training / Segmentation Benchmark only)** |
| **Refined Deep-SAR SOS (Option A)** | ✅ Yes | ✅ Yes (8,070 images/masks, 0 corrupt, 100% paired) | ✅ Yes (Binary oil-spill vs background with edge refinement) | ❌ No (Global patch dataset, uncoupled from case study) | **READY (ML Training / Binary Segmentation only)** |
| **Sentinel-2 L2A Optical Multi-Band** | ✅ Yes | ✅ Yes (GeoTIFF, 4 bands: B2, B3, B4, B8, EPSG:4326) | ✅ Yes (Copernicus CDSE, 3.7% cloud cover) | ✅ Yes (Defines Mediterranean 2024-08-23 spatial/temporal testbed) | **READY (Multi-Sensor Optical Validation Pipeline)** |
| **ERA5 Hourly 10m Wind NetCDF** | ✅ Yes | ✅ Yes (NetCDF4, 72 hourly timesteps, u10/v10) | ✅ Yes (ECMWF / Copernicus CDS Reanalysis) | ✅ Yes (Covers 2024-08-22 to 2024-08-24 over Mediterranean domain) | **READY (Trajectory Drift Hindcast Physics)** |
| **NASA OSCAR Surface Ocean Currents** | ✅ Yes | ✅ Yes (NetCDF4, 0.25° grid, u/v/ug/vg components) | ✅ Yes (NASA PO.DAAC authenticated) | ✅ Yes (Observation date 2024-08-23 covers Mediterranean domain) | **READY (Trajectory Drift Hindcast Physics)** |
| **Natural Earth 10m Coastlines & Land** | ✅ Yes | ✅ Yes (4,133 coastlines + 11 land polygons, EPSG:4326) | ✅ Yes (Authoritative GIS cartographic reference) | ✅ Yes (Global coverage intersects Mediterranean domain) | **READY (Boundary Masking & Coastal Stranding Logic)** |
| **MarineCadastre Real AIS Reference** | ✅ Yes | ✅ Yes (10,224 rows, 16 standard columns) | ✅ Yes (Official NOAA / BOEM dataset) | ❌ No (Alaska / Pacific Zone 01, Jan 2017) | **READY (Schema Reference & Parser Ingestion Unit Tests only; NOT CASE-LINKED)** |
| **Synthetic AIS Scenario (Current)** | ✅ Yes | ✅ Yes (2,592 rows, 16 MarineCadastre columns) | ⚠️ Partial (Manually engineered single suspect; not adversarial) | ⚠️ Synthetic (Placed in Mediterranean coordinates, but simulated) | **NOT READY as Attribution Benchmark** (Must implement 7 isolated benchmark scenarios) |

---

## Readiness Summary

1. **ML Training Pipeline**: **READY** (We possess 9,110 verified SAR image/mask pairs across Krestenitis and Deep-SAR SOS).
2. **Environmental Drift Modeling**: **READY** (ERA5 hourly wind and OSCAR ocean currents are co-temporal, co-located, and scientifically validated).
3. **End-to-End Mediterranean Golden Case Attribution**: **NOT READY** (Blocked by lack of co-temporal real incident AIS and absence of verified oil pollution ground truth in the Mediterranean 2024 scene).
