"""
Admin router — system management endpoints.

GET    /api/admin/users              List all users
PATCH  /api/admin/users/{uid}/role   Change user role
DELETE /api/admin/users/{uid}        Suspend/delete account
GET    /api/admin/reports/{id}/delete Remove spam report
GET    /api/admin/system             System health & model info
"""
from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from app.database import get_db
from app.routers.deps import require_admin
from pydantic import BaseModel

router = APIRouter()


class RoleUpdate(BaseModel):
    role: str  # citizen | municipal | admin


@router.get("/users")
async def list_users(
    page: int = 1,
    page_size: int = 50,
    role: str = None,
    user: dict = Depends(require_admin),
):
    """List all users with optional role filter."""
    db = get_db()
    query = db.collection("users")
    if role:
        query = query.where("role", "==", role)
    docs = list(query.stream())

    all_users = [d.to_dict() for d in docs]
    all_users.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)

    page_size = min(page_size, 200)
    start = (page - 1) * page_size
    return {
        "users": all_users[start: start + page_size],
        "total": len(all_users),
        "page": page,
    }


@router.patch("/users/{uid}/role")
async def update_user_role(uid: str, body: RoleUpdate, user: dict = Depends(require_admin)):
    """Change a user's role (e.g., promote to municipal)."""
    if body.role not in ("citizen", "municipal", "admin"):
        raise HTTPException(status_code=400, detail="Invalid role")
    db = get_db()
    ref = db.collection("users").document(uid)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")
    ref.update({"role": body.role, "updated_at": datetime.utcnow().isoformat()})
    return {"message": f"User {uid} role updated to {body.role}"}


@router.patch("/users/{uid}/suspend")
async def suspend_user(uid: str, suspend: bool = True, user: dict = Depends(require_admin)):
    """Suspend or re-activate a user account."""
    db = get_db()
    ref = db.collection("users").document(uid)
    if not ref.get().exists:
        raise HTTPException(status_code=404, detail="User not found")
    ref.update({"is_active": not suspend, "updated_at": datetime.utcnow().isoformat()})
    action = "suspended" if suspend else "reactivated"
    return {"message": f"User {uid} {action}"}


@router.delete("/reports/{report_id}")
async def delete_report(report_id: str, user: dict = Depends(require_admin)):
    """Remove a spam or invalid report and its images."""
    db = get_db()
    ref = db.collection("reports").document(report_id)
    doc = ref.get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Report not found")
        
    data = doc.to_dict()
    citizen_uid = data.get("citizen_uid")
    
    ref.delete()
    
    if citizen_uid:
        user_ref = db.collection("users").document(citizen_uid)
        user_doc = user_ref.get()
        if user_doc.exists:
            count = user_doc.to_dict().get("total_reports", 1)
            user_ref.update({"total_reports": max(0, count - 1)})
            
    # Clean up local images
    import shutil
    from pathlib import Path
    from app.config import settings
    if settings.storage_mode == "local":
        local_dir = Path(settings.local_storage_path) / "images" / report_id
        if local_dir.exists() and local_dir.is_dir():
            shutil.rmtree(local_dir, ignore_errors=True)
            
    return {"message": f"Report {report_id} deleted"}


@router.delete("/users/{uid}/reports")
async def delete_all_user_reports(uid: str, user: dict = Depends(require_admin)):
    """Delete all reports submitted by a specific user and their images."""
    db = get_db()
    reports = db.collection("reports").where("citizen_uid", "==", uid).stream()
    count = 0
    
    import shutil
    from pathlib import Path
    from app.config import settings
    
    for r in list(reports):
        report_id = r.id
        db.collection("reports").document(report_id).delete()
        
        if settings.storage_mode == "local":
            local_dir = Path(settings.local_storage_path) / "images" / report_id
            if local_dir.exists() and local_dir.is_dir():
                shutil.rmtree(local_dir, ignore_errors=True)
                
        count += 1
    
    user_ref = db.collection("users").document(uid)
    if user_ref.get().exists:
        user_ref.update({"total_reports": 0, "resolved_reports": 0})
        
    return {"message": f"Deleted {count} reports for user {uid}"}


@router.get("/users/{uid}/reports")
async def get_user_reports_admin(uid: str, user: dict = Depends(require_admin)):
    """Get all reports submitted by a specific user."""
    db = get_db()
    reports = db.collection("reports").where("citizen_uid", "==", uid).stream()
    
    results = []
    for r in list(reports):
        data = r.to_dict()
        data["id"] = r.id
        results.append(data)
        
    results.sort(key=lambda x: str(x.get("created_at", "")), reverse=True)
    return {"reports": results}


@router.get("/system")
async def system_stats(user: dict = Depends(require_admin)):
    """System health, model info, and aggregate stats."""
    import torch, platform
    from app.config import settings

    db = get_db()
    total_reports = len(list(db.collection("reports").stream()))
    total_users   = len(list(db.collection("users").stream()))

    return {
        "status": "healthy",
        "model_path": settings.model_weights_path,
        "cuda_available": torch.cuda.is_available(),
        "gpu_name": torch.cuda.get_device_name(0) if torch.cuda.is_available() else "CPU",
        "python_version": platform.python_version(),
        "total_reports": total_reports,
        "total_users": total_users,
        "storage_mode": settings.storage_mode,
    }
