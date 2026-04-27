"""
ZooLime: Fusion of LIME + Grad-CAM for Visual Pollution Detection.

ZooLime combines the complementary strengths of:
  • Grad-CAM: Gradient-based, pixel-precise, computationally fast. Shows
              WHICH spatial regions activated the convolutional filters.
  • LIME:     Model-agnostic, region-based, human-interpretable. Shows
              WHICH semantic regions (superpixels) support the prediction.

The fusion produces a more robust and faithful explanation that is both
spatially precise (Grad-CAM) and semantically meaningful (LIME).

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
ZOOLIME ALGORITHM — STEP BY STEP
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

INPUT:  Image I, trained model M, target class c

STEP 1 — Grad-CAM:
  a. Forward-pass I through M, collecting activations at target layer L.
  b. Backpropagate gradient of score(c) to layer L.
  c. Global-average-pool gradients → channel weights α_k.
  d. CAM_raw = ReLU( Σ_k α_k · A_k )  where A_k = activation map channel k
  e. Upsample CAM_raw to image size → G ∈ ℝ^{H×W}
  f. Normalize: G_norm = (G - min(G)) / (max(G) - min(G))  → G_norm ∈ [0,1]

STEP 2 — LIME:
  a. Segment I into superpixels {S_1 … S_n} (QuickShift / SLIC)
  b. For t = 1…T (T=500 samples):
       - Sample binary mask z_t ~ Bernoulli(0.5)^n  (which superpixels to keep)
       - Create perturbed image I_t = I ⊙ z_t  (occlude masked superpixels)
       - Compute f(I_t, c) = model confidence for class c
  c. Fit weighted linear model: w* = argmin_w Σ_t π(z_t) · (f(I_t,c) - w·z_t)²
       where π(z_t) = exp(-D(I,I_t)²/σ²) is proximity kernel
  d. Assign weight w*_j to superpixel S_j
  e. Build pixel map: L[pixel p] = w*_j  for p ∈ S_j
  f. Normalize: L_norm = (|L| - min|L|) / (max|L| - min|L|)  → L_norm ∈ [0,1]

STEP 3 — ZooLime Fusion:
  a. Resize G_norm and L_norm to same resolution (H×W)
  b. Apply Gaussian smoothing to both (σ=5) for spatial coherence
  c. Weighted fusion:
       Z_raw = α · G_norm + (1-α) · L_norm
       where α = 0.6 (Grad-CAM has higher spatial precision)
  d. Multiplicative boost (highlight agreement regions):
       Z_boost = Z_raw + β · (G_norm × L_norm)
       where β = 0.3
  e. Final normalization: Z = (Z_boost - min) / (max - min)

STEP 4 — Visualization:
  a. Apply JET colormap to Z → heatmap H_color
  b. Overlay: final_viz = 0.5 · I + 0.5 · H_color
  c. Draw detection bounding boxes with class labels + confidence
  d. Add colorbar legend

OUTPUT: Z ∈ [0,1]^{H×W}, final_viz ∈ ℝ^{H×W×3}
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

PSEUDO-CODE:
  G = gradcam(model, image, class)               # → [0,1] HxW
  L = lime(model, image, class)                  # → [0,1] HxW
  G_s = gaussian_blur(G, sigma=5)
  L_s = gaussian_blur(L, sigma=5)
  Z_raw = 0.6 * G_s + 0.4 * L_s
  Z_boost = Z_raw + 0.3 * (G_s * L_s)
  Z = normalize(Z_boost)
  output = overlay(image, colormap(Z))
"""

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont
from scipy.ndimage import gaussian_filter
from typing import Tuple, Optional
import time


CLASSES = ["Potholes", "Abandoned_Vehicles", "Construction_Debris"]

# Fusion hyperparameters
ALPHA = 0.6          # Grad-CAM weight (spatial precision)
BETA = 0.3           # Multiplicative agreement boost
SIGMA_GRADCAM = 3.0  # Gaussian smoothing for Grad-CAM
SIGMA_LIME = 5.0     # Gaussian smoothing for LIME (coarser superpixels need more smoothing)


