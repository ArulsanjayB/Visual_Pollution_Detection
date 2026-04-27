"""
Dataset preparation script for Visual Pollution Detector.

Handles:
- Unzipping the dataset
- Train/Val/Test split (70/20/10)
- Aggressive augmentation for underrepresented classes:
    Class 0 (Potholes):           ~800 images -> keep as is
    Class 1 (Abandoned Vehicles): ~452 images -> augment to ~800
    Class 2 (Construction Debris):~163 images -> augment to ~800

Additional recommended open datasets to download and merge:
  Construction Debris:
    - Roboflow: "Construction Site Safety" dataset (filtered for debris)
    - TACO dataset (http://tacodataset.org) classes: Hard plastic, Trash
    - https://universe.roboflow.com/search?q=construction+debris
  Abandoned Vehicles:
    - Google Open Images (class: Car) + filter parked/abandoned context
    - https://universe.roboflow.com/search?q=abandoned+vehicle
    - COCO dataset (vehicle subset)
  Potholes (supplementary):
    - Pothole-600 dataset (Kaggle)
    - https://universe.roboflow.com/search?q=pothole

Run this script ONCE before training:
    python data_prep.py --zip_path combined_dataset_final.zip --output_dir dataset
"""

import os
import zipfile
import shutil
import random
import argparse
import yaml
from pathlib import Path

import cv2
import numpy as np
import albumentations as A
from tqdm import tqdm

CLASSES = ["Potholes", "Abandoned_Vehicles", "Construction_Debris"]
# Augmentation targets per class
TARGET_COUNTS = {0: 900, 1: 800, 2: 800}

# ── Augmentation pipelines ────────────────────────────────────────────────────

def get_augmentation_pipeline(severity: str = "medium") -> A.Compose:
    """Return bbox-aware augmentation pipeline."""
    bbox_params = A.BboxParams(
        format="yolo",
        label_fields=["class_labels"],
        min_visibility=0.3,
    )
    if severity == "light":
        return A.Compose([
            A.HorizontalFlip(p=0.5),
            A.RandomBrightnessContrast(p=0.4),
            A.GaussNoise(std_range=(0.02, 0.08), p=0.3),
        ], bbox_params=bbox_params)
    elif severity == "medium":
        return A.Compose([
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.1),
            A.RandomBrightnessContrast(brightness_limit=0.3, contrast_limit=0.3, p=0.6),
            A.HueSaturationValue(p=0.4),
            A.GaussNoise(std_range=(0.04, 0.15), p=0.4),
            A.MotionBlur(blur_limit=5, p=0.3),
            A.RandomRotate90(p=0.2),
            A.Affine(translate_percent=(-0.05,0.05), scale=(0.9,1.1), rotate=(-15,15), p=0.5),
            A.CLAHE(p=0.3),
            A.RandomShadow(p=0.2),
        ], bbox_params=bbox_params)
    else:  # heavy
        return A.Compose([
            A.HorizontalFlip(p=0.5),
            A.VerticalFlip(p=0.2),
            A.RandomBrightnessContrast(brightness_limit=0.4, contrast_limit=0.4, p=0.7),
            A.HueSaturationValue(hue_shift_limit=20, sat_shift_limit=40, val_shift_limit=30, p=0.6),
            A.GaussNoise(std_range=(0.08, 0.3), p=0.5),
            A.MotionBlur(blur_limit=7, p=0.4),
            A.Affine(translate_percent=(-0.1,0.1), scale=(0.8,1.2), rotate=(-30,30), p=0.6),
            A.CLAHE(p=0.4),
            A.RandomShadow(shadow_roi=(0, 0, 1, 1), p=0.3),
            A.CoarseDropout(num_holes_range=(4,8), hole_height_range=(16,32), hole_width_range=(16,32), p=0.3),
            A.Perspective(scale=(0.05, 0.15), p=0.3),
            A.RandomRain(brightness_coefficient=0.9, p=0.15),
        ], bbox_params=bbox_params)


