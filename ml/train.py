"""
Local GPU training for Visual Pollution Detector (YOLOv8).

This is tuned for training on an NVIDIA GPU on your own PC — not Colab.
It auto-detects your GPU's VRAM and picks a safe batch size, so it runs
on anything from a GTX 1660 (6 GB) up to an RTX 4090.

Usage:
    # First prepare the dataset (one time):
    python data_prep.py --zip_path ../combined_dataset_final.zip --output_dir ../dataset

    # Then train:
    python train.py                                  # default: yolov8s, auto batch, 60 epochs
    python train.py --model yolov8n --epochs 100     # lighter model, more epochs
    python train.py --model yolov8m --batch 8        # medium model, fixed batch
    python train.py --resume                         # resume from last checkpoint
"""
import argparse
import os
import sys
from pathlib import Path
import torch
from ultralytics import YOLO


# ── Auto batch sizing by VRAM ─────────────────────────────────────────────────
# These are conservative so other programs can still run while training.
def pick_batch_size(model_name: str) -> int:
    """Pick a batch size that fits in the GPU's available VRAM."""
    if not torch.cuda.is_available():
        print("  [WARN] No CUDA GPU detected. Training on CPU will be extremely slow.")
        return 4
    props = torch.cuda.get_device_properties(0)
    vram_gb = props.total_memory / (1024 ** 3)
    print(f"  GPU: {props.name}  ({vram_gb:.1f} GB VRAM)")

    # Model-size-aware defaults (values tested at imgsz=640)
    table = {
        "yolov8n": {6: 16, 8: 24, 10: 32, 12: 48, 16: 64, 24: 96},
        "yolov8s": {6: 8,  8: 16, 10: 24, 12: 32, 16: 48, 24: 64},
        "yolov8m": {6: 4,  8: 8,  10: 12, 12: 16, 16: 24, 24: 40},
        "yolov8l": {6: 2,  8: 4,  10: 8,  12: 12, 16: 16, 24: 24},
        "yolov8x": {6: 1,  8: 2,  10: 4,  12: 6,  16: 10, 24: 16},
    }
    tier_map = table.get(model_name, table["yolov8s"])
    # Pick the largest tier that fits, then back off by 25% for safety margin
    thresholds = sorted(tier_map.keys())
    for t in reversed(thresholds):
        if vram_gb >= t:
            bs = max(2, int(tier_map[t] * 0.75))
            return bs
    return 4


# ── Training hyperparameters ──────────────────────────────────────────────────
def get_hparams(epochs: int) -> dict:
    return {
        "epochs":        epochs,
        "patience":      20,            # early stopping if no mAP improvement for 20 epochs
        "imgsz":         640,
        "optimizer":     "AdamW",
        "lr0":           0.001,
        "lrf":           0.01,          # final_lr = lr0 * lrf
        "momentum":      0.937,
        "weight_decay":  0.0005,
        "warmup_epochs": 3,
        "cos_lr":        True,          # cosine LR schedule

        # ── Augmentation (on top of what data_prep.py already did) ─────────
        "mosaic":        1.0,
        "mixup":         0.15,
        "copy_paste":    0.1,
        "degrees":       10.0,
        "translate":     0.1,
        "scale":         0.5,
        "shear":         2.0,
        "perspective":   0.0003,
        "flipud":        0.05,
        "fliplr":        0.5,
        "hsv_h":         0.015,
        "hsv_s":         0.7,
        "hsv_v":         0.4,

        # ── Loss weights ───────────────────────────────────────────────────
        "box": 7.5, "cls": 0.5, "dfl": 1.5,

        # ── Speed / precision ──────────────────────────────────────────────
        "amp":     True,     # mixed-precision — big speedup, tiny accuracy hit
        "workers": 4,
        "cache":   False,    # set True if you have 16+ GB RAM and want max speed
    }


