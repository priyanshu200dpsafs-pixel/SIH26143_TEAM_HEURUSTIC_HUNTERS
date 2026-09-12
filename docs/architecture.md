# Maritime Oil Spill Detection and Vessel Attribution Architecture

## 1. System Overview

The **Oil Spill Attribution System** is an end-to-end multi-sensor intelligence platform designed to detect illicit maritime hydrocarbon discharges, model their hydrodynamic drift back to origin, identify suspect vessels from AIS traffic, and produce legally admissible evidence dossiers.

```mermaid
flowchart TD
    subgraph DataIngestion ["1. Multi-Modal Data Ingestion"]
        S1["Sentinel-1 SAR (C-Band GRD)"]
        S2["Sentinel-2 Optical (MSI L2A)"]
        AIS["Terrestrial & Satellite AIS Messages"]
        HYCOM["HYCOM / OSCAR Surface Currents (u, v)"]
        ERA5["ECMWF ERA5 10m Wind Vectors (u, v)"]
    end

    subgraph DetectionModule ["2. Detection & Spill Profiling (src/detection)"]
        SAR_SEG["SAR Segmentation<br/>(Radiometric Calib + Lee Filter + U-Net)"]
        OPT_FUS["Optical Cross-Check<br/>(NDWI + Sunglint + Algal Filter)"]
        PROPS["Spill Morphometrics & Fay Age Estimation<br/>(Area, Perimeter, Orientation, Elapsed Time)"]
        S1 --> SAR_SEG
        SAR_SEG --> OPT_FUS
        S2 --> OPT_FUS
        OPT_FUS --> PROPS
    end

    subgraph DriftModule ["3. Hydrodynamic Drift Hindcast (src/drift_model)"]
        LAGR["Lagrangian Backward Tracker<br/>(RK4 Integration + 3% Leeway Windage)"]
        DIFF["Monte Carlo Turbulent Dispersion<br/>(Uncertainty Cones & Release Envelopes)"]
        PROPS --> LAGR
        HYCOM --> LAGR
        ERA5 --> LAGR
        LAGR --> DIFF
    end

    subgraph AISModule ["4. AIS Kinematic Attribution (src/ais_analysis)"]
        TRAF_FILT["Spatiotemporal Traffic Filter<br/>(Polygon & Release Window Intersect)"]
        SPOOF["Kinematic Anomaly & Dark Detector<br/>(Impossible SOG, AIS Gaps, MMSI Clones)"]
        SCORER["Probabilistic Suspicion Scorer<br/>(Proximity, Vessel Type, Draft Deltas)"]
        DIFF --> TRAF_FILT
        AIS --> TRAF_FILT
        TRAF_FILT --> SPOOF
        SPOOF --> SCORER
    end

    subgraph Presentation ["5. Evidentiary Delivery & Interfaces"]
        REPORT["Prosecutor's Brief Generator<br/>(PDF Dossier, Imagery Chips, Chain of Custody)"]
        DASH["Interactive Dashboard<br/>(Streamlit / Folium Map Console)"]
        SCORER --> REPORT
        SCORER --> DASH
    end
```

---

## 2. Component Breakdown

### A. Detection Engine (`src/detection/`)
- **`sar_segmentation.py`**: Ingests Sentinel-1 Level-1 GRD imagery in VV and VH polarizations. Performs radiometric calibration to $\sigma_0$ (dB), reduces speckle via Lee/Frost adaptive filtering, and executes deep neural network inference (U-Net or ONNX runtime) to segment dark ocean surface patches caused by capillary wave damping.
- **`optical_fusion.py`**: Intersects SAR candidates with co-registered Sentinel-2 multi-spectral bands. Computes Normalized Difference Water Index (NDWI) and checks for elevated chlorophyll-a (algal bloom) or sunglint artifacts to eliminate false positives.
- **`spill_properties.py`**: Extracts slick polygon metrics (surface area in $km^2$, major/minor elongation axes, perimeter) and applies the Fay three-phase spreading model to estimate slick age $t_{spill}$.

### B. Hydrodynamic Drift Model (`src/drift_model/`)
- **`lagrangian_tracker.py`**: Solves the Lagrangian particle transport equations backwards in time (hindcasting) from detection timestamp $t_{det}$ to $t_{det} - \Delta t_{lookback}$. Uses 4th-order Runge-Kutta (RK4) integration:
  $$\vec{x}(t - \Delta t) = \vec{x}(t) - \int_{t-\Delta t}^t (\vec{u}_{current} + \alpha_{leeway} \mathbf{R}(\theta) \vec{u}_{wind}) \, dt$$
- **`uncertainty.py`**: Injects stochastic Gaussian turbulence ($\sqrt{2 K_h \Delta t}$) across an ensemble of $N$ particles to generate dynamic 95% confidence release envelopes (convex hulls / alpha shapes).

### C. AIS Attribution Engine (`src/ais_analysis/`)
- **`traffic_filter.py`**: Performs spatiotemporal intersection between the hindcasted uncertainty envelope and historical AIS trajectory broadcasts.
- **`spoofing_detector.py`**: Validates kinematic plausibility: identifies impossible velocity jumps ($> 40\text{ knots}$ for commercial tankers), duplicate MMSIs simultaneously broadcasting from distant locations, and deliberate transponder dark periods.
- **`suspicion_scorer.py`**: Combines spatial distance to release origin, temporal coincidence, vessel class risk factors (e.g. crude carrier vs bulk carrier), draft reductions (cargo discharge indicators), and AIS blackout flags into a normalized index $S \in [0.0, 1.0]$.

### D. Legal Evidentiary Reporting (`src/reporting/`)
- **`generate_report.py`**: Compiles an automated "Prosecutor's Evidentiary Brief" formatted as a secure PDF dossier. Embeds georeferenced satellite chips, backward drift path overlays, suspect vessel profiles, and SHA-256 digital hashes for chain-of-custody preservation under MARPOL Annex I.

### E. Analytical Dashboard (`dashboard/`)
- **`app.py`**: Multi-page interactive console built with Streamlit and Folium, offering map-based inspection, dynamic slider adjustments for leeway windage, interactive vessel trajectory inspection, and one-click PDF generation.
