"""資料庫檢視頁（SPEC.md §6.7）。"""

from app.config.tables import BUSINESS_TABLES
from tests.helpers import login_headers


async def test_admin_can_view_schema(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.get("/api/admin/schema", headers=headers)

    assert response.status_code == 200
    assert set(response.json()["tables"].keys()) == set(BUSINESS_TABLES)


async def test_users_table_has_expected_columns_and_keys(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.get("/api/admin/schema", headers=headers)

    users_columns = {c["name"]: c for c in response.json()["tables"]["users"]}
    assert users_columns["id"]["is_primary_key"] is True
    assert users_columns["department_id"]["is_foreign_key"] is True
    assert users_columns["department_id"]["references"]["table"] == "departments"
    assert users_columns["email"]["nullable"] is False


async def test_non_admin_forbidden(client):
    manager_headers = await login_headers(client, "manager@demo.com")
    employee_headers = await login_headers(client, "employee@demo.com")

    manager_res = await client.get("/api/admin/schema", headers=manager_headers)
    employee_res = await client.get("/api/admin/schema", headers=employee_headers)

    assert manager_res.status_code == 403
    assert employee_res.status_code == 403


async def test_admin_can_preview_table_rows(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.get("/api/admin/schema/users/rows", headers=headers)

    assert response.status_code == 200
    rows = response.json()["rows"]
    assert 0 < len(rows) <= 20


async def test_preview_rejects_table_outside_allowlist(client):
    headers = await login_headers(client, "admin@demo.com")

    injection_attempt = await client.get(
        "/api/admin/schema/users%3B%20DROP%20TABLE%20users%3B--/rows", headers=headers
    )
    unknown_table = await client.get("/api/admin/schema/pg_shadow/rows", headers=headers)

    assert injection_attempt.status_code == 400
    assert unknown_table.status_code == 400


async def test_preview_masks_password_hash(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.get("/api/admin/schema/users/rows", headers=headers)

    assert all(row["password_hash"] == "******" for row in response.json()["rows"])


async def test_preview_non_admin_forbidden(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.get("/api/admin/schema/users/rows", headers=headers)

    assert response.status_code == 403