# ── Helpers ───────────────────────────────────────────────────────────────────

def read_yolo_label(label_path: str):
    """Read YOLO label file -> list of (class_id, cx, cy, w, h)."""
    annotations = []
    with open(label_path, "r") as f:
        for line in f.readlines():
            parts = line.strip().split()
            if len(parts) == 5:
                cls = int(parts[0])
                cx, cy, w, h = map(float, parts[1:])
                annotations.append((cls, cx, cy, w, h))
    return annotations


def write_yolo_label(label_path: str, annotations):
    """Write annotations to YOLO label file."""
    with open(label_path, "w") as f:
        for cls, cx, cy, w, h in annotations:
            f.write(f"{cls} {cx:.6f} {cy:.6f} {w:.6f} {h:.6f}\n")


def get_primary_class(label_path: str) -> int:
    """Return the most frequent class in a label file."""
    anns = read_yolo_label(label_path)
    if not anns:
        return -1
    classes = [a[0] for a in anns]
    return max(set(classes), key=classes.count)


def augment_image(img_path: str, lbl_path: str, aug_pipeline, out_img_path: str, out_lbl_path: str):
    """Apply augmentation and save result."""
    image = cv2.imread(img_path)
    if image is None:
        return False
    image = cv2.cvtColor(image, cv2.COLOR_BGR2RGB)
    annotations = read_yolo_label(lbl_path)
    if not annotations:
        return False

    bboxes = [(a[1], a[2], a[3], a[4]) for a in annotations]
    class_labels = [a[0] for a in annotations]

    try:
        result = aug_pipeline(image=image, bboxes=bboxes, class_labels=class_labels)
        aug_image = cv2.cvtColor(result["image"], cv2.COLOR_RGB2BGR)
        aug_bboxes = result["bboxes"]
        aug_classes = result["class_labels"]

        if not aug_bboxes:
            return False

        cv2.imwrite(out_img_path, aug_image)
        write_yolo_label(out_lbl_path, [
            (c, *b) for c, b in zip(aug_classes, aug_bboxes)
        ])
        return True
    except Exception as e:
        print(f"  Augmentation failed for {img_path}: {e}")
        return False


# ── Main pipeline ─────────────────────────────────────────────────────────────

