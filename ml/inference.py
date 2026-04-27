"""
Inference pipeline for Visual Pollution Detector.

This module is called by the FastAPI backend to:
1. Run YOLO detection
2. Generate Grad-CAM (default, fast)
3. Generate LIME (on-demand)
4. Generate SHAP (demo only)
5. Generate ZooLime fusion
6. Build the structured result for report generation

Usage:
    from inference import PollutionInferenceEngine
    engine = PollutionInferenceEngine("runs/visual_pollution_v1/weights/best.pt")
    result = engine.run(image_path, xai_mode="gradcam")
"""

import os
import time
import base64
import tempfile
import numpy as np
import cv2
from pathlib import Path
from typing import Optional, Literal
from ultralytics import YOLO
from PIL import Image
import io

from xai.gradcam import GradCAM
from xai.lime_explainer import LIMEExplainer
from xai.shap_explainer import SHAPExplainer
from xai.zoolime import ZooLime

CLASSES = ["Potholes", "Abandoned_Vehicles", "Construction_Debris"]
SEVERITY_THRESHOLDS = {
    "LOW": 0.40,
    "MEDIUM": 0.60,
    "HIGH": 0.80,
}


class PollutionInferenceEngine:
    """
    Main inference engine combining YOLO detection + XAI explanation.
    """

    def __init__(self, weights_path: str, conf_threshold: float = 0.20):
        """
        Args:
            weights_path: Path to trained YOLOv8 weights (.pt or .onnx)
            conf_threshold: Detection confidence threshold
        """
        if not Path(weights_path).exists():
            raise FileNotFoundError(f"Model weights not found: {weights_path}")

        print(f"Loading model: {weights_path}")
        self.model = YOLO(weights_path)
        self.conf_threshold = conf_threshold
        self.weights_path = weights_path
        print("Model loaded successfully")

    def run(
        self,
        image_path: str,
        xai_mode: Literal["gradcam", "lime", "zoolime", "shap", "none"] = "gradcam",
        lime_samples: int = 500,
        class_idx: Optional[int] = None,
    ) -> dict:
        """
        Run full inference + XAI pipeline on an image.

        Args:
            image_path: Path to input image
            xai_mode: XAI method to use
                - "gradcam": Grad-CAM only (fast, default)
                - "lime":    LIME only (medium, 30-60s)
                - "zoolime": Full ZooLime fusion (comprehensive, 1-2min)
                - "shap":    SHAP demo (very slow, demo only)
                - "none":    Detection only, no XAI
            lime_samples: LIME perturbation count (500 default)
            class_idx: Force specific class for XAI (auto if None)

        Returns:
            result dict with structure:
            {
                "detections": [...],
                "primary_class": str,
                "confidence": float,
                "severity": str,
                "xai": {
                    "method": str,
                    "heatmap_b64": str,   # base64 PNG
                    "overlay_b64": str,   # base64 PNG
                    "metadata": dict,
                },
                "inference_time_ms": int,
            }
        """
        t_start = time.time()

        # Validate image
        img = cv2.imread(image_path)
        if img is None:
            raise ValueError(f"Cannot read image: {image_path}")

        # ── Detection ────────────────────────────────────────────────
        results = self.model.predict(
            image_path,
            conf=self.conf_threshold,
            verbose=False,
            imgsz=640,
        )
        detections = self._parse_detections(results)
        primary = self._get_primary_detection(detections)

        target_cls = class_idx
        if target_cls is None and primary:
            target_cls = primary["class_id"]
        elif target_cls is None:
            target_cls = 0

        # Severity score based on max confidence
        max_conf = max([d["confidence"] for d in detections], default=0.0)
        severity = self._compute_severity(max_conf, detections)

        # ── XAI ─────────────────────────────────────────────────────
        xai_result = {"method": xai_mode, "heatmap_b64": None, "overlay_b64": None, "metadata": {}}

        if xai_mode != "none":
            xai_result = self._run_xai(image_path, xai_mode, target_cls, lime_samples)

        # ── Build result ─────────────────────────────────────────────
        inference_ms = int((time.time() - t_start) * 1000)

        return {
            "detections": detections,
            "primary_class": primary["class_name"] if primary else "none",
            "primary_class_id": primary["class_id"] if primary else -1,
            "confidence": round(max_conf, 4),
            "severity": severity,
            "severity_score": self._severity_score(detections),
            "num_detections": len(detections),
            "xai": xai_result,
            "inference_time_ms": inference_ms,
        }

    def run_from_bytes(self, image_bytes: bytes, **kwargs) -> dict:
        """Run inference on raw image bytes (from API upload)."""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        try:
            return self.run(tmp_path, **kwargs)
        finally:
            os.unlink(tmp_path)

    def _run_xai(self, image_path: str, mode: str, class_idx: int, lime_samples: int) -> dict:
        """Dispatch to the appropriate XAI method."""
        xai_data = {"method": mode, "heatmap_b64": None, "overlay_b64": None, "metadata": {}}

        try:
            if mode == "gradcam":
                cam = GradCAM(self.model)
                try:
                    hmap, overlay, info = cam.generate(image_path, class_idx=class_idx)
                finally:
                    cam.remove_hooks()
                xai_data["heatmap_b64"] = _array_to_b64(hmap, colormap=True)
                xai_data["overlay_b64"] = _array_to_b64(overlay)
                xai_data["metadata"] = {
                    "class_idx": class_idx,
                    "class_name": CLASSES[class_idx],
                    "detections": info["boxes"],
                }

            elif mode == "lime":
                lime = LIMEExplainer(self.model, num_samples=lime_samples)
                lmap, overlay, info = lime.explain(image_path, class_idx=class_idx)
                xai_data["heatmap_b64"] = _array_to_b64(lmap, colormap=True, cmap=cv2.COLORMAP_HOT)
                xai_data["overlay_b64"] = _array_to_b64(overlay)
                xai_data["metadata"] = info

            elif mode == "zoolime":
                zl = ZooLime(self.model)
                zmap, overlay, info = zl.explain(image_path, class_idx=class_idx, lime_samples=lime_samples)
                xai_data["heatmap_b64"] = _array_to_b64(zmap, colormap=True)
                xai_data["overlay_b64"] = _array_to_b64(overlay)
                xai_data["metadata"] = info

            elif mode == "shap":
                shap_exp = SHAPExplainer(self.model)
                smap, overlay, info = shap_exp.explain(image_path, class_idx=class_idx)
                xai_data["heatmap_b64"] = _array_to_b64(smap, colormap=True, cmap=cv2.COLORMAP_INFERNO)
                xai_data["overlay_b64"] = _array_to_b64(overlay)
                xai_data["metadata"] = info

        except Exception as e:
            print(f"  XAI ({mode}) failed: {e}")
            xai_data["metadata"]["error"] = str(e)

        return xai_data

    def _parse_detections(self, results) -> list:
        boxes = []
        if not results or results[0].boxes is None:
            return boxes
        for box in results[0].boxes:
            cls_id = int(box.cls.item())
            conf = float(box.conf.item())
            x1, y1, x2, y2 = box.xyxy[0].tolist()
            area = (x2 - x1) * (y2 - y1)
            boxes.append({
                "class_id": cls_id,
                "class_name": CLASSES[cls_id] if cls_id < len(CLASSES) else f"class_{cls_id}",
                "confidence": round(conf, 4),
                "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                "area_px": round(area, 1),
            })
        # Sort by confidence
        return sorted(boxes, key=lambda x: x["confidence"], reverse=True)

    def _get_primary_detection(self, detections: list) -> Optional[dict]:
        return detections[0] if detections else None

    def _compute_severity(self, confidence: float, detections: list) -> str:
        """
        Severity classification:
        - Based on confidence score AND number of detections AND detection area.
        """
        score = self._severity_score(detections)
        if score >= 0.75:
            return "HIGH"
        elif score >= 0.45:
            return "MEDIUM"
        else:
            return "LOW"

    def _severity_score(self, detections: list) -> float:
        """
        Composite severity score [0,1] combining:
        - Max confidence: 50%
        - Detection count: 30%
        - Largest area ratio: 20%
        """
        if not detections:
            return 0.0
        max_conf = max(d["confidence"] for d in detections)
        count_score = min(len(detections) / 5.0, 1.0)
        max_area = max(d["area_px"] for d in detections)
        area_score = min(max_area / (640 * 640 * 0.25), 1.0)  # 25% of image = max
        return round(0.5 * max_conf + 0.3 * count_score + 0.2 * area_score, 4)


# ── Helpers ───────────────────────────────────────────────────────────────────

def _array_to_b64(arr: np.ndarray, colormap: bool = False, cmap: int = cv2.COLORMAP_JET) -> str:
    """Convert numpy array to base64-encoded PNG string."""
    if arr.dtype != np.uint8:
        arr_uint8 = (np.clip(arr, 0, 1) * 255).astype(np.uint8)
    else:
        arr_uint8 = arr

    if colormap and arr_uint8.ndim == 2:
        arr_uint8 = cv2.cvtColor(cv2.applyColorMap(arr_uint8, cmap), cv2.COLOR_BGR2RGB)

    if arr_uint8.ndim == 2:
        img = Image.fromarray(arr_uint8, mode="L")
    else:
        img = Image.fromarray(arr_uint8, mode="RGB")

    buf = io.BytesIO()
    img.save(buf, format="PNG", optimize=True)
    return base64.b64encode(buf.getvalue()).decode("utf-8")