def train(args):
    # ── GPU info ─────────────────────────────────────────────────────────────
    print()
    print("=" * 60)
    print("  Visual Pollution Detector — Local GPU Training")
    print("=" * 60)

    if torch.cuda.is_available():
        device = 0
        print(f"  CUDA:      {torch.version.cuda}")
        print(f"  PyTorch:   {torch.__version__}")
    else:
        device = "cpu"
        print("  [WARNING] No CUDA GPU — training on CPU will take hours per epoch.")
        print("            Check: python -c \"import torch; print(torch.cuda.is_available())\"")

    # ── Batch size ───────────────────────────────────────────────────────────
    batch = args.batch if args.batch > 0 else pick_batch_size(args.model)
    print(f"  Model:     {args.model}.pt")
    print(f"  Batch:     {batch}  {'(auto)' if args.batch <= 0 else '(user)'}")
    print(f"  Epochs:    {args.epochs}")
    print(f"  Data YAML: {args.data}")
    print(f"  Output:    {args.project}/{args.name}")
    print("=" * 60)
    print()

    # ── Sanity-check data yaml exists ────────────────────────────────────────
    if not Path(args.data).exists():
        print(f"[ERROR] Data YAML not found: {args.data}")
        print("        Run data_prep.py first:")
        print("          python data_prep.py --zip_path ../combined_dataset_final.zip --output_dir ../dataset")
        sys.exit(1)

    # ── Load model ───────────────────────────────────────────────────────────
    # Prefer local weights if already downloaded
    local_weights = Path(__file__).parent / "weights" / f"{args.model}.pt"
    model_path = str(local_weights) if local_weights.exists() else f"{args.model}.pt"
    print(f"  Starting from: {model_path}")

    model = YOLO(model_path)

    # ── Train ────────────────────────────────────────────────────────────────
    hparams = get_hparams(args.epochs)
    results = model.train(
        data=args.data,
        project=args.project,
        name=args.name,
        exist_ok=True,
        resume=args.resume,
        device=device,
        batch=batch,
        plots=True,
        save=True,
        save_period=-1,    # only save best + last (saves disk)
        verbose=True,
        val=True,
        **hparams,
    )

    best = Path(args.project) / args.name / "weights" / "best.pt"
    print()
    print("=" * 60)
    print("  Training complete!")
    print("=" * 60)
    print(f"  Best weights: {best.absolute()}")
    print(f"  Plots/curves: {Path(args.project) / args.name}")
    print()
    print("  The backend auto-loads this path on startup. Restart your backend:")
    print("    (Ctrl+C in run_backend terminal, then run it again)")
    print()

    # ── Evaluate on test set ─────────────────────────────────────────────────
    if best.exists():
        print("Running evaluation on test set ...")
        try:
            metrics = model.val(data=args.data, split="test", plots=True)
            print()
            print("  Test-set metrics:")
            print(f"    mAP50:     {metrics.box.map50:.4f}")
            print(f"    mAP50-95:  {metrics.box.map:.4f}")
            print(f"    Precision: {metrics.box.mp:.4f}")
            print(f"    Recall:    {metrics.box.mr:.4f}")
            classes = ["Potholes", "Abandoned_Vehicles", "Construction_Debris"]
            if hasattr(metrics.box, "ap50"):
                print()
                print("  Per-class AP50:")
                for i, ap in enumerate(metrics.box.ap50):
                    print(f"    {classes[i]:25s}: {ap:.4f}")
        except Exception as e:
            print(f"  [WARN] Evaluation skipped: {e}")

    return str(best)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Train visual pollution detector locally on GPU")
    parser.add_argument("--data",    default="../dataset/yolo_dataset/dataset.yaml",
                        help="Path to dataset.yaml from data_prep.py")
    parser.add_argument("--model",   default="yolov8s",
                        choices=["yolov8n", "yolov8s", "yolov8m", "yolov8l", "yolov8x"],
                        help="YOLOv8 size. n=nano (fastest), s=small (recommended), m/l/x need 8+/12+/16+ GB VRAM")
    parser.add_argument("--epochs",  type=int, default=60,   help="Training epochs (60 is usually enough)")
    parser.add_argument("--batch",   type=int, default=-1,   help="Batch size (-1 = auto from VRAM)")
    parser.add_argument("--project", default="runs",         help="Output dir")
    parser.add_argument("--name",    default="visual_pollution_v1", help="Run name (= subfolder)")
    parser.add_argument("--resume",  action="store_true",    help="Resume from last checkpoint")
    args = parser.parse_args()

    train(args)
