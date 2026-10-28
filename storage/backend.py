"""
Storage Backend Abstraction for VisionGuard AI.

Supports:
- LocalStorageBackend: Stores and retrieves images from local project filesystem (data/uploads, data/processed). Default for local development and offline testing.
- CloudflareR2StorageBackend: S3-compatible object storage via Cloudflare R2 for zero-egress production deployments.

Ensures:
- Path traversal prevention.
- Non-guessable generated keys.
- Private by default: signed URLs with short expiry or authenticated byte streaming.
- No secrets exposed in logs, error messages, or exception representations.
"""

import abc
import os
import io
import re
import uuid
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger("visionguard.storage")

# Root path of the application
PROJECT_ROOT = Path(__file__).resolve().parent.parent


def sanitize_filename(filename: str) -> str:
    """Sanitizes user filename, removing unsafe path characters and non-ascii tokens."""
    if not filename:
        return f"file_{uuid.uuid4().hex[:8]}.jpg"
    base = os.path.basename(filename)
    safe = re.sub(r"[^a-zA-Z0-9_.-]", "_", base)
    return safe if safe.strip("._-") else f"file_{uuid.uuid4().hex[:8]}.jpg"


class StorageBackend(abc.ABC):
    """Abstract interface for image persistence in VisionGuard AI."""

    @abc.abstractmethod
    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        """
        Persists raw image bytes under the designated key.
        Returns the persistent identifier/key to be stored in the database.
        """
        pass

    @abc.abstractmethod
    def get_bytes(self, key: str) -> Optional[bytes]:
        """Retrieves binary image data for the given key, or None if not found."""
        pass

    @abc.abstractmethod
    def exists(self, key: str) -> bool:
        """Checks whether the object exists."""
        pass

    @abc.abstractmethod
    def delete(self, key: str) -> bool:
        """Deletes the object if it exists. Returns True if deleted."""
        pass

    @abc.abstractmethod
    def get_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """
        Returns a secure, short-lived signed URL for reading the image,
        or None if direct signed URLs are not supported (e.g. local storage).
        """
        pass


class LocalStorageBackend(StorageBackend):
    """
    Local filesystem storage backend for local development and offline testing.
    Anchored to PROJECT_ROOT / 'data'.
    """

    def __init__(self, base_dir: Optional[str] = None):
        self.base_dir = Path(base_dir).resolve() if base_dir else (PROJECT_ROOT / "data").resolve()
        self.uploads_dir = (self.base_dir / "uploads").resolve()
        self.processed_dir = (self.base_dir / "processed").resolve()

        self.uploads_dir.mkdir(parents=True, exist_ok=True)
        self.processed_dir.mkdir(parents=True, exist_ok=True)

    def _resolve_file_path(self, key: str) -> Optional[Path]:
        """
        Resolves a key or relative path to a validated local Path.
        Enforces that target file resides inside self.base_dir (preventing path traversal).
        """
        if not key:
            return None

        key_clean = key.strip().replace("\\", "/")

        # Handle legacy or relative paths like "data/uploads/foo.jpg" or "uploads/foo.jpg"
        if key_clean.startswith("data/"):
            target = (PROJECT_ROOT / key_clean).resolve()
        elif key_clean.startswith("uploads/") or key_clean.startswith("processed/"):
            target = (self.base_dir / key_clean).resolve()
        else:
            # Check if key directly exists as absolute or relative
            p = Path(key_clean)
            if p.is_absolute():
                target = p.resolve()
            else:
                target = (self.base_dir / key_clean).resolve()

        # Enforce directory boundary security check
        try:
            target.relative_to(self.base_dir)
            return target
        except ValueError:
            # If path is inside PROJECT_ROOT / 'data'
            try:
                target.relative_to((PROJECT_ROOT / "data").resolve())
                return target
            except ValueError:
                logger.warning(f"Prevented out-of-bounds local storage access: {key}")
                return None

    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        """Saves binary data to local file path."""
        target_path = self._resolve_file_path(key)
        if not target_path:
            # Default to uploads if key is invalid
            clean_name = sanitize_filename(key)
            target_path = self.uploads_dir / clean_name

        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, "wb") as f:
            f.write(data)

        # Return relative path for database storage (backward compatibility)
        try:
            rel = target_path.relative_to(PROJECT_ROOT)
            return str(rel).replace("\\", "/")
        except ValueError:
            return str(target_path).replace("\\", "/")

    def get_bytes(self, key: str) -> Optional[bytes]:
        """Reads and returns file bytes from local disk."""
        path = self._resolve_file_path(key)
        if path and path.is_file():
            try:
                with open(path, "rb") as f:
                    return f.read()
            except OSError as exc:
                logger.error(f"Error reading local file '{path}': {exc}")
                return None
        return None

    def exists(self, key: str) -> bool:
        """Checks if local file exists."""
        path = self._resolve_file_path(key)
        return bool(path and path.is_file())

    def delete(self, key: str) -> bool:
        """Deletes local file."""
        path = self._resolve_file_path(key)
        if path and path.is_file():
            try:
                path.unlink()
                return True
            except OSError as exc:
                logger.error(f"Error deleting local file '{path}': {exc}")
                return False
        return False

    def get_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """Local filesystem does not provide direct presigned URLs."""
        return None


