PROJECT_CATEGORIES_URL = "/api/v1/admin/project_categories"
PROJECTS_URL = "/api/v1/admin/projects"
PROJECT_CATEGORY_ITEMS_URL = "/api/v1/admin/project_category_items"
MEDIA_ASSETS_URL = "/api/v1/admin/media_assets"
ENTITY_MEDIA_URL = "/api/v1/admin/entity_media"
PUBLIC_PROJECT_CASE_URL = "/api/v1/public/project-case"


def _create_entity(client, admin_headers: dict[str, str], url: str, payload: dict):
    response = client.post(url, headers=admin_headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def test_public_project_case_returns_expected_shape_and_order(client, admin_headers: dict[str, str]) -> None:
    category = _create_entity(
        client,
        admin_headers,
        PROJECT_CATEGORIES_URL,
        {
            "name": "Star Hotel",
            "slug": "star-hotel",
            "status": "active",
            "sort_order": 20,
        },
    )

    project_one = _create_entity(
        client,
        admin_headers,
        PROJECTS_URL,
        {
            "title": "W HOTEL",
            "slug": "w-hotel",
            "summary": "W hotel summary",
            "language_id": 1,
            "status": "published",
        },
    )
    project_two = _create_entity(
        client,
        admin_headers,
        PROJECTS_URL,
        {
            "title": "BEIJING HOTEL",
            "slug": "beijing-hotel-star",
            "summary": "Beijing hotel summary",
            "language_id": 1,
            "status": "published",
        },
    )

    _create_entity(
        client,
        admin_headers,
        PROJECT_CATEGORY_ITEMS_URL,
        {
            "category_id": category["id"],
            "project_id": project_one["id"],
            "sort_order": 1,
            "anchor": "ctn2",
            "layout_variant": "feature",
            "is_featured": True,
        },
    )
    _create_entity(
        client,
        admin_headers,
        PROJECT_CATEGORY_ITEMS_URL,
        {
            "category_id": category["id"],
            "project_id": project_two["id"],
            "sort_order": 2,
            "anchor": "ctn3",
            "layout_variant": "standard",
            "is_featured": False,
        },
    )

    hero_desktop = _create_entity(
        client,
        admin_headers,
        MEDIA_ASSETS_URL,
        {
            "uuid": "project-case-test-hero-desktop",
            "url": "https://example.com/hero-desktop.jpg",
            "asset_type": "image",
            "file_name": "hero-desktop.jpg",
        },
    )
    project_gallery = _create_entity(
        client,
        admin_headers,
        MEDIA_ASSETS_URL,
        {
            "uuid": "project-case-test-left-gallery",
            "url": "https://example.com/left-1.jpg",
            "asset_type": "image",
            "file_name": "left-1.jpg",
        },
    )

    _create_entity(
        client,
        admin_headers,
        ENTITY_MEDIA_URL,
        {
            "entity_type": "project_category",
            "entity_id": category["id"],
            "group_name": "hero_desktop",
            "media_id": hero_desktop["id"],
            "sort_order": 1,
        },
    )
    _create_entity(
        client,
        admin_headers,
        ENTITY_MEDIA_URL,
        {
            "entity_type": "project",
            "entity_id": project_one["id"],
            "group_name": "left_gallery",
            "media_id": project_gallery["id"],
            "sort_order": 1,
        },
    )

    response = client.get(f"{PUBLIC_PROJECT_CASE_URL}/{category['id']}")
    assert response.status_code == 200, response.text

    data = response.json()
    assert data["currentCategory"]["id"] == str(category["id"])
    assert isinstance(data["categories"], list) and data["categories"]
    assert isinstance(data["heroSlides"], list) and data["heroSlides"]
    assert isinstance(data["cases"], list) and len(data["cases"]) == 2
    assert set(data.keys()) == {"currentCategory", "categories", "heroSlides", "cases"}
    assert data["cases"][0]["anchor"] == "ctn2"
    assert data["cases"][1]["anchor"] == "ctn3"
    assert data["cases"][0]["title"] == "W HOTEL"
    assert data["cases"][0]["detailHref"] == "/project/w-hotel"
    assert data["cases"][0]["legacyDetailHref"] is None
    assert data["cases"][0]["leftGallery"] == ["https://example.com/left-1.jpg"]
    assert data["categories"][0]["projects"][0]["anchor"] == "ctn2"


def test_public_project_case_returns_404_for_unknown_category(client) -> None:
    response = client.get(f"{PUBLIC_PROJECT_CASE_URL}/999999")
    assert response.status_code == 404, response.text