class ZooLime:
    """
    ZooLime: LIME + Grad-CAM Fusion Explainer.

    Produces a single, unified saliency map that combines gradient-based
    spatial precision (Grad-CAM) with perturbation-based semantic
    interpretability (LIME).
    """

    def __init__(self, model, alpha: float = ALPHA, beta: float = BETA):
        """
        Args:
            model: Loaded YOLO model
            alpha: Weight for Grad-CAM in fusion (1-alpha for LIME). Default 0.6.
            beta: Multiplicative agreement boost weight. Default 0.3.
        """
        self.model = model
        self.alpha = alpha
        self.beta = beta

    def explain(
        self,
        image_path: str,
        class_idx: Optional[int] = None,
        lime_samples: int = 500,
        save_path: Optional[str] = None,
    ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """
        Generate ZooLime fusion explanation.

        Args:
            image_path: Path to input image
            class_idx: Target class (auto-detect if None)
            lime_samples: LIME perturbation samples (500 recommended)
            save_path: If provided, save visualization here

        Returns:
            zoolime_map: Fused saliency map [0,1], shape (H, W)
            overlay: Visualization overlay, shape (H, W, 3) RGB
            info: Metadata dict with all intermediate results
        """
        from .gradcam import GradCAM
        from .lime_explainer import LIMEExplainer

        t_start = time.time()

        # Load image dimensions
        img_bgr = cv2.imread(image_path)
        if img_bgr is None:
            raise FileNotFoundError(f"Image not found: {image_path}")
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        H, W = img_rgb.shape[:2]

        # Auto-detect class
        if class_idx is None:
            results = self.model.predict(image_path, conf=0.25, verbose=False)
            class_idx = self._get_primary_class(results)
        class_name = CLASSES[class_idx] if class_idx < len(CLASSES) else f"class_{class_idx}"
        print(f"\n{'─'*55}")
        print(f"  ZooLime Fusion — Target: {class_name}")
        print(f"{'─'*55}")

        # ── STEP 1: Grad-CAM ──────────────────────────────────────────
        print("  [1/3] Running Grad-CAM...")
        t1 = time.time()
        gradcam = GradCAM(self.model)
        try:
            gradcam_map, _, detection_info = gradcam.generate(image_path, class_idx=class_idx)
        finally:
            gradcam.remove_hooks()
        print(f"        Done in {time.time()-t1:.1f}s")

        # ── STEP 2: LIME ──────────────────────────────────────────────
        print(f"  [2/3] Running LIME ({lime_samples} samples)...")
        t2 = time.time()
        lime_exp = LIMEExplainer(self.model, num_samples=lime_samples)
        lime_map, _, lime_info = lime_exp.explain(image_path, class_idx=class_idx)
        print(f"        Done in {time.time()-t2:.1f}s")

        # ── STEP 3: ZooLime Fusion ────────────────────────────────────
        print("  [3/3] Fusing (ZooLime)...")
        zoolime_map = self._fuse(gradcam_map, lime_map)

        # ── STEP 4: Visualization ─────────────────────────────────────
        overlay = self._build_overlay(img_rgb, zoolime_map, gradcam_map, lime_map, detection_info)

        corr_matrix = np.corrcoef(gradcam_map.flatten(), lime_map.flatten())
        corr = float(corr_matrix[0, 1])
        if np.isnan(corr):
            corr = 0.0

        total_time = time.time() - t_start
        info = {
            "class_idx": class_idx,
            "class_name": class_name,
            "alpha": self.alpha,
            "beta": self.beta,
            "gradcam_mean": float(gradcam_map.mean()),
            "lime_mean": float(lime_map.mean()),
            "zoolime_mean": float(zoolime_map.mean()),
            "correlation": corr,
            "lime_fidelity": lime_info.get("score", 0),
            "detections": detection_info["boxes"],
            "total_time_s": round(total_time, 1),
        }
        print(f"  ZooLime complete in {total_time:.1f}s")
        print(f"  Grad-CAM ↔ LIME correlation: {info['correlation']:.3f}")

        if save_path:
            self.save_full_report(image_path, gradcam_map, lime_map, zoolime_map, overlay, info, save_path)

        return zoolime_map, overlay, info

    def _fuse(self, gradcam_map: np.ndarray, lime_map: np.ndarray) -> np.ndarray:
        """
        Core ZooLime fusion function.

        Implements the algorithm documented in the module docstring.
        """
        # Ensure same shape
        H, W = gradcam_map.shape[:2]
        lime_resized = cv2.resize(lime_map, (W, H))

        # Gaussian smoothing for spatial coherence
        G_s = gaussian_filter(gradcam_map.astype(np.float64), sigma=SIGMA_GRADCAM)
        L_s = gaussian_filter(lime_resized.astype(np.float64), sigma=SIGMA_LIME)

        # Re-normalize after smoothing (smoothing can shift range)
        G_s = _minmax_normalize(G_s)
        L_s = _minmax_normalize(L_s)

        # Weighted additive fusion
        Z_raw = self.alpha * G_s + (1.0 - self.alpha) * L_s

        # Multiplicative agreement boost: amplify regions where both agree
        agreement = G_s * L_s  # high only where both are high
        Z_boost = Z_raw + self.beta * agreement

        # Final normalization
        Z = _minmax_normalize(Z_boost)

        return Z.astype(np.float32)

    def _get_primary_class(self, results) -> int:
        if not results or results[0].boxes is None or len(results[0].boxes) == 0:
            return 0
        best_cls, best_conf = 0, 0
        for box in results[0].boxes:
            conf = float(box.conf.item())
            cls = int(box.cls.item())
            if conf > best_conf:
                best_conf, best_cls = conf, cls
        return best_cls

    def _build_overlay(
        self,
        image_rgb: np.ndarray,
        zoolime_map: np.ndarray,
        gradcam_map: np.ndarray,
        lime_map: np.ndarray,
        detection_info: dict,
    ) -> np.ndarray:
        """Build overlay showing ZooLime heatmap on original image with boxes."""
        H, W = image_rgb.shape[:2]

        # Apply JET colormap to ZooLime map
        zm_uint8 = (zoolime_map * 255).astype(np.uint8)
        heatmap_color = cv2.applyColorMap(zm_uint8, cv2.COLORMAP_JET)
        heatmap_color = cv2.cvtColor(heatmap_color, cv2.COLOR_BGR2RGB)

        # Blend
        overlay = cv2.addWeighted(image_rgb, 0.45, heatmap_color, 0.55, 0)

        # Draw bounding boxes
        colors = [(255, 60, 60), (60, 220, 60), (60, 100, 255)]
        for det in detection_info.get("boxes", []):
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            cls_id = det["class_id"]
            color = colors[cls_id % len(colors)]
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 3)
            label = f"{det['class_name']} {det['confidence']:.0%}"
            (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.6, 2)
            cv2.rectangle(overlay, (x1, y1 - th - 8), (x1 + tw + 4, y1), color, -1)
            cv2.putText(overlay, label, (x1 + 2, y1 - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 255), 2)

        # Add ZooLime label
        cv2.putText(overlay, "ZooLime", (8, 28), cv2.FONT_HERSHEY_SIMPLEX, 0.85, (255, 255, 100), 2)

        return overlay

    def save_full_report(
        self,
        image_path: str,
        gradcam_map: np.ndarray,
        lime_map: np.ndarray,
        zoolime_map: np.ndarray,
        overlay: np.ndarray,
        info: dict,
        output_path: str,
    ):
        """
        Save a 4-panel XAI report image:
          [Original] [Grad-CAM] [LIME] [ZooLime Fusion]
        """
        original = cv2.cvtColor(cv2.imread(image_path), cv2.COLOR_BGR2RGB)
        H, W = original.shape[:2]

        def to_heatmap(m, cmap=cv2.COLORMAP_JET):
            h = cv2.applyColorMap((m * 255).astype(np.uint8), cmap)
            h = cv2.cvtColor(h, cv2.COLOR_BGR2RGB)
            return cv2.addWeighted(cv2.resize(original, (W, H)), 0.4, cv2.resize(h, (W, H)), 0.6, 0)

        panels = [
            ("Original", original),
            ("Grad-CAM", to_heatmap(cv2.resize(gradcam_map, (W, H)))),
            ("LIME", to_heatmap(cv2.resize(lime_map, (W, H)), cv2.COLORMAP_HOT)),
            (f"ZooLime (α={self.alpha})", cv2.resize(overlay, (W, H))),
        ]

        # Create panel grid
        label_height = 40
        panel_h = H + label_height
        panel_w = W
        canvas = np.zeros((panel_h, panel_w * 4, 3), dtype=np.uint8)

        for i, (title, panel) in enumerate(panels):
            # Label background
            col_start = i * panel_w
            cv2.rectangle(canvas, (col_start, 0), (col_start + panel_w, label_height), (30, 30, 30), -1)
            cv2.putText(canvas, title, (col_start + 8, label_height - 10),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.7, (220, 220, 100), 2)
            canvas[label_height:, col_start:col_start + panel_w] = cv2.resize(panel, (panel_w, H))

        Image.fromarray(canvas).save(output_path)
        print(f"  ZooLime report saved: {output_path}")


# ── Helpers ───────────────────────────────────────────────────────────────────

def _minmax_normalize(arr: np.ndarray, eps: float = 1e-8) -> np.ndarray:
    """Normalize array to [0, 1]."""
    vmin, vmax = arr.min(), arr.max()
    if vmax - vmin < eps:
        return np.zeros_like(arr)
    return (arr - vmin) / (vmax - vmin)


def run_zoolime(model, image_path: str, class_idx: int = None, save_path: str = None, lime_samples: int = 500):
    """
    Convenience function to run ZooLime fusion.

    Args:
        model: YOLO model
        image_path: Input image path
        class_idx: Target class (auto if None)
        save_path: Output path for visualization (optional)
        lime_samples: LIME perturbation count

    Returns:
        zoolime_map, overlay, info
    """
    zl = ZooLime(model)
    return zl.explain(image_path, class_idx=class_idx, lime_samples=lime_samples, save_path=save_path)
