"""
SHAP (SHapley Additive exPlanations) for Visual Pollution Detector.

NOTE: SHAP with deep models is computationally expensive.
This module uses GradientExplainer (fastest for CNNs) and is intended
for DEMONSTRATION / offline reporting only, NOT real-time inference.

Reference: Lundberg & Lee, 2017. "A Unified Approach to Interpreting
           Model Predictions."
"""

import numpy as np
import torch
import cv2
from PIL import Image
from pathlib import Path
import warnings
warnings.filterwarnings("ignore")

CLASSES = ["Potholes", "Abandoned_Vehicles", "Construction_Debris"]


class SHAPExplainer:
    """
    SHAP explainer for the visual pollution model.

    Uses GradientExplainer which leverages backpropagation to estimate
    Shapley values efficiently for image inputs.
    """

    def __init__(self, model, background_images_dir: str = None, n_background: int = 20):
        """
        Args:
            model: Loaded YOLO model
            background_images_dir: Directory of background images for SHAP baseline.
                                   If None, uses random noise as baseline.
            n_background: Number of background samples
        """
        self.model = model
        self.n_background = n_background
        self.background = self._load_background(background_images_dir, n_background)

    def _load_background(self, bg_dir: str, n: int) -> torch.Tensor:
        """Load background images or create random baseline."""
        if bg_dir and Path(bg_dir).exists():
            imgs = []
            for p in Path(bg_dir).glob("*.jpg")[:n]:
                img = cv2.imread(str(p))
                if img is not None:
                    img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
                    img = cv2.resize(img, (640, 640)).astype(np.float32) / 255.0
                    imgs.append(np.transpose(img, (2, 0, 1)))
            if imgs:
                return torch.from_numpy(np.stack(imgs))

        # Fallback: random noise background (uniform gray)
        print("  SHAP: using random noise background (provide background images for better results)")
        background = np.full((n, 3, 640, 640), 0.5, dtype=np.float32)
        background += np.random.normal(0, 0.02, background.shape)
        return torch.from_numpy(background.astype(np.float32))

    def _get_backbone_model(self):
        """Extract the backbone as a standalone callable for SHAP."""
        backbone = self.model.model.model if hasattr(self.model.model, 'model') else self.model.model

        class BackboneWrapper(torch.nn.Module):
            """Wraps YOLO backbone to output a single class confidence vector."""
            def __init__(self, full_model, cls_idx):
                super().__init__()
                self.full_model = full_model
                self.cls_idx = cls_idx

            def forward(self, x):
                out = self.full_model(x)
                if isinstance(out, (list, tuple)):
                    out = out[0] if isinstance(out[0], torch.Tensor) else out[0][0]
                if out.dim() == 3:
                    if out.shape[1] > out.shape[2]:
                        scores = out[:, 4 + self.cls_idx, :]
                    else:
                        scores = out[:, :, 4 + self.cls_idx]
                    return scores.max(dim=-1, keepdim=True)[0]
                return out[:, :1]

        return BackboneWrapper

    def explain(
        self,
        image_path: str,
        class_idx: int = 0,
        n_evals: int = 200,
    ) -> tuple:
        """
        Generate SHAP explanation (DEMO mode — runs offline).

        Args:
            image_path: Path to image
            class_idx: Class to explain (0, 1, or 2)
            n_evals: Number of evaluations (more = more accurate, slower)

        Returns:
            shap_map: Normalized SHAP importance map [0,1], shape (H, W)
            overlay: RGB overlay image
            info: Explanation metadata dict
        """
        try:
            import shap
        except ImportError:
            raise ImportError("Install shap: pip install shap")

        # Load image
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Image not found: {image_path}")
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        H, W = img_rgb.shape[:2]

        # Preprocess
        img_resized = cv2.resize(img_rgb, (640, 640)).astype(np.float32) / 255.0
        img_tensor = torch.from_numpy(np.transpose(img_resized, (2, 0, 1))).unsqueeze(0)

        print(f"  SHAP: explaining class {CLASSES[class_idx]}...")
        print(f"  SHAP: {n_evals} evaluations × {self.n_background} background samples")
        print(f"  SHAP: estimated time ~2-5 minutes (demo mode)")

        # Build wrapper model
        BackboneWrapper = self._get_backbone_model()
        wrapper = BackboneWrapper(
            self.model.model.model if hasattr(self.model.model, 'model') else self.model.model,
            class_idx,
        )
        wrapper.eval()

        # Use GradientExplainer (faster than KernelExplainer for CNNs)
        explainer = shap.GradientExplainer(wrapper, self.background)

        shap_values = explainer.shap_values(img_tensor, nsamples=n_evals)  # (1, 3, 640, 640)

        # Convert to pixel importance map
        if isinstance(shap_values, list):
            sv = shap_values[0]
        else:
            sv = shap_values

        sv = sv.squeeze()  # (3, 640, 640)
        # Average over color channels, take absolute value
        sv_mean = np.abs(sv).mean(axis=0)  # (640, 640)

        # Resize to original image size
        shap_map = cv2.resize(sv_mean, (W, H))

        # Normalize to [0, 1]
        smin, smax = shap_map.min(), shap_map.max()
        if smax - smin > 1e-8:
            shap_map = (shap_map - smin) / (smax - smin)

        shap_map = shap_map.astype(np.float32)
        overlay = self._build_overlay(img_rgb, shap_map)

        info = {
            "class_idx": class_idx,
            "class_name": CLASSES[class_idx],
            "mean_abs_shap": float(np.abs(sv_mean).mean()),
            "top_pixel_value": float(shap_map.max()),
            "n_evaluations": n_evals,
            "method": "GradientExplainer",
            "note": "DEMO mode — not for real-time use",
        }
        print(f"  SHAP: done. Mean |SHAP| = {info['mean_abs_shap']:.6f}")
        return shap_map, overlay, info

    def _build_overlay(self, image_rgb: np.ndarray, shap_map: np.ndarray) -> np.ndarray:
        """Apply SHAP heatmap overlay (red = high contribution)."""
        shap_uint8 = (shap_map * 255).astype(np.uint8)
        heatmap = cv2.applyColorMap(shap_uint8, cv2.COLORMAP_INFERNO)
        heatmap = cv2.cvtColor(heatmap, cv2.COLOR_BGR2RGB)
        overlay = cv2.addWeighted(image_rgb, 0.55, heatmap, 0.45, 0)
        return overlay

    def save_visualization(self, original_path: str, shap_map: np.ndarray, overlay: np.ndarray, output_path: str):
        """Save SHAP visualization."""
        original = cv2.cvtColor(cv2.imread(original_path), cv2.COLOR_BGR2RGB)
        H, W = original.shape[:2]
        shap_color = cv2.applyColorMap((shap_map * 255).astype(np.uint8), cv2.COLORMAP_INFERNO)
        shap_color = cv2.cvtColor(cv2.resize(shap_color, (W, H)), cv2.COLOR_BGR2RGB)
        combined = np.hstack([original, shap_color, cv2.resize(overlay, (W, H))])
        Image.fromarray(combined).save(output_path)
        print(f"  SHAP visualization saved: {output_path}")
