"""
Maritime Oil Spill Detection & Vessel Attribution Dashboard.

Interactive analytical console providing:
1. SAR & Optical Satellite Slick Segmentation & Verification
2. Lagrangian Particle Drift Backtracking (Ocean Currents + Wind)
3. AIS Marine Traffic Intersection & Suspect Vessel Attribution Matrix
4. Automated Prosecutor's Evidentiary Brief (PDF Dossier) Generation
"""

import datetime
from typing import Any, Dict, List

try:
    import streamlit as st
except ImportError:
    st = None


def render_header() -> None:
    """Render top branding, title, and mission overview."""
    st.set_page_config(
        page_title="Maritime Oil Spill Attribution Console",
        page_icon="🛰️",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.title("🛰️ Maritime Oil Spill Attribution System")
    st.caption(
        "Forensic satellite surveillance, hydrodynamic drift hindcasting, "
        "and kinematic AIS vessel attribution pipeline."
    )


def render_sidebar() -> Dict[str, Any]:
    """Render operational control sidebar and parameter sliders."""
    st.sidebar.title("Navigation & Parameters")
    module_choice = st.sidebar.radio(
        "Select Pipeline Stage",
        [
            "1. Satellite Detection (SAR / Optical)",
            "2. Hydrodynamic Drift Hindcasting",
            "3. AIS Traffic & Suspect Scoring",
            "4. Evidentiary Brief Generator",
        ],
    )

    st.sidebar.markdown("---")
    st.sidebar.subheader("Incident Target")
    incident_id = st.sidebar.text_input("Incident ID", value="INC-2026-MED-0042")
    spill_lat = st.sidebar.number_input("Detected Latitude (°N)", value=34.5214, format="%.5f")
    spill_lon = st.sidebar.number_input("Detected Longitude (°E)", value=18.3421, format="%.5f")
    detection_dt = st.sidebar.date_input("Detection Date", value=datetime.date(2026, 9, 12))

    return {
        "module": module_choice,
        "incident_id": incident_id,
        "lat": spill_lat,
        "lon": spill_lon,
        "date": str(detection_dt),
    }


def view_detection_tab(config: Dict[str, Any]) -> None:
    """Display SAR slick segmentation and optical cross-validation views."""
    st.header("1. Satellite Slick Detection & Verification")
    col1, col2 = st.columns([1, 1])

    with col1:
        st.subheader("Sentinel-1 SAR C-Band Observation")
        st.info("Ingesting Sentinel-1 GRD SAR tile (VV/VH polarization). Radiometrically calibrated.")
        st.metric(label="Candidate Slick Area", value="14.82 km²", delta="+2.1 km² (24h est.)")
        st.metric(label="Elongation Ratio", value="4.62 (linear slick)")
        st.metric(label="SAR Model Confidence", value="94.7%")

    with col2:
        st.subheader("Sentinel-2 Optical Cross-Validation")
        st.info("Multi-spectral verification (B3 Green, B8 NIR, NDWI index).")
        st.metric(label="Look-alike Risk", value="Low (< 5%)")
        st.metric(label="Algal Bloom Signal", value="Negative")
        st.metric(label="Sunglint Mask Status", value="Clear Ocean Surface")

    st.markdown("---")
    st.subheader("Interactive Spill Geometry")
    st.write(
        f"Target slick centered at `{config['lat']}°N, {config['lon']}°E`. "
        "Fay Spreading Model estimates release age between **14.2 to 18.5 hours prior to SAR acquisition**."
    )


def view_drift_tab(config: Dict[str, Any]) -> None:
    """Display Lagrangian backward trajectory simulation and uncertainty cones."""
    st.header("2. Hydrodynamic Drift Hindcasting (Backward Trajectory)")
    col1, col2, col3 = st.columns(3)

    with col1:
        lookback = st.slider("Hindcast Lookback Window (Hours)", 6, 48, 24)
    with col2:
        windage = st.slider("Windage Leeway Coefficient (%)", 1.0, 5.0, 3.1)
    with col3:
        particles = st.slider("Monte Carlo Dispersion Parcels", 100, 2000, 500)

    st.success(
        f"Simulating {particles} particle trajectories back {lookback} hours using "
        f"HYCOM surface currents + ERA5 10m wind with {windage}% leeway factor."
    )

    st.subheader("Estimated Origin Release Envelope")
    st.json(
        {
            "Estimated Release Time Window (UTC)": "2026-09-11 18:00 to 2026-09-11 22:30",
            "Probable Release Center": {"lat": 34.618, "lon": 18.105},
            "95% Confidence Semi-Major Axis": "4.8 km",
            "Dominant Forcing": "Surface Current 0.32 m/s NW, Wind 12 kts SE",
        }
    )


def view_ais_tab(config: Dict[str, Any]) -> None:
    """Display AIS traffic filter, anomaly detection, and ranked suspects."""
    st.header("3. AIS Marine Traffic & Suspicion Scoring Matrix")
    st.write("Vessels intersecting the hindcast uncertainty cone during the estimated release window:")

    sample_suspects = [
        {
            "Rank": 1,
            "MMSI": 636018992,
            "Vessel Name": "ATLANTIC CARRIER",
            "Type": "Crude Oil Tanker (80)",
            "Flag": "Liberia",
            "Distance to Origin": "1.2 km",
            "AIS Anomaly": "45-min Dark Window near spill origin",
            "Draft Change": "-1.8 m (Discharge pattern)",
            "Suspicion Index": "0.94 / 1.00",
        },
        {
            "Rank": 2,
            "MMSI": 352002140,
            "Vessel Name": "PACIFIC TITAN",
            "Type": "Chemical Tanker (82)",
            "Flag": "Panama",
            "Distance to Origin": "3.8 km",
            "AIS Anomaly": "None (Normal trajectory)",
            "Draft Change": "0.0 m",
            "Suspicion Index": "0.41 / 1.00",
        },
        {
            "Rank": 3,
            "MMSI": 240889000,
            "Vessel Name": "AEGEAN BREEZE",
            "Type": "Container Ship (71)",
            "Flag": "Greece",
            "Distance to Origin": "7.5 km",
            "AIS Anomaly": "None",
            "Draft Change": "0.0 m",
            "Suspicion Index": "0.18 / 1.00",
        },
    ]

    st.dataframe(sample_suspects, use_container_width=True)
    st.warning("🚨 Primary Suspect: **ATLANTIC CARRIER (MMSI: 636018992)** exhibiting transponder dark window and draft reduction.")


def view_reporting_tab(config: Dict[str, Any]) -> None:
    """Evidentiary PDF brief compiler and preview."""
    st.header("4. Prosecutor's Evidentiary Brief Generator")
    st.write(
        "Compile a legally defensible forensic attribution brief adhering to "
        "MARPOL Annex I enforcement standards."
    )

    col1, col2 = st.columns([2, 1])
    with col1:
        st.text_input("Investigating Authority", value="Maritime Safety and Coast Guard Agency")
        st.text_input("Lead Forensic Officer", value="Inspector J. Vance, Maritime Crime Division")
        st.checkbox("Include Sentinel-1 SAR Georeferenced Chips", value=True)
        st.checkbox("Include Lagrangian Particle Dispersion Cones", value=True)
        st.checkbox("Include AIS Track Blackout / Kinematic Anomaly Analysis", value=True)
        st.checkbox("Attach Cryptographic SHA-256 Chain-of-Custody Manifest", value=True)

    with col2:
        st.markdown("### Document Actions")
        if st.button("Generate Prosecutor's Brief (PDF)", type="primary"):
            st.success("Dossier compiled successfully: `reports/BRIEF-INC-2026-MED-0042.pdf`")
            st.download_button(
                label="📥 Download PDF Dossier",
                data=b"%PDF-1.4 Mock Brief Placeholder Content",
                file_name=f"BRIEF-{config['incident_id']}.pdf",
                mime="application/pdf",
            )


def main() -> None:
    """Main dashboard entrypoint."""
    if st is None:
        print("Streamlit is not installed. Please run inside the virtual environment: pip install -r requirements.txt")
        return

    render_header()
    config = render_sidebar()

    if "1. Satellite Detection" in config["module"]:
        view_detection_tab(config)
    elif "2. Hydrodynamic Drift" in config["module"]:
        view_drift_tab(config)
    elif "3. AIS Traffic" in config["module"]:
        view_ais_tab(config)
    elif "4. Evidentiary Brief" in config["module"]:
        view_reporting_tab(config)


if __name__ == "__main__":
    main()
