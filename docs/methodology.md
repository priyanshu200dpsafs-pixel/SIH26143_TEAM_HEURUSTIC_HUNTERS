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

### 4.2 Multi-Factor Suspicion Index ($S$)
Candidate vessels intersecting the dispersion cone are evaluated via multi-criteria weighting:
$$S = w_{prox} \cdot \left(1 - \frac{d_{origin}}{d_{max}}\right) + w_{type} \cdot C_{vessel} + w_{gap} \cdot \mathbf{1}_{AIS\_blackout} + w_{draft} \cdot \Delta_{draft}$$

- $w_{prox} = 0.35$: Minimum distance between vessel track and estimated release centroid.
- $w_{type} = 0.25$: Vessel type risk weight (Crude Oil Tanker = 1.0, Chemical Tanker = 0.8, Cargo = 0.4, Pleasure Craft = 0.05).
- $w_{gap} = 0.25$: Transponder blackout penalty during transit through the spill zone.
- $w_{draft} = 0.15$: Normalized draft reduction indicating potential liquid cargo or ballast discharge.

---

## 5. Legal Standards for Evidentiary Briefs

Attribution outputs are formatted to meet forensic standards under **MARPOL 73/78 Annex I** (Prevention of Pollution by Oil) and **UNCLOS Article 220**:
1. **Cryptographic Integrity**: SHA-256 checksums on all source SAR rasters and AIS NMEA/JSON extracts.
2. **Chain of Custody Log**: Immutable timeline of data acquisition, calibration, and inference execution.
3. **Statistical Confidence**: Quantitative error bounds on drift backward trajectories and AIS matching probabilities.
