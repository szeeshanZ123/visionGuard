#!/usr/bin/env python3
"""
VisionGuard AI - Dataset Preparation for Experiment A and Experiment B.
Reads directly from existing dataset split folders:
- /content/visionguard_home_dataset/labels/{train, val, test}
Does NOT assume random seeds. Discovers actual split membership directly from existing files.
"""

import os
import shutil
from pathlib import Path

# Paths
ORIGINAL_DATASET = Path(os.environ.get("ORIGINAL_DATASET", "/content/visionguard_home_dataset"))
EXP_A_ROOT = Path("/content/visionguard_home_dataset_experiment/exp_a_preserve")
EXP_B_ROOT = Path("/content/visionguard_home_dataset_experiment/exp_b_pruned")

UNCERTAIN_STEMS = [
    "zenodo_masonry_crack_022", "zenodo_masonry_crack_030", "zenodo_masonry_crack_031",
    "zenodo_masonry_crack_041", "zenodo_masonry_crack_042", "zenodo_masonry_crack_043",
    "zenodo_masonry_crack_049", "zenodo_masonry_crack_064", "zenodo_masonry_crack_065",
    "zenodo_masonry_crack_066", "zenodo_masonry_crack_069"
]

def verify_actual_splits():
    print("=" * 70)
    print("VERIFYING ACTUAL SPLIT MEMBERSHIP FROM EXISTING FILES")
    print("=" * 70)
    if not ORIGINAL_DATASET.is_dir():
        print(f"Original dataset not found at {ORIGINAL_DATASET}.")
        return {}

    split_membership = {}
    for stem in UNCERTAIN_STEMS:
        found_split = None
        for split in ["train", "val", "test"]:
            lbl_file = ORIGINAL_DATASET / "labels" / split / f"{stem}.txt"
            if lbl_file.is_file():
                found_split = split
                break
        split_membership[stem] = found_split
        print(f"  {stem:<30} -> {found_split or 'NOT FOUND'}")
    return split_membership

def assemble_experiments():
    if not ORIGINAL_DATASET.is_dir():
        print("Cannot assemble: original dataset not present.")
        return

    membership = verify_actual_splits()
    pruned_from_train = [stem for stem, split in membership.items() if split == "train"]

    print("\nAssembling Experiment A (Preserve Control)...")
    for split in ["train", "val", "test"]:
        src_lbl = ORIGINAL_DATASET / "labels" / split
        src_img = ORIGINAL_DATASET / "images" / split
        dst_lbl_a = EXP_A_ROOT / "labels" / split
        dst_img_a = EXP_A_ROOT / "images" / split
        dst_lbl_a.mkdir(parents=True, exist_ok=True)
        dst_img_a.mkdir(parents=True, exist_ok=True)

        for lf in src_lbl.glob("*.txt"):
            shutil.copy2(lf, dst_lbl_a / lf.name)
        for img_ext in [".jpg", ".jpeg", ".png"]:
            for im in src_img.glob(f"*{img_ext}"):
                shutil.copy2(im, dst_img_a / im.name)

    print(f"\nAssembling Experiment B (Pruning {len(pruned_from_train)} training images)...")
    for split in ["train", "val", "test"]:
        src_lbl = ORIGINAL_DATASET / "labels" / split
        src_img = ORIGINAL_DATASET / "images" / split
        dst_lbl_b = EXP_B_ROOT / "labels" / split
        dst_img_b = EXP_B_ROOT / "images" / split
        dst_lbl_b.mkdir(parents=True, exist_ok=True)
        dst_img_b.mkdir(parents=True, exist_ok=True)

        for lf in src_lbl.glob("*.txt"):
            if split == "train" and lf.stem in pruned_from_train:
                continue # Exclude from training
            shutil.copy2(lf, dst_lbl_b / lf.name)

        for img_ext in [".jpg", ".jpeg", ".png"]:
            for im in src_img.glob(f"*{img_ext}"):
                if split == "train" and im.stem in pruned_from_train:
                    continue # Exclude from training
                shutil.copy2(im, dst_img_b / im.name)

    print("\nAssembly complete. Validation and test sets are 100% untouched.")

if __name__ == "__main__":
    verify_actual_splits()
