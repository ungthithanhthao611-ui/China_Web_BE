from collections.abc import Iterable
from typing import Any


ADMIN_NAVIGATION_MENUS_URL = "/api/v1/admin/navigation/menus"


def _create_menu(client, admin_headers: dict[str, str]) -> dict[str, Any]:
    response = client.post(
        ADMIN_NAVIGATION_MENUS_URL,
        headers=admin_headers,
        json={
            "name": "Main Navigation",
            "location": "header",
            "language_id": 1,
            "is_active": True,
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def _get_menu_by_id(client, admin_headers: dict[str, str], menu_id: int) -> dict[str, Any]:
    response = client.get(ADMIN_NAVIGATION_MENUS_URL, headers=admin_headers)
    assert response.status_code == 200, response.text
    menus = response.json().get("items", [])
    for menu in menus:
        if menu["id"] == menu_id:
            return menu
    raise AssertionError(f"Menu #{menu_id} not found in response: {menus}")


def _flatten_item_ids(nodes: Iterable[dict[str, Any]]) -> list[int]:
    ids: list[int] = []

    def walk(items: Iterable[dict[str, Any]]) -> None:
        for item in items:
            ids.append(item["id"])
            walk(item.get("children", []))

    walk(nodes)
    return ids


def test_replace_navigation_tree_persists_nested_items(client, admin_headers: dict[str, str]) -> None:
    menu = _create_menu(client, admin_headers)
    menu_id = menu["id"]

    payload = {
        "items": [
            {
                "title": "Home",
                "url": "/",
                "sort_order": 0,
                "children": [],
            },
            {
                "title": "About Us",
                "url": "/about-us",
                "sort_order": 10,
                "children": [
                    {
                        "title": "Our Team",
                        "url": "/about-us/team",
                        "sort_order": 0,
                        "children": [],
                    }
                ],
            },
        ]
    }
    save_response = client.put(
        f"{ADMIN_NAVIGATION_MENUS_URL}/{menu_id}/tree",
        headers=admin_headers,
        json=payload,
    )
    assert save_response.status_code == 200, save_response.text
    saved_menu = save_response.json()

    assert len(saved_menu["items"]) == 2
    assert saved_menu["items"][0]["title"] == "Home"
    assert saved_menu["items"][1]["title"] == "About Us"
    assert saved_menu["items"][1]["children"][0]["title"] == "Our Team"
    assert (
        saved_menu["items"][1]["children"][0]["parent_id"]
        == saved_menu["items"][1]["id"]
    )

    menu_from_list = _get_menu_by_id(client, admin_headers, menu_id)
    assert [item["title"] for item in menu_from_list["items"]] == ["Home", "About Us"]
    assert menu_from_list["items"][1]["children"][0]["title"] == "Our Team"


def test_replace_navigation_tree_updates_and_removes_stale_nodes(client, admin_headers: dict[str, str]) -> None:
    menu = _create_menu(client, admin_headers)
    menu_id = menu["id"]

    initial_payload = {
        "items": [
            {
                "title": "About",
                "url": "/about",
                "sort_order": 0,
                "children": [
                    {
                        "title": "Team",
                        "url": "/about/team",
                        "sort_order": 0,
                        "children": [],
                    }
                ],
            },
            {
                "title": "Legacy",
                "url": "/legacy",
                "sort_order": 10,
                "children": [],
            },
        ]
    }
    initial_save_response = client.put(
        f"{ADMIN_NAVIGATION_MENUS_URL}/{menu_id}/tree",
        headers=admin_headers,
        json=initial_payload,
    )
    assert initial_save_response.status_code == 200, initial_save_response.text
    initial_tree = initial_save_response.json()["items"]

    root_about_id = initial_tree[0]["id"]
    child_team_id = initial_tree[0]["children"][0]["id"]
    stale_legacy_id = initial_tree[1]["id"]

    update_payload = {
        "items": [
            {
                "id": root_about_id,
                "title": "About Updated",
                "url": "/about-us",
                "sort_order": 0,
                "children": [
                    {
                        "id": child_team_id,
                        "title": "Team Updated",
                        "url": "/about-us/team",
                        "sort_order": 5,
                        "children": [],
                    }
                ],
            },
            {
                "title": "Contact",
                "url": "/contact",
                "children": [],
            },
        ]
    }
    update_response = client.put(
        f"{ADMIN_NAVIGATION_MENUS_URL}/{menu_id}/tree",
        headers=admin_headers,
        json=update_payload,
    )
    assert update_response.status_code == 200, update_response.text
    updated_menu = update_response.json()

    assert [item["title"] for item in updated_menu["items"]] == ["About Updated", "Contact"]
    assert updated_menu["items"][0]["children"][0]["id"] == child_team_id
    assert updated_menu["items"][0]["children"][0]["title"] == "Team Updated"
    assert updated_menu["items"][1]["sort_order"] == 10

    menu_from_list = _get_menu_by_id(client, admin_headers, menu_id)
    persisted_ids = _flatten_item_ids(menu_from_list["items"])
    assert stale_legacy_id not in persisted_ids
    assert root_about_id in persisted_ids
    assert child_team_id in persisted_ids
