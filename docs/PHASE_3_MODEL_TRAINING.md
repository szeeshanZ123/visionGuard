# VisionGuard AI — Phase 3.4: YOLOv8 Nano Training & Evaluation Protocol

**Document Status:** Approved Engineering Specification  
**Project Phase:** Phase 3.4 — Model Training, Validation, and Held-Out Test Evaluation  
**Execution Platform:** Google Colab (Tesla T4 GPU, 15 GB VRAM)  
**Planned Model:** YOLOv8 Nano (`yolov8n.pt`)  
**Target Dataset:** Road Damage Dataset 2022 (RDD2022 India Subset)  
**Target Classes:** `0: D00_longitudinal_crack`, `1: D10_transverse_crack`, `2: D20_alligator_crack`, `3: D40_pothole`  
**Version:** 1.0  

---

## 1. Executive Summary & Scope

This document specifies the training, validation, error analysis, and held-out test evaluation workflow for training **YOLOv8 Nano (`yolov8n`)** on the prepared **RDD2022 India subset** inside Google Colab.

Following the successful completion of Phase 3.3 (India subset extraction, Pascal VOC to YOLO normalization, sequence block partitioning, and visual ground-truth verification), Phase 3.4 establishes the technical protocol to:
1. Restore and verify the prepared dataset and `data.yaml` in Google Colab.
2. Initialize pretrained `yolov8n.pt` for transfer learning with fixed seed reproducibility (`seed=42`).
3. Train under conservative hardware settings (`imgsz=640`, `batch=8`, `epochs=30`, `patience=10`).
4. Perform honest class-wise evaluation with explicit handling of severe class imbalance (notably transverse crack `D10` scarcity).
5. Quarantined evaluation of the held-out test set (`1,200 images`) only after checkpoint selection is finalized.
6. Export the validated best checkpoint (`best.pt`, ~6.2 MB) for subsequent Phase 4 Flask serving.

> [!IMPORTANT]
> **Strict Phase Guardrails:**  
> - No fake or simulated accuracy metrics. Results must reflect authentic validation and test runs.
> - The held-out test set (`1,200 images`) is quarantined: it must **never** be used for gradient descent, hyperparameter tuning, or early stopping.
> - Model confidence reflects statistical prediction likelihood, **not structural safety or pavement distress depth**.
> - Bounding boxes provide spatial defect localization, **not millimeter physical crack width**.

---

## 2. Hardware & Software Environment

All training runs are executed inside a Google Colab GPU runtime:

| Component | Specification | Diagnostic Command / Source |
| :--- | :--- | :--- |
| **GPU Model** | **NVIDIA Tesla T4** (or available Colab GPU) | `!nvidia-smi` |
| **Dedicated VRAM** | **15.0 to 16.0 GB GDDR6** | `torch.cuda.get_device_properties(0).total_memory` |
| **Host System RAM** | **12.7 GB** (Standard Colab runtime) | `cat /proc/meminfo` |
| **Active Storage** | **/content (NVMe SSD)**, ~75–100 GB free | `shutil.disk_usage('/content')` |
| **Python Version** | **Python 3.10 / 3.11** | `sys.version` |
| **Deep Learning Framework** | **PyTorch 2.1+ with CUDA 12.x** | `torch.__version__` |
| **Object Detection Framework** | **Ultralytics 8.1+** | `ultralytics.__version__` |
| **Image Processing** | **OpenCV 4.x / Pillow 10+** | `cv2.__version__`, `PIL.__version__` |

---

## 3. Dataset Baseline & Split Verification

The training environment ingests the RDD2022 India subset prepared during Phase 3.3.

### 3.1 Image Counts and Partitioning

| Partition | Image Count | Share (%) | Purpose in Pipeline |
| :--- | :---: | :---: | :--- |
| **Training Split (`train`)** | **5,356** | 69.5% | Weight updates via backpropagation. |
| **Validation Split (`val`)** | **1,150** | 14.9% | Epoch-wise validation loss, checkpoint selection (`best.pt`), early stopping. |
| **Held-Out Test Split (`test`)** | **1,200** | 15.6% | **Strictly quarantined.** Evaluated only once after training is finalized. |
| **Total** | **7,706** | **100.0%** | Full verified RDD2022 India training corpus. |

### 3.2 Dataset Configuration (`data.yaml`)

```yaml
path: /content/visionguard_dataset
train: images/train
val: images/val
test: images/test

names:
  0: D00_longitudinal_crack
  1: D10_transverse_crack
  2: D20_alligator_crack
  3: D40_pothole
```

### 3.3 Verification Assertions Enforced in Notebook:
1. `data.yaml` exists and all directory paths (`images/{train,val,test}` and `labels/{train,val,test}`) resolve.
2. Every image has an identically named label file (`.txt`), including sound pavement images (empty 0-byte label files).
3. All three sets are **strictly disjoint**:
   $$\text{train} \cap \text{val} = \emptyset, \quad \text{train} \cap \text{test} = \emptyset, \quad \text{val} \cap \text{test} = \emptyset$$

