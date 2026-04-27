"""
Reports router — citizen-facing endpoints.

POST /api/reports/submit        Upload image + location → run AI → create report
GET  /api/reports/my            Citizen's own report history
GET  /api/reports/{id}          Get single report details
POST /api/reports/{id}/xai      Re-run XAI with a different method (on-demand LIME)
"""
import json
import uuid
import os
import tempfile
from datetime import datetime
from typing import Optional, Literal

from fastapi import APIRouter, Depends, UploadFile, File, Form, Request, HTTPException, BackgroundTasks
from fastapi.responses import JSONResponse

from app.database import get_db
from app.models.report import ReportModel, ReportStatus, LocationModel, ReportCreate
from app.routers.deps import get_current_user, require_citizen
from app.services.storage_service import StorageService
from app.services.report_service import build_priority_score, issue_reward_if_resolved


router = APIRouter()
storage = StorageService()


@router.post("/submit")
async def submit_report(
    request: Request,
    background_tasks: BackgroundTasks,
    image: UploadFile = File(...),
    latitude: float = Form(...),
    longitude: float = Form(...),
    address: str = Form(""),
    location_source: str = Form("gps"),
    description: str = Form(""),
    xai_mode: str = Form("gradcam"),
    user: dict = Depends(require_citizen),
):
    """
    Main report submission endpoint.

    Flow:
    1. Validate image
    2. Run AI detection + Grad-CAM (synchronous, fast ~1-3s)
    3. Save report to Firestore
    4. Save images to Storage
    5. Return report ID + results to citizen
    6. Background: run ZooLime if requested
    """
    # Validate
    if image.content_type not in ("image/jpeg", "image/jpg", "image/png"):
        raise HTTPException(status_code=400, detail="Only JPEG/PNG images accepted")

    image_bytes = await image.read()
    if len(image_bytes) > 20 * 1024 * 1024:  # 20MB limit
        raise HTTPException(status_code=400, detail="Image too large (max 20MB)")

    # ─────────────────────────────────────────────────────────────────────
    # Fully non-blocking flow: the phone gets a response in ~500ms.
    # All inference (detection + Grad-CAM + requested XAI) runs in a
    # background task. The client polls GET /api/reports/{id} to see
    # the final result.
    # ─────────────────────────────────────────────────────────────────────

    report_id = str(uuid.uuid4())
    location = LocationModel(
        latitude=latitude,
        longitude=longitude,
        address=address,
        source=location_source,
    )

    # Create a skeleton report with status=pending and inference=None so the
    # citizen's history shows it immediately.
    skeleton_inference = {
        "detections": [],
        "primary_class": "Processing...",
        "primary_class_id": 0,
        "confidence": 0.0,
        "severity": "LOW",
        "severity_score": 0.0,
        "num_detections": 0,
        "xai": {"method": "pending", "heatmap_b64": None, "overlay_b64": None, "metadata": {}},
        "inference_time_ms": 0,
        "processing": True,  # UI can show "Analyzing..." on this report
    }

    report = ReportModel(
        id=report_id,
        citizen_uid=user["uid"],
        citizen_name=user.get("display_name", ""),
        status=ReportStatus.PENDING,
        location=location,
        description=description,
        inference=skeleton_inference,
        priority_score=0.0,
        created_at=datetime.utcnow(),
        updated_at=datetime.utcnow(),
    )

    # Persist the image to storage right now (cheap, <200ms)
    orig_url = await storage.upload_bytes(image_bytes, f"images/{report_id}/original.jpg", content_type="image/jpeg")
    report.image_url = orig_url
    report.image_filename = image.filename

    db = get_db()
    db.collection("reports").document(report_id).set(report.model_dump())

    db.collection("users").document(user["uid"]).update({
        "total_reports": _increment(db, user["uid"], "total_reports"),
    })

    # Queue ALL inference in the background
    background_tasks.add_task(_run_full_inference_background, report_id, image_bytes, xai_mode, request)

    return {
        "report_id": report_id,
        "status": "pending",
        "primary_class": "Processing...",
        "confidence": 0.0,
        "severity": "LOW",
        "num_detections": 0,
        "xai_method": xai_mode,
        "xai_queued": True,
        "xai_queued_method": xai_mode,
        "processing": True,
        "message": (
            f"Report received! AI analysis (detection + {xai_mode.upper()}) is running "
            "in the background. Pull to refresh or check back in ~30-90 seconds."
        ),
    }


