"""
Storage service — handles image uploads.
Supports Firebase Storage (production) and local filesystem (development).
"""
import os
import uuid
from pathlib import Path
from app.config import settings


class StorageService:
    def __init__(self):
        self.mode = settings.storage_mode
        if self.mode == "local":
            Path(settings.local_storage_path).mkdir(parents=True, exist_ok=True)

    async def upload_bytes(self, data: bytes, remote_path: str, content_type: str = "image/jpeg") -> str:
        """Upload bytes to storage and return public URL."""
        if self.mode == "firebase":
            return await self._upload_firebase(data, remote_path, content_type)
        else:
            return self._upload_local(data, remote_path)

    async def _upload_firebase(self, data: bytes, remote_path: str, content_type: str) -> str:
        from app.database import get_bucket
        bucket = get_bucket()
        blob = bucket.blob(remote_path)
        blob.upload_from_string(data, content_type=content_type)
        blob.make_public()
        return blob.public_url

    def _upload_local(self, data: bytes, remote_path: str) -> str:
        local_path = Path(settings.local_storage_path) / remote_path
        local_path.parent.mkdir(parents=True, exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(data)
        # Return a URL that the local server can serve
        return f"/storage/{remote_path}"

    async def delete(self, remote_path: str):
        """Delete a file from storage."""
        if self.mode == "firebase":
            from app.database import get_bucket
            bucket = get_bucket()
            bucket.blob(remote_path).delete()
        else:
            local_path = Path(settings.local_storage_path) / remote_path
            if local_path.exists():
                local_path.unlink()
