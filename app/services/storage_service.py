"""
File storage abstraction backed by Supabase Storage.

storage.upload(path, bytes, content_type) -> public_or_signed_url
storage.delete(path)

Keeps Supabase specifics out of route handlers so the backend could move to
S3/GCS later by editing only this file.
"""
import requests
from flask import current_app


class StorageProvider:
    def upload(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        raise NotImplementedError

    def delete(self, path: str):
        raise NotImplementedError


class SupabaseStorageProvider(StorageProvider):
    def __init__(self, url, key, bucket):
        self.url = url.rstrip("/") if url else ""
        self.key = key
        self.bucket = bucket

    def _configured(self):
        return bool(self.url and self.key)

    def upload(self, path: str, data: bytes, content_type: str = "application/octet-stream") -> str:
        if not self._configured():
            # Not configured yet - caller should treat None as "store locally / skip".
            return None
        endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        resp = requests.post(
            endpoint,
            headers={
                "Authorization": f"Bearer {self.key}",
                "Content-Type": content_type,
                "x-upsert": "true",
            },
            data=data,
            timeout=30,
        )
        resp.raise_for_status()
        return f"{self.url}/storage/v1/object/public/{self.bucket}/{path}"

    def delete(self, path: str):
        if not self._configured():
            return
        endpoint = f"{self.url}/storage/v1/object/{self.bucket}/{path}"
        requests.delete(endpoint, headers={"Authorization": f"Bearer {self.key}"}, timeout=15)


def get_storage_provider() -> StorageProvider:
    cfg = current_app.config
    return SupabaseStorageProvider(cfg.get("SUPABASE_URL"), cfg.get("SUPABASE_KEY"), cfg.get("SUPABASE_BUCKET"))
