CONTACTS_URL = "/api/v1/admin/contacts"


def test_admin_create_contact_requires_valid_lat_lng(client, admin_headers: dict[str, str]) -> None:
    response = client.post(
        CONTACTS_URL,
        headers=admin_headers,
        json={
            "name": "Head Office",
            "language_id": 1,
            "latitude": "",
            "longitude": "116.44079",
        },
    )

    assert response.status_code == 422, response.text

    response = client.post(
        CONTACTS_URL,
        headers=admin_headers,
        json={
            "name": "Head Office",
            "language_id": 1,
            "latitude": "39.910466",
            "longitude": "200",
        },
    )

    assert response.status_code == 422, response.text


def test_admin_update_contact_rejects_missing_or_invalid_coordinates(client, admin_headers: dict[str, str]) -> None:
    create_response = client.post(
        CONTACTS_URL,
        headers=admin_headers,
        json={
            "name": "Head Office",
            "language_id": 1,
            "latitude": "39.910466",
            "longitude": "116.44079",
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()

    response = client.put(
        f"{CONTACTS_URL}/{created['id']}",
        headers=admin_headers,
        json={
            "name": "Head Office Updated",
            "language_id": 1,
            "latitude": "39.910466",
        },
    )

    assert response.status_code == 422, response.text

    response = client.put(
        f"{CONTACTS_URL}/{created['id']}",
        headers=admin_headers,
        json={
            "name": "Head Office Updated",
            "language_id": 1,
            "latitude": "95",
            "longitude": "116.44079",
        },
    )

    assert response.status_code == 422, response.text


def test_admin_create_contact_can_extract_coordinates_from_dms_map_input(
    client,
    admin_headers: dict[str, str],
) -> None:
    response = client.post(
        CONTACTS_URL,
        headers=admin_headers,
        json={
            "name": "Factory Office",
            "language_id": 1,
            "map_url": '11°11\'53.2"N 106°43\'10.0"E',
        },
    )

    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["latitude"] == "11.198111"
    assert payload["longitude"] == "106.719444"
    assert payload["map_url"] == "https://www.google.com/maps?q=11.198111,106.719444"


def test_admin_update_contact_normalizes_openstreetmap_marker_to_google_maps(
    client,
    admin_headers: dict[str, str],
) -> None:
    create_response = client.post(
        CONTACTS_URL,
        headers=admin_headers,
        json={
            "name": "Factory Office",
            "language_id": 1,
            "latitude": "11.198111",
            "longitude": "106.719444",
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()

    response = client.put(
        f"{CONTACTS_URL}/{created['id']}",
        headers=admin_headers,
        json={
            "name": "Factory Office",
            "language_id": 1,
            "map_url": "https://www.openstreetmap.org/export/embed.html?bbox=106.716%2C11.196%2C106.722%2C11.2&layer=mapnik&marker=11.198111%2C106.719444",
        },
    )

    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["latitude"] == "11.198111"
    assert payload["longitude"] == "106.719444"
    assert payload["map_url"] == "https://www.google.com/maps?q=11.198111,106.719444"
