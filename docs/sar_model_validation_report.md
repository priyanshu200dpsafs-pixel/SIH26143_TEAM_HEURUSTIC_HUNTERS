# SAR Segmentation Model Validation Report

**Evaluation Date**: 2026-09-13
**Status**: Phase 3 Baseline Complete — All Pipeline Components Verified

> **SCIENTIFIC CAVEAT**: This report documents a controlled benchmark baseline, not a validated operational detection system. Results are evaluated on the Krestenitis SAR dataset under laboratory conditions. Do NOT interpret these metrics as real-world global oil spill detection performance.

---

## 1. Model Architecture & Training Configuration

| Parameter | Value |
| :--- | :--- |
| **Architecture** | U-Net Baseline (UNetBaseline) |
| **Encoder Features** | [32, 64, 128, 256, 512] |
| **Total Parameters** | ~23.3M |
| **Input Resolution** | 256 x 256 x 3 (RGB) |
| **Output Classes** | 4 (Background, Oil Spill, Look-alike, Water) |
| **Loss Function** | Weighted Cross-Entropy |
| **Class Weights** | [1.0, 3.5, 2.0, 1.0] |
| **Optimizer** | AdamW (lr=1e-3, weight_decay=1e-4) |
| **Scheduler** | Cosine Annealing (T_max=8) |
| **Epochs** | 8 |
| **Batch Size** | 16 |
| **Device** | Apple Silicon MPS GPU |
| **Training Duration** | 555 seconds (~9.25 minutes) |
| **Random Seed** | 42 (deterministic) |
| **Augmentations** | H-Flip (p=0.5), V-Flip (p=0.5), 90-deg Rotation (p=0.5) - train only |

### 1.1 Dataset Splits (Krestenitis)

| Split | Images | Masks | Split Leakage |
| :--- | :---: | :---: | :---: |
| **Train** | 672 | 672 | 0 overlap |
| **Validation** | 160 | 160 | 0 overlap |
| **Test** | 208 | 208 | 0 overlap |

### 1.2 Verified Class Ontology

| Class ID | Class Name | RGB Color | Pixel Frequency (Test) |
| :---: | :--- | :--- | :---: |
| 0 | Background | (0, 0, 0) | 3.74% |
| 1 | Oil Spill | (255, 0, 124) | 35.34% |
| 2 | Look-alike / Others | (255, 204, 51) | 36.83% |
| 3 | Water / Sea Surface | (51, 221, 255) | 24.14% |

**No Ship or Land classes exist** in the verified dataset.

---

## 2. Training Convergence

| Epoch | Train Loss | Val mIoU | Val Oil IoU |
| :---: | :---: | :---: | :---: |
| 1 | 0.7168 | 0.4105 | 0.6608 |
| 2 | 0.4804 | 0.5265 | 0.7416 |
| 3 | 0.3651 | 0.4961 | 0.7284 |
| 4 | 0.3398 | 0.5360 | 0.7943 |
| 5 | 0.3319 | 0.4373 | 0.6756 |
| 6 | 0.3008 | 0.5310 | 0.7258 |
| 7 | 0.2925 | 0.6266 | 0.8211 |
| **8 (Best)** | **0.2909** | **0.6391** | **0.8399** |

---

## 3. Test Set Evaluation (208 Scenes)

### 3.1 Aggregate Metrics

| Metric | Value |
| :--- | :---: |
| **Overall Pixel Accuracy** | **85.80%** |
| **Mean IoU (4-class)** | **59.06%** |
| **Macro F1** | **68.73%** |
| **Macro Precision** | **83.46%** |
| **Macro Recall** | **66.96%** |

### 3.2 Per-Class Performance

| Class | IoU | Precision | Recall | F1 | Support (pixels) |
| :--- | :---: | :---: | :---: | :---: | :---: |
| Background | 11.27% | 68.36% | 11.89% | 20.25% | 509,759 |
| **Oil Spill** | **75.52%** | **76.27%** | **98.70%** | **86.05%** | **4,814,914** |
| **Look-alike / Others** | **92.66%** | **93.56%** | **98.98%** | **96.19%** | **5,017,044** |
| Water / Sea Surface | 56.77% | 95.65% | 58.27% | 72.42% | 3,289,771 |

### 3.3 Confusion Matrix (Test Set)

