from typing import Any


def _upload_thumbnail_media(client, admin_headers: dict[str, str], title: str) -> dict[str, Any]:
    response = client.post(
        "/api/v1/admin/media/upload",
        headers=admin_headers,
        files={"file": ("thumb.png", b"fake-image-bytes", "image/png")},
        data={"title": title, "alt_text": f"{title} alt"},
    )
    assert response.status_code == 201, response.text
    return response.json()


def _create_video(
    client,
    admin_headers: dict[str, str],
    *,
    title: str,
    language_id: int,
    status: str = "published",
    sort_order: int = 0,
    thumbnail_id: int | None = None,
    video_url: str = "https://cdn.example.com/sample.mp4",
) -> dict[str, Any]:
    response = client.post(
        "/api/v1/admin/videos",
        headers=admin_headers,
        json={
            "title": title,
            "description": f"{title} description",
            "video_url": video_url,
            "thumbnail_id": thumbnail_id,
            "language_id": language_id,
            "sort_order": sort_order,
            "status": status,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def test_admin_can_create_video_with_thumbnail(client, admin_headers: dict[str, str]) -> None:
    thumbnail = _upload_thumbnail_media(client, admin_headers, "Video Thumb A")

    created = _create_video(
        client,
        admin_headers,
        title="Signature Project Film",
        language_id=1,
        sort_order=5,
        thumbnail_id=thumbnail["id"],
        video_url="https://cdn.example.com/signature.mp4",
    )

    assert created["title"] == "Signature Project Film"
    assert created["video_url"] == "https://cdn.example.com/signature.mp4"
    assert created["thumbnail_id"] == thumbnail["id"]
    assert created["language_id"] == 1
    assert created["sort_order"] == 5
    assert created["status"] == "published"
    assert created["thumbnail"] is not None
    assert created["thumbnail"]["id"] == thumbnail["id"]

    detail_response = client.get(f"/api/v1/admin/videos/{created['id']}", headers=admin_headers)
    assert detail_response.status_code == 200, detail_response.text
    detail = detail_response.json()
    assert detail["id"] == created["id"]
    assert detail["thumbnail"]["id"] == thumbnail["id"]


def test_public_videos_filter_by_status_language_and_sort_order(client, admin_headers: dict[str, str]) -> None:
    thumbnail = _upload_thumbnail_media(client, admin_headers, "Video Thumb B")

    language_response = client.post(
        "/api/v1/admin/languages",
        headers=admin_headers,
        json={
            "code": "zh",
            "name": "Chinese",
            "is_default": False,
            "status": "active",
        },
    )
    assert language_response.status_code == 201, language_response.text
    zh_language_id = language_response.json()["id"]

    _create_video(
        client,
        admin_headers,
        title="Draft EN Video",
        language_id=1,
        status="draft",
        sort_order=0,
        thumbnail_id=thumbnail["id"],
    )
    first_published_en = _create_video(
        client,
        admin_headers,
        title="Published EN Video 1",
        language_id=1,
        status="published",
        sort_order=10,
        thumbnail_id=thumbnail["id"],
    )
    second_published_en = _create_video(
        client,
        admin_headers,
        title="Published EN Video 2",
        language_id=1,
        status="published",
        sort_order=10,
        thumbnail_id=thumbnail["id"],
    )
    _create_video(
        client,
        admin_headers,
        title="Published ZH Video",
        language_id=zh_language_id,
        status="published",
        sort_order=1,
        thumbnail_id=thumbnail["id"],
    )

    en_response = client.get("/api/v1/public/videos", params={"language_code": "en"})
    assert en_response.status_code == 200, en_response.text
    en_items = en_response.json()["items"]

    assert [item["title"] for item in en_items] == ["Published EN Video 2", "Published EN Video 1"]
    assert [item["id"] for item in en_items] == [second_published_en["id"], first_published_en["id"]]
    assert all(item["status"] == "published" for item in en_items)
    assert all(item["language_id"] == 1 for item in en_items)
    assert all(item["thumbnail"] is not None for item in en_items)

    zh_response = client.get("/api/v1/public/videos", params={"language_code": "zh"})
    assert zh_response.status_code == 200, zh_response.text
    zh_items = zh_response.json()["items"]

    assert len(zh_items) == 1
    assert zh_items[0]["title"] == "Published ZH Video"
    assert zh_items[0]["language_id"] == zh_language_id


def test_admin_create_video_requires_video_url(client, admin_headers: dict[str, str]) -> None:
    response = client.post(
        "/api/v1/admin/videos",
        headers=admin_headers,
        json={
            "title": "Missing URL",
            "description": "Video URL is required",
            "language_id": 1,
            "sort_order": 0,
            "status": "published",
        },
    )

    assert response.status_code == 422, response.text