---

## 4. Class Distribution & Critical Imbalance Analysis

### 4.1 Authoritative Training Set Distribution

The RDD2022 India training set contains **6,831 annotated damage instances** distributed across classes:

| Class ID | Class Label | Distress Category | Annotations (Total) | Percentage Share | Expected Detection Behavior |
| :---: | :--- | :--- | :---: | :---: | :--- |
| `0` | `D00_longitudinal_crack` | Longitudinal Crack | 1,555 | 22.8% | Good representation; reliable detection along wheel paths. |
| `1` | `D10_transverse_crack` | Transverse Crack | **68** | **1.0%** | **Severe scarcity.** Constrained precision and recall expected. |
| `2` | `D20_alligator_crack` | Alligator Crack | 2,021 | 29.6% | High representation; strong detection of fatigue cracking. |
| `3` | `D40_pothole` | Pothole | **3,187** | **46.7%** | **Dominant class.** Exceptional density for road cavity detection. |
| — | **Total** | — | **6,831** | **100.0%** | — |

### 4.2 Engineering Handling of `D10` Scarcity
- **Root Cause:** In the Indian road network sampled by RDD2022 (urban and national highways in Delhi, Gurugram, Haryana), transverse thermal shrinkage cracks rarely occur compared to load-induced alligator cracking and monsoon potholes.
- **Reporting Rule:** Transverse crack performance must be reported explicitly on its own row in all evaluation tables. We do not hide `D10` performance behind macro-averaged mAP.
- **No Synthetic Fabrication:** We do not duplicate images or invent fake bounding boxes. The model will be trained on the authentic ground-truth distribution.
- **Future Mitigation (Phase 3.5 / Future Iterations):** If transverse crack detection is deemed a commercial requirement, supplementary `D10` instances from `RDD2022_Japan.zip` (~3,000 instances) will be incorporated in a subsequent multi-country fine-tuning cycle.

---

## 5. Data Leakage & Sequence Splitting Limitations

### 5.1 Heuristic Used in Phase 3.3
To prevent temporal data leakage from sequential dashcam video frames captured at 1 frame per second, the Phase 3.3 notebook grouped consecutive filename stems into **blocks of 50 images**, shuffling whole blocks into `train`, `val`, and `test` splits using a fixed random seed (`seed=42`).

### 5.2 Documented Limitation
While block-based splitting is vastly superior to naive uniform random shuffling (which leaks adjacent frames between train and test), **it is an empirical heuristic**:
- The filename index in RDD2022 does not strictly reset at the start of a new video session.
- A 50-frame block may occasionally straddle the transition between two driving sessions, or a single long continuous road survey may span several consecutive blocks.
- Therefore, some background road texture similarities may still exist across block boundaries.

### 5.3 Safer Grouping Recommendation for Future Iterations
If camera metadata, GPS coordinates, or explicit video route IDs are released by Sekimoto Lab:
- Splits should be partitioned by **Route / Drive Session ID** or **Geographical Zone** (e.g. northern routes vs. southern routes).
- Until explicit route metadata is available, block-based partitioning with a 50-frame window represents the most conservative, leakage-resistant strategy achievable on the public dataset.

---

## 6. Training Configuration & Hyperparameters

Training executes using the following audited hyperparameters:

```python
TRAINING_CONFIG = {
    'model': 'yolov8n.pt',      # Official pretrained Nano weights (3.2M params)
    'data': '/content/visionguard_dataset/data.yaml',
    'epochs': 30,               # Initial training budget
    'imgsz': 640,               # Standard input tensor resolution
    'batch': 8,                 # Conservative batch size (prevents CUDA OOM on T4)
    'patience': 10,             # Early stopping trigger if val loss plateaus
    'seed': 42,                 # Deterministic reproducibility
    'device': 0,                # GPU device 0
    'workers': 2,               # Dataloader worker subprocesses
    'project': '/content/visionguard_runs',
    'name': 'yolov8n_rdd_india_exp1',
    'exist_ok': True,
    'verbose': True,
    'plots': True,              # Automatically generate loss curves and confusion matrix
    'save': True,               # Save last.pt and best.pt
    'val': True                 # Run validation at every epoch for best checkpoint selection
}
```

### Justification of Hyperparameters:
- **`yolov8n.pt`:** Only 3.2M parameters. Fine-tuning from COCO pretrained weights provides fast convergence on low data budgets.
- **`batch=8`:** Requires ~2.2 GB VRAM during training, leaving ample headroom on the 15 GB Tesla T4 and preventing Out-of-Memory crashes.
- **`patience=10`:** Prevents overfitting if the validation mAP stops improving after epoch 15–20.

---

## 7. Model Evaluation Protocol & Baseline Metrics

