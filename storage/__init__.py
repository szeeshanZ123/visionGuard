"""
Storage package for VisionGuard AI.

Provides unified storage abstractions for local filesystem and Cloudflare R2 object storage.
"""

from storage.backend import (
    StorageBackend,
    LocalStorageBackend,
    CloudflareR2StorageBackend,
    get_storage_backend,
)

__all__ = [
    "StorageBackend",
    "LocalStorageBackend",
    "CloudflareR2StorageBackend",
    "get_storage_backend",
]
