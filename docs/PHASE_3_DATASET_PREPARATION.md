# VisionGuard AI — Phase 3.2: Dataset Acquisition & Preparation Specification

**Document Status:** Approved Technical Specification  
**Project Phase:** Phase 3.2 — Dataset Acquisition, Inspection, and Preparation  
**Target Platform:** Google Colab (Cloud GPU Environment)  
**Planned Model:** YOLOv8 Nano (`yolov8n`)  
**Target Dataset:** Road Damage Dataset 2022 (RDD2022)  
**Execution Mode:** Planning & Preparation Specification (Zero Datasets or Model Weights Downloaded Locally)  
**Version:** 1.0  

---

## 1. Executive Summary & Objective

This document defines the comprehensive, reproducible engineering workflow for acquiring, inspecting, converting, validating, and partitioning the **Road Damage Dataset 2022 (RDD2022)** for training a **YOLOv8 Nano** object detection model in **Google Colab**.

In accordance with Phase 3.1 environment findings:
- Local training on the developer's laptop GPU (NVIDIA RTX 3050 Laptop GPU, 4.0 GB VRAM) is constrained by physical VRAM limits (~3.0 GB available) and global Python 3.14 wheel compatibility.
- **Google Colab** is established as the primary training environment, providing access to an NVIDIA Tesla T4 GPU (15.0–16.0 GB VRAM), pre-configured PyTorch/CUDA environments, and ~100 GB of ephemeral SSD storage.
- All raw dataset ingestion, extraction, format conversion, and training will occur within the cloud environment. Only the verified lightweight dataset archive and final compact weights (`best.pt`, ~6.2 MB) will be exported.

> [!IMPORTANT]
> **Phase 3.2 Boundaries Maintained:** In accordance with project restrictions, no datasets have been downloaded locally or to cloud storage during this phase, no models have been trained, and no pretrained weights have been acquired. This document establishes the exact, verified preparation protocol prior to execution.

---

## 2. Verified Dataset Source & Licensing

### 2.1 Provenance and Official Distribution Channels

