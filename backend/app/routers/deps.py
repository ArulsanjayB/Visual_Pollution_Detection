"""
Authentication dependency for FastAPI routes.
In dev mode: accepts X-Dev-User header or Bearer dev:<uid> tokens.
In production: verifies Firebase ID tokens sent from the mobile app.
"""
from fastapi import Header, HTTPException, Depends, Request
from typing import Optional
from app.database import verify_token, get_db, is_dev_mode
from app.models.report import UserRole


async def get_current_user(
    authorization: Optional[str] = Header(None),
    x_dev_user: Optional[str] = Header(None, alias="X-Dev-User"),
) -> dict:
    """
    Dependency: Verify token and return user info.
    Dev mode: accepts X-Dev-User header with uid (e.g., 'dev_citizen')
    Production: requires Firebase Bearer token
    """
    db = get_db()

    # Dev mode: accept X-Dev-User header
    if is_dev_mode() and x_dev_user:
        uid = x_dev_user
        user_doc = db.collection("users").document(uid).get()
        if user_doc.exists:
            user_data = user_doc.to_dict()
            return {
                "uid": uid,
                "role": user_data.get("role", UserRole.CITIZEN),
                "display_name": user_data.get("display_name", uid),
                "is_active": user_data.get("is_active", True),
                "email": user_data.get("email", ""),
            }
        else:
            # Auto-create user in dev mode
            user_data = {
                "uid": uid,
                "email": f"{uid}@civiclens.dev",
                "display_name": uid,
                "role": "citizen",
                "total_reports": 0,
                "resolved_reports": 0,
                "total_tokens": 0,
                "is_active": True,
            }
            db.collection("users").document(uid).set(user_data)
            return {
                "uid": uid,
                "role": UserRole.CITIZEN,
                "display_name": uid,
                "is_active": True,
                "email": user_data["email"],
            }

    # Standard Bearer token
    if not authorization or not authorization.startswith("Bearer "):
        if is_dev_mode():
            # Default to dev_citizen in dev mode with no auth
            return {
                "uid": "dev_citizen",
                "role": UserRole.CITIZEN,
                "display_name": "Test Citizen",
                "is_active": True,
            }
        raise HTTPException(status_code=401, detail="Missing authorization header. Send 'Authorization: Bearer <token>'")

    token = authorization[7:]
    try:
        decoded = verify_token(token)
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))

    # Fetch user role from DB
    uid = decoded.get("uid", "unknown")
    user_doc = db.collection("users").document(uid).get()
    if user_doc.exists:
        user_data = user_doc.to_dict()
        decoded["role"] = user_data.get("role", UserRole.CITIZEN)
        decoded["display_name"] = user_data.get("display_name", decoded.get("name", ""))
        decoded["is_active"] = user_data.get("is_active", True)
    else:
        decoded["role"] = UserRole.CITIZEN
        decoded["is_active"] = True

    if not decoded.get("is_active", True):
        raise HTTPException(status_code=403, detail="Account suspended")

    return decoded


def require_role(*roles: UserRole):
    """Dependency factory: require specific user roles."""
    async def checker(user: dict = Depends(get_current_user)):
        user_role = user.get("role", "citizen")
        allowed = [r.value if hasattr(r, 'value') else r for r in roles]
        if user_role not in allowed:
            raise HTTPException(status_code=403, detail=f"Access denied. Required roles: {allowed}, your role: {user_role}")
        return user
    return checker


require_citizen   = require_role(UserRole.CITIZEN, UserRole.MUNICIPAL, UserRole.ADMIN)
require_municipal = require_role(UserRole.MUNICIPAL, UserRole.ADMIN)
require_admin     = require_role(UserRole.ADMIN)
