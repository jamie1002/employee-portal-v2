"""國定假日維護（SPEC.md §4.9 §6.6）。"""

from tests.helpers import login_headers


async def test_list_visible_to_any_role(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/holidays", headers=headers)

    assert response.status_code == 200
    assert len(response.json()["holidays"]) == 12


async def test_list_requires_auth(client):
    response = await client.get("/api/holidays")

    assert response.status_code == 401


async def test_admin_create_holiday(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/holidays", headers=headers, json={"holiday_date": "2026-12-25", "name": "聖誕節（示範）"},
    )

    assert response.status_code == 201
    assert response.json()["holiday"]["name"] == "聖誕節（示範）"


async def test_duplicate_date_returns_409(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/holidays", headers=headers, json={"holiday_date": "2026-01-01", "name": "重複"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "HOLIDAY_ALREADY_EXISTS"


async def test_employee_create_forbidden(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/holidays", headers=headers, json={"holiday_date": "2026-12-25", "name": "聖誕節（示範）"},
    )

    assert response.status_code == 403


async def test_permission_holder_can_create_and_delete(client):
    """持有 holidays.manage 權限的一般員工也能維護，不需要是 admin（SPEC.md §3.4）。"""
    admin_headers = await login_headers(client, "admin@demo.com")
    await client.put(
        "/api/users/3/permissions", headers=admin_headers, json={"permissions": ["holidays.manage"]},
    )
    grantee_headers = await login_headers(client, "employee@demo.com")

    create_res = await client.post(
        "/api/holidays", headers=grantee_headers, json={"holiday_date": "2026-12-25", "name": "聖誕節（示範）"},
    )
    assert create_res.status_code == 201

    delete_res = await client.delete("/api/holidays/2026-12-25", headers=grantee_headers)
    assert delete_res.status_code == 204


async def test_admin_delete_holiday(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.delete("/api/holidays/2026-01-01", headers=headers)

    assert response.status_code == 204


async def test_delete_nonexistent_returns_404(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.delete("/api/holidays/2099-01-01", headers=headers)

    assert response.status_code == 404


async def test_employee_delete_forbidden(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.delete("/api/holidays/2026-01-01", headers=headers)

    assert response.status_code == 403