class CloudflareR2StorageBackend(StorageBackend):
    """
    Cloudflare R2 Object Storage Backend (S3-compatible API).
    Provides persistent, zero-egress cloud storage for VisionGuard AI images.
    """

    def __init__(
        self,
        bucket_name: str,
        account_id: Optional[str] = None,
        access_key_id: Optional[str] = None,
        secret_access_key: Optional[str] = None,
        endpoint_url: Optional[str] = None,
        s3_client: Optional[Any] = None,
    ):
        self.bucket_name = bucket_name
        self.account_id = account_id
        self.endpoint_url = endpoint_url or (
            f"https://{account_id}.r2.cloudflarestorage.com" if account_id else None
        )

        if s3_client is not None:
            self._s3_client = s3_client
        else:
            try:
                import boto3
                from botocore.config import Config
            except ImportError:
                raise RuntimeError(
                    "Cloudflare R2 storage requires 'boto3'. Install it using 'pip install boto3'."
                )

            if not self.endpoint_url or not access_key_id or not secret_access_key:
                raise ValueError(
                    "Cloudflare R2 configuration error: R2_ENDPOINT_URL (or R2_ACCOUNT_ID), "
                    "R2_ACCESS_KEY_ID, and R2_SECRET_ACCESS_KEY must be provided."
                )

            # R2 requires s3v4 signature version
            cfg = Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"},
            )
            self._s3_client = boto3.client(
                "s3",
                endpoint_url=self.endpoint_url,
                aws_access_key_id=access_key_id,
                aws_secret_access_key=secret_access_key,
                region_name="auto",
                config=cfg,
            )

    def _normalize_key(self, key: str) -> str:
        """Normalizes local paths and keys into canonical S3 object keys."""
        if not key:
            return f"uploads/{uuid.uuid4().hex}.jpg"
        clean = key.strip().replace("\\", "/").lstrip("/")
        if clean.startswith("data/"):
            clean = clean[5:]
        return clean

    def save(self, key: str, data: bytes, content_type: str = "image/jpeg") -> str:
        """Uploads binary data to Cloudflare R2."""
        norm_key = self._normalize_key(key)
        try:
            self._s3_client.put_object(
                Bucket=self.bucket_name,
                Key=norm_key,
                Body=data,
                ContentType=content_type,
            )
            logger.info(f"Persisted object to R2: bucket='{self.bucket_name}', key='{norm_key}' ({len(data)} bytes)")
            return norm_key
        except Exception as exc:
            logger.error(f"Failed to upload object to Cloudflare R2 (key='{norm_key}'): {exc}")
            raise RuntimeError(f"Cloudflare R2 storage error: {str(exc)}") from exc

    def get_bytes(self, key: str) -> Optional[bytes]:
        """Downloads and returns object bytes from Cloudflare R2."""
        norm_key = self._normalize_key(key)
        try:
            resp = self._s3_client.get_object(
                Bucket=self.bucket_name,
                Key=norm_key,
            )
            body = resp["Body"]
            return body.read()
        except Exception as exc:
            # Handle NoSuchKey or ClientError gracefully
            err_code = getattr(exc, "response", {}).get("Error", {}).get("Code", "")
            if err_code in ("NoSuchKey", "404"):
                logger.warning(f"R2 object not found: bucket='{self.bucket_name}', key='{norm_key}'")
                return None
            logger.error(f"Failed to fetch object from R2 (key='{norm_key}'): {exc}")
            return None

    def exists(self, key: str) -> bool:
        """Verifies if object exists in Cloudflare R2."""
        norm_key = self._normalize_key(key)
        try:
            self._s3_client.head_object(
                Bucket=self.bucket_name,
                Key=norm_key,
            )
            return True
        except Exception:
            return False

    def delete(self, key: str) -> bool:
        """Deletes object from Cloudflare R2."""
        norm_key = self._normalize_key(key)
        try:
            self._s3_client.delete_object(
                Bucket=self.bucket_name,
                Key=norm_key,
            )
            return True
        except Exception as exc:
            logger.error(f"Failed to delete object from R2 (key='{norm_key}'): {exc}")
            return False

    def get_url(self, key: str, expires_in: int = 3600) -> Optional[str]:
        """Generates a secure, short-lived presigned URL for private R2 object download."""
        norm_key = self._normalize_key(key)
        try:
            url = self._s3_client.generate_presigned_url(
                ClientMethod="get_object",
                Params={
                    "Bucket": self.bucket_name,
                    "Key": norm_key,
                },
                ExpiresIn=expires_in,
            )
            return url
        except Exception as exc:
            logger.error(f"Failed to generate presigned URL for R2 key '{norm_key}': {exc}")
            return None


