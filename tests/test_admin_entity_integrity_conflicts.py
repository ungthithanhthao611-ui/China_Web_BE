PROJECT_CATEGORIES_URL = "/api/v1/admin/project_categories"
PROJECTS_URL = "/api/v1/admin/projects"
PROJECT_CATEGORY_ITEMS_URL = "/api/v1/admin/project_category_items"
NEWS_POSTS_URL = "/api/v1/admin/news_posts"


def test_project_category_item_duplicate_conflict_returns_409(client, admin_headers: dict[str, str]) -> None:
  category_response = client.post(
    PROJECT_CATEGORIES_URL,
    headers=admin_headers,
    json={"name": "Star Hotel", "slug": "star-hotel", "status": "active"},
  )
  assert category_response.status_code == 201, category_response.text
  category = category_response.json()

  project_one_response = client.post(
    PROJECTS_URL,
    headers=admin_headers,
    json={"title": "W HOTEL", "slug": "w-hotel", "language_id": 1, "status": "published"},
  )
  assert project_one_response.status_code == 201, project_one_response.text
  project_one = project_one_response.json()

  project_two_response = client.post(
    PROJECTS_URL,
    headers=admin_headers,
    json={"title": "BEIJING HOTEL", "slug": "beijing-hotel-star", "language_id": 1, "status": "published"},
  )
  assert project_two_response.status_code == 201, project_two_response.text
  project_two = project_two_response.json()

  first_mapping_response = client.post(
    PROJECT_CATEGORY_ITEMS_URL,
    headers=admin_headers,
    json={
      "category_id": category["id"],
      "project_id": project_one["id"],
      "sort_order": 10,
      "anchor": "ctn2",
      "layout_variant": "feature",
      "is_featured": True,
    },
  )
  assert first_mapping_response.status_code == 201, first_mapping_response.text

  duplicate_mapping_response = client.post(
    PROJECT_CATEGORY_ITEMS_URL,
    headers=admin_headers,
    json={
      "category_id": category["id"],
      "project_id": project_two["id"],
      "sort_order": 20,
      "anchor": "ctn2",
      "layout_variant": "standard",
      "is_featured": False,
    },
  )
  assert duplicate_mapping_response.status_code == 409, duplicate_mapping_response.text
  assert "unique project" in duplicate_mapping_response.json()["detail"].lower()


def test_unrelated_entity_duplicate_conflict_still_returns_409(client, admin_headers: dict[str, str]) -> None:
  first_response = client.post(
    NEWS_POSTS_URL,
    headers=admin_headers,
    json={
      "title": "Corporate News",
      "slug": "corporate-news",
      "summary": "First record",
      "status": "draft",
    },
  )
  assert first_response.status_code == 201, first_response.text

  duplicate_response = client.post(
    NEWS_POSTS_URL,
    headers=admin_headers,
    json={
      "title": "Corporate News Copy",
      "slug": "corporate-news",
      "summary": "Duplicate slug",
      "status": "draft",
    },
  )
  assert duplicate_response.status_code == 409, duplicate_response.text
  assert "unique field conflicts" in duplicate_response.json()["detail"].lower()
