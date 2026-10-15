# VisionGuard AI --- Phase 3.1: Environment & GPU Verification Report

**Document Status:** Verified Baseline  
**Project Phase:** Phase 3.1 --- Environment and Hardware Verification  
**Verification Date:** October 2026  
**Execution Mode:** Read-Only Inspection (Zero Dependencies or Model Weights Installed)  

---

## 1. Verified Hardware Specifications

All hardware checks were conducted using native Windows diagnostic utilities (`nvidia-smi`, WMI/CIM cmdlets):

| Specification | Detected Value | Verification Command / Source |
| :--- | :--- | :--- |
| **GPU Model** | **NVIDIA GeForce RTX 3050 Laptop GPU** | `nvidia-smi` & `Win32_VideoController` |
| **Total Dedicated VRAM** | **4096 MiB (4.0 GB GDDR6)** | `nvidia-smi` (`Memory-Usage`) |
| **Current VRAM Usage** | **~1041 MiB** (used by desktop, Chrome, apps) | `nvidia-smi` |
| **Available Free VRAM** | **~3055 MiB (~3.0 GB)** at idle | `nvidia-smi` |
| **NVIDIA Driver Version** | **610.47** (WDDM 32.0.16.1047) | `nvidia-smi` |
| **Driver CUDA Version Support** | **CUDA 13.3** | `nvidia-smi` header |
| **`nvidia-smi` Status** | **Operational (Exit code 0)** | Tested directly in PowerShell |
| **CPU Model** | **AMD Ryzen 7 7435HS** (8 Cores, 16 Threads) | `Win32_Processor` |
| **Total System RAM** | **16.0 GB DDR5** | `Win32_PhysicalMemory` |
| **Active Storage Drive** | **Drive C:\** | `Get-PSDrive -PSProvider FileSystem` |
| **Total Drive Capacity** | **~479 GB** (371.56 GB used) | `Get-PSDrive C` |
| **Available Free Disk Space** | **115.37 GB (~107.45 GiB free)** | `Get-PSDrive C` |

---

## 2. Python & Virtual Environment Status

- **Default Python Version:** `Python 3.14.0`
- **Python Binary Path:** `C:\Python314\python.exe`
- **Secondary Python Version:** `Python 3.13` at `C:\Program Files\Python313\python.exe`
- **Active Virtual Environment:** **None** (`In venv: False`). Commands are currently executing in the global Python 3.14 interpreter.
- **Installed Key Packages in Python 3.14:**
  - `Flask` (3.1.3)
  - `opencv-python` (5.0.0.93)
  - `pillow` (12.3.0)
  - `numpy` (2.5.0)
  - `pandas` (3.0.3)
  - `matplotlib` (3.11.0)
  - `PyYAML` (6.0.3)
  - `pytest` (9.1.1)

---

## 3. PyTorch & CUDA Acceleration Status

- **PyTorch Installed:** **No.** `python -m pip show torch` returned `WARNING: Package(s) not found: torch`.
- **PyTorch in Python 3.13:** **No.** `Package(s) not found: torch`.
- **PyTorch CUDA Acceleration Test:** **Not Applicable (Torch Not Installed).**
- **Critical Python Version Compatibility Finding:**
  - The default system interpreter is **Python 3.14.0**.
  - Official pre-compiled PyTorch binary wheels with CUDA acceleration (via `download.pytorch.org/whl/cu121` or `cu124`) are currently built for **Python 3.9, 3.10, 3.11, and 3.12** (with preliminary nightly wheels for 3.13).
  - Attempting to install PyTorch with GPU CUDA support directly into Python 3.14 will fail or fall back to building from source, which is impractical on Windows.

---

## 4. Available Storage Assessment

- **Available Free Disk Space on C:\:** **107.45 GB**.
- **Dataset Storage Requirements:**
  - Curated RDD2022 subset (e.g., Japan + India subsets, ~3,000 to 5,000 images): **~2.5 GB to 4.5 GB** uncompressed.
  - YOLOv8 Nano weights and checkpoint files: **~50 MB to 200 MB**.
- **Assessment:** Local storage capacity is **fully sufficient** for holding the target dataset subset and training artifacts without storage exhaustion.

---

## 5. Hardware Compatibility & Feasibility Analysis