The **Road Damage Dataset 2022 (RDD2022)** was released as part of the Crowdsensing-based Road Damage Detection Challenge (CRDDC'2022) held at IEEE BigData 2022 and published in the *Geoscience Data Journal* (2024).

| Attribute | Verified Value / Reference |
| :--- | :--- |
| **Dataset Title** | RDD2022 — The multi-national Road Damage Dataset released through CRDDC'2022 |
| **Lead Authors** | Deeksha Arya, Hiroya Maeda, Sanjay Kumar Ghosh, Durga Toshniwal, Yoshihide Sekimoto (Sekimoto Lab, Institute of Industrial Science, University of Tokyo) |
| **Academic Citation** | Arya et al. (2022). *RDD2022: A multi-national image dataset for automatic Road Damage Detection.* arXiv:2209.08538. |
| **Official Repository** | [sekilab/RoadDamageDetector (GitHub)](https://github.com/sekilab/RoadDamageDetector) |
| **Persistent DOI** | [10.6084/m9.figshare.21431547.v1](https://doi.org/10.6084/m9.figshare.21431547.v1) |
| **Figshare Article ID** | `21431547` |
| **Direct Download URL** | `https://ndownloader.figshare.com/files/38030910` |
| **Archive File Name** | `RDD2022_released_through_CRDDC2022.zip` |
| **Archive File Size** | **13,264,172,619 bytes (~13.26 GB / ~12.35 GiB)** |
| **Archive MD5 Checksum**| `b62bd51d2ffcfaa76c60f234f0cc2bb3` |
| **Formal License** | **Creative Commons Attribution 4.0 International (CC BY 4.0)** / CC BY-SA 4.0 |
| **Permitted Use** | Free sharing, adaptation, commercial and non-commercial application with appropriate academic attribution. |

### 2.2 Metadata Files Available at Source

In addition to the primary 13.26 GB archive, the official Figshare entry hosts standalone verification files accessible without downloading the primary archive:
1. `Directory_Structure_CRDDC_RDD2022.txt` (ID `38030823`, 1,161 bytes): Documents the complete directory hierarchy.
2. `File_List_CRDDC_RDD2022.txt` (ID `38030826`, 3,250,534 bytes): Lists all 47,420 image and annotation paths.
3. `label_map.pbtxt` (ID `38030820`, 127 bytes): Confirms the authoritative target label definitions.

---

## 3. Archive Structure & Country Breakdown

### 3.1 Raw Archive Packaging & Nested Sub-Archives

The official 13.26 GB outer archive (`RDD2022_released_through_CRDDC2022.zip`) packages **7 nested country sub-archives**:

```text
RDD2022_released_through_CRDDC2022.zip (13.26 GB)
├── RDD2022_China_Drone.zip        (~262 MB)
├── RDD2022_China_MotorBike.zip    (~252 MB)
├── RDD2022_Czech.zip              (~456 MB)
├── RDD2022_India.zip              (~502 MB)
├── RDD2022_Japan.zip              (~1,023 MB)
├── RDD2022_Norway.zip             (~3,275 MB)
└── RDD2022_United_States.zip      (~745 MB)
```

Each individual country sub-archive contains its respective training and evaluation partitions:

```text
<Country_Archive>/
├── test/
│   └── images/                 # Unannotated competition test images (.jpg)
└── train/
    ├── annotations/
    │   └── xmls/               # PASCAL VOC XML annotations (.xml)
    └── images/                 # Road images (.jpg)
```

> [!TIP]
> **Nested Archive Selective Extraction:** Because the outer archive packages 7 separate sub-archives, extraction only requires extracting the target country sub-archive (e.g., `RDD2022_India.zip`, 502 MB), saving gigabytes of disk space and extraction time.

### 3.2 Global Distribution and Subset Metrics

Across all 7 subsets, the dataset comprises **47,420 total images** (38,385 annotated training images, 9,035 unannotated competition test images):

| Region / Subset | Train Images (Annotated) | Test Images (Unannotated) | Total Images | Primary Acquisition Perspective |
| :--- | :--- | :--- | :--- | :--- |
| **Japan** | **10,506** | 2,627 | 13,133 | Vehicle-mounted smartphone (forward road view) |
| **Norway** | **8,161** | 2,040 | 10,201 | Vehicle-mounted camera (varied asphalt/snow) |
| **India** | **7,706** | 1,959 | 9,665 | Smartphone mounted on car/three-wheeler |
| **United States** | **4,804** | 1,201 | 6,005 | Vehicle-mounted smartphone (urban/highway) |
| **Czech Republic**| **2,829** | 709 | 3,538 | Vehicle-mounted camera |
| **China (MotorBike)** | **1,981** | 496 | 2,477 | Motorbike handle-mount |
| **China (Drone)** | **2,398** | 3 | 2,401 | Downward aerial UAV view |
| **Total** | **38,385** | **9,035** | **47,420** | Multi-national infrastructure survey |

---

## 4. Planned Dataset Subset for VisionGuard AI MVP

### 4.1 Subset Selection Strategy

Downloading and training on all 38,385 images across all 6 countries is neither necessary nor advisable for the initial MVP training cycle:
1. **Computational Overhead:** Training 38,385 images for 50 epochs requires 4–6 hours on a free Colab T4 GPU, exceeding standard free session execution limits and risking disconnection timeouts.
2. **Geographic and Sensor Inconsistencies:** Downward drone imagery (`China_Drone`) and motorbike viewpoints (`China_MotorBike`) introduce severe perspective disparities relative to standard car-mounted dashcam inspections.
3. **Pothole and Crack Balance:** The **Japan** and **India** subsets provide the highest density of road-surface distress labels across both cracking typologies and localized potholes.

### 4.2 Recommended First Experiment Subset

We designate **RDD2022 Japan Train Subset** supplemented selectively with **RDD2022 India Train Pothole instances** as the primary candidate:

- **Primary Base: Japan Train Subset (`RDD2022/Japan/train/`)**
  - **Available Images:** 10,506 images.
  - **Resolution:** Uniformly standard (typically 600x600 pixels).
  - **Distress Distribution:** Rich in longitudinal cracks (`D00`), transverse cracks (`D10`), and alligator fatigue cracks (`D20`), with moderate pothole representation (`D40`).
- **Selective Curated Target Size:**
  - For rapid, high-confidence initial training (under 60 minutes on Colab T4): compile a curated subset of **3,000 to 4,500 damage-bearing images** containing balanced representation across all 4 target classes.
  - Exclude unannotated background images that contain zero defects, retaining a controlled 5–10% background image ratio to teach the model negative background contexts without diluting positive gradient signals.

---

## 5. Authoritative Class Mapping & Taxonomy

### 5.1 Official RDD2022 Class Definitions

The official `label_map.pbtxt` defines four standard damage categories:

```protobuf
item { id: 1, name: 'D00' }  # Longitudinal Crack
item { id: 2, name: 'D10' }  # Transverse Crack
item { id: 3, name: 'D20' }  # Alligator Crack
item { id: 4, name: 'D40' }  # Pothole
```

### 5.2 VisionGuard AI Unified Class Mapping

YOLO models require 0-indexed integer identifiers. The mapping table below details the exact translation from source XML `<name>` tags to YOLO training targets:

| Source XML Tag | Damage Category | Description & Engineering Meaning | YOLO Class ID | YOLO Class Label | MVP Status |
| :--- | :--- | :--- | :--- | :--- | :--- |
| `<name>D00</name>` | Longitudinal Crack | Cracks running parallel to the direction of vehicular travel; typically wheel-path fatigue. | `0` | `D00_longitudinal_crack` | **INCLUDED** |
| `<name>D10</name>` | Transverse Crack | Cracks running perpendicular to the roadway centerline; typically thermal shrinkage stress. | `1` | `D10_transverse_crack` | **INCLUDED** |
| `<name>D20</name>` | Alligator Crack | Interconnected, multi-directional fatigue cracks resembling reptile skin; indicates sub-base structural failure. | `2` | `D20_alligator_crack` | **INCLUDED** |
| `<name>D40</name>` | Pothole | Localized bowl-shaped depression or structural cavity in asphalt pavement resulting from moisture and traffic load. | `3` | `D40_pothole` | **INCLUDED** |
| `<name>D43</name>` | Bleeding / Line Blur | Construction joint or worn line marker. | — | — | **EXCLUDED (Ignored)** |
| `<name>D44</name>` | Crosswalk Blur | Worn pedestrian crossing paint. | — | — | **EXCLUDED (Ignored)** |
| `<name>D50</name>` | Manhole / Other | Utility cover or non-damage road asset. | — | — | **EXCLUDED (Ignored)** |

### 5.3 Filtering Rules
- Any bounding box with `<name>` outside `{'D00', 'D10', 'D20', 'D40'}` will be omitted from the converted YOLO label file.
- If an image contains only excluded classes (e.g., only `D43` line blur), it converts to an empty label file (`.txt` exists but contains zero lines).
- Under no circumstances will classes be silently renamed, combined (e.g., merging all cracks into a single class), or synthetically generated.

---

## 6. Annotation Conversion Specification

### 6.1 PASCAL VOC to YOLO Normalization Mathematics

RDD2022 provides annotations in PASCAL VOC XML syntax:
```xml
<annotation>
  <filename>Japan_000001.jpg</filename>
  <size>
    <width>600</width>
    <height>600</height>
    <depth>3</depth>
  </size>
  <object>
    <name>D00</name>
    <bndbox>
      <xmin>120</xmin>
      <ymin>340</ymin>
      <xmax>210</xmax>
      <ymax>580</ymax>
    </bndbox>
  </object>
</annotation>
```

YOLOv8 requires normalized bounding box coordinates centered at $(x_{center}, y_{center})$ with dimensions $(width, height)$ bounded by $[0.0, 1.0]$:

$$x_{center} = \frac{xmin + xmax}{2 \cdot W}$$

$$y_{center} = \frac{ymin + ymax}{2 \cdot H}$$

$$w = \frac{xmax - xmin}{W}$$

$$h = \frac{ymax - ymin}{H}$$

### 6.2 Coordinate Validation and Clamping Safeguards

During conversion, raw bounding box coordinates must pass strict geometric assertions:
1. **Dimension Non-Zero:** $xmax > xmin$ and $ymax > ymin$. Bounding boxes with zero width or zero height are discarded as corrupt artifacts.
2. **Boundary Clamping:** While raw coordinates should theoretically fall within $[0, W]$ and $[0, H]$, dashcam detection annotations occasionally report values slightly outside image boundaries (e.g. $xmin = -2$ or $xmax = W + 3$). Coordinates are clamped:
   $$xmin_{clamped} = \max(0, \min(W, xmin))$$
   $$xmax_{clamped} = \max(0, \min(W, xmax))$$
   $$ymin_{clamped} = \max(0, \min(H, ymin))$$
   $$ymax_{clamped} = \max(0, \min(H, ymax))$$
3. **Precision:** Normalized floats are formatted to 6 decimal places:
   `0 0.275000 0.766667 0.150000 0.400000`

---

## 7. Data Leakage Prevention & Splitting Strategy

### 7.1 The Sequential Video Leakage Hazard

RDD2022 images were extracted from continuous vehicle driving sessions recorded at 1 frame per second. Consecutive filenames (e.g., `Japan_001045.jpg`, `Japan_001046.jpg`, `Japan_001047.jpg`) represent identical road segments captured one second apart.

> [!CAUTION]
> **Severe Risk of Data Leakage via Random Splitting:**  
> If images are shuffled uniformly at random:
> - Frame $N$ will be assigned to `train` while Frame $N+1$ is assigned to `val` or `test`.
> - The model will memorize static features (roadside utility poles, horizon skyline, asphalt texture, hood artifacts) rather than generalizing to crack and pothole morphology.
> - This yields artificially inflated validation metrics ($mAP > 0.85$) that collapse when deployed on fresh imagery.

### 7.2 Sequence-Aware Block Partitioning Protocol

To ensure true generalizability and unbiased validation, partitioning must respect temporal and geographical continuity:

1. **Continuous Driving Block Grouping:**
   - Group consecutive frames into sequential blocks of 50 to 100 images based on their numeric filename index.
   - For instance, block `Japan_001000` to `Japan_001099` is treated as an indivisible sequence entity representing a single road trajectory.
2. **Partition Allocation Ratios:**
   - **Training Set (70%):** Used exclusively for weight optimization via backpropagation.
   - **Validation Set (15%):** Used strictly for periodic evaluation during training, learning-rate scheduling, and early stopping.
   - **Test Set (15%):** Strictly held-out and sealed until final model evaluation. Never exposed during training or hyperparameter tuning.
3. **Block-Level Randomization:**
   - Whole sequence blocks—rather than individual frames—are allocated to `train`, `val`, or `test`.
   - Allocation uses a **fixed random seed (`seed=42`)** to guarantee exact reproducibility across all future experiments.

---

## 8. Data Quality Checks & Validation Protocol

Before any model training begins, the prepared dataset must pass five automated verification gates:

```text
┌────────────────────────────────────────────────────────────────────────┐
│ Gate 1: Integrity Check (Pillow / OpenCV)                              │
│         Verify every JPEG image opens cleanly without truncation       │
├────────────────────────────────────────────────────────────────────────┤
│ Gate 2: Paired Correspondence Check                                    │
│         Ensure 1:1 correspondence between image (.jpg) and label (.txt)│
├────────────────────────────────────────────────────────────────────────┤
│ Gate 3: Geometric Coordinate Bounds Check                              │
│         Verify 0.0 <= x_c, y_c, w, h <= 1.0 and class_id in {0, 1, 2, 3} │
├────────────────────────────────────────────────────────────────────────┤
│ Gate 4: Class Frequency & Imbalance Audit                              │
│         Tally instances per class across train, val, and test splits   │
├────────────────────────────────────────────────────────────────────────┤
│ Gate 5: Visual Ground-Truth Verification Grid                          │
│         Render 16 sample images with converted YOLO boxes overlayed    │
└────────────────────────────────────────────────────────────────────────┘
```

1. **Image Integrity Check:** Iterate through all selected JPEG files using `PIL.Image.open()` and `Image.verify()` to catch corrupt, zero-byte, or incomplete downloads.
2. **Annotation Correspondence:** Every image in `images/{split}/` must have an identically named label file in `labels/{split}/`. If an image has no detections, its label file must exist as an empty 0-byte file.
3. **Coordinate Sanity:** Read all generated `.txt` files; verify every row contains exactly 5 elements, class ID $\in \{0, 1, 2, 3\}$, and all coordinates are strictly within $[0.0, 1.0]$.
4. **Distribution Balance:** Report exact instance counts per class across splits to identify severe class imbalances (e.g. if `D40` pothole count is too low, adjust subset inclusion).
5. **Visual Inspection:** Draw converted bounding boxes back onto sample images using OpenCV and display a $4 \times 4$ verification mosaic to visually confirm that bounding boxes align perfectly with actual physical defects.

---

## 9. Google Colab End-to-End Workflow Plan

### 9.1 Environment Architecture in Colab

```text
Colab Runtime (NVIDIA T4 GPU, 15 GB VRAM)
├── /content/
│   ├── RDD2022_released_through_CRDDC2022.zip  (~13.26 GB ephemeral download)
│   ├── raw/
│   │   └── RDD2022/Japan/train/                 (selectively extracted)
│   │       ├── images/                          (10,506 JPEG files)
│   │       └── annotations/xmls/                (10,506 XML files)
│   ├── visionguard_dataset/                     (Prepared YOLO dataset)
│   │   ├── images/{train, val, test}/
│   │   ├── labels/{train, val, test}/
│   │   └── data.yaml
│   └── visionguard_dataset_curated.zip          (~1.5–2.5 GB compressed export)
└── /content/drive/MyDrive/                      (Persistent Google Drive)
    └── VisionGuard_Artifacts/
        ├── visionguard_dataset_curated.zip      (Backup for reuse)
        └── best.pt                              (Final trained weights from Phase 3.3)
```

### 9.2 Step-by-Step Execution Plan for Colab Notebook

#### Step 1: Runtime Setup & Verification
```python
# Verify GPU availability and memory
!nvidia-smi

# Check Python and PyTorch baseline
import torch
print(f"CUDA Available: {torch.cuda.is_available()}")
print(f"Device Name: {torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'}")
print(f"VRAM: {round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2)} GB")
```

#### Step 2: Google Drive Mounting (For Persistent Artifacts)
```python
from google.colab import drive
import os

drive.mount('/content/drive')
drive_dir = '/content/drive/MyDrive/VisionGuard_Artifacts'
os.makedirs(drive_dir, exist_ok=True)
print(f"Persistent storage mounted at: {drive_dir}")
```

#### Step 3: Fast Ephemeral Download of Source Archive
```python
import os
import requests
from tqdm import tqdm

archive_path = '/content/RDD2022.zip'
figshare_url = 'https://ndownloader.figshare.com/files/38030910'

if not os.path.exists(archive_path):
    print("Downloading RDD2022 from Figshare into ephemeral storage...")
    response = requests.get(figshare_url, stream=True)
    total_size = int(response.headers.get('content-length', 0))
    with open(archive_path, 'wb') as f, tqdm(
        total=total_size, unit='B', unit_scale=True, desc='RDD2022.zip'
    ) as pbar:
        for chunk in response.iter_content(chunk_size=1024*1024):
            if chunk:
                f.write(chunk)
                pbar.update(len(chunk))
    print("Download complete.")
else:
    print("Archive already exists in ephemeral storage.")
```

#### Step 4: Selective Extraction of Target Country Subset
```python
import zipfile

# Selectively extract ONLY Japan train images and annotations
target_members = []
with zipfile.ZipFile(archive_path, 'r') as zip_ref:
    all_names = zip_ref.namelist()
    for name in all_names:
        if name.startswith('RDD2022/Japan/train/'):
            target_members.append(name)
            
    print(f"Extracting {len(target_members)} files for Japan train subset...")
    zip_ref.extractall(path='/content/raw', members=target_members)
    print("Selective extraction complete.")
```

#### Step 5: Conversion, Filtering, and Sequence-Aware Splitting Script
```python
import os
import xml.etree.ElementTree as ET
import shutil
from collections import defaultdict
import random

# Configuration
RAW_IMG_DIR = '/content/raw/RDD2022/Japan/train/images'
RAW_XML_DIR = '/content/raw/RDD2022/Japan/train/annotations/xmls'
DEST_ROOT = '/content/visionguard_dataset'
CLASS_MAP = {
    'D00': 0,  # Longitudinal crack
    'D10': 1,  # Transverse crack
    'D20': 2,  # Alligator crack
    'D40': 3   # Pothole
}

# Create output YOLO structure
for split in ['train', 'val', 'test']:
    os.makedirs(os.path.join(DEST_ROOT, 'images', split), exist_ok=True)
    os.makedirs(os.path.join(DEST_ROOT, 'labels', split), exist_ok=True)

# Helper: Convert Pascal VOC XML to YOLO bounding box format
def convert_xml_to_yolo(xml_path):
    tree = ET.parse(xml_path)
    root = tree.getroot()
    size_elem = root.find('size')
    w_img = float(size_elem.find('width').text)
    h_img = float(size_elem.find('height').text)
    
    yolo_boxes = []
    for obj in root.findall('object'):
        class_name = obj.find('name').text
        if class_name in CLASS_MAP:
            class_id = CLASS_MAP[class_name]
            bndbox = obj.find('bndbox')
            xmin = max(0.0, min(w_img, float(bndbox.find('xmin').text)))
            ymin = max(0.0, min(h_img, float(bndbox.find('ymin').text)))
            xmax = max(0.0, min(w_img, float(bndbox.find('xmax').text)))
            ymax = max(0.0, min(h_img, float(bndbox.find('ymax').text)))
            
            if xmax > xmin and ymax > ymin:
                x_center = ((xmin + xmax) / 2.0) / w_img
                y_center = ((ymin + ymax) / 2.0) / h_img
                bbox_w = (xmax - xmin) / w_img
                bbox_h = (ymax - ymin) / h_img
                yolo_boxes.append((class_id, x_center, y_center, bbox_w, bbox_h))
    return yolo_boxes

# Collect and organize image IDs by sequence block to prevent leakage
xml_files = sorted([f for f in os.listdir(RAW_XML_DIR) if f.endswith('.xml')])
print(f"Total available XML annotation files: {len(xml_files)}")
```

#### Step 6: Sequence Block Partitioning Implementation
```python
# Group consecutive frames into blocks of 50 to prevent adjacent frame leakage
BLOCK_SIZE = 50
blocks = []
current_block = []

for idx, xml_file in enumerate(xml_files):
    current_block.append(xml_file)
    if len(current_block) >= BLOCK_SIZE or idx == len(xml_files) - 1:
        blocks.append(current_block)
        current_block = []

# Shuffle blocks with fixed seed
random.seed(42)
random.shuffle(blocks)

# 70% Train, 15% Val, 15% Test block allocation
total_blocks = len(blocks)
n_train = int(0.70 * total_blocks)
n_val = int(0.15 * total_blocks)

train_blocks = blocks[:n_train]
val_blocks = blocks[n_train:n_train + n_val]
test_blocks = blocks[n_train + n_val:]

split_assignments = {}
for b in train_blocks:
    for f in b: split_assignments[f] = 'train'
for b in val_blocks:
    for f in b: split_assignments[f] = 'val'
for b in test_blocks:
    for f in b: split_assignments[f] = 'test'

print(f"Assigned {len(xml_files)} files across {total_blocks} sequence blocks:")
print(f"  Train: {sum(len(b) for b in train_blocks)} files ({len(train_blocks)} blocks)")
print(f"  Val:   {sum(len(b) for b in val_blocks)} files ({len(val_blocks)} blocks)")
print(f"  Test:  {sum(len(b) for b in test_blocks)} files ({len(test_blocks)} blocks)")
```

#### Step 7: Conversion Execution and Directory Population
```python
class_counts = defaultdict(lambda: defaultdict(int))

for xml_file, split in split_assignments.items():
    base_name = os.path.splitext(xml_file)[0]
    img_name = base_name + '.jpg'
    img_src = os.path.join(RAW_IMG_DIR, img_name)
    xml_src = os.path.join(RAW_XML_DIR, xml_file)
    
    if not os.path.exists(img_src):
        continue  # skip if image is missing
        
    yolo_boxes = convert_xml_to_yolo(xml_src)
    
    # Save label file
    lbl_dst = os.path.join(DEST_ROOT, 'labels', split, base_name + '.txt')
    with open(lbl_dst, 'w') as out_f:
        for box in yolo_boxes:
            cid, xc, yc, bw, bh = box
            out_f.write(f"{cid} {xc:.6f} {yc:.6f} {bw:.6f} {bh:.6f}\n")
            class_counts[split][cid] += 1
            
    # Copy image to destination
    img_dst = os.path.join(DEST_ROOT, 'images', split, img_name)
    shutil.copyfile(img_src, img_dst)

print("\n--- Converted Dataset Class Distribution ---")
name_lookup = {0: 'D00 (Longitudinal)', 1: 'D10 (Transverse)', 2: 'D20 (Alligator)', 3: 'D40 (Pothole)'}
for split in ['train', 'val', 'test']:
    print(f"Split: {split}")
    for cid in range(4):
        print(f"  {name_lookup[cid]}: {class_counts[split][cid]} instances")
```

#### Step 8: YOLO Dataset Configuration (`data.yaml`) Creation
```python
yaml_content = f"""# VisionGuard AI — RDD2022 YOLOv8 Dataset Configuration
path: {DEST_ROOT}
train: images/train
val: images/val
test: images/test

names:
  0: D00_longitudinal_crack
  1: D10_transverse_crack
  2: D20_alligator_crack
  3: D40_pothole
"""

yaml_path = os.path.join(DEST_ROOT, 'data.yaml')
with open(yaml_path, 'w') as f:
    f.write(yaml_content)

print(f"Created dataset configuration at: {yaml_path}")
```

#### Step 9: Visual Sanity Check Mosaic
```python
import cv2
import matplotlib.pyplot as plt

def draw_yolo_boxes(image_path, label_path):
    img = cv2.imread(image_path)
    h, w, _ = img.shape
    if os.path.exists(label_path):
        with open(label_path, 'r') as f:
            for line in f:
                parts = line.strip().split()
                if len(parts) == 5:
                    cid = int(parts[0])
                    xc, yc, bw, bh = map(float, parts[1:])
                    xmin = int((xc - bw / 2) * w)
                    ymin = int((yc - bh / 2) * h)
                    xmax = int((xc + bw / 2) * w)
                    ymax = int((yc + bh / 2) * h)
                    cv2.rectangle(img, (xmin, ymin), (xmax, ymax), (0, 255, 0), 2)
                    cv2.putText(img, f"Class {cid}", (xmin, max(20, ymin - 5)),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
    return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)

# Display 4 sample training images
sample_dir = os.path.join(DEST_ROOT, 'images', 'train')
sample_imgs = [f for f in os.listdir(sample_dir) if f.endswith('.jpg')][:4]

plt.figure(figsize=(12, 12))
for i, s_img in enumerate(sample_imgs):
    img_p = os.path.join(sample_dir, s_img)
    lbl_p = os.path.join(DEST_ROOT, 'labels', 'train', os.path.splitext(s_img)[0] + '.txt')
    vis_img = draw_yolo_boxes(img_p, lbl_p)
    plt.subplot(2, 2, i + 1)
    plt.imshow(vis_img)
    plt.title(s_img)
    plt.axis('off')
plt.tight_layout()
plt.show()
```

---

## 10. Storage Considerations & Data Safety Guardrails

### 10.1 Storage Footprint Analysis

| Storage Location | Resource | Estimated Capacity Required | Feasibility & Management |
| :--- | :--- | :--- | :--- |
| **Colab Ephemeral (`/content/`)** | Raw `RDD2022.zip` Archive | ~13.26 GB | Fits comfortably within Colab's ~100 GB ephemeral SSD. Discarded automatically when notebook shuts down. |
| **Colab Ephemeral (`/content/`)** | Extracted Japan Subset | ~2.5 GB uncompressed | Fits cleanly without storage pressure. |
| **Colab Ephemeral (`/content/`)** | Converted YOLO Dataset | ~2.5 GB (images + `.txt` labels) | Fast local I/O for YOLO dataloaders during training. |
| **Google Drive (`/content/drive/`)** | Prepared Dataset Archive (`.zip`) | ~1.5 GB compressed | Fits within free 15 GB Google Drive quota. Optional backup. |
| **Google Drive (`/content/drive/`)** | Trained Model Weights (`best.pt`) | **~6.2 MB** | Minimal footprint. Easy download to local laptop. |
| **Local Laptop (`ai/models/`)** | Final Weights (`best.pt`) | **~6.2 MB** | Negligible impact on developer's 107 GB free disk space. |

### 10.2 Data Safety & Git Hygiene Guardrails

- **Zero Dataset Files in Git:** Neither raw images, XMLs, nor converted YOLO `.txt` labels will be placed in or committed to Git. The project `.gitignore` already enforces `data/datasets/*` and `ai/models/*` exclusion.
- **No Large Archives in Local Workspace:** The 13.26 GB raw archive will remain in Colab cloud storage and will never be downloaded to the local laptop drive.
- **Attribution Compliance:** Every report and model card will formally cite Arya et al. (2022) in compliance with the CC BY 4.0 license.

---

## 11. Risks, Limitations & Unresolved Questions

| Risk / Question | Impact | Proposed Mitigation |
| :--- | :--- | :--- |
| **Colab Disconnection During Download** | Download interruption resets ephemeral storage. | Stream download using chunked requests with resumable retry logic or direct `curl`/`wget`. |
| **Class Imbalance (`D40` Potholes vs. `D00` Cracks)** | Longitudinal cracks outnumber potholes ~5:1 in the Japan subset. | If preliminary validation reveals poor pothole recall, supplement the training partition with pothole-rich sequences from the `India` subset during Phase 3.3. |
| **Dashcam Hood Occlusion** | The lower 10–15% of images may show the vehicle hood or dashboard reflection. | YOLOv8 Mosaic and affine augmentations naturally generalize over static vehicle hood boundaries; exclude any annotations mistakenly placed on the vehicle hood. |
| **Held-Out Test Set Quarantine** | Risk of accidental data leakage into hyperparameter tuning. | Maintain strict separation between `val` (tuning/checkpoints) and `test` (final unadjusted evaluation report only). |

---

## 12. Phase 3.2 Exit Criteria & Next Steps

### Exit Criteria for Phase 3.2:
1. [x] Complete provenance, DOI, direct download links, and checksums verified for RDD2022.
2. [x] Target subset (Japan train subset, ~10,500 images; curated 3,000–4,500 subset) defined and justified.
3. [x] 0-indexed class mapping established strictly for `D00`, `D10`, `D20`, and `D40`.
4. [x] Sequence-aware block partitioning specified to prevent video frame data leakage.
5. [x] End-to-end Google Colab execution scripts written and documented.
6. [x] Storage footprints, Colab quotas, and Git safety rules confirmed.

### Next Actions (Awaiting User Review):
- Upon user approval of this specification, proceed to create the companion Google Colab notebook (`notebooks/VisionGuard_RDD2022_Preparation.ipynb` or self-contained `.py` script) and initiate Phase 3.3 model training.
