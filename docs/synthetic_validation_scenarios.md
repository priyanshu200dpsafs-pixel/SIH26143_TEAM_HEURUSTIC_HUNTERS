# Synthetic AIS Benchmark & Attribution Engine Validation Scenarios

## 1. Executive Summary & Objective

The purpose of synthetic AIS generation is **NOT** to provide easy confirmation by manually hardcoding a single suspicious tanker, but rather to subject the trajectory hindcasting and attribution engine to rigorous, adversarial stress-testing.

To prevent evaluation bias and circular reasoning:
* **Strict Ground-Truth Isolation**: The ground-truth responsible vessel, release timestamp, and deliberate transponder anomalies must be recorded in an isolated metadata file that is strictly hidden from the attribution scoring algorithm.
* **Adversarial Benchmark**: The attribution engine must discover the true culprit purely from kinematic trajectory backtracking, ocean drift cones, and transponder consistency scoring.

---

## 2. Seven Mandatory Benchmark Scenarios

| Scenario # | Scenario Name | Ground Truth State | Observed AIS Signature | Attribution Engine Target Outcome |
| :--- | :--- | :--- | :--- | :--- |
| **1** | **True Source + Continuous AIS** | Culprit vessel discharged oil during normal navigation | Complete, continuous AIS transponder broadcast with no gaps; trajectory passes directly through hindcast spill origin at release time | Primary suspect ranked #1; high spatial-temporal proximity; anomaly score = 0 (covert operational discharge while broadcasting) |
| **2** | **True Source + AIS Gap** | Culprit vessel deliberately disabled AIS transponder during discharge | Transponder abruptly cuts off 30 min before entering spill zone and re-appears 30 min after passing; straight-line dead reckoning crosses spill origin | Primary suspect ranked #1; high spatial-temporal intersection of dead-reckoned track; high anomaly score (>0.8) for transponder blackout |
| **3** | **Innocent Vessel + AIS Gap** | Innocent ship experienced genuine radio shadow, antenna failure, or satellite outage elsewhere | AIS gap occurs 15–30 nautical miles outside the backwards drift uncertainty cone | Exonerated; spatial-temporal intersection test fails; high transponder gap score must NOT trigger false attribution |
| **4** | **Two Plausible Vessels** | Two separate vessels (e.g., a cargo ship and an oil tanker) transited adjacent corridors near the spill release window | Both vessels have trajectories intersecting the uncertainty cone within ±1.5 hours of estimated release | Disambiguation required: engine must differentiate using cargo type (Tanker vs Container), vessel draft changes, and hydrodynamic drift probabilities; confidence score split |
| **5** | **No Compatible Vessel (Ghost Ship)** | Oil discharged by a completely non-broadcasting unflagged vessel ("dark fleet" with no AIS transmission) | Zero AIS tracks intersect the hindcast drift cone at release time | Attribution engine outputs `UNATTRIBUTED / UNIDENTIFIED VESSEL`; zero innocent vessels falsely accused |
| **6** | **Impossible Kinematics** | Vessel transponder spoofed or reporting erratic positions (GPS jumps, impossible speeds) | Reported positions show speed-over-ground $>45\text{ knots}$ or teleportation across the Mediterranean | Flagged by kinematic filter as `SPOOFED / INVALID DATA`; rejected from hindcast matching; excluded from innocent candidate list |
| **7** | **Nearby but Incompatible Vessel** | Innocent vessel passed very close geographically, but at a temporally incompatible timestamp (e.g., 6 hours after slick formed) | Perfect AIS broadcast, physically near current slick location, but outside the backward-drift temporal release window | Exonerated; physical backward-drift physics proves slick was already 12 nm downstream when vessel arrived |

---

## 3. Evaluation Metrics

For any candidate attribution algorithm evaluated against these 7 scenarios, the following metrics are mandatory:
1. **Attribution Precision & Recall**: Accuracy of identifying true source vs false positive accusations.
2. **Exoneration Specificity**: Rate of correctly exonerating vessels in Scenarios 3, 5, 6, and 7.
3. **Anomaly Discrimination**: Ability to decouple innocent equipment outages (Scenario 3) from deliberate discharge cover-ups (Scenario 2).
4. **Calibration Confidence**: Calibrated posterior probability reflecting ambiguous evidence (Scenario 4) or unobserved sources (Scenario 5).
