"""
Automated unit tests for VisionGuard AI Storage Backend Abstraction (Local & Cloudflare R2).
"""

import os
import io
import pytest
from unittest.mock import MagicMock, patch
from botocore.exceptions import ClientError

from storage.backend import (
    LocalStorageBackend,
    CloudflareR2StorageBackend,
    get_storage_backend,
    sanitize_filename,
    PROJECT_ROOT,
)


class TestFilenameSanitization:
    def test_sanitize_filename_basic(self):
        assert sanitize_filename("test_image.jpg") == "test_image.jpg"
        assert sanitize_filename("my photo 123.png") == "my_photo_123.png"

    def test_sanitize_filename_path_traversal(self):
        cleaned = sanitize_filename("../../../etc/passwd")
        assert "/" not in cleaned
        assert "\\" not in cleaned
        assert "passwd" in cleaned

    def test_sanitize_filename_empty(self):
        cleaned = sanitize_filename("")
        assert cleaned.startswith("file_")
        assert cleaned.endswith(".jpg")


class TestLocalStorageBackend:
    @pytest.fixture
    def local_storage(self, tmp_path):
        return LocalStorageBackend(base_dir=str(tmp_path))

    def test_save_and_retrieve_bytes(self, local_storage):
        test_data = b"\xff\xd8\xff\xe0test_jpeg_bytes"
        key = "uploads/test_file.jpg"

        saved_path = local_storage.save(key, test_data)
        assert saved_path is not None
        assert "test_file.jpg" in saved_path

        retrieved = local_storage.get_bytes(key)
        assert retrieved == test_data

    def test_exists_and_delete(self, local_storage):
        test_data = b"image content"
        key = "processed/annotated_sample.jpg"

        local_storage.save(key, test_data)
        assert local_storage.exists(key) is True

        deleted = local_storage.delete(key)
        assert deleted is True
        assert local_storage.exists(key) is False

    def test_path_traversal_prevention(self, local_storage):
        # Attempt to access outside base directory
        traversal_key = "../../secret.txt"
        assert local_storage.get_bytes(traversal_key) is None

        # Saving with traversal key must be safely confined
        saved_key = local_storage.save("../../hacked.jpg", b"malicious")
        assert "../../" not in saved_key

    def test_get_url_returns_none(self, local_storage):
        # Local filesystem storage does not provide direct signed URLs
        assert local_storage.get_url("uploads/foo.jpg") is None


class TestCloudflareR2StorageBackend:
    @pytest.fixture
    def mock_s3_client(self):
        return MagicMock()

    @pytest.fixture
    def r2_backend(self, mock_s3_client):
        return CloudflareR2StorageBackend(
            bucket_name="test-bucket",
            account_id="fake-account-id",
            access_key_id="fake-access-key",
            secret_access_key="fake-secret-key",
            s3_client=mock_s3_client,
        )

    def test_r2_save(self, r2_backend, mock_s3_client):
        test_bytes = b"fake image data"
        key = "data/uploads/sample.jpg"

        returned_key = r2_backend.save(key, test_bytes, content_type="image/jpeg")

        assert returned_key == "uploads/sample.jpg"
        mock_s3_client.put_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="uploads/sample.jpg",
            Body=test_bytes,
            ContentType="image/jpeg",
        )

    def test_r2_get_bytes_success(self, r2_backend, mock_s3_client):
        fake_body = MagicMock()
        fake_body.read.return_value = b"image binary content"
        mock_s3_client.get_object.return_value = {"Body": fake_body}

        data = r2_backend.get_bytes("uploads/test.jpg")
        assert data == b"image binary content"
        mock_s3_client.get_object.assert_called_once_with(
            Bucket="test-bucket",
            Key="uploads/test.jpg",
        )

    def test_r2_get_bytes_not_found(self, r2_backend, mock_s3_client):
        error_response = {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}}
        mock_s3_client.get_object.side_effect = ClientError(error_response, "GetObject")

        data = r2_backend.get_bytes("uploads/nonexistent.jpg")
        assert data is None

    def test_r2_exists(self, r2_backend, mock_s3_client):
        mock_s3_client.head_object.return_value = {"ContentLength": 1024}
        assert r2_backend.exists("uploads/valid.jpg") is True

        error_response = {"Error": {"Code": "404", "Message": "Not Found"}}
        mock_s3_client.head_object.side_effect = ClientError(error_response, "HeadObject")
        assert r2_backend.exists("uploads/missing.jpg") is False

    def test_r2_presigned_url(self, r2_backend, mock_s3_client):
        mock_s3_client.generate_presigned_url.return_value = "https://r2.cloudflarestorage.com/signed-url?token=xyz"

        url = r2_backend.get_url("uploads/private.jpg", expires_in=1800)
        assert url == "https://r2.cloudflarestorage.com/signed-url?token=xyz"
        mock_s3_client.generate_presigned_url.assert_called_once_with(
            ClientMethod="get_object",
            Params={"Bucket": "test-bucket", "Key": "uploads/private.jpg"},
            ExpiresIn=1800,
        )

    def test_r2_init_missing_bucket_raises(self):
        with pytest.raises(ValueError, match="R2_BUCKET_NAME is not configured"):
            get_storage_backend({"STORAGE_BACKEND": "r2", "R2_BUCKET_NAME": ""})


class TestStorageBackendFactory:
    def test_default_is_local(self):
        backend = get_storage_backend({})
        assert isinstance(backend, LocalStorageBackend)

    def test_factory_returns_r2(self):
        mock_client = MagicMock()
        cfg = {
            "STORAGE_BACKEND": "r2",
            "R2_BUCKET_NAME": "my-bucket",
            "R2_ACCOUNT_ID": "acct123",
            "R2_ACCESS_KEY_ID": "key123",
            "R2_SECRET_ACCESS_KEY": "sec123",
            "R2_S3_CLIENT": mock_client,
        }
        backend = get_storage_backend(cfg)
        assert isinstance(backend, CloudflareR2StorageBackend)
        assert backend.bucket_name == "my-bucket"