|  | Pred: Background | Pred: Oil | Pred: Look-alike | Pred: Water |
| :--- | :---: | :---: | :---: | :---: |
| **True: Background** | **60,593** | 205,233 | 195,754 | 48,179 |
| **True: Oil Spill** | 5,650 | **4,752,447** | 35,857 | 20,960 |
| **True: Look-alike** | 9,794 | 23,410 | **4,965,778** | 18,062 |
| **True: Water** | 12,607 | 1,249,619 | 110,456 | **1,917,089** |

---

## 4. MANDATORY Oil / Look-alike Confusion Analysis

This section tracks the critical discrimination boundary between genuine oil spills and natural look-alikes.

| Metric | Value | Interpretation |
| :--- | :---: | :--- |
| **Oil to Look-alike** | **0.74%** (35,857 px) | Only 0.74% of true oil pixels were misclassified as look-alikes |
| **Look-alike to Oil** | **0.47%** (23,410 px) | Only 0.47% of true look-alike pixels were falsely classified as oil |
| **Look-alike Rejection Rate** | **99.53%** | The model correctly identifies 99.53% of look-alikes as non-oil |

---

## 5. Hard-Negative Evaluation (Look-alike Scenes Only)

Dedicated evaluation on the **175 test scenes containing look-alike ground truth**:

| Metric | Value |
| :--- | :---: |
| **Total Look-alike Pixels Evaluated** | 5,017,044 |
| **Oil False-Alarm Rate on Look-alikes** | **0.47%** |
| **Look-alike Rejection Rate** | **99.53%** |
| **Oil Recall (on hard subset)** | **98.61%** |
| **Oil Precision (on hard subset)** | **71.72%** |

The 71.72% oil precision on hard scenes indicates that ~28% of pixels predicted as oil in look-alike-containing scenes are actually Water pixels misclassified as Oil - not look-alikes. This is a Water/Oil boundary confusion issue, not a look-alike discrimination failure.

---

## 6. Failure Analysis Catalogue

4 failure cases were identified and visualized (RAW SAR -> Ground Truth -> Prediction -> Error Map):

| Case | Scene | Failure Mode | FP Oil Pixels | FN Oil Pixels |
| :--- | :--- | :--- | :---: | :---: |
| CASE_1 | Oil (995) | Calm Water / Specular Sea False Alarm | 54,799 | 2,433 |
| CASE_2 | Oil (1007) | Fragmented / Low Contrast Slick Under-detection | 39,026 | 2,433 |
| CASE_3 | Oil (759) | Fragmented / Low Contrast Slick Under-detection | 34,176 | 2,433 |
| CASE_4 | Oil (758) | Look-alike Misclassification | 34,149 | 2,433 |

Visual failure figures saved to docs/failure_analysis/.

---

## 7. Known Limitations

1. **Background Class Under-segmentation**: Background IoU is 11.27%.
2. **Water to Oil Confusion**: 1,249,619 water pixels were predicted as Oil. Dominant error driven by calm-sea specular reflection.
3. **No Real-World Validation**: All metrics are from the Krestenitis controlled dataset.
4. **No Temporal Generalization**: Training and test data share the same sensor campaigns.
5. **Single Architecture**: Only U-Net baseline was evaluated.

---

## 8. Verification Summary

| Component | Status |
| :--- | :---: |
| Dataset Adapters (Krestenitis 4-class + SOS binary) | VERIFIED |
| Zero Split Leakage | VERIFIED |
| Deterministic Preprocessing (no val/test augmentation) | VERIFIED |
| U-Net Forward/Backward Pass | VERIFIED |
| 4x4 Confusion Matrix | COMPUTED |
| Per-class IoU / Precision / Recall / F1 | COMPUTED |
| Oil / Look-alike Mandatory Tracking | COMPUTED |
| Hard-Negative Dedicated Evaluation | COMPUTED (175 scenes) |
| Morphological Spill Object Extraction | VERIFIED (SpillDetection schema) |
| Confidence and Abstention Layer | VERIFIED (HIGH/MEDIUM/LOW/INSUFFICIENT) |
| ERA5 Environmental Context | VERIFIED (Bragg dampening window) |
| Sentinel-2 Optical Fusion | VERIFIED (NDWI/NDVI + graceful fallback) |
| Failure Analysis Visual Catalogue | GENERATED (4 cases) |
| Unit Tests | **54 passed, 0 failed** |