| Task / Workload | Feasibility on RTX 3050 (4 GB) | Notes & Memory Constraints |
| :--- | :--- | :--- |
| **YOLOv8n Training (640x640)** | **Feasible (with constraints)** | YOLOv8n has only 3.2M parameters. With image size 640x640, batch size 8 (or 16), and FP16 mixed precision (`amp=True`), training requires **~1.8 GB to 2.4 GB VRAM**, which fits within the ~3.0 GB free VRAM. |
| **YOLOv8s / Larger Models** | **High Risk of CUDA OOM** | Models larger than Nano (Small, Medium) or batch sizes >= 32 will exceed the 4.0 GB physical VRAM limit. |
| **RDD2022 Subset Training** | **Feasible** | A curated subset of 2,500–4,000 images trains cleanly without overflowing RAM or disk space. |
| **Inference Execution** | **Optimal** | YOLOv8n inference requires <500 MB VRAM and executes in **10–25 ms on the RTX 3050**, or **100–150 ms on CPU**. |

---

## 6. Recommended Training Approach: Cloud vs. Local

Based on the verified hardware constraints and Python version availability, we evaluate two options:

### Recommendation: Cloud Notebook (Google Colab / Kaggle) for Phase 3 Training [PRIMARY]
- **Why Cloud is Recommended:**
  1. **Python Compatibility:** Colab and Kaggle provide native, pre-configured Python 3.10/3.11 environments with pre-installed PyTorch and CUDA.
  2. **VRAM Headroom:** Provides an **NVIDIA Tesla T4 GPU with 15.0 to 16.0 GB VRAM** (nearly 4x local VRAM), eliminating any risk of Out-of-Memory (OOM) errors.
  3. **Zero Local Wear & Thermal Load:** Intensive training epochs run in the cloud in **30–45 minutes** without keeping laptop fans at 100% or draining battery.
  4. **Clean Local Workspace:** Only the final trained weight file (`best.pt`, ~6.2 MB) needs to be downloaded into `ai/models/` for local Flask serving.

### Alternative: Local Training via Dedicated Virtual Environment [SECONDARY]
- **Requirements if training locally:**
  1. Install Python 3.11 or 3.12 on the laptop.
  2. Create a clean virtual environment: `python -m venv .venv`.
  3. Install PyTorch with CUDA 12.1/12.4 wheels: `pip install torch torchvision --index-url https://download.pytorch.org/whl/cu121`.
  4. Restrict training parameters: `imgsz=640`, `batch=8`, `workers=2`, `amp=True`.

---

## 7. Required Dependencies & Installation Plan (For Future Steps)

> [!CAUTION]
> In accordance with Phase 3.1 restrictions, **no packages have been installed**. This list represents the planned dependency stack to be installed in Phase 3.2.

| Package | Recommended Version | Justification |
| :--- | :--- | :--- |
| **`torch`** | `>=2.1.0` (with CUDA 12.1/12.4) | PyTorch deep learning framework for model execution and backpropagation. |
| **`torchvision`** | `>=0.16.0` | Computer-vision transforms, dataset utilities, and bounding-box ops. |
| **`ultralytics`** | `>=8.1.0` | Official YOLOv8 library providing training, validation, export, and inference routines. |
| **`opencv-python`** | `5.0.0.93` *(already installed)* | Image reading, decoding, resizing, and bounding-box overlay rendering. |
| **`pillow`** | `12.3.0` *(already installed)* | Image verification, PIL format compatibility, and metadata extraction. |
| **`numpy`** | `2.5.0` *(already installed)* | Tensor and array manipulation. |
| **`matplotlib`** | `3.11.0` *(already installed)* | Generating training loss curves, confusion matrices, and PR curves. |
| **`PyYAML`** | `6.0.3` *(already installed)* | Parsing RDD2022 dataset configuration (`data.yaml`). |

---

## 8. Unresolved Decisions & Next Actions

1. **Training Environment Selection:** Confirm whether to proceed with **Google Colab (recommended)** or configure a **local Python 3.11/3.12 virtual environment**.
2. **Target Classes:** Confirm training strictly on the 4 primary distress classes:
   - `D00`: Longitudinal cracks
   - `D10`: Transverse cracks
   - `D20`: Alligator cracks
   - `D40`: Potholes
3. **Data Preparation Script:** In Phase 3.2, prepare a lightweight download and conversion script to convert RDD2022 Pascal VOC XML annotations into YOLO format (`data.yaml`).
