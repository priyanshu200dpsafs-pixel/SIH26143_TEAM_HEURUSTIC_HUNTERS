# Maritime Oil Spill Detection and Vessel Attribution

[![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Framework: PyTorch](https://img.shields.io/badge/Framework-PyTorch-orange.svg)](https://pytorch.org/)
[![UI: Streamlit](https://img.shields.io/badge/UI-Streamlit-red.svg)](https://streamlit.io/)

An integrated forensic intelligence system designed to detect illicit maritime hydrocarbon spills via satellite remote sensing (SAR/optical), trace their hydrodynamic drift back to release points via Lagrangian hindcasting, identify offending ships using kinematic AIS trajectory analytics, and assemble automated legal evidence briefs.

---

## 🗂️ Folder Structure

```text
oil-spill-attribution/
├── README.md                 # Project mission, setup instructions, and module execution
├── requirements.txt          # Python dependencies (NumPy, PyTorch, GeoPandas, Streamlit, etc.)
├── .gitignore                # Git exclusions (data tiles, model weights, venvs, reports)
├── data/                     # Raw and sample datasets (git-ignored, structure preserved)
│   ├── sar_images/           # Raw + sample Sentinel-1 SAR tiles (GRD GeoTIFF)
│   ├── optical_images/       # Sentinel-2 MSI multispectral tiles (L2A)
│   ├── ais/                  # AIS vessel trajectory data (CSV / Parquet / JSON)
│   ├── ocean_currents/       # OSCAR / HYCOM hydrodynamic current velocity grids
│   └── weather/              # ECMWF ERA5 10m surface wind velocity fields
├── src/                      # Source code modules
│   ├── detection/            # Satellite detection and spill characterization
│   │   ├── sar_segmentation.py     # Sentinel-1 SAR dark patch segmentation model
│   │   ├── optical_fusion.py       # Sentinel-2 multispectral cross-check (look-alike filter)
│   │   └── spill_properties.py     # Area, elongation, perimeter, and Fay spreading age
│   ├── drift_model/          # Hydrodynamic transport modeling
│   │   ├── lagrangian_tracker.py   # Backward/forward Lagrangian particle drift (RK4)
│   │   └── uncertainty.py          # Monte Carlo dispersion and uncertainty cone generation
│   ├── ais_analysis/         # Maritime traffic intelligence
│   │   ├── traffic_filter.py       # Spatial-temporal vessel filtering against drift cones
│   │   ├── spoofing_detector.py    # Kinematic speed checks & dark transponder detection
│   │   └── suspicion_scorer.py     # Multi-factor suspect vessel attribution ranking
│   ├── reporting/            # Evidentiary brief generation
│   │   └── generate_report.py      # Automated PDF "prosecutor's brief" compiler
│   └── utils/                # Shared utilities
│       └── geo_helpers.py          # Great-circle distance, bearings, and GeoJSON utilities
├── models/                   # Serialized model checkpoints (.pt, .onnx)
├── dashboard/                # Visual user interface
│   └── app.py                # Interactive Streamlit dashboard
├── notebooks/                # Prototyping and exploration
│   └── exploration.ipynb     # Jupyter sandbox for data inspection & modeling experiments
├── tests/                    # Automated testing suite
│   ├── test_detection.py     # Tests for SAR/optical segmentation and geometry
│   ├── test_drift.py         # Tests for Lagrangian drift and uncertainty cones
│   ├── test_ais.py           # Tests for AIS filtering, spoofing, and scoring
│   └── test_reporting.py     # Tests for PDF dossier generation
└── docs/                     # Scientific and architectural documentation
    ├── architecture.md       # Pipeline architecture, system diagram, and contracts
    └── methodology.md        # Scientific references (CleanSeaNet, Fay spreading, NOAA GNOME)
```

---

## 🚀 Getting Started

### 1. Prerequisites
- Python 3.10 to 3.13
- Git

### 2. Virtual Environment Setup
From the project root:

```bash
# Activate the pre-created virtual environment
source .venv/bin/activate

# Install project dependencies
pip install -r requirements.txt
```

---

## 🛠️ How to Run Each Module

### 1. Launch the Interactive Dashboard
Launch the multi-stage operational web dashboard:
```bash
streamlit run dashboard/app.py
```
This launches a browser interface allowing you to:
- Inspect detected SAR slicks and optical confirmation.
- Configure and simulate backward Lagrangian drift particle trajectories.
- View ranked suspect vessels and AIS dark window anomalies.
- Generate and download PDF prosecutor's dossiers.

### 2. Run Individual Modules via Python
All modules are organized under the `src` package. You can import and invoke them in Python scripts or interactive sessions:

```python
# SAR Detection & Spill Properties
from src.detection import SARSARSegmentor, SpillPropertyExtractor
segmentor = SARSARSegmentor(device="cpu")
extractor = SpillPropertyExtractor(pixel_resolution_meters=10.0)

# Lagrangian Drift Hindcasting
from src.drift_model import LagrangianDriftTracker, UncertaintyConeGenerator
tracker = LagrangianDriftTracker(windage_factor=0.031)

# AIS Traffic Filtering & Scoring
from src.ais_analysis import AISTrafficFilter, SpoofingDetector, SuspicionScorer
scorer = SuspicionScorer()

# Generate Prosecutor's Evidentiary Brief
from src.reporting import ProsecutorBriefGenerator
reporter = ProsecutorBriefGenerator(output_dir="reports")
```

### 3. Run Automated Tests
Execute the unit test suite across all modules:
```bash
pytest tests/ -v
```

### 4. Interactive Data Prototyping
Launch Jupyter to explore data, test algorithms, and visualize trajectories:
```bash
jupyter lab notebooks/exploration.ipynb
```

---

## 📚 References & Methodology
Detailed scientific formulations and operational references are available in the `docs/` directory:
- [Pipeline Architecture](docs/architecture.md): Data flows, interface contracts, and Mermaid pipeline diagram.
- [Scientific Methodology](docs/methodology.md): EMSA CleanSeaNet detection standards, Fay spreading model equations, NOAA GNOME advection-diffusion formulations, and MARPOL evidentiary standards.

---

## 📄 License
This project is licensed under the MIT License.
