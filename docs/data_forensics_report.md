# Comprehensive Data Forensics & Readiness Report

**Date of Forensics Pass**: 2026-09-13  
**Status**: Data Forensics Complete — Model Training Halted Pending Architecture Review

---

## 1. SAR Class Ground Truth & Inventory Forensics

### 1.1 Krestenitis Dataset Forensics (`data/sar_images/krestenitis_dataset/`)
An exhaustive programmatic scan was conducted across **all 1,040 images and all 1,040 masks** (2,296,621,056 total pixels analyzed):

* **Image Dimensions**:
  * $1920 \times 1080$ (RGB): 1,028 images
  * $5184 \times 2920$ (RGB): 6 images
  * $4056 \times 3040$ (RGB): 4 images
  * $5184 \times 3888$ (RGB): 2 images
* **Mask Dimensions**: Identical to corresponding image dimensions ($100\%$ spatial match).
* **Pairing & Integrity**:
  * `train`: 672 images, 672 masks ($100\%$ paired)
  * `val`: 160 images, 160 masks ($100\%$ paired)
  * `test`: 208 images, 208 masks ($100\%$ paired)
  * **Missing pairs**: **0**
  * **Corrupt files**: **0**
* **Verification of `label_colors.txt`**:
  ```text
  0 0 0 background
  255 0 124 oil
  255 204 51 others
  51 221 255 water
  ```

#### Discovered Class Inventory:
Across all 2.296 billion mask pixels, **only 4 RGB color values exist in the entire dataset**:

```text
Actual classes discovered:
0: Background        RGB (0, 0, 0)       —    90,017,308 pixels ( 3.92%)
1: Oil Spill         RGB (255, 0, 124)   —   796,274,739 pixels (34.67%)
2: Look-alike/Others RGB (255, 204, 51)  —   906,818,020 pixels (39.48%)
3: Water/Sea Surface RGB (51, 221, 255)  —   503,510,989 pixels (21.92%)

Evidence:
- label_colors.txt defines exactly these 4 classes.
- Exhaustive numpy scan over all 1,040 masks discovered zero pixels outside these 4 values.
- SHIP CLASS NOT VERIFIED (0 occurrences across all masks)
- LAND CLASS NOT VERIFIED (0 occurrences across all masks)
```

> [!WARNING]
> **Class Absence Notice**: Although literature referencing Krestenitis et al. (2019) discusses a 5-class taxonomy (including ship and land), the released dataset mirror **does NOT contain ship or land annotations**. The model architecture must be configured for **4 classes** (or 3 active classes plus background). Ship and land classes must NOT be invented or assumed.

---

### 1.2 Refined Deep-SAR (SOS) Dataset Forensics (`data/sar_images/sos_dataset/`)
* **Archive Status**: `images.zip` (**1,148,063,776 bytes**) is **100% downloaded, tested via `zipfile.testzip()`, and fully extracted**.
* **Integrity & Pairing**:
  * `train`: **6,455 PNG images** + **6,455 PNG masks** (256×256 RGB)
  * `val`: **1,615 PNG images** + **1,615 PNG masks** (256×256 RGB)
  * **Total**: **8,070 matched pairs**
  * **Missing pairs**: **0**
  * **Corrupt files**: **0**
* **Class Encoding**: Binary semantic segmentation with anti-aliased edge refinements.
  * $0$ / `(0,0,0)`: Sea surface / Background
  * $255$ / `(255,255,255)`: Verified Oil Spill
  * Intermediate values ($9, 60, 70, 111, 144, 195$): Refined boundary transition pixels resulting from manual label revision by Zuenko & Khaidarova.

---

## 2. Sentinel-2 & Environmental Co-Registration Forensics

