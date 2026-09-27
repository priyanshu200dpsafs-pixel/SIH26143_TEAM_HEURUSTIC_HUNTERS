# Scientific Methodology and Operational Standards

This document describes the theoretical, mathematical, and legal frameworks powering the **oil-spill-attribution** platform.

---

## 1. SAR Oil Spill Detection Principles (EMSA CleanSeaNet)

### 1.1 Radar Backscatter & Capillary Wave Damping
Synthetic Aperture Radar (SAR) sensors (such as Sentinel-1 C-band, 5.405 GHz) measure normalized radar cross-section ($\sigma_0$). Clean seawater surfaces appear bright in SAR imagery due to Bragg scattering from short gravity-capillary waves (1–10 cm) induced by surface winds.

Liquid hydrocarbons (crude oil, fuel oil, bilge water emulsions) form a viscoelastic monomolecular or thin film that dampens surface capillary waves:
- Damped surface acts as a specular reflector, deflecting radar pulses away from the sensor.
- The spill appears as a distinct **dark patch** against the surrounding rough sea clutter.

### 1.2 Look-Alike Discrimination (CleanSeaNet Guidelines)
Dark formations in SAR are not always petroleum discharges. Natural look-alikes include:
1. **Low-wind calm areas**: Wind speeds $< 2\text{--}3\text{ m/s}$ fail to generate capillary waves.
2. **Biogenic slicks**: Natural surfactant films produced by marine plankton and algae.
3. **Rain cells and atmospheric downdrafts**: Heavy precipitation attenuates radar energy.
4. **Internal waves & upwelling**: Oceanic circulation features damping surface roughness.

To filter look-alikes, the system incorporates:
- **Wind speed checks**: ERA5 wind speeds must fall within the detectable window ($3\text{ m/s} \le U_{10} \le 12\text{--}14\text{ m/s}$).
- **Optical Multi-Spectral Cross-Check**: Sentinel-2 MSI bands evaluate NDWI:
  $$\text{NDWI} = \frac{\rho_{560\text{nm}} - \rho_{842\text{nm}}}{\rho_{560\text{nm}} + \rho_{842\text{nm}}}$$
  Chlorophyll-a indices detect algal blooms, while true mineral oils show distinct thermal/reflectance anomalies in sunglint regimes.

---

## 2. Spreading Dynamics: The Fay Formulation

To constrain the release timestamp, the system applies **Fay's classical 3-phase spreading theory** for a sudden oil discharge of volume $V$:

1. **Gravity-Inertial Phase** (dominant immediately after discharge):
   $$r_1(t) = k_1 \cdot \left(\Delta \cdot g \cdot V \cdot t^2\right)^{1/4}$$
2. **Gravity-Viscous Phase** (buoyancy vs. water viscous drag):
   $$r_2(t) = k_2 \cdot \left(\frac{\Delta \cdot g \cdot V^2 \cdot t^{3/2}}{\nu_w^{1/2}}\right)^{1/6}$$
3. **Surface Tension-Viscous Phase** (spreading driven by net spreading coefficient $\sigma_{net}$):
   $$r_3(t) = k_3 \cdot \left(\frac{\sigma_{net}^2 \cdot t^3}{\rho_w^2 \cdot \nu_w}\right)^{1/4}$$

Where:
- $\Delta = \frac{\rho_w - \rho_{oil}}{\rho_w}$ (relative density difference)
- $g = 9.81\text{ m/s}^2$
- $\nu_w$ = kinematic viscosity of water ($\approx 10^{-6}\text{ m}^2/\text{s}$)
- $\sigma_{net} = \sigma_{w} - \sigma_{oil} - \sigma_{w/oil}$

By measuring the segmented slick area $A = \pi r_{eff}^2$ and estimating slick thickness from SAR texture/contrast, we invert Fay's equations to bound the discharge elapsed time $t_{spill}$.

---

## 3. Hydrodynamic Drift Modeling (NOAA GNOME Standards)

### 3.1 Advection-Diffusion Formulation
The displacement of slick parcels is governed by the Langevin equation:
$$d\vec{x} = \left[\vec{u}_{current}(x, t) + \vec{u}_{leeway}(x, t)\right] dt + \sqrt{2 K_h dt} \cdot \vec{\xi}$$

Where:
- $\vec{u}_{current}$: Hydrodynamic surface current velocity from HYCOM / OSCAR.
- $\vec{u}_{leeway}$: Wind-driven advection parameterized by standard leeway rules:
  $$\vec{u}_{leeway} = \alpha_{wind} \cdot \mathbf{R}(\theta_{Coriolis}) \cdot \vec{U}_{10}$$
  - $\alpha_{wind} \approx 0.030\text{--}0.035$ (3.0% to 3.5% of 10m wind speed).
  - $\mathbf{R}(\theta)$: Coriolis deflection matrix ($0^\circ\text{ to }15^\circ$ right of wind in Northern Hemisphere).
- $K_h$: Horizontal turbulent diffusion coefficient ($1\text{ to }20\text{ m}^2/\text{s}$).
- $\vec{\xi} \sim \mathcal{N}(0, \mathbf{I})$: Gaussian stochastic perturbation vector.

