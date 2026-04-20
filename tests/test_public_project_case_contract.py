PROJECT_CATEGORIES_URL = "/api/v1/admin/project_categories"
PROJECTS_URL = "/api/v1/admin/projects"
PROJECT_CATEGORY_ITEMS_URL = "/api/v1/admin/project_category_items"
PUBLIC_PROJECT_CASE_URL = "/api/v1/public/project-case"


def _create_entity(client, admin_headers: dict[str, str], url: str, payload: dict):
    response = client.post(url, headers=admin_headers, json=payload)
    assert response.status_code == 201, response.text
    return response.json()


def _seed_project_case_contract_fixture(client, admin_headers: dict[str, str]) -> dict[str, int]:
    category = _create_entity(
        client,
        admin_headers,
        PROJECT_CATEGORIES_URL,
        {
            "name": "Star Hotel",
            "slug": "star-hotel",
            "status": "active",
            "sort_order": 10,
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
            "legacy_detail_id": "1676516550370418688",
            "legacy_detail_href": "/project_detail/1676516550370418688.html",
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
            "project_id": project_two["id"],
            "sort_order": 20,
            "anchor": "ctn3",
            "layout_variant": "standard",
            "is_featured": False,
        },
    )
    _create_entity(
        client,
        admin_headers,
        PROJECT_CATEGORY_ITEMS_URL,
        {
            "category_id": category["id"],
            "project_id": project_one["id"],
            "sort_order": 10,
            "anchor": "ctn2",
            "layout_variant": "feature",
            "is_featured": True,
        },
    )

    return {
        "category_id": category["id"],
        "project_one_id": project_one["id"],
        "project_two_id": project_two["id"],
    }


def test_project_case_contract_is_minimal_and_stable(client, admin_headers: dict[str, str]) -> None:
    fixture = _seed_project_case_contract_fixture(client, admin_headers)

    response = client.get(f"{PUBLIC_PROJECT_CASE_URL}/{fixture['category_id']}")
    assert response.status_code == 200, response.text

    data = response.json()
    assert set(data.keys()) == {"currentCategory", "categories", "heroSlides", "cases"}
    assert set(data["currentCategory"].keys()) == {"id", "name", "slug"}
    assert set(data["categories"][0].keys()) == {"id", "name", "slug"}
    assert set(data["heroSlides"][0].keys()) == {"categoryId", "title", "desktopImage", "mobileImage", "summary"}
    assert set(data["cases"][0].keys()) == {
        "anchor",
        "title",
        "summary",
        "detailHref",
        "legacyDetailHref",
        "leftGallery",
        "rightGallery",
        "layoutVariant",
    }

    assert [item["anchor"] for item in data["cases"]] == ["ctn2", "ctn3"]
    assert data["cases"][0]["detailHref"] == "/project/w-hotel"
    assert data["cases"][0]["legacyDetailHref"] == "/project_detail/1676516550370418688.html"


def test_project_case_query_endpoint_matches_path_endpoint(client, admin_headers: dict[str, str]) -> None:
    fixture = _seed_project_case_contract_fixture(client, admin_headers)

    path_response = client.get(f"{PUBLIC_PROJECT_CASE_URL}/{fixture['category_id']}")
    query_response = client.get(PUBLIC_PROJECT_CASE_URL, params={"category_id": fixture["category_id"]})

    assert path_response.status_code == 200, path_response.text
    assert query_response.status_code == 200, query_response.text
    assert query_response.json() == path_response.json()


def test_project_case_mapping_anchor_must_be_unique_within_category(client, admin_headers: dict[str, str]) -> None:
    fixture = _seed_project_case_contract_fixture(client, admin_headers)

    duplicate_response = client.post(
        PROJECT_CATEGORY_ITEMS_URL,
        headers=admin_headers,
        json={
            "category_id": fixture["category_id"],
            "project_id": fixture["project_two_id"],
            "sort_order": 30,
            "anchor": "ctn2",
            "layout_variant": "feature",
            "is_featured": False,
        },
    )

    assert duplicate_response.status_code == 409, duplicate_response.text
    assert "unique anchor" in duplicate_response.json()["detail"].lower()
