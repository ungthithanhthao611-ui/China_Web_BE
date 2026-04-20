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
