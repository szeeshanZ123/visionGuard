# VisionGuard AI — Supplementary Dataset Specification: RDD2022 Japan

## 1. Overview & Provenance

To resolve the severe class collapse observed on **`D10_transverse_crack` (0.0% recall)** and the constrained detection confidence on thin **`D00_longitudinal_crack`**, VisionGuard AI incorporates the **Japan subset of the Road Damage Dataset 2022 (RDD2022)** as supplementary training and validation data.

- **Official Repository**: [Sekimoto Lab / RoadDamageDetector (GitHub)](https://github.com/sekilab/RoadDamageDetector)
- **Repository DOI / Source**: [Figshare: 10.6084/m9.figshare.21431547](https://api.figshare.com/v2/articles/21431547)
- **Archive Name**: `RDD2022_released_through_CRDDC2022.zip` containing `Japan.zip`
- **Citation**: Arya, D., Maeda, H., Ghosh, S. K., Toshniwal, D., & Sekimoto, Y. (2022). *RDD2022: A multi-national image dataset for automatic Road Damage Detection.* IEEE BigData 2022 / Geoscience Data Journal (2024).
- **Licensing & Permitted Use**: **Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)**. Free adaptation, modification, and commercial/educational usage provided proper attribution is given.

---

## 2. Class Taxonomy & Conversion Protocol

RDD2022 Japan uses standard Pascal VOC XML annotations paired with JPEG imagery. Annotations are parsed, filtered, and converted to YOLO normalized format (`class_id x_center y_center width height`):

| VOC Code | Class ID | Canonical Label | Distress Description | Role in Supplementary Dataset |
| :---: | :---: | :--- | :--- | :--- |
| `D00` | `0` | `D00_longitudinal_crack` | Linear crack parallel to traffic | Supplements thin crack features (~4,000 instances) |
| `D10` | `1` | `D10_transverse_crack` | Linear crack perpendicular to traffic | **Primary motivation: supplements >3,000 instances (recovering from 44 instances in India subset)** |
| `D20` | `2` | `D20_alligator_crack` | Interconnected fatigue mesh | Preserves multi-mesh defect learning |
| `D40` | `3` | `D40_pothole` | Localized depression or cavity | Preserves asphalt cavity detection |

### Non-Target Classes Filtered
The VOC XMLs also include non-distress features (`D43`: repair patch, `D44`: blurred line, `D50`: blurred crosswalk). These are explicitly filtered out to maintain VisionGuard AI's strict 4-class taxonomy.

---

## 3. Strict Quarantine & Leakage Prevention Protocol

1. **Held-Out Test Set Quarantine**:
   - The **1,200-image Indian held-out test split** is strictly quarantined.
   - Zero Japanese images are added to the test split.
   - The test set evaluates whether multi-country training generalizes successfully to Indian road conditions.
2. **Local Evaluation Benchmark Quarantine**:
   - The **16-image local benchmark** (`data/evaluation_benchmark/`) remains completely untouched for local regression sanity tests.
3. **Sequence-Aware Grouping**:
   - Japanese dashcam frames are grouped into **contiguous sequence blocks of 50 frames**.
   - Whole blocks are assigned to `train` (80%) and `val` (20%) using deterministic shuffling (`seed=42`).
   - Adjacent video frames are strictly prevented from crossing split boundaries.

---

## 4. Projected Multi-Country Dataset Statistics

| Defect Class | Baseline India Train Instances | Supplementary Japan Instances | Total Combined Training Instances | Factor Increase |
| :--- | :---: | :---: | :---: | :---: |
| `D00_longitudinal_crack` | 1,050 | ~3,200 | **~4,250** | ~4.0x |
| `D10_transverse_crack` | **44** ⚠️ | **~2,400** | **~2,444** | **~55.5x** |
| `D20_alligator_crack` | 1,436 | ~2,100 | **~3,536** | ~2.5x |
| `D40_pothole` | 2,232 | ~1,100 | **~3,332** | ~1.5x |
| **Total Defect Instances** | **4,762** | **~8,800** | **~13,562** | **~2.85x** |

This resolves the critical 1% scarcity of `D10`, boosting its training representation to a healthy ~18% of all instances.