### 7.1 Validation Set vs. Held-Out Test Set

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. During Training (Epochs 1–30):                                      │
│    Validation Split (1,150 images) evaluated at every epoch.           │
│    Weights with highest validation mAP@0.5 saved as best.pt.           │
├────────────────────────────────────────────────────────────────────────┤
│ 2. Checkpoint Selection Finalized:                                     │
│    Training finishes; best.pt is frozen and selected.                  │
├────────────────────────────────────────────────────────────────────────┤
│ 3. Held-Out Test Evaluation (ONCE):                                    │
│    Quarantined Test Split (1,200 images) evaluated with best.pt.       │
│    Results recorded in final report without adjusting settings.        │
└────────────────────────────────────────────────────────────────────────┘
```

### 7.2 Target Acceptance Metrics

| Metric | Target Baseline | Minimum Engineering Threshold | Notes |
| :--- | :---: | :---: | :--- |
| **mAP@0.5 (Overall)** | **$\ge 0.50$** | $\ge 0.40$ | Mean Average Precision at IoU threshold 0.5. |
| **mAP@0.5:0.95** | **$\ge 0.25$** | $\ge 0.20$ | Stringent multi-threshold COCO metric. |
| **Overall Precision** | **$\ge 0.60$** | $\ge 0.50$ | Minimizes false positive alarms on sound pavement. |
| **Overall Recall** | **$\ge 0.55$** | $\ge 0.45$ | Ensures high defect capture rate. |
| **Pothole (`D40`) mAP@0.5** | **$\ge 0.65$** | $\ge 0.55$ | High expectation due to 46.7% label density. |
| **Transverse (`D10`) mAP@0.5**| **Documented Honestly** | N/A | Expected low ($\le 0.20$) due to extreme scarcity (68 instances). |

---

## 8. Artifact Management & Deployment Workflow

### 8.1 Generated Artifacts
At the conclusion of Phase 3.4 execution in Google Colab:
- **Trained Weights:** `/content/visionguard_runs/yolov8n_rdd_india_exp1/weights/best.pt` (~6.2 MB).
- **Evaluation Summary:** `/content/visionguard_runs/yolov8n_rdd_india_exp1/experiment_summary.json`.
- **Training Curves:** `results.png` (Box loss, Class loss, DFL loss, mAP progression).
- **Confusion Matrix:** `confusion_matrix.png` and `confusion_matrix_normalized.png`.

### 8.2 Google Drive Backup
The notebook automatically copies artifacts to:
`/content/drive/MyDrive/VisionGuard_Artifacts/best.pt`  
`/content/drive/MyDrive/VisionGuard_Artifacts/experiment_summary.json`

### 8.3 Ingestion into Local VisionGuard AI Repository
For Phase 4 (Flask backend integration):
1. Download `best.pt` from Google Drive (or via `files.download()`).
2. Move `best.pt` to the local repository path:  
   `visionGuard/ai/models/best.pt`
3. Verify that `best.pt` is ignored by Git (`.gitignore` enforces `ai/models/*` exclusion while preserving `.gitkeep`).

---

## 9. Engineering Guardrails & Disclaimers

1. **Structural Safety Disclaimer:** VisionGuard AI is an automated inspection support tool. Computer vision detections from photographic road images **cannot certify structural roadway stability, sub-base integrity, or traffic bearing capacity**.
2. **Confidence vs. Severity:** Detection confidence reflects model classification probability ($0.0 \text{ to } 1.0$), **not pavement failure severity, cavity depth, or road danger level**.
3. **Bounding Dimensions vs. Crack Width:** Bounding boxes $[xmin, ymin, xmax, ymax]$ measure bounding rectangular extents in pixels. **A bounding box cannot measure true physical crack width (e.g. 1 mm vs. 5 mm)** without physical ground-plane calibration and camera intrinsics.

---

## 10. Step-by-Step Reproduction Guide

To run Phase 3.4 in Google Colab:

1. Open Google Colab at [colab.research.google.com](https://colab.research.google.com).
2. Upload [`VisionGuard_Phase_3_4_YOLOv8_Training.ipynb`](file:///c:/Users/ASUS/OneDrive/visionGuard/VisionGuard_Phase_3_4_YOLOv8_Training.ipynb).
3. Switch runtime: **Runtime** > **Change runtime type** > **T4 GPU** > **Save**.
4. Run cells sequentially:
   - **Step 1 & 2:** Verifies GPU and installs dependencies.
   - **Step 2.5 & 3:** Diagnoses backup archive, restores dataset into `/content/visionguard_dataset`, and verifies split integrity.
   - **Step 4:** Audits training set class distribution.
   - **Step 5 & 6:** Initializes YOLOv8 Nano and executes 30 training epochs (~35–45 min).
   - **Step 7 & 8:** Displays loss curves and evaluates `best.pt` on validation split.
   - **Step 9 & 10:** Runs final evaluation on the quarantined held-out test split and visualizes predictions.
   - **Step 11:** Saves `best.pt` to Google Drive for local download.
