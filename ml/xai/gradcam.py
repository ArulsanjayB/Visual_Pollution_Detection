"""
Grad-CAM (Gradient-weighted Class Activation Mapping) for YOLOv8.

Generates a heatmap showing which image regions most influenced the model's
prediction — critical for explainable AI in municipal reporting.

CRITICAL IMPLEMENTATION NOTE:
  The Ultralytics YOLO wrapper's `.model(x)` method triggers a full training
  run in recent versions because it sees `.train()` being called. To avoid this
  we operate on the underlying `nn.Module` (DetectionModel) directly, calling
  `.forward()` in eval mode with `torch.enable_grad()` instead of `.train()`.

Reference: Selvaraju et al., 2017. "Grad-CAM: Visual Explanations from Deep
           Networks via Gradient-based Localization."
"""

import cv2
import numpy as np
import torch
import torch.nn.functional as F
from PIL import Image
from typing import Optional, Tuple
from pathlib import Path


class GradCAM:
    """
    Grad-CAM implementation for YOLOv8.

    Hooks into a late-stage Conv2d layer from the BACKBONE/NECK (not the
    detection head) to capture gradients and activations.
    """

    def __init__(self, model, target_layer_name: str = "auto"):
        """
        Args:
            model: Loaded ultralytics YOLO model
            target_layer_name: Layer to hook. "auto" picks the last Conv2d in
                               the backbone (before the detection head).
        """
        # Get the raw nn.Module inside the Ultralytics wrapper.
        # Chain: YOLO -> DetectionModel -> nn.Sequential of layers
        self.yolo = model
        self.torch_model = model.model  # DetectionModel (nn.Module)
        self.device = next(self.torch_model.parameters()).device
        self.torch_model.eval()

        # Disable inplace operations which cause backward pass hook errors
        for m in self.torch_model.modules():
            if hasattr(m, 'inplace'):
                m.inplace = False

        self.gradients: Optional[torch.Tensor] = None
        self.activations: Optional[torch.Tensor] = None
        self._hook_handles = []
        self._register_hooks(target_layer_name)

    def _find_target_layer(self, target_layer_name: str):
        """
        Find the target convolutional layer.

        For YOLOv8 the backbone ends around layer 9 (SPPF), and the neck runs
        layers 10-21. The detection head is layer 22 (model.22.*). We want a
        late neck layer — typically the last Conv2d before the head.
        """
        # nn_model is the DetectionModel, which has a .model attribute that
        # is an nn.Sequential of the 23 YOLOv8 layers.
        nn_model = self.torch_model

        if target_layer_name == "auto":
            # Find the last Conv2d that lives OUTSIDE the detection head (model.22).
            target_name = None
            target_module = None
            for name, module in nn_model.named_modules():
                # Skip anything inside the detection head
                if name.startswith("model.22"):
                    continue
                if isinstance(module, torch.nn.Conv2d):
                    target_name = name
                    target_module = module
            if target_module is None:
                raise RuntimeError("Could not find a Conv2d layer in the backbone/neck")
            print(f"  Grad-CAM target layer: {target_name}")
            return target_module
        else:
            for name, module in nn_model.named_modules():
                if name == target_layer_name:
                    return module
            raise ValueError(f"Layer '{target_layer_name}' not found in model")

    def _register_hooks(self, target_layer_name: str):
        """Register forward and backward hooks on the target layer."""
        layer = self._find_target_layer(target_layer_name)

        def forward_hook(module, input, output):
            # Save activations so we can use them in backward pass
            self.activations = output

        def backward_hook(module, grad_input, grad_output):
            self.gradients = grad_output[0].detach()

        h1 = layer.register_forward_hook(forward_hook)
        h2 = layer.register_full_backward_hook(backward_hook)
        self._hook_handles.extend([h1, h2])

    def remove_hooks(self):
        """Clean up hooks."""
        for h in self._hook_handles:
            h.remove()
        self._hook_handles.clear()

    def generate(
        self,
        image_path: str,
        class_idx: Optional[int] = None,
        confidence_threshold: float = 0.25,
    ) -> Tuple[np.ndarray, np.ndarray, dict]:
        """
        Generate Grad-CAM heatmap for an image.
        """
        # Load image
        original_img = cv2.imread(image_path)
        if original_img is None:
            raise FileNotFoundError(f"Image not found: {image_path}")
        original_rgb = cv2.cvtColor(original_img, cv2.COLOR_BGR2RGB)
        H, W = original_rgb.shape[:2]

        # Preprocess (640x640 YOLO input)
        img_tensor = self._preprocess(original_rgb).to(self.device)
        img_tensor.requires_grad_(True)

        # Detection pass (for bounding boxes) — uses the high-level wrapper
        # with verbose=False so it's silent.
        with torch.no_grad():
            results = self.yolo.predict(image_path, conf=confidence_threshold, verbose=False)
        detection_info = self._parse_detections(results, W, H)

        # Select target class
        target_cls = class_idx
        if target_cls is None and detection_info["boxes"]:
            target_cls = detection_info["boxes"][0]["class_id"]
        elif target_cls is None:
            target_cls = 0  # default to pothole

        # Forward pass on the RAW nn.Module (does NOT trigger training).
        # We keep the model in eval mode but enable gradients so the hook fires.
        self.torch_model.eval()
        self.torch_model.zero_grad(set_to_none=True)
        # Reset captured tensors
        self.activations = None
        self.gradients = None

        with torch.inference_mode(mode=False):
            with torch.enable_grad():
                # Force YOLOv8 Detect head to recompute anchors/strides 
                # inside enable_grad to prevent "Inference tensors" errors.
                if hasattr(self.torch_model, 'model') and len(self.torch_model.model) > 0:
                    head = self.torch_model.model[-1]
                    if hasattr(head, 'shape'):
                        head.shape = None
                        
                # Clone to avoid saving inference tensors for backward
                img_tensor = img_tensor.detach().clone().requires_grad_(True)
                
                # Call .forward() directly on the nn.Module. Do NOT use `.train()`
                # here — on recent Ultralytics, .train() on the YOLO wrapper
                # triggers a training run.
                raw_output = self.torch_model(img_tensor)

                # Get the predictions tensor
                # YOLOv8 DetectionModel in eval mode returns: (preds, features) or preds
                if isinstance(raw_output, (list, tuple)):
                    output = raw_output[0]
                else:
                    output = raw_output

                # Build a scalar score to backprop: sum of confidence for target class
                # across all anchors / predictions.
                #
                # Ultralytics YOLOv8 prediction shape (eval): (B, 4+nc, anchors)
                # We sum over anchors for the target class channel.
                try:
                    if output.dim() == 3:
                        # Shape is typically (1, 4+nc, anchors). Channel index 4+target_cls
                        # is the target class score.
                        nc_dim = output.shape[1]
                        anchors_dim = output.shape[2]
                        if nc_dim < anchors_dim:
                            # (1, 4+nc, anchors)
                            class_channel = 4 + target_cls
                            if class_channel < nc_dim:
                                score = output[0, class_channel, :].sum()
                            else:
                                score = output.sum()
                        else:
                            # (1, anchors, 4+nc)
                            class_channel = 4 + target_cls
                            if class_channel < output.shape[2]:
                                score = output[0, :, class_channel].sum()
                            else:
                                score = output.sum()
                    else:
                        score = output.sum()
                except Exception:
                    score = output.sum()

                # Backward pass. If activations is still None the hook didn't fire —
                # degrade gracefully instead of crashing the whole request.
                if self.activations is None:
                    print("  Grad-CAM: hook did not capture activations; returning blank heatmap")
                    heatmap_norm = np.zeros((H, W), dtype=np.float32)
                    overlay = self._apply_overlay(original_rgb, heatmap_norm, detection_info)
                    return heatmap_norm, overlay, detection_info

                score.backward(retain_graph=False)

        if self.gradients is None:
            print("  Grad-CAM: backward did not capture gradients; returning blank heatmap")
            heatmap_norm = np.zeros((H, W), dtype=np.float32)
            overlay = self._apply_overlay(original_rgb, heatmap_norm, detection_info)
            return heatmap_norm, overlay, detection_info

        # Generate CAM
        heatmap_norm = self._compute_cam(H, W)

        # Overlay on original image
        overlay = self._apply_overlay(original_rgb, heatmap_norm, detection_info)

        return heatmap_norm, overlay, detection_info

    def _preprocess(self, image_rgb: np.ndarray, size: int = 640) -> torch.Tensor:
        """Preprocess image for model input."""
        img = cv2.resize(image_rgb, (size, size))
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))
        return torch.from_numpy(img).unsqueeze(0)

    def _compute_cam(self, out_H: int, out_W: int) -> np.ndarray:
        """Compute class activation map from gradients and activations."""
        # Global average pool gradients over spatial dims
        weights = self.gradients.mean(dim=[2, 3], keepdim=True)  # (1, C, 1, 1)

        # Weighted combination of activation maps
        cam = (weights * self.activations).sum(dim=1, keepdim=True)  # (1, 1, h, w)
        cam = F.relu(cam)

        # Resize to original image size
        cam = F.interpolate(cam, size=(out_H, out_W), mode="bilinear", align_corners=False)
        cam = cam.squeeze().detach().cpu().numpy()

        # Normalize to [0, 1]
        cam_min, cam_max = cam.min(), cam.max()
        if cam_max - cam_min > 1e-8:
            cam = (cam - cam_min) / (cam_max - cam_min)
        else:
            cam = np.zeros_like(cam)

        return cam.astype(np.float32)

    def _parse_detections(self, results, W: int, H: int) -> dict:
        """Parse YOLO detection results."""
        classes = ["Potholes", "Abandoned_Vehicles", "Construction_Debris"]
        boxes = []
        if results and len(results) > 0 and results[0].boxes is not None:
            for box in results[0].boxes:
                cls_id = int(box.cls.item())
                conf = float(box.conf.item())
                x1, y1, x2, y2 = box.xyxy[0].tolist()
                boxes.append({
                    "class_id": cls_id,
                    "class_name": classes[cls_id] if cls_id < len(classes) else f"class_{cls_id}",
                    "confidence": conf,
                    "bbox": [x1, y1, x2, y2],
                })
        return {"boxes": boxes, "image_size": (W, H)}

    def _apply_overlay(self, image_rgb: np.ndarray, heatmap: np.ndarray, detection_info: dict) -> np.ndarray:
        """Apply Grad-CAM heatmap overlay on image with detection boxes."""
        heatmap_uint8 = (heatmap * 255).astype(np.uint8)
        heatmap_color = cv2.applyColorMap(heatmap_uint8, cv2.COLORMAP_JET)
        heatmap_color = cv2.cvtColor(heatmap_color, cv2.COLOR_BGR2RGB)

        overlay = cv2.addWeighted(image_rgb, 0.5, heatmap_color, 0.5, 0)

        # Draw bounding boxes
        colors = [(255, 80, 80), (80, 255, 80), (80, 80, 255)]
        for det in detection_info["boxes"]:
            x1, y1, x2, y2 = [int(v) for v in det["bbox"]]
            cls_id = det["class_id"]
            color = colors[cls_id % len(colors)]
            cv2.rectangle(overlay, (x1, y1), (x2, y2), color, 2)
            label = f"{det['class_name']} {det['confidence']:.2f}"
            cv2.putText(overlay, label, (x1, max(y1 - 8, 10)),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, color, 2)

        return overlay

    def save_visualization(self, heatmap: np.ndarray, overlay: np.ndarray, output_path: str):
        """Save heatmap and overlay side-by-side."""
        H, W = overlay.shape[:2]
        hm_uint8 = (heatmap * 255).astype(np.uint8)
        hm_color = cv2.applyColorMap(hm_uint8, cv2.COLORMAP_JET)
        hm_color = cv2.cvtColor(hm_color, cv2.COLOR_BGR2RGB)
        hm_resized = cv2.resize(hm_color, (W, H))
        combined = np.hstack([hm_resized, overlay])
        Image.fromarray(combined).save(output_path)
        print(f"  Grad-CAM saved: {output_path}")


def run_gradcam(model, image_path: str, output_path: str = None, class_idx: int = None):
    """High-level Grad-CAM helper."""
    cam = GradCAM(model)
    try:
        heatmap, overlay, info = cam.generate(image_path, class_idx=class_idx)
        if output_path:
            cam.save_visualization(heatmap, overlay, output_path)
        return heatmap, overlay, info
    finally:
        cam.remove_hooks()