@router.get("/my")
async def my_reports(
    page: int = 1,
    page_size: int = 10,
    user: dict = Depends(require_citizen),
):
    """Get the authenticated citizen's report history."""
    db = get_db()
    page_size = min(page_size, 50)

    query = (
        db.collection("reports")
        .where("citizen_uid", "==", user["uid"])
        .order_by("created_at", direction="DESCENDING")
    )
    docs = list(query.stream())
    total = len(docs)
    start = (page - 1) * page_size
    page_docs = docs[start: start + page_size]

    reports = []
    for doc in page_docs:
        data = doc.to_dict()
        reports.append({
            "id": data.get("id"),
            "status": data.get("status"),
            "primary_class": data.get("inference", {}).get("primary_class", "Unknown") if data.get("inference") else "Unknown",
            "severity": data.get("inference", {}).get("severity", "UNKNOWN") if data.get("inference") else "UNKNOWN",
            "confidence": data.get("inference", {}).get("confidence", 0) if data.get("inference") else 0,
            "location": data.get("location"),
            "image_url": data.get("image_url"),
            "created_at": data.get("created_at"),
            "reward_tokens": data.get("reward_tokens", 0),
        })

    return {
        "reports": reports,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (start + page_size) < total,
    }


@router.get("/{report_id}")
async def get_report(report_id: str, user: dict = Depends(get_current_user)):
    """Get full report details. Citizens can only see their own."""
    db = get_db()
    doc = db.collection("reports").document(report_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")

    data = doc.to_dict()
    role = user.get("role", "citizen")
    if role == "citizen" and data.get("citizen_uid") != user["uid"]:
        raise HTTPException(status_code=403, detail="Access denied")

    return data


@router.post("/{report_id}/xai")
async def request_xai(
    request: Request,
    report_id: str,
    background_tasks: BackgroundTasks,
    method: Literal["lime", "zoolime", "shap"] = "zoolime",
    user: dict = Depends(require_citizen),
):
    """
    On-demand XAI: re-run explanation with a specific method.
    This is slower (LIME ~60s, ZooLime ~90s) — runs in background.
    """
    db = get_db()
    doc = db.collection("reports").document(report_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")

    data = doc.to_dict()
    if data.get("citizen_uid") != user["uid"] and user.get("role") == "citizen":
        raise HTTPException(status_code=403, detail="Access denied")

    # Mark as processing
    db.collection("reports").document(report_id).update({
        f"xai_pending_{method}": True,
        "updated_at": datetime.utcnow().isoformat(),
    })

    # Schedule actual XAI computation using the stored image
    image_url = data.get("image_url", "")
    if image_url.startswith("/storage"):
        from pathlib import Path
        from app.config import settings
        local_path = Path(settings.local_storage_path) / image_url.replace("/storage/", "")
        if local_path.exists():
            with open(local_path, "rb") as f:
                image_bytes = f.read()
            background_tasks.add_task(_run_xai_background, report_id, image_bytes, method, request)

    return {"message": f"XAI ({method}) queued. Check report in ~2 minutes.", "report_id": report_id}


async def _run_xai_background(report_id: str, image_bytes: bytes, method: str, request: Request):
    """Run any XAI method in background and save results."""
    import tempfile, base64
    try:
        engine = request.app.state.inference
        if engine is None:
            return
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name
        try:
            result = engine.run(tmp_path, xai_mode=method)
        finally:
            os.unlink(tmp_path)

        db = get_db()
        overlay_b64 = result.get("xai", {}).get("overlay_b64", "")
        if overlay_b64:
            overlay_bytes = base64.b64decode(overlay_b64)
            url = await storage.upload_bytes(overlay_bytes, f"images/{report_id}/{method}.png", "image/png")
            update = {
                f"{method}_url": url,
                f"{method}_metadata": result.get("xai", {}).get("metadata", {}),
                f"xai_pending_{method}": False,
                "updated_at": datetime.utcnow().isoformat(),
            }
            db.collection("reports").document(report_id).update(update)
    except Exception as e:
        print(f"XAI background ({method}) failed for {report_id}: {e}")


# ── Background tasks ──────────────────────────────────────────────────────────

async def _run_full_inference_background(
    report_id: str, image_bytes: bytes, xai_mode: str, request: Request
):
    """
    Run the COMPLETE inference pipeline in the background:
      1. YOLO detection + Grad-CAM (fast, ~2s)
      2. Upload Grad-CAM overlay
      3. If user asked for LIME/ZooLime/SHAP: run that too and upload

    At the end, update the report document with all results so the client
    can see them on next fetch.
    """
    import tempfile, base64
    db = get_db()
    engine = request.app.state.inference

    try:
        if engine is None:
            # Model not loaded — mark as low-confidence placeholder
            db.collection("reports").document(report_id).update({
                "inference.processing": False,
                "inference.primary_class": "Model not loaded",
                "updated_at": datetime.utcnow().isoformat(),
            })
            return

        # Write the image to a temp file (engine expects a path)
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        try:
            # Step 1: always run Grad-CAM first (fast). This gives us detections
            # + a heatmap in one pass.
            gradcam_result = engine.run(tmp_path, xai_mode="gradcam")

            # Upload the Grad-CAM overlay
            overlay_b64 = gradcam_result.get("xai", {}).get("overlay_b64", "")
            gradcam_url = None
            if overlay_b64:
                overlay_bytes = base64.b64decode(overlay_b64)
                gradcam_url = await storage.upload_bytes(
                    overlay_bytes,
                    f"images/{report_id}/xai_gradcam.png",
                    "image/png",
                )

            # Strip base64 blobs (keep DB small); keep metadata
            gradcam_inference = {
                **{k: v for k, v in gradcam_result.items() if k != "xai"},
                "xai": {
                    "method": "gradcam",
                    "metadata": gradcam_result.get("xai", {}).get("metadata", {}),
                    "heatmap_b64": None,
                    "overlay_b64": None,
                },
                "processing": xai_mode not in ("gradcam", "none"),
            }

            # Save the Grad-CAM result immediately so the citizen sees detections
            # even before LIME/ZooLime finish.
            update = {
                "inference": gradcam_inference,
                "priority_score": build_priority_score(gradcam_result),
                "updated_at": datetime.utcnow().isoformat(),
            }
            if gradcam_url:
                update["gradcam_url"] = gradcam_url
            db.collection("reports").document(report_id).update(update)

            # Step 2: if the user asked for LIME/ZooLime/SHAP, run that too.
            if xai_mode in ("lime", "zoolime", "shap"):
                try:
                    extra_result = engine.run(tmp_path, xai_mode=xai_mode)
                    extra_overlay_b64 = extra_result.get("xai", {}).get("overlay_b64", "")
                    if extra_overlay_b64:
                        extra_bytes = base64.b64decode(extra_overlay_b64)
                        extra_url = await storage.upload_bytes(
                            extra_bytes,
                            f"images/{report_id}/{xai_mode}.png",
                            "image/png",
                        )
                        db.collection("reports").document(report_id).update({
                            f"{xai_mode}_url": extra_url,
                            f"{xai_mode}_metadata": extra_result.get("xai", {}).get("metadata", {}),
                            "inference.xai.method": xai_mode,
                            "inference.processing": False,
                            "updated_at": datetime.utcnow().isoformat(),
                        })
                except Exception as e:
                    print(f"XAI ({xai_mode}) background failed for {report_id}: {e}")
                    db.collection("reports").document(report_id).update({
                        "inference.processing": False,
                        f"{xai_mode}_error": str(e),
                        "updated_at": datetime.utcnow().isoformat(),
                    })
            else:
                # Nothing more to do — mark processing complete
                db.collection("reports").document(report_id).update({
                    "inference.processing": False,
                    "updated_at": datetime.utcnow().isoformat(),
                })

        finally:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    except Exception as e:
        print(f"Full inference background failed for {report_id}: {e}")
        import traceback; traceback.print_exc()
        try:
            db.collection("reports").document(report_id).update({
                "inference.processing": False,
                "inference.error": str(e),
                "updated_at": datetime.utcnow().isoformat(),
            })
        except Exception:
            pass


async def _run_zoolime_background(report_id: str, image_bytes: bytes, prev_result: dict, request: Request):
    """Run ZooLime fusion in background for high-severity reports."""
    try:
        import tempfile, base64
        engine = request.app.state.inference

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            tmp.write(image_bytes)
            tmp_path = tmp.name

        zl_result = engine.run(tmp_path, xai_mode="zoolime")
        os.unlink(tmp_path)

        db = get_db()
        overlay_b64 = zl_result.get("xai", {}).get("overlay_b64", "")
        if overlay_b64:
            overlay_bytes = base64.b64decode(overlay_b64)
            zl_url = await storage.upload_bytes(overlay_bytes, f"images/{report_id}/zoolime.png", "image/png")
            db.collection("reports").document(report_id).update({
                "zoolime_url": zl_url,
                "zoolime_metadata": zl_result.get("xai", {}).get("metadata", {}),
                "updated_at": datetime.utcnow().isoformat(),
            })
    except Exception as e:
        print(f"ZooLime background task failed for {report_id}: {e}")


def _increment(db, uid: str, field: str) -> int:
    """Get incremented field value."""
    doc = db.collection("users").document(uid).get()
    if doc.exists:
        return doc.to_dict().get(field, 0) + 1
    return 1
