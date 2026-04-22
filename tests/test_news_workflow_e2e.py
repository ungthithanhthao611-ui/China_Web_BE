from sqlalchemy import select

from app.api.deps import get_db
from app.models.admin import AdminUser
from app.models.news import NewsPost


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
            content=None,
            author=admin.username if admin else None,
            status="draft",
        )
        db.add(post)
        db.commit()
        db.refresh(post)

        response = client.get(f"/api/v1/admin/news_posts/{post.id}", headers=admin_headers)

        assert response.status_code == 200, response.text
        payload = response.json()
        assert payload["id"] == post.id
        assert payload["content_json"] is None
    finally:
        db.close()
        try:
            next(db_generator)
        except StopIteration:
            pass