### 3.2 Backward Integration (Hindcasting)
To find the origin, time is reversed ($dt \rightarrow -dt$) from the SAR observation timestamp $t_{sat}$. A Monte Carlo ensemble of $N = 500\text{--}2000$ particles generates an expanding spatial uncertainty cone backward in time.

---

## 4. AIS Kinematic Integrity & Vessel Attribution

### 4.1 Kinematic Feasibility Checks
For consecutive AIS message transmissions $p_i = (\phi_i, \lambda_i, t_i)$ and $p_{i+1} = (\phi_{i+1}, \lambda_{i+1}, t_{i+1})$:
- Geodesic distance $D(p_i, p_{i+1})$ is calculated via the Vincenty or Haversine formulation.
- Apparent velocity:
  $$v_{app} = \frac{D(p_i, p_{i+1})}{t_{i+1} - t_i}$$
- If $v_{app} > v_{max}$ (e.g. $> 35\text{--}40\text{ knots}$ for cargo/tankers), an **AIS Teleportation / Spoofing Anomaly** is recorded.

### 4.2 Multi-Factor Suspicion Index ($)
Candidate vessels intersecting the dispersion cone are evaluated via the normalized multi-criteria weighting implemented in `src/ais_analysis/suspicion_scorer.py`:

87184S = w'_p \cdot S_{\text{prox}} + w'_t \cdot S_{\text{type}} + w'_g \cdot S_{\text{gap}} + w'_d \cdot S_{\text{draft}}87184

where weights are normalized to sum to 1.0:
87184w'_k = rac{w_k}{\sum_{j \in \{p, t, g, d\}} w_j} \quad \text{with defaults: } w_p = 0.35, \, w_t = 0.25, \, w_g = 0.25, \, w_d = 0.1587184

#### Implemented Scoring Components:
1. **Spatiotemporal Proximity Component ({\text{prox}}$)**:
   87184S_{\text{prox}} = 0.60 \cdot S_{\text{spatial}} + 0.40 \cdot S_{\text{temporal}}87184
   - **Spatial Compatibility ({\text{spatial}}$)**:
     87184S_{\text{spatial}} = \max\left(0, \, 1 - rac{d_{\min}}{d_{\max}}\right)87184
     where {\min}$ is the minimum geodesic distance (nm) from the vessel track to the hindcast release centroid ({\max} = 5.0\text{ nm}$). If {\min} > d_{\max}$, {\text{spatial}} = 0.0$.
   - **Temporal Compatibility ({\text{temporal}}$)**:
     87184S_{\text{temporal}} = \max\left(0, \, 1 - rac{|t_{\text{transit}} - t_{\text{release}}|}{\Delta t_{\max}}\right)87184
     bounded by the estimated hindcast release window ($\Delta t_{\max} = 12.0\text{ hours}$).

2. **Vessel Prior Component ({\text{type}}$)**:
   - {\text{type}} = 1.00$ for Crude Oil Tanker or Chemical Tanker.
   - {\text{type}} = 0.60$ for General Cargo / Container vessel.
   - {\text{type}} = 0.30$ for other vessel categories or unspecified types.

3. **AIS Integrity Component ({\text{gap}}$)**:
   - {\text{gap}} = 1.00$ if an AIS transmission gap $> 1800\text{ s}$ (\text{ min}$) occurs within .0\text{ nm}$ of the hindcast release centroid.
   - {\text{gap}} = 0.50$ if an AIS transmission gap occurs outside the immediate spill vicinity.
   - {\text{gap}} = 0.00$ for continuous, unimpeded broadcast.

4. **Draft Reduction Component ({\text{draft}}$)**:
   - {\text{draft}} = 1.00$ if reported vessel draft drops by $\Delta \text{draft} < -0.5\text{ m}$ along the track (indicative of bulk liquid cargo discharge or deballasting).
   - {\text{draft}} = 0.20$ if vessel draft is unchanged or changes within normal operational tolerance ($\ge -0.5\text{ m}$).

#### Gating & Exoneration Rules:
* **Strict Spatial Disjointness**: If {\text{spatial}} = 0.0$, attribution is gated to **`EXONERATED_SPATIALLY_DISJOINT`** regardless of vessel prior or transponder gaps.
* **Strict Temporal Incompatibility**: If {\text{temporal}} = 0.0$, attribution is gated to **`EXONERATED_TEMPORALLY_INCOMPATIBLE`**.
* **Classification Thresholds**:
  -  \ge 0.70$ and {\text{spatial}} \ge 0.80$ $\implies$ **`PRIMARY_SUSPECT`**
  -  \ge 0.45$ $\implies$ **`PLAUSIBLE_CANDIDATE`**
  -  < 0.45$ $\implies$ **`INSUFFICIENT_EVIDENCE_EXONERATED`**

---

## 5. Legal Standards for Evidentiary Briefs

Attribution outputs are formatted to meet forensic standards under **MARPOL 73/78 Annex I** (Prevention of Pollution by Oil) and **UNCLOS Article 220**:
1. **Cryptographic Integrity**: SHA-256 checksums on all source SAR rasters and AIS NMEA/JSON extracts.
2. **Chain of Custody Log**: Immutable timeline of data acquisition, calibration, and inference execution.
3. **Statistical Confidence**: Quantitative error bounds on drift backward trajectories and AIS matching probabilities.
