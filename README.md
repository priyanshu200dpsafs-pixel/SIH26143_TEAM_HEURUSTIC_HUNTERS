# AEGIS-SAR: Autonomous Maritime Oil Spill Intelligence & Vessel Attribution Platform
### SIH Problem Statement 26143 — Deployable Production Operations Platform

[![Python 3.13](https://img.shields.io/badge/python-3.13-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-009688.svg)](https://fastapi.tiangolo.com/)
[![React 18](https://img.shields.io/badge/React-18.3-61dafb.svg)](https://react.dev/)
[![MapLibre GL](https://img.shields.io/badge/MapLibre_GL-4.7-38bdf8.svg)](https://maplibre.org/)
[![PyTorch](https://img.shields.io/badge/PyTorch-7.76M_Params-ee4c2c.svg)](https://pytorch.org/)
[![Docker](https://img.shields.io/badge/Docker-Ready-2496ed.svg)](https://www.docker.com/)
[![Tests](https://img.shields.io/badge/Tests-114%2F114_Passing-brightgreen.svg)]()

An integrated, mission-critical maritime surveillance and forensic intelligence web platform designed to detect illicit hydrocarbon spills at sea via Copernicus Sentinel-1 Synthetic Aperture Radar (SAR), calculate oceanographic Lagrangian hindcasts (Runge-Kutta 4th Order with Fay spreading age), reconstruct historical AIS vessel traffic, rank suspect vessels through multi-factor Bayesian attribution, execute counterfactual forward simulations, and assemble cryptographically sealed evidentiary dossiers adhering to international maritime law enforcement standards (UNCLOS and MARPOL 73/78 Annex I).

---

## 🌊 Primary Intelligence Workflow

```
MONITOR (Copernicus Sentinel-1 SAR OData Catalog & Live AOI Poller)
   ↓
DETECT (SARSARSegmentor 4-Class Deep Learning U-Net with 7.76M Weights)
   ↓
VALIDATE (Fay Spreading Age, Compactness Ratio & Sentinel-2 MSI Optical Fusion)
   ↓
HINDCAST (Lagrangian RK4 Particle Tracker with 3% ERA5 Windage, Coriolis & OSCAR Currents)
   ↓
CORRELATE AIS (Sliding Temporal Buffer, Kinematic Limits & Dark Vessel Anomaly Filtering)
   ↓
RANK CANDIDATES (Multi-Factor Bayesian Attribution: Spatial, Temporal, Trajectory, Draft)
   ↓
COUNTERFACTUAL (Forward Particle Perturbation Testing IoU Overlap with Observed Slick)
   ↓
FORECAST (Forward Ocean Transport Projecting 12h, 24h, and 48h Coastal Intersections)
   ↓
INVESTIGATE (3-Panel Interactive MapLibre GL Maritime Investigation Console)
   ↓
EXPORT EVIDENCE (Cryptographically Sealed Forensic Dossiers with SHA-256 Chain of Custody)
```

---

## 🚀 Quick Start & Deployment

### Option 1: Direct Local Execution (FastAPI + React)

1. **Activate Environment & Install Requirements**:
   ```bash
   source .venv/bin/activate
   pip install -r requirements.txt
   pip install fastapi uvicorn websockets python-multipart httpx
   ```

2. **Build Frontend**:
   ```bash
   cd frontend
   npm install
   npm run build
   cd ..
   ```

3. **Start Platform Service**:
   ```bash
   python -m uvicorn src.api.main:app --host 0.0.0.0 --port 8000
   ```
   Open your browser at **`http://localhost:8000`**.

---

### Option 2: Docker / Container Deployment

1. **Configure Environment Variables**:
   ```bash
   cp .env.example .env
   ```

2. **Launch with Docker Compose**:
   ```bash
   docker compose up --build -d
   ```
   The entire application will be compiled, containerized, and served at `http://localhost:8000`.

---

## 🖥️ Operational Routes & Capabilities

The platform implements 10 production routes:

| Route | View | Description | Key Functional Actions |
| :--- | :--- | :--- | :--- |
| **`/operations`** | Tactical Command Overview | Real-time maritime status, KPI cards (Active Watches, Incidents, Vessels, Scenes, Alerts), interactive MapLibre GL map. | Incident quick-select, live vessel inspect, map layer toggling, distance measurement. |
| **`/watch`** | Continuous Surveillance Watch | Autonomous background surveillance loop monitoring configured AOI for newly available Sentinel-1 scenes. | Start/Stop watch, Pause/Resume, Run Once, update AOI coordinates, configure polling intervals. |
| **`/incidents`** | Forensic Incident Registry | Filterable registry of confirmed spills with morphological properties, confidence tiers, and primary suspects. | Multi-factor filtering, search, pagination, Export JSON, Export GeoJSON. |
| **`/incidents/:id`** | Investigation Workspace | Mission-critical forensic investigation console with 3-panel layout (Morphology, MapLibre Layers, Attribution Scorecard, Evidence Timeline). | Rerun analysis, recompute hindcast, re-correlate AIS, run counterfactual test, forward forecast, export dossiers. |
| **`/satellite`** | SAR Catalog & Ingestion | Real Sentinel-1 catalog search against Copernicus OData (CDSE). | Search by AOI/date, product metadata inspection, download scene, validate GeoTIFF raster, trigger incident pipeline. |
| **`/ais`** | Vessel Traffic & Telemetry | Live sliding buffer of maritime traffic with kinematic anomaly detection. | Connection test, buffer lookback adjustment, vessel detail modal, full trajectory map, GeoJSON track export. |
| **`/analysis`** | Attribution Workspace | Multi-factor scorecard decomposition comparing suspect vessels against release origins. | Radar/bar score breakdown, wind/current perturbation sliders, counterfactual forward simulation. |
| **`/reports`** | Forensic Briefs & Dossiers | UNCLOS/MARPOL admissible evidentiary packages with cryptographic chain of custody. | View brief in browser, download HTML/JSON packages, verify SHA-256 seal against disk. |
| **`/settings`** | Platform Settings | Surveillance AOI bounds, polling intervals, forecast horizon, and external provider authentication status. | Edit and persist configuration parameters. Secrets are strictly masked. |
| **`/system`** | System Diagnostics | Infrastructure health checks, PyTorch device status, U-Net weights verification, active async jobs, and immutable audit trail. | Live health checks, active worker monitoring, audit log viewer. |

---

## 🔒 Strict Data Provenance Philosophy

To prevent deceptive mockups or fabricated data:
- Every number, slick area, ship coordinate, and probability cone is computed by real backend Python engines.
- Every metric and visualization carries an explicit provenance tag:
  - `REAL`: Direct empirical observation (e.g. Sentinel-1 SAR acquisition, verified AIS message).
  - `INFERRED`: Derived scientific computation (e.g. U-Net segmentation, Lagrangian RK4 hindcast origin).
  - `SIMULATED`: Counterfactual forward drift test or forecast projection.
  - `UNAVAILABLE`: Honestly reported when external provider credentials are not configured or data is stale.

---

## 🧪 Automated Testing & Verification

Run the complete 114-test automated suite:
```bash
pytest -v
```

- **103 Baseline Tests**: Validating physics (ERA5 windage, Fay spreading, OSCAR currents), U-Net weights (7.76M params), Lagrangian tracking, kinematics, and Bayesian attribution.
- **10 Platform API Tests** (`tests/test_api_platform.py`): Validating all REST endpoints, async jobs, and WebSocket integration.
- **1 E2E Acceptance Test** (`tests/test_e2e_platform_flow.py`): Validating the complete 16-step operational workflow.

---

## ⚖️ Regulatory & Legal Compliance

Forensic dossiers generated by AEGIS-SAR satisfy:
- **UNCLOS Article 217 & 218**: Enforcement of international rules and port state jurisdiction.
- **MARPOL 73/78 Annex I**: Regulations for the Prevention of Pollution by Oil.
- **Cryptographic Chain of Custody**: Every compiled brief receives an SHA-256 seal recorded in `data/reports/reports_index.json` and `data/audit/audit_log.jsonl`.