A formal machine-readable case record was constructed at [`data/case_studies/mediterranean_case_001.json`](file:///Users/priyanshu/Desktop/oil-spill-attribution/data/case_studies/mediterranean_case_001.json):

```text
Sentinel-2 acquisition: 2024-08-23 09:41:12 UTC (Product: S2A_MSIL2A_20240823T093031_N0511_R136_T33SYT_20240823T155251.SAFE)
ERA5 coverage:         2024-08-22 00:00:00 to 2024-08-24 23:00:00 (72 hourly steps, bounds [17.0°E, 33.0°N, 20.0°E, 36.0°N])
OSCAR date:            2024-08-23 (Global 0.25° grid, variables u, v, ug, vg)
Temporal offset:       0 hours (S2 acquisition at 09:41 UTC directly interpolates between ERA5 09:00 and 10:00 UTC; OSCAR observation date matches day of acquisition)
Spatial overlap:       100% nested. Sentinel-2 bounds [18.10°E, 34.30°N, 18.60°E, 34.70°N] are fully enclosed within the ERA5 spatial domain [17.00°E, 33.00°N, 20.00°E, 36.00°N] and OSCAR global grid.
```

> [!IMPORTANT]
> **Scientific Integrity Caveat**: Although the optical imagery, ERA5 winds, and OSCAR currents are strictly co-registered in space and time, **there is NO confirmed real-world oil-spill pollution accident associated with this scene**. It serves as an environmental testbed for multi-modal data fusion, not a verified spill accident.

---

## 3. AIS Data Forensics & Geographic Mismatch

### 3.1 Real AIS Reference (`data/ais/real_reference/AIS_2017_01_Zone01.csv`)
* **Total Rows**: 10,224 rows across 58 unique commercial vessels.
* **Geographic Bounds**: Latitude `[19.8718°N, 75.8356°N]`, Longitude `[-179.9766°W, -174.0001°W]`.
* **Temporal Range**: `2017-01-01 23:58:14` to `2017-01-31 23:59:32 UTC`.
* **Geographic Reality**: This dataset covers the **Bering Sea / Aleutian Islands / Alaska (UTM Zone 01)**, over **5,500 nautical miles away from the Mediterranean Sea**, and is separated in time by **7.5 years**.
* **Official Designation**:
  ```text
  REFERENCE DATASET — NOT CASE-LINKED
  ```
* **Permitted Use**: Validating CSV parser schema conformity, data cleaning routines, and AIS kinematic filtering logic. **Must NOT be ingested as incident AIS for the Mediterranean case.**

---

### 3.2 Synthetic AIS Scenario (`data/ais/synthetic/synthetic_ais_spill_scenario.csv`)
* **Total Rows**: 2,592 records across 9 vessels.
* **Limitation**: Manually created with 1 obvious suspicious tanker (`ATLANTIC CARRIER`). It does not represent an objective, adversarial evaluation benchmark.
* **Remediation**: Developed [`docs/synthetic_validation_scenarios.md`](file:///Users/priyanshu/Desktop/oil-spill-attribution/docs/synthetic_validation_scenarios.md) specifying **7 mandatory stress-test scenarios** where ground-truth source identities are strictly hidden from the attribution engine:
  1. True source + continuous AIS
  2. True source + AIS gap
  3. Innocent vessel + AIS gap (exoneration test)
  4. Two plausible vessels (disambiguation test)
  5. No compatible vessel / ghost ship (unattributed test)
  6. Impossible kinematics / GPS spoofing (rejection test)
  7. Nearby but temporally incompatible vessel (physical exclusion test)

---

## 4. Golden Case Status

As recorded in [`data/case_studies/README.md`](file:///Users/priyanshu/Desktop/oil-spill-attribution/data/case_studies/README.md):

```text
GOLDEN CASE STATUS = NOT READY
```

### Explanation:
While atmospheric (ERA5), hydrodynamic (OSCAR), and optical (Sentinel-2) assets are co-registered for 2024-08-23, the case lacks:
1. An officially documented real-world pollution incident report.
2. A co-temporal Sentinel-1 SAR acquisition directly over the scene.
3. Genuine, real-world AIS tracking data for Mediterranean vessels transiting that corridor in August 2024.

---

## 5. Remaining Blockers

1. **Model Architecture Parameterization**: The SAR segmentation network must be explicitly constrained to 4 classes (Background, Water, Oil, Look-alike) for Krestenitis, and binary for Deep-SAR SOS. Any code expecting 5 classes will fail or invent labels.
2. **Attribution Engine Benchmark Data**: The current single synthetic scenario is insufficient to validate an attribution engine. The 7 benchmark scenarios in `docs/synthetic_validation_scenarios.md` must be generated with ground truth hidden.
3. **End-to-End Real Incident Case Study**: Until a fully authenticated historic spill case (with co-located SAR, AIS, wind, and currents) is acquired, end-to-end attribution must be evaluated against the 7 isolated synthetic benchmarks.

---

## 6. Exact Recommended Next Step

**Action Item**:
1. Implement the **Synthetic Scenario Generator Engine** following `docs/synthetic_validation_scenarios.md` to produce the 7 isolated test scenarios with ground-truth metadata held in a blind manifest.
2. Implement the **Drift Hindcasting & Uncertainty Cone Generator** using the co-registered ERA5 wind and OSCAR current NetCDF datasets.
3. Implement the **Kinematic AIS Filter & Anomaly Detector** (testing against both real Alaska reference data and the 7 synthetic scenarios).
4. **Halt ML training** until the data pipelines and attribution scoring logic are validated.
