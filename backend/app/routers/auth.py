from fastapi import APIRouter, Depends, HTTPException
from datetime import datetime
from app.database import get_db, verify_token
from app.models.report import UserProfile, UserRole
from app.routers.deps import get_current_user
from pydantic import BaseModel

router = APIRouter()


class RegisterRequest(BaseModel):
    id_token: str
    display_name: str = ""
    phone: str = ""
    role: str = "citizen"


@router.post("/register", response_model=UserProfile)
async def register(body: RegisterRequest):
    """
    Register a new user after Firebase Auth (Google / phone).
    Called once after the user signs in for the first time.
    """
    try:
        decoded = verify_token(body.id_token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    uid = decoded["uid"]
    db = get_db()
    user_ref = db.collection("users").document(uid)

    if user_ref.get().exists:
        return UserProfile(**user_ref.get().to_dict())

    # Only allow citizen self-registration; municipal/admin set by admin
    allowed_role = UserRole.CITIZEN
    profile = UserProfile(
        uid=uid,
        email=decoded.get("email"),
        display_name=body.display_name or decoded.get("name", ""),
        phone=body.phone or decoded.get("phone_number", ""),
        role=allowed_role,
        created_at=datetime.utcnow(),
    )
    user_ref.set(profile.model_dump())
    return profile


@router.get("/me", response_model=UserProfile)
async def get_profile(user: dict = Depends(get_current_user)):
    db = get_db()
    doc = db.collection("users").document(user["uid"]).get()
    if not doc.exists:
        raise HTTPException(status_code=404, detail="Profile not found")
    return UserProfile(**doc.to_dict())


@router.patch("/me")
async def update_profile(updates: dict, user: dict = Depends(get_current_user)):
    """Update citizen's own profile (display name, phone only)."""
    allowed = {"display_name", "phone"}
    safe_updates = {k: v for k, v in updates.items() if k in allowed}
    safe_updates["updated_at"] = datetime.utcnow().isoformat()
    db = get_db()
    db.collection("users").document(user["uid"]).update(safe_updates)
    return {"message": "Profile updated"}
