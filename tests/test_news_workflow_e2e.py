from sqlalchemy import select

from app.api.deps import get_db
from app.models.admin import AdminUser
from app.models.news_workflow import NewsPost


def test_news_categories_route_is_not_shadowed_by_post_id_route(client, admin_headers: dict[str, str]) -> None:
    response = client.get("/api/v1/admin/news/categories", headers=admin_headers)

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["success"] is True
    assert isinstance(payload["data"], list)


def test_news_detail_serializes_null_content_json_without_500(client, admin_headers: dict[str, str]) -> None:
    override_get_db = client.app.dependency_overrides[get_db]
    db_generator = override_get_db()
    db = next(db_generator)
    try:
        admin = db.scalar(select(AdminUser).where(AdminUser.username == "admin"))
        post = NewsPost(
            title="Legacy post",
            slug="legacy-post",
            summary="Legacy summary",
            thumbnail_url=None,
            content_json=None,
            content_html=None,
            source_url=None,
            source_note=None,
            status="draft",
            author_id=admin.id if admin else None,
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        response = client.get(f"/api/v1/admin/news/{post.id}", headers=admin_headers)

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["success"] is True
        assert payload["data"]["id"] == post.id
        assert payload["data"]["content_json"]["blocks"] == []
        assert payload["data"]["content_json"]["page"]["width"] == 900
    finally:
        db.close()
        try:
            next(db_generator)
        except StopIteration:
            pass
