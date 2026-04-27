"""
LIME (Local Interpretable Model-agnostic Explanations) for Visual Pollution Detector.

LIME perturbs the image (masks superpixels) and fits a local linear model
to explain which image regions support the predicted class.

Reference: Ribeiro et al., 2016. "Why Should I Trust You?": Explaining the
           Predictions of Any Classifier.
"""

import numpy as np
import cv2
from PIL import Image
from typing import Tuple, Optional
from lime import lime_image
from lime.wrappers.scikit_image import SegmentationAlgorithm
import warnings
warnings.filterwarnings("ignore")


CLASSES = ["Potholes", "Abandoned_Vehicles", "Construction_Debris"]


class LIMEExplainer:
    """
    LIME explainer for YOLOv8 visual pollution detection.

    Wraps the YOLO model as a classifier (using max-confidence detection
    per class) so LIME can perturb inputs and measure prediction changes.
    """

    def __init__(self, model, num_samples: int = 500, random_seed: int = 42):
        """
        Args:
            model: Loaded YOLO model (ultralytics)
            num_samples: LIME perturbation samples. Higher = more accurate but slower.
                         500 is a good balance; use 1000 for final reports.
            random_seed: For reproducibility
        """
        self.model = model
        self.num_samples = num_samples
        self.random_seed = random_seed
        self.explainer = lime_image.LimeImageExplainer(random_state=random_seed)

    def _predict_fn(self, images: np.ndarray) -> np.ndarray:
        """
        Prediction function for LIME.

        LIME passes batches of perturbed images (H, W, 3) uint8.
        We must return (N, num_classes) probability scores.
        """
        scores = np.zeros((len(images), len(CLASSES)), dtype=np.float32)

        for i, img in enumerate(images):
            try:
                results = self.model.predict(
                    img,
                    conf=0.01,           # Low threshold to get all detections
                    verbose=False,
                    imgsz=640,
                )
                if results and results[0].boxes is not None and len(results[0].boxes) > 0:
                    for box in results[0].boxes:
                        cls_id = int(box.cls.item())
                        conf = float(box.conf.item())
                        if 0 <= cls_id < len(CLASSES):
                            scores[i, cls_id] = max(scores[i, cls_id], conf)
            except Exception:
                pass  # Leave as zeros

        # Normalize rows to sum to 1 (make it a probability distribution)
        row_sums = scores.sum(axis=1, keepdims=True)
        row_sums = np.where(row_sums == 0, 1.0, row_sums)
        return scores / row_sums

    def explain(
        self,
        image_path: str,
        class_idx: Optional[int] = None,
        num_features: int = 10,
        segmentation_fn: str = "quickshift",
    ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """
        Generate LIME explanation for an image.

        Args:
            image_path: Path to input image
            class_idx: Target class to explain. None = auto-detect from model.
            num_features: Number of superpixels to highlight in explanation.
            segmentation_fn: Segmentation method ('quickshift', 'slic', 'felzenszwalb')

        Returns:
            lime_map: Normalized importance map [0,1], shape (H, W)
            overlay: Original image with LIME overlay, shape (H, W, 3)
            explanation_info: Dict with superpixel weights and metadata
        """
        # Load image
        img = cv2.imread(image_path)
        if img is None:
            raise FileNotFoundError(f"Image not found: {image_path}")
        img_rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        H, W = img_rgb.shape[:2]

        # Auto-detect target class
        if class_idx is None:
            results = self.model.predict(image_path, conf=0.25, verbose=False)
            class_idx = self._get_primary_class(results)
        class_name = CLASSES[class_idx] if class_idx < len(CLASSES) else f"class_{class_idx}"
        print(f"  LIME explaining class: {class_name} (idx={class_idx})")
        print(f"  Running {self.num_samples} perturbations... (this takes ~30-60 seconds)")

        # Configure segmentation
        if segmentation_fn == "quickshift":
            seg_fn = SegmentationAlgorithm(
                "quickshift", kernel_size=4, max_dist=200, ratio=0.2, random_seed=self.random_seed
            )
        elif segmentation_fn == "slic":
            seg_fn = SegmentationAlgorithm("slic", n_segments=80, compactness=10)
        else:
            seg_fn = SegmentationAlgorithm("felzenszwalb", scale=100, sigma=0.8, min_size=50)

        # Run LIME
        explanation = self.explainer.explain_instance(
            img_rgb,
            self._predict_fn,
            labels=[class_idx],
            hide_color=0,
            num_samples=self.num_samples,
            segmentation_fn=seg_fn,
            batch_size=16,
        )

        # Extract superpixel weights for target class
        segments = explanation.segments
        local_weights = dict(explanation.local_exp.get(class_idx, []))

        # Build pixel-level importance map
        lime_map = self._build_importance_map(segments, local_weights, H, W)

        # Build overlay visualization
        overlay = self._build_overlay(img_rgb, explanation, class_idx, num_features)

        # LIME's `intercept` and `score` attributes are dicts keyed by class_idx
        # in older versions but floats in newer versions. Handle both.
        def _safe_get(attr, key, default=0):
            if isinstance(attr, dict):
                return attr.get(key, default)
            try:
                return float(attr)
            except Exception:
                return default

        fidelity = _safe_get(explanation.score, class_idx, 0.0)
        intercept = _safe_get(explanation.intercept, class_idx, 0.0)

        top_weights_raw = sorted(local_weights.items(), key=lambda x: abs(x[1]), reverse=True)[:10]
        top_weights_clean = [(int(k), float(v)) for k, v in top_weights_raw]

        explanation_info = {
            "class_idx": int(class_idx),
            "class_name": class_name,
            "num_superpixels": int(len(np.unique(segments))),
            "top_weights": top_weights_clean,
            "intercept": float(intercept),
            "score": float(fidelity),
        }
        print(f"  LIME fidelity score: {fidelity:.4f}")

        return lime_map, overlay, explanation_info

    def _get_primary_class(self, results) -> int:
        """Extract highest-confidence class from YOLO results."""
        if not results or results[0].boxes is None or len(results[0].boxes) == 0:
            return 0
        best_cls, best_conf = 0, 0
        for box in results[0].boxes:
            conf = float(box.conf.item())
            cls = int(box.cls.item())
            if conf > best_conf:
                best_conf, best_cls = conf, cls
        return best_cls

    def _build_importance_map(self, segments: np.ndarray, weights: dict, H: int, W: int) -> np.ndarray:
        """
        Convert LIME superpixel weights to a pixel-level map.

        Positive weights = regions supporting the prediction.
        Negative weights = regions opposing the prediction.
        Output is normalized to [0, 1].
        """
        importance_map = np.zeros((H, W), dtype=np.float32)
        for seg_id, weight in weights.items():
            importance_map[segments == seg_id] = weight

        # Normalize to [0, 1] — take absolute value for heatmap
        abs_map = np.abs(importance_map)
        vmin, vmax = abs_map.min(), abs_map.max()
        if vmax - vmin > 1e-8:
            abs_map = (abs_map - vmin) / (vmax - vmin)

        return abs_map.astype(np.float32)

    def _build_overlay(self, image_rgb: np.ndarray, explanation, class_idx: int, num_features: int) -> np.ndarray:
        """Build visual overlay showing positive (green) and negative (red) superpixels."""
        # Get positive regions
        temp_pos, mask_pos = explanation.get_image_and_mask(
            class_idx,
            positive_only=True,
            num_features=num_features,
            hide_rest=False,
        )

        # Get negative regions
        temp_neg, mask_neg = explanation.get_image_and_mask(
            class_idx,
            positive_only=False,
            negative_only=True,
            num_features=num_features,
            hide_rest=False,
        )

        overlay = image_rgb.copy().astype(np.float32)

        # Green tint for positive regions
        if mask_pos.any():
            overlay[mask_pos == 1, 0] = overlay[mask_pos == 1, 0] * 0.4        # reduce R
            overlay[mask_pos == 1, 1] = np.clip(overlay[mask_pos == 1, 1] * 0.6 + 120, 0, 255)  # boost G
            overlay[mask_pos == 1, 2] = overlay[mask_pos == 1, 2] * 0.4        # reduce B

        # Red tint for negative regions
        if mask_neg.any():
            overlay[mask_neg == 1, 0] = np.clip(overlay[mask_neg == 1, 0] * 0.6 + 120, 0, 255)
            overlay[mask_neg == 1, 1] = overlay[mask_neg == 1, 1] * 0.4
            overlay[mask_neg == 1, 2] = overlay[mask_neg == 1, 2] * 0.4

        return overlay.astype(np.uint8)

    def save_visualization(self, original_path: str, lime_map: np.ndarray, overlay: np.ndarray, output_path: str):
        """Save LIME explanation visualization."""
        original = cv2.cvtColor(cv2.imread(original_path), cv2.COLOR_BGR2RGB)
        H, W = original.shape[:2]

        # Resize if needed
        lime_color = cv2.applyColorMap((lime_map * 255).astype(np.uint8), cv2.COLORMAP_HOT)
        lime_color = cv2.cvtColor(cv2.resize(lime_color, (W, H)), cv2.COLOR_BGR2RGB)
        overlay_resized = cv2.resize(overlay, (W, H))

        # Add title text
        combined = np.hstack([original, lime_color, overlay_resized])
        Image.fromarray(combined).save(output_path)
        print(f"  LIME visualization saved: {output_path}")
