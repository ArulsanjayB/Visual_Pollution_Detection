"""
Municipal router — endpoints for municipal authority staff.

GET  /api/municipal/reports          Paginated list with filters
GET  /api/municipal/reports/{id}     Full report with XAI images
PATCH /api/municipal/reports/{id}    Update status, assign, add notes
GET  /api/municipal/stats            Dashboard summary statistics
GET  /api/municipal/heatmap          Location data for map heatmap
POST /api/municipal/reports/{id}/pdf Generate downloadable PDF report
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from datetime import datetime
from typing import Optional
from app.database import get_db
from app.models.report import ReportUpdate, ReportStatus, SeverityLevel
from app.routers.deps import require_municipal
from app.services.report_service import generate_pdf_report, issue_reward_if_resolved

router = APIRouter()


@router.get("/reports")
async def list_reports(
    page: int = 1,
    page_size: int = 20,
    status: Optional[str] = None,
    severity: Optional[str] = None,
    class_name: Optional[str] = None,
    sort_by: str = "priority_score",   # priority_score | created_at | severity
    user: dict = Depends(require_municipal),
):
    """
    List all reports with filtering and sorting.
    Default sort: highest priority_score first (composite of severity + confidence + count).
    """
    db = get_db()
    query = db.collection("reports")

    if status:
        query = query.where("status", "==", status)

    docs = list(query.stream())

    # Filter in Python (Firestore has limited multi-field filtering without composite indexes)
    results = []
    for doc in docs:
        d = doc.to_dict()
        inf = d.get("inference") or {}
        if severity and inf.get("severity") != severity.upper():
            continue
        if class_name and inf.get("primary_class", "").lower() != class_name.lower():
            continue
        results.append(d)

    # Sort
    if sort_by == "priority_score":
        results.sort(key=lambda x: x.get("priority_score", 0), reverse=True)
    elif sort_by == "created_at":
        results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    elif sort_by == "confidence":
        results.sort(key=lambda x: (x.get("inference") or {}).get("confidence", 0), reverse=True)

    total = len(results)
    page_size = min(page_size, 100)
    start = (page - 1) * page_size
    page_results = results[start: start + page_size]

    # Slim response for list view
    slim = []
    for d in page_results:
        inf = d.get("inference") or {}
        slim.append({
            "id": d.get("id"),
            "status": d.get("status"),
            "primary_class": inf.get("primary_class", "Unknown"),
            "severity": inf.get("severity", "UNKNOWN"),
            "confidence": inf.get("confidence", 0),
            "num_detections": inf.get("num_detections", 0),
            "priority_score": d.get("priority_score", 0),
            "location": d.get("location"),
            "image_url": d.get("image_url"),
            "gradcam_url": d.get("gradcam_url"),
            "citizen_name": d.get("citizen_name"),
            "created_at": d.get("created_at"),
            "assigned_to": d.get("assigned_to"),
        })

    return {
        "reports": slim,
        "total": total,
        "page": page,
        "page_size": page_size,
        "has_next": (start + page_size) < total,
    }


@router.get("/reports/{report_id}")
async def get_report_detail(report_id: str, user: dict = Depends(require_municipal)):
    """Full report with AI results and XAI images."""
    db = get_db()
    doc = db.collection("reports").document(report_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")
    return doc.to_dict()


@router.patch("/reports/{report_id}")
async def update_report(
    report_id: str,
    updates: ReportUpdate,
    user: dict = Depends(require_municipal),
):
    """
    Update report status, assignment, or notes.
    Triggers citizen reward if status changed to COMPLETED.
    """
    db = get_db()
    doc_ref = db.collection("reports").document(report_id)
    doc = doc_ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")

    data = doc.to_dict()
    patch = {}

    if updates.status is not None:
        patch["status"] = updates.status if isinstance(updates.status, str) else updates.status.value
        if patch["status"] == ReportStatus.COMPLETED:
            patch["resolved_at"] = datetime.utcnow().isoformat()
            # Issue reward to citizen
            await issue_reward_if_resolved(data.get("citizen_uid"), report_id, db)

    if updates.assigned_to is not None:
        patch["assigned_to"] = updates.assigned_to
    if updates.municipal_notes is not None:
        patch["municipal_notes"] = updates.municipal_notes
    if updates.priority_score is not None:
        patch["priority_score"] = updates.priority_score

    patch["updated_at"] = datetime.utcnow().isoformat()
    doc_ref.update(patch)
    return {"message": "Report updated", "report_id": report_id}


@router.get("/stats")
async def dashboard_stats(user: dict = Depends(require_municipal)):
    """Summary statistics for the municipal dashboard."""
    db = get_db()
    docs = list(db.collection("reports").stream())
    data = [d.to_dict() for d in docs]

    total = len(data)
    by_status = {"pending": 0, "in_progress": 0, "completed": 0, "rejected": 0}
    by_class = {"Potholes": 0, "Abandoned_Vehicles": 0, "Construction_Debris": 0}
    by_severity = {"LOW": 0, "MEDIUM": 0, "HIGH": 0}
    avg_confidence = 0.0

    for d in data:
        status = d.get("status", "pending")
        by_status[status] = by_status.get(status, 0) + 1
        inf = d.get("inference") or {}
        cls = inf.get("primary_class", "Unknown")
        by_class[cls] = by_class.get(cls, 0) + 1
        sev = inf.get("severity", "LOW")
        by_severity[sev] = by_severity.get(sev, 0) + 1
        avg_confidence += inf.get("confidence", 0)

    if total > 0:
        avg_confidence /= total

    # Recent trend (last 7 days)
    from datetime import timedelta
    cutoff = (datetime.utcnow() - timedelta(days=7)).isoformat()
    recent = sum(1 for d in data if str(d.get("created_at", "")) >= cutoff)

    return {
        "total_reports": total,
        "by_status": by_status,
        "by_class": by_class,
        "by_severity": by_severity,
        "avg_confidence": round(avg_confidence, 3),
        "recent_7_days": recent,
        "resolution_rate": round(by_status["completed"] / total, 3) if total else 0,
    }


@router.get("/heatmap")
async def heatmap_data(user: dict = Depends(require_municipal)):
    """Return location + severity data for map heatmap visualization."""
    db = get_db()
    docs = list(db.collection("reports").stream())
    points = []
    for doc in docs:
        d = doc.to_dict()
        loc = d.get("location") or {}
        inf = d.get("inference") or {}
        if loc.get("latitude") and loc.get("longitude"):
            points.append({
                "lat": loc["latitude"],
                "lng": loc["longitude"],
                "severity": inf.get("severity", "LOW"),
                "class": inf.get("primary_class", "Unknown"),
                "weight": {"LOW": 0.3, "MEDIUM": 0.6, "HIGH": 1.0}.get(inf.get("severity", "LOW"), 0.3),
                "report_id": d.get("id"),
            })
    return {"points": points, "total": len(points)}


@router.post("/reports/{report_id}/pdf")
async def download_pdf(report_id: str, user: dict = Depends(require_municipal)):
    """Generate and return a PDF report for the given report ID."""
    from fastapi.responses import StreamingResponse
    import io

    db = get_db()
    doc = db.collection("reports").document(report_id).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")

    pdf_bytes = await generate_pdf_report(doc.to_dict())
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f"attachment; filename=report_{report_id[:8]}.pdf"},
    )
