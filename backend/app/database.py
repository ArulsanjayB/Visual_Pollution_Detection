"""
Firebase Admin SDK initialization and Firestore client.
Falls back to local JSON database when Firebase credentials are not available.
"""
import os
from pathlib import Path
from app.config import settings

_initialized = False
_db = None
_bucket = None
_dev_mode = False


def init_firebase():
    """Initialize Firebase Admin SDK, or fall back to local JSON DB."""
    global _initialized, _db, _bucket, _dev_mode

    if _initialized:
        return

    creds_path = Path(settings.firebase_credentials_path)
    if not creds_path.exists() or settings.database_mode == "local":
        print("=" * 55)
        print("  Running in LOCAL DEV MODE (no Firebase)")
        print("  Using local JSON database at ./local_db/")
        print("=" * 55)
        from app.local_db import LocalJsonDB
        _db = LocalJsonDB(data_dir="./local_db")
        _dev_mode = True
        _initialized = True

        # Create default admin user
        users = _db.collection("users")
        if not users.document("dev_admin").get().exists:
            users.document("dev_admin").set({
                "uid": "dev_admin",
                "email": "admin@civiclens.dev",
                "display_name": "Dev Admin",
                "role": "admin",
                "total_reports": 0,
                "resolved_reports": 0,
                "total_tokens": 0,
                "is_active": True,
            })
            users.document("dev_citizen").set({
                "uid": "dev_citizen",
                "email": "citizen@civiclens.dev",
                "display_name": "Test Citizen",
                "role": "citizen",
                "total_reports": 0,
                "resolved_reports": 0,
                "total_tokens": 0,
                "is_active": True,
            })
            users.document("dev_municipal").set({
                "uid": "dev_municipal",
                "email": "municipal@civiclens.dev",
                "display_name": "Municipal Officer",
                "role": "municipal",
                "total_reports": 0,
                "resolved_reports": 0,
                "total_tokens": 0,
                "is_active": True,
            })
            print("  Created default dev users: admin, citizen, municipal")
        return

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore, storage
        cred = credentials.Certificate(str(creds_path))
        firebase_admin.initialize_app(cred, {
            "storageBucket": settings.firebase_storage_bucket,
        })
        _db = firestore.client()
        _bucket = storage.bucket()
        _initialized = True
        print("Firebase initialized successfully")
    except Exception as e:
        print(f"Firebase initialization failed: {e}. Falling back to local mode.")
        from app.local_db import LocalJsonDB
        _db = LocalJsonDB(data_dir="./local_db")
        _dev_mode = True
        _initialized = True


def get_db():
    """Get database client (Firestore or local JSON)."""
    global _db
    if _db is None:
        init_firebase()
    return _db


def get_bucket():
    """Get Firebase Storage bucket."""
    global _bucket
    if _bucket is None:
        init_firebase()
    return _bucket


def is_dev_mode() -> bool:
    return _dev_mode


def verify_token(id_token: str) -> dict:
    """
    Verify Firebase ID token from mobile app.
    In dev mode, accepts tokens in format 'dev:<uid>'.
    """
    if _dev_mode:
        if id_token.startswith("dev:"):
            uid = id_token[4:]
            return {"uid": uid}
        # In dev mode, accept any token as dev_citizen
        return {"uid": "dev_citizen"}

    try:
        from firebase_admin import auth
        return auth.verify_id_token(id_token)
    except Exception as e:
        raise ValueError(f"Invalid token: {e}")
