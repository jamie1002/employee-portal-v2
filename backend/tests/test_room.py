"""場地清單（SPEC.md §6.4）。"""

from tests.helpers import login_headers


async def test_three_rooms_with_full_fields(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/rooms", headers=headers)

    assert response.status_code == 200
    rooms = response.json()["rooms"]
    assert len(rooms) == 3
    for room in rooms:
        assert set(["id", "name", "capacity", "location_info"]).issubset(room.keys())


async def test_requires_auth(client):
    response = await client.get("/api/rooms")

    assert response.status_code == 401


async def test_consistent_order_across_calls(client):
    headers = await login_headers(client, "employee@demo.com")

    first = await client.get("/api/rooms", headers=headers)
    second = await client.get("/api/rooms", headers=headers)

    assert [r["id"] for r in first.json()["rooms"]] == [1, 2, 3]
    assert [r["id"] for r in second.json()["rooms"]] == [1, 2, 3]
