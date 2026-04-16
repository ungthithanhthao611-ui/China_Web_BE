from pathlib import Path
from unittest.mock import patch

from app.core.config import settings


def test_media_upload_falls_back_to_local_when_cloudinary_is_not_configured(
    client,
    admin_headers,
    tmp_path: Path,
):
    original_media_storage = settings.media_storage
    original_upload_dir = settings.upload_dir
    original_cloudinary_url = settings.cloudinary_url
    original_cloudinary_cloud_name = settings.cloudinary_cloud_name
    original_cloudinary_api_key = settings.cloudinary_api_key
    original_cloudinary_api_secret = settings.cloudinary_api_secret

    settings.media_storage = "cloudinary"
    settings.upload_dir = str(tmp_path / "uploads")
    settings.cloudinary_url = ""
    settings.cloudinary_cloud_name = ""
    settings.cloudinary_api_key = ""
    settings.cloudinary_api_secret = ""

    try:
        response = client.post(
            f"{settings.api_v1_prefix}/admin/media/upload",
            headers=admin_headers,
            files={"file": ("sample.txt", b"hello world", "image/png")},
            data={"title": "Sample Upload", "alt_text": "Sample Alt"},
        )
    finally:
        settings.media_storage = original_media_storage
        settings.upload_dir = original_upload_dir
        settings.cloudinary_url = original_cloudinary_url
        settings.cloudinary_cloud_name = original_cloudinary_cloud_name
        settings.cloudinary_api_key = original_cloudinary_api_key
        settings.cloudinary_api_secret = original_cloudinary_api_secret

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Sample Upload"
    assert payload["alt_text"] == "Sample Alt"
    assert payload["url"].startswith("/uploads/")
    assert Path(payload["storage_path"]).exists()


def test_media_upload_falls_back_to_local_when_cloudinary_upload_fails(
    client,
    admin_headers,
    tmp_path: Path,
):
    original_media_storage = settings.media_storage
    original_upload_dir = settings.upload_dir
    original_cloudinary_url = settings.cloudinary_url
    original_cloudinary_cloud_name = settings.cloudinary_cloud_name
    original_cloudinary_api_key = settings.cloudinary_api_key
    original_cloudinary_api_secret = settings.cloudinary_api_secret

    settings.media_storage = "cloudinary"
    settings.upload_dir = str(tmp_path / "uploads")
    settings.cloudinary_url = ""
    settings.cloudinary_cloud_name = "Root"
    settings.cloudinary_api_key = "test-api-key"
    settings.cloudinary_api_secret = "test-api-secret"

    try:
        with patch("app.services.media.cloudinary.uploader.upload", side_effect=Exception("Invalid cloud_name Root")):
            response = client.post(
                f"{settings.api_v1_prefix}/admin/media/upload",
                headers=admin_headers,
                files={"file": ("sample.txt", b"hello world", "image/png")},
                data={"title": "Fallback Upload", "alt_text": "Fallback Alt"},
            )
    finally:
        settings.media_storage = original_media_storage
        settings.upload_dir = original_upload_dir
        settings.cloudinary_url = original_cloudinary_url
        settings.cloudinary_cloud_name = original_cloudinary_cloud_name
        settings.cloudinary_api_key = original_cloudinary_api_key
        settings.cloudinary_api_secret = original_cloudinary_api_secret

    assert response.status_code == 201
    payload = response.json()
    assert payload["title"] == "Fallback Upload"
    assert payload["alt_text"] == "Fallback Alt"
    assert payload["url"].startswith("/uploads/")
    assert Path(payload["storage_path"]).exists()
