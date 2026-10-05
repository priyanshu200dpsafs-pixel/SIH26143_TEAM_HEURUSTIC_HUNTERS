# Case Studies Directory: Provenance & Status

## GOLDEN CASE STATUS = NOT READY

---

### Explicit Scientific Audit & Justification

A case study cannot be certified as a **Golden Case** unless ALL 7 critical components are co-located, co-temporal, and authenticated by independent incident reports:

| Component | Status | Current Repository Asset | Deficiency / Blocker |
| :--- | :--- | :--- | :--- |
| **1. Confirmed Incident Event** | ❌ **Missing** | N/A | There is no officially documented, corroborated marine oil-spill accident (e.g., from EMSA CleanSeaNet, ITOPF, or REMPEC) associated with the coordinates on 2024-08-23. |
| **2. Co-temporal SAR Observation** | ❌ **Missing** | Krestenitis (2019) / Deep-SAR SOS | The SAR datasets in the repo are localized patch benchmarks (2015–2020), not co-temporal Sentinel-1 GRD/SLC scenes acquired over the Mediterranean scene on 2024-08-23. |
| **3. Optical Observation** | ✅ **Present** | Sentinel-2 L2A (`S2A_...T33SYT`, 2024-08-23 09:41 UTC) | High quality, 3.7% cloud cover, 4 spectral bands. |
| **4. Matching ERA5 Wind** | ✅ **Present** | ERA5 NetCDF (`2024-08-22 00:00` to `2024-08-24 23:00 UTC`) | 72 hourly timesteps covering the exact spatial domain [17°E–20°E, 33°N–36°N]. |
| **5. Matching Ocean Currents** | ✅ **Present** | NASA OSCAR NetCDF (`2024-08-23`) | Daily 0.25° surface currents covering the Mediterranean. |
| **6. Real Matching AIS Data** | ❌ **Missing** | MarineCadastre `AIS_2017_01_Zone01.csv` | Real AIS in the repo is from **Alaska / Bering Sea in January 2017**, having zero spatial or temporal intersection with the Mediterranean 2024 case. |
| **7. Provenance & Metadata** | ⚠️ **Partial** | `mediterranean_case_001.json` | Validated environment alignment, but clearly flagged as `verified_incident_event: false`. |

---

### Operational Conclusion

The current Mediterranean configuration serves as a **Multi-Sensor Environmental Co-registration Testbed** (validating optical-weather-current data fusion pipelines), but **must NOT be presented as a verified oil spill attribution Golden Case** until a co-registered real incident dataset with genuine matching AIS is acquired.
