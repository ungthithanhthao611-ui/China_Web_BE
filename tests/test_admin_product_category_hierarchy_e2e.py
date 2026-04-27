PRODUCT_CATEGORIES_URL = "/api/v1/admin/product_categories"


def test_product_category_can_create_parent_child(client, admin_headers: dict[str, str]) -> None:
    parent_response = client.post(
        PRODUCT_CATEGORIES_URL,
        headers=admin_headers,
        json={
            "name": "Parent Category",
            "slug": "parent-category",
            "is_active": True,
        },
    )
    assert parent_response.status_code == 201, parent_response.text
    parent = parent_response.json()

    child_response = client.post(
        PRODUCT_CATEGORIES_URL,
        headers=admin_headers,
        json={
            "name": "Child Category",
            "slug": "child-category",
            "parent_id": parent["id"],
            "is_active": True,
        },
    )
    assert child_response.status_code == 201, child_response.text
    child = child_response.json()

    assert child["parent_id"] == parent["id"]


def test_product_category_rejects_self_parent(client, admin_headers: dict[str, str]) -> None:
    response = client.post(
        PRODUCT_CATEGORIES_URL,
        headers=admin_headers,
        json={
            "name": "Solo Category",
            "slug": "solo-category",
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    category = response.json()

    update_response = client.put(
        f"{PRODUCT_CATEGORIES_URL}/{category['id']}",
        headers=admin_headers,
        json={"parent_id": category["id"]},
    )
    assert update_response.status_code == 409, update_response.text
    assert "own parent" in str(update_response.json().get("detail", "")).lower()


def test_product_category_rejects_cycle(client, admin_headers: dict[str, str]) -> None:
    parent_response = client.post(
        PRODUCT_CATEGORIES_URL,
        headers=admin_headers,
        json={
            "name": "Cycle Parent",
            "slug": "cycle-parent",
            "is_active": True,
        },
    )
    assert parent_response.status_code == 201, parent_response.text
    parent = parent_response.json()

    child_response = client.post(
        PRODUCT_CATEGORIES_URL,
        headers=admin_headers,
        json={
            "name": "Cycle Child",
            "slug": "cycle-child",
            "parent_id": parent["id"],
            "is_active": True,
        },
    )
    assert child_response.status_code == 201, child_response.text
    child = child_response.json()

    make_cycle_response = client.put(
        f"{PRODUCT_CATEGORIES_URL}/{parent['id']}",
        headers=admin_headers,
        json={"parent_id": child["id"]},
    )
    assert make_cycle_response.status_code == 409, make_cycle_response.text
    detail = str(make_cycle_response.json().get("detail", "")).lower()
    assert "top-level categories" in detail or "cyclic hierarchy" in detail


def test_product_category_rejects_child_as_parent_option(client, admin_headers: dict[str, str]) -> None:
    root_response = client.post(
        PRODUCT_CATEGORIES_URL,
        headers=admin_headers,
        json={
            "name": "Root Category",
            "slug": "root-category",
            "is_active": True,
        },
    )
    assert root_response.status_code == 201, root_response.text
    root = root_response.json()

    child_response = client.post(
        PRODUCT_CATEGORIES_URL,
        headers=admin_headers,
        json={
            "name": "Child Category A",
            "slug": "child-category-a",
            "parent_id": root["id"],
            "is_active": True,
        },
    )
    assert child_response.status_code == 201, child_response.text
    child = child_response.json()

    invalid_response = client.post(
        PRODUCT_CATEGORIES_URL,
        headers=admin_headers,
        json={
            "name": "Category Uses Child As Parent",
            "slug": "category-uses-child-as-parent",
            "parent_id": child["id"],
            "is_active": True,
        },
    )
    assert invalid_response.status_code == 409, invalid_response.text
    assert "top-level categories" in str(invalid_response.json().get("detail", "")).lower()