def get_storage_backend(config: Optional[Dict[str, Any]] = None) -> StorageBackend:
    """
    Factory function returning the configured StorageBackend instance.

    Priority:
    1. config dictionary parameters
    2. Environment variables:
       - STORAGE_BACKEND: 'r2' | 'local' (default: 'local')
       - R2_BUCKET_NAME
       - R2_ACCOUNT_ID
       - R2_ACCESS_KEY_ID
       - R2_SECRET_ACCESS_KEY
       - R2_ENDPOINT_URL
    """
    cfg = config or {}
    backend_type = (
        cfg.get("STORAGE_BACKEND")
        or os.environ.get("STORAGE_BACKEND")
        or "local"
    ).lower().strip()

    if backend_type in ("r2", "cloudflare_r2", "s3"):
        bucket = cfg.get("R2_BUCKET_NAME") or os.environ.get("R2_BUCKET_NAME")
        if not bucket:
            raise ValueError(
                "Storage configuration error: STORAGE_BACKEND is set to 'r2', "
                "but R2_BUCKET_NAME is not configured."
            )
        account_id = cfg.get("R2_ACCOUNT_ID") or os.environ.get("R2_ACCOUNT_ID")
        access_key = cfg.get("R2_ACCESS_KEY_ID") or os.environ.get("R2_ACCESS_KEY_ID")
        secret_key = cfg.get("R2_SECRET_ACCESS_KEY") or os.environ.get("R2_SECRET_ACCESS_KEY")
        endpoint_url = cfg.get("R2_ENDPOINT_URL") or os.environ.get("R2_ENDPOINT_URL")

        return CloudflareR2StorageBackend(
            bucket_name=bucket,
            account_id=account_id,
            access_key_id=access_key,
            secret_access_key=secret_key,
            endpoint_url=endpoint_url,
            s3_client=cfg.get("R2_S3_CLIENT"),
        )

    # Default to LocalStorageBackend
    base_dir = cfg.get("LOCAL_STORAGE_BASE_DIR") or os.environ.get("LOCAL_STORAGE_BASE_DIR")
    return LocalStorageBackend(base_dir=base_dir)