def prepare_dataset(zip_path: str, output_dir: str, seed: int = 42, from_dir: str = None):
    random.seed(seed)
    np.random.seed(seed)
    output_dir = Path(output_dir)

    # 1. Extract zip OR use existing directory
    if from_dir and Path(from_dir).exists():
        print(f"[1/5] Using existing dataset directory: {from_dir}")
        from_dir = Path(from_dir)
        img_dir = from_dir / "images"
        lbl_dir = from_dir / "labels"
        if not img_dir.exists():
            img_dir = from_dir
            lbl_dir = from_dir
    else:
        raw_dir = output_dir / "raw"
        print(f"[1/5] Extracting {zip_path} ...")
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(raw_dir)

        img_dir = raw_dir / "images"
        lbl_dir = raw_dir / "labels"

        # Support both flat structure and nested
        if not img_dir.exists():
            img_dir = raw_dir
            lbl_dir = raw_dir

    image_files = sorted(list(img_dir.glob("*.jpeg")) + list(img_dir.glob("*.jpg")) + list(img_dir.glob("*.png")))
    print(f"   Found {len(image_files)} images")

    # Pair images with labels
    pairs = []
    for img_path in image_files:
        lbl_path = lbl_dir / (img_path.stem + ".txt")
        if lbl_path.exists():
            pairs.append((str(img_path), str(lbl_path)))

    print(f"   Paired: {len(pairs)} image-label sets")

    # 2. Group by primary class
    class_groups = {0: [], 1: [], 2: []}
    for img_p, lbl_p in pairs:
        cls = get_primary_class(lbl_p)
        if cls in class_groups:
            class_groups[cls].append((img_p, lbl_p))

    print(f"\n[2/5] Class distribution (by primary class in image):")
    for c, items in class_groups.items():
        print(f"   Class {c} ({CLASSES[c]}): {len(items)} images")

    # 3. Augment underrepresented classes
    aug_dir = output_dir / "augmented"
    aug_img_dir = aug_dir / "images"
    aug_lbl_dir = aug_dir / "labels"
    aug_img_dir.mkdir(parents=True, exist_ok=True)
    aug_lbl_dir.mkdir(parents=True, exist_ok=True)

    # Copy all originals first
    print(f"\n[3/5] Copying originals ...")
    for img_p, lbl_p in pairs:
        shutil.copy(img_p, aug_img_dir / Path(img_p).name)
        shutil.copy(lbl_p, aug_lbl_dir / Path(lbl_p).name)

    all_pairs = list(pairs)  # running list

    # Augment classes below target
    for cls_id, target in TARGET_COUNTS.items():
        current = len(class_groups[cls_id])
        needed = target - current
        if needed <= 0:
            print(f"   Class {cls_id} ({CLASSES[cls_id]}): already at target ({current}), skipping augmentation")
            continue

        severity = "heavy" if current < 300 else "medium"
        aug_pipeline = get_augmentation_pipeline(severity)
        print(f"   Augmenting Class {cls_id} ({CLASSES[cls_id]}): {current} -> {target} (need {needed}, severity={severity})")

        source_pairs = class_groups[cls_id]
        aug_count = 0
        aug_idx = 0

        with tqdm(total=needed, desc=f"  Class {cls_id}") as pbar:
            while aug_count < needed:
                src_img, src_lbl = source_pairs[aug_idx % len(source_pairs)]
                stem = Path(src_img).stem
                out_img = str(aug_img_dir / f"aug_{cls_id}_{aug_count}_{stem}.jpeg")
                out_lbl = str(aug_lbl_dir / f"aug_{cls_id}_{aug_count}_{stem}.txt")

                if augment_image(src_img, src_lbl, aug_pipeline, out_img, out_lbl):
                    all_pairs.append((out_img, out_lbl))
                    aug_count += 1
                    pbar.update(1)
                aug_idx += 1

    # 4. Train / Val / Test split
    print(f"\n[4/5] Splitting {len(all_pairs)} total images -> 70/20/10 ...")
    random.shuffle(all_pairs)
    n = len(all_pairs)
    n_train = int(n * 0.70)
    n_val = int(n * 0.20)
    splits = {
        "train": all_pairs[:n_train],
        "val": all_pairs[n_train:n_train + n_val],
        "test": all_pairs[n_train + n_val:],
    }

    final_dir = output_dir / "yolo_dataset"
    for split, split_pairs in splits.items():
        si = final_dir / split / "images"
        sl = final_dir / split / "labels"
        si.mkdir(parents=True, exist_ok=True)
        sl.mkdir(parents=True, exist_ok=True)
        for img_p, lbl_p in split_pairs:
            shutil.copy(img_p, si / Path(img_p).name)
            shutil.copy(lbl_p, sl / Path(lbl_p).name)
        print(f"   {split}: {len(split_pairs)} images")

    # 5. Write dataset.yaml
    dataset_yaml = {
        "path": str(final_dir.absolute()),
        "train": "train/images",
        "val": "val/images",
        "test": "test/images",
        "nc": 3,
        "names": CLASSES,
    }
    yaml_path = final_dir / "dataset.yaml"
    with open(yaml_path, "w") as f:
        yaml.dump(dataset_yaml, f, default_flow_style=False)

    print(f"\n[5/5] Done! Dataset ready at: {final_dir}")
    print(f"      YAML config: {yaml_path}")
    return str(yaml_path)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--zip_path", default="combined_dataset_final.zip")
    parser.add_argument("--output_dir", default="dataset")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--from_dir", default=None, help="Path to already-extracted dataset directory (with images/ and labels/ subdirs)")
    args = parser.parse_args()
    prepare_dataset(args.zip_path, args.output_dir, args.seed, from_dir=args.from_dir)
