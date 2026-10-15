# VisionGuard AI --- Dataset and Model Research Report (Phase 2)

**Document Status:** Approved Technical Baseline  
**Project Phase:** Phase 2 --- Dataset Research & Selection  
**Research Status:** Completed Evaluation & Recommendation (Zero Datasets or Weights Downloaded)  
**Version:** 2.0  

---

## 1. Executive Summary & Objective

The objective of Phase 2 is to research, evaluate, and recommend a verified computer-vision dataset and model architecture for detecting **road cracks and potholes** in VisionGuard AI.

The goal is to establish an authentic computer-vision baseline that will eventually run genuine inference, produce accurate spatial localizations, and support technical defect property estimation (e.g., bounding dimensions and aspect ratios) without using language models or mock data to simulate predictions.

> [!IMPORTANT]
> **Phase 2 Restrictions Maintained:** No datasets have been downloaded, no model training has occurred, and no dependencies or weights have been installed. This document provides the empirical evaluation and architectural justification required before entering Phase 3.

---

## 2. Comprehensive Survey of Public Datasets

We surveyed public datasets across three infrastructure defect domains: **roadway pavement defects**, **structural/concrete cracks**, and **dedicated pothole datasets**.

### Candidate 1: Road Damage Dataset 2022 (RDD2022 / CRDDC'2022)
- **Official Source / Repository:** [sekilab/RoadDamageDetector (GitHub)](https://github.com/sekilab/RoadDamageDetector)  
- **Foundational Paper:** Arya, D., Maeda, H., Ghosh, S. K., Toshniwal, D., & Sekimoto, Y. (2022). *RDD2022: A multi-national image dataset for automatic Road Damage Detection.* arXiv:2209.08538. Conference: IEEE BigData 2022 (CRDDC'2022). Published in *Geoscience Data Journal* (2024).  
- **Defect Categories Annotated:**
  - `D00`: Longitudinal Crack (parallel to traffic direction)
  - `D10`: Transverse Crack (perpendicular to traffic direction)
  - `D20`: Alligator Crack (interconnected fatigue map cracking)
  - `D40`: Pothole (localized road depressions/cavities)
  - *(Note: Specific sub-datasets also include repair markings `D43`/`D44` and crosswalk blur `D50`, which can be filtered out).*
- **Verified Image Count:**
  - Total road images: **47,420** images captured across 6 countries (Japan, India, Czech Republic, Norway, United States, and China).
  - Train Set (publicly annotated): **38,385** images containing **55,000+** damage instances.
  - Test Set (unannotated competition benchmark): **9,035** images.
- **Annotation Type:** **Bounding Boxes** (2D axis-aligned rectangles: `xmin`, `ymin`, `xmax`, `ymax`).
- **Dataset Format:** Standard **PASCAL VOC XML** annotations paired with JPEG imagery. (Readily convertible to YOLO `.txt` format).
- **Licensing & Permitted Use:** **Creative Commons Attribution-ShareAlike 4.0 International (CC BY-SA 4.0)**. Permits free sharing, adaptation, and commercial/educational usage provided attribution is given and contributions are shared under the same license.
- **Image Quality & Variety:** Vehicle-mounted smartphone dashcam imagery capturing realistic driving perspectives under varied natural lighting, weather conditions (dry, overcast, rain), asphalt surface textures, and geographic roadway standards.
- **Task Suitability:** **Excellent for Object Detection.** It is the only major open-access benchmark that unifies both cracks and potholes under a single, consistent labeling schema.
- **Limitations & Leakage Risks:**
  - Many images are sequential frames extracted from driving video logs. A naive random train/test split will cause severe **data leakage** (similar road backgrounds in both sets). Splitting must be executed chronologically by video sequence or country sub-folder.
  - Test set labels are unreleased; an internal validation and test split must be partitioned from the 38,385 training images.
  - Annotations provide bounding boxes, not pixel-level crack widths.

---

### Candidate 2: CRACK500 (Pavement Crack Segmentation)
- **Official Source / Repository:** [fyangneil/pavement-crack-detection (GitHub)](https://github.com/fyangneil/pavement-crack-detection)  
- **Foundational Paper:** Yang, F., Zhang, L., Yu, S., Prokhorov, D., Mei, X., & Ling, H. (2020). *Feature Pyramid and Hierarchical Boosting Network for Pavement Crack Detection.* IEEE Transactions on Intelligent Transportation Systems (T-ITS), 21(4), 1525–1535.  
- **Defect Categories Annotated:** Road surface cracks (longitudinal, transverse, alligator, multifurcate). All labeled as general crack pixels. **No potholes.**
- **Verified Image Count:**
  - 500 high-resolution source images (~2000x1500 px) captured on Temple University campus.
  - Standard pre-cropped patch dataset: **3,368 total cropped images** (1,896 train, 348 validation, 1,124 test).
- **Annotation Type:** **Pixel-Level Binary Segmentation Masks** (white/255 = crack pixel, black/0 = background).
- **Dataset Format:** Paired images and binary PNG masks.
- **Licensing & Permitted Use:** Academic / Research use. *Note on formal license:* The original repository does not include an explicit OSI license file (e.g., MIT/Apache). Standard academic attribution to Yang et al. (2020) is required.
- **Image Quality & Variety:** High-resolution downward mobile phone photography. Excellent detail for crack tortuosity, but geographically homogenous (single university campus).
- **Task Suitability:** **Excellent for Semantic/Instance Segmentation.** Unsuitable for pothole detection.
- **Limitations & Leakage Risks:**
  - Zero pothole instances.
  - Cropped patch format lacks the broad road context seen by inspection vehicles.
  - Cannot be directly merged with wide-angle bounding-box datasets without severe domain shift.

---

### Candidate 3: SDNET2018 (Concrete Structural Cracks)
- **Official Source / Repository:** [Utah State University DigitalCommons (DOI: 10.15142/T3TN6X)](https://doi.org/10.15142/T3TN6X)  
- **Foundational Paper:** Maguire, M., Dorafshan, S., & Thomas, R. J. (2018). *SDNET2018: An image dataset for concrete crack detection.* Utah State University.  
- **Defect Categories Annotated:** Concrete cracks across three structural asset types: Bridge Decks (reinforced), Walls (reinforced), and Pavements (unreinforced). **No potholes.**
- **Verified Image Count:**
  - **56,092** sub-images at uniform 256x256 pixel resolution.
  - 8,484 cracked images; 47,608 uncracked background images.
- **Annotation Type:** **Image-Level Binary Classification Labels** (`C` = Cracked, `U` = Uncracked). **No bounding boxes or masks.**
- **Dataset Format:** Directory hierarchy of JPEG patch images.
- **Licensing & Permitted Use:** **Creative Commons Attribution 4.0 International (CC BY 4.0)**.
- **Image Quality & Variety:** High visual clarity of concrete surface micro-textures, shadows, voids, and surface roughness.
- **Task Suitability:** **Classification Only.**
- **Limitations & Leakage Risks:**
  - Does not locate defects within an image (no coordinates).
  - Concrete structures rather than asphalt roadways.
  - Cannot fulfill VisionGuard AI's core requirement of spatial defect localization without manual re-annotation.

---

### Candidate 4: METU Concrete Crack Images Dataset
- **Official Source / Repository:** [Mendeley Data (DOI: 10.17632/5y9wdsg2zt.2)](https://doi.org/10.17632/5y9wdsg2zt.2)  
- **Foundational Paper:** Özgenel, Ç. F., & Sorguç, A. G. (2018). *Performance Comparison of Pretrained Convolutional Neural Networks on Crack Detection in Buildings.* ISARC 2018, Berlin.  
- **Defect Categories Annotated:** Surface concrete cracks (Binary: Positive vs. Negative). **No potholes.**
- **Verified Image Count:** **40,000** RGB images (227x227 pixels) cropped from 458 high-resolution building photos (20,000 cracked, 20,000 uncracked).
- **Annotation Type:** **Image-Level Classification Labels.**
- **Dataset Format:** Folders of 227x227 JPEG crops.
- **Licensing & Permitted Use:** **Creative Commons Attribution 4.0 International (CC BY 4.0)**.
- **Task Suitability:** **Classification Benchmark Only.**
- **Limitations & Leakage Risks:** Lacks spatial bounding coordinates; building concrete domain; does not support road defect inspection.

---

### Candidate 5: Pothole Detection Datasets (Roboflow Universe / Kaggle Curations)
- **Official Source / Repository:** [Brad Dwyer Pothole Dataset (Roboflow Universe)](https://universe.roboflow.com/) and Kaggle mirrors.  
- **Defect Categories Annotated:** Single class: `pothole`. **No cracks.**
- **Verified Image Count:** Typically **665 images** (465 train, 133 val, 67 test) in the classic benchmark curation; community expansions range from 1,000 to 1,900 images.
- **Annotation Type:** **Bounding Boxes** (`xmin`, `ymin`, `xmax`, `ymax`).
- **Dataset Format:** YOLO `.txt` format and PASCAL VOC XML.
- **Licensing & Permitted Use:** **CC BY 4.0** or **CC0 Public Domain** (depending on community mirror).
- **Image Quality & Variety:** Real-world street-level pothole captures under varied road wear and moisture conditions.
- **Task Suitability:** Good for standalone pothole object detection.
- **Limitations & Leakage Risks:**
  - Very small sample size (665 images) leads to rapid overfitting.
  - Cracks are completely omitted from annotations; cracks appearing in the background are treated as unannotated negative space, which confuses models trained on both defect types.

---

## 3. Dataset Comparison Matrix

| Evaluation Dimension | RDD2022 (Sekilab) | CRACK500 (Yang et al.) | SDNET2018 (Maguire) | Roboflow Pothole (665) |
| :--- | :--- | :--- | :--- | :--- |
| **Defect Classes** | Cracks (Long., Trans., Allig.) & Potholes | Cracks (All typologies) | Concrete Cracks only | Potholes only |
| **Primary Domain** | Asphalt Roadway (Dashcam) | Asphalt Roadway (Macro) | Concrete Bridges & Walls | Asphalt Roadway |
| **Verified Image Count** | 47,420 (38,385 annotated) | 3,368 patches (500 photos) | 56,092 patches | 665 images |
| **Annotation Level** | Bounding Boxes (Pascal VOC) | Binary Pixel Masks (PNG) | Image Classification | Bounding Boxes (YOLO/VOC) |
| **Verified License** | CC BY-SA 4.0 | Research / Unstated OSI | CC BY 4.0 | CC BY 4.0 / CC0 |
| **Crack Localization?** | Yes (Bounding Boxes) | Yes (Pixel Mask) | No (Image level only) | N/A (No cracks) |
| **Pothole Detection?** | Yes | No | No | Yes |
| **Unified Taxonomy?** | **Yes (Single consistent set)** | No | No | No |
| **Recommendation** | **PRIMARY SELECTION** | Candidate for Phase 3 Seg. | Excluded from MVP | Secondary Validation |

---

## 4. Comparison of Computer-Vision Model Approaches

We evaluated three architectural paradigms for infrastructure defect inspection:

```text
┌────────────────────────────────────────────────────────────────────────┐
│ 1. Object Detection (Bounding Boxes)                                   │
│    Outputs [x1, y1, x2, y2] + Class + Confidence                       │
│    Fast, widely supported, ideal for real-time web deployment          │
├────────────────────────────────────────────────────────────────────────┤
│ 2. Image Segmentation (Pixel Masks)                                    │
│    Outputs Binary/Polygonal pixel masks delineating exact contour      │
│    Precise crack shape, computationally intensive, scarce labels       │
├────────────────────────────────────────────────────────────────────────┤
│ 3. Image Classification (Image / Patch Labels)                         │
│    Outputs "Cracked / Sound" without coordinates                       │
│    Cannot localize defects; unsuitable for inspection workflows        │
└────────────────────────────────────────────────────────────────────────┘
```

### Approach 1: Object Detection (Bounding Boxes)
- **Candidate Architectures:** YOLOv8 (nano/small), Faster R-CNN (ResNet-50 backbone), SSD-MobileNet.
- **Advantages:**
  - Exceptional inference speed (<150 ms on CPU, 15–30 ms on GPU), allowing seamless Flask API responses.
  - Large volume of verified bounding-box training data (RDD2022).
  - Compact weight footprints (~6 MB for YOLOv8n, ~22 MB for YOLOv8s).
  - Straightforward integration into web visualization (OpenCV draws standard labeled rectangles).
- **Disadvantages:**
  - Rectangular boxes enclose surrounding sound asphalt alongside the crack.
  - Cannot trace winding, branching crack paths.
- **Defect Property Estimation Feasibility:**
  - Bounding box width, height, aspect ratio, and bounding pixel area are readily computed.
  - **Important Guardrail:** A bounding box **cannot measure crack width**. A bounding box around a 1-millimeter hairline diagonal crack spanning a 500x500 pixel box has a 500-pixel bounding width, which is not the crack width. True crack width requires pixel segmentation and physical ground calibration.

### Approach 2: Image Segmentation (Semantic / Instance)
- **Candidate Architectures:** YOLOv8-Seg, Mask R-CNN, U-Net, DeepLabV3+.
- **Advantages:**
  - Delineates the exact pixel contour and morphology of cracks and potholes.
  - Enables true surface area estimation and morphological skeletonization to approximate crack length in pixels.
- **Disadvantages:**
  - Training requires pixel-mask annotations. RDD2022 does not have segmentation masks; CRACK500 has masks but has zero potholes.
  - Considerably higher VRAM demand and inference latency (unsuitable for low-spec CPU deployment).
  - Significantly higher risk of training instability on custom road domains.
- **Defect Property Estimation Feasibility:**
  - Morphological skeleton thinning can calculate crack centerline length in pixels.
  - Physical millimeter dimensions require external ground-plane calibration or reference markers.

### Approach 3: Image Classification (Image / Patch Level)
- **Candidate Architectures:** ResNet-18/50, MobileNetV3, EfficientNet.
- **Advantages:** Low training complexity, vast public patch datasets (SDNET2018, METU).
- **Disadvantages:** **Fails core engineering requirements.** It only reports whether an image patch contains a defect, completely omitting spatial coordinates, bounding overlays, and location metrics.
- **Defect Property Estimation Feasibility:** Not feasible.

---

## 5. Hardware Constraints & Training Feasibility

### Development Environment Baseline
- **Operating System:** Windows 10/11.
- **Host System RAM:** 16 GB.
- **GPU Hardware:** NVIDIA-capable gaming laptop GPU (VRAM unconfirmed; typically 4 GB to 8 GB on modern gaming laptops).
- **Local Storage:** Limited available disk space.

### How to Check Local GPU Specifications & VRAM
Before running training, the developer must verify the exact GPU model and dedicated VRAM:
1. **Via Command Line:** Open PowerShell and run:
   ```powershell
   nvidia-smi
   ```
   Inspect the `Product Name` (e.g. NVIDIA GeForce RTX 3050 Laptop GPU) and `Memory-Usage` (e.g., `4096MiB` or `6144MiB`).
2. **Via Windows Task Manager:** Press `Ctrl + Shift + Esc`, navigate to **Performance** > **GPU**, and check **Dedicated GPU memory**.
3. **Via PyTorch CLI:** Execute:
   ```bash
   python -c "import torch; print('CUDA Available:', torch.cuda.is_available()); print('Device:', torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'CPU'); print('VRAM (GB):', round(torch.cuda.get_device_properties(0).total_memory / 1e9, 2) if torch.cuda.is_available() else 0)"
   ```

### Recommended Training Strategy
- **If Local GPU has >= 6 GB VRAM:**
  - Local fine-tuning of a lightweight model (e.g. YOLOv8n or YOLOv8s) is practical.
  - Set image resolution to **640x640 pixels**, batch size to **8 or 16**, and mixed-precision (`amp=True`).
  - Train on a curated country subset of RDD2022 (e.g., Japan + India subsets, ~3,000–5,000 images) to keep disk storage under 3 GB.
- **If Local GPU has <= 4 GB VRAM or Disk Space is Constrained (<10 GB free):**
  - **Recommend Cloud Notebook Execution (Google Colab or Kaggle Notebooks).**
  - Cloud notebooks provide free NVIDIA T4 GPUs with **15–16 GB VRAM** and ~50–100 GB ephemeral disk space.
  - The dataset can be downloaded and extracted directly into cloud scratch storage, fine-tuned in 45–90 minutes, and only the final compact weights (`best.pt`, ~6 MB to 22 MB) downloaded locally to `ai/models/`.
  - This avoids filling the developer's laptop drive with 25+ GB of raw image archives.

---

## 6. MVP Scope Evaluation & Recommendation

We evaluated three potential MVP starting scopes:

### Option A: Crack Detection Only
- *Pros:* Abundant patch datasets; focused algorithmic problem.
- *Cons:* Misses potholes, which represent the most urgent and safety-critical civic road hazard. Fails to demonstrate multi-class detection capabilities.

### Option B: Pothole Detection Only
- *Pros:* High demonstration appeal; potholes are visually distinct.
- *Cons:* Ignores road cracks, which precede potholes and constitute the bulk of routine highway maintenance surveys. Datasets strictly for potholes are small (~665 images).

### Option C: Unified Crack & Pothole Detection (RECOMMENDED)
- *Justification:*
  1. **High Engineering & Civic Value:** Captures the full degradation spectrum—from fatigue cracking (D00, D10, D20) to pavement cavity failure (D40 Pothole).
  2. **Single Cohesive Dataset:** RDD2022 annotates both cracks and potholes simultaneously across identical road scenes and camera perspectives.
  3. **Zero Dataset Harmonization Hazards:** Eliminates the severe risks associated with artificially merging conflicting datasets.

> [!WARNING]
> **Warning on Artificial Dataset Merging:**
> Merging separate crack datasets (like CRACK500) and pothole datasets (like Roboflow Pothole) is strongly discouraged:
> - **Domain Incompatibility:** CRACK500 consists of macro top-down smartphone images of asphalt patches; pothole datasets are wide-angle road scenes.
> - **False Negative Noise:** Wide-angle pothole images contain visible cracks that were never labeled; training a combined model on them forces the network to penalize correct crack detections.
> - Using **RDD2022 directly** solves this because all target classes were labeled under a unified standard.

---

## 7. Recommended Model Architecture & Approach

We formally recommend **Object Detection using YOLOv8 (Nano or Small variant: YOLOv8n / YOLOv8s)** trained on the **RDD2022 dataset**:

1. **Why YOLOv8 over Faster R-CNN:** YOLOv8 provides state-of-the-art accuracy-to-speed tradeoffs, single-stage anchor-free architecture, and native export options (PyTorch `.pt`, ONNX, OpenVINO) for rapid CPU deployment.
2. **Why Bounding Boxes over Segmentation for MVP:**
   - Enables immediate training on RDD2022's 38,000+ verified bounding-box annotations.
   - Fits cleanly into the Phase 4 Flask REST API and OpenCV overlay pipeline.
   - Keeps inference latency under 200 ms on standard laptops without dedicated GPUs.
3. **Property Estimation Approach:**
   - The bounding box provides localized coordinates `[x1, y1, x2, y2]`, aspect ratio ($\frac{w}{h}$), and bounding pixel area.
   - For presentation, the UI will report bounding dimensions and label aspect ratios (e.g., distinguishing elongated longitudinal cracks from compact potholes).
   - Clear disclaimers will state that physical millimeter widths require camera calibration.

---

## 8. Summary of Unresolved Decisions & Next Actions for Phase 3

Before model training begins in Phase 3, the following decisions must be executed:
1. **Target Subset Selection:** Select specific national subsets from RDD2022 (e.g., Japan + India) to compile a lightweight training split (~3,000–5,000 images) suitable for rapid training.
2. **Class Filtering:** Confirm filtering out non-damage annotations (`D43`, `D44`, `D50`) to keep the model focused strictly on `D00` (Longitudinal), `D10` (Transverse), `D20` (Alligator), and `D40` (Pothole).
3. **Environment Decision:** Verify the local laptop GPU via `nvidia-smi` to finalize whether training will run locally or on a Google Colab / Kaggle cloud notebook.
