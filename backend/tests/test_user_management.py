"""員工與部門管理（SPEC.md §4.7 §3.3）。"""

from tests.helpers import ADMIN_ID, EMPLOYEE_ID, MANAGER_ID, login_headers


async def test_admin_create_user(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/users", headers=headers,
        json={"name": "新員工", "email": "new1@demo.com", "role": "employee", "department_id": 1, "password": "Demo1234"},
    )

    assert response.status_code == 201
    body = response.json()["user"]
    assert "password_hash" not in body
    assert body["employee_no"].startswith("EMP")


async def test_new_account_login_is_first_login_true(client):
    admin_headers = await login_headers(client, "admin@demo.com")
    await client.post(
        "/api/users", headers=admin_headers,
        json={"name": "新員工", "email": "new2@demo.com", "role": "employee", "department_id": 1, "password": "Demo1234"},
    )

    response = await client.post("/api/auth/login", json={"email": "new2@demo.com", "password": "Demo1234"})

    assert response.json()["user"]["is_first_login"] is True


async def test_duplicate_email_returns_409(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/users", headers=headers,
        json={"name": "重複", "email": "employee@demo.com", "role": "employee", "department_id": 1, "password": "Demo1234"},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


async def test_invalid_role_returns_400(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/users", headers=headers,
        json={"name": "x", "email": "new3@demo.com", "role": "superadmin", "department_id": 1, "password": "Demo1234"},
    )

    assert response.status_code == 400


async def test_nonexistent_department_returns_400(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/users", headers=headers,
        json={"name": "x", "email": "new4@demo.com", "role": "employee", "department_id": 999, "password": "Demo1234"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "DEPARTMENT_NOT_FOUND"


async def test_single_admin_only_on_create(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/users", headers=headers,
        json={"name": "第二位管理者", "email": "new5@demo.com", "role": "admin", "department_id": None, "password": "Demo1234"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SINGLE_ADMIN_ONLY"


async def test_non_admin_create_forbidden(client):
    manager_headers = await login_headers(client, "manager@demo.com")
    employee_headers = await login_headers(client, "employee@demo.com")
    payload = {"name": "x", "email": "new6@demo.com", "role": "employee", "department_id": 1, "password": "Demo1234"}

    manager_res = await client.post("/api/users", headers=manager_headers, json=payload)
    employee_res = await client.post("/api/users", headers=employee_headers, json=payload)

    assert manager_res.status_code == 403
    assert employee_res.status_code == 403


async def test_admin_update_user(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.put(
        f"/api/users/{EMPLOYEE_ID}", headers=headers,
        json={"name": "陳小華改名", "email": "employee@demo.com", "role": "employee", "department_id": 1},
    )

    assert response.status_code == 200
    assert response.json()["user"]["name"] == "陳小華改名"


async def test_update_to_existing_email_returns_409(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.put(
        f"/api/users/{EMPLOYEE_ID}", headers=headers,
        json={"name": "陳小華", "email": "manager@demo.com", "role": "employee", "department_id": 1},
    )

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "EMAIL_ALREADY_EXISTS"


async def test_last_admin_protected(client, db):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.put(
        f"/api/users/{ADMIN_ID}", headers=headers,
        json={"name": "系統管理者", "email": "admin@demo.com", "role": "employee", "department_id": None},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "LAST_ADMIN_PROTECTED"
    row = await db.fetchrow("SELECT role FROM users WHERE id = $1", ADMIN_ID)
    assert row["role"] == "admin"


async def test_single_admin_only_on_update(client, db):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.put(
        f"/api/users/{MANAGER_ID}", headers=headers,
        json={"name": "王小明", "email": "manager@demo.com", "role": "admin", "department_id": 1},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "SINGLE_ADMIN_ONLY"
    row = await db.fetchrow("SELECT role FROM users WHERE id = $1", MANAGER_ID)
    assert row["role"] == "manager"


async def test_update_extension_and_hire_date(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.put(
        f"/api/users/{EMPLOYEE_ID}", headers=headers,
        json={
            "name": "陳小華", "email": "employee@demo.com", "role": "employee", "department_id": 1,
            "extension_number": "999", "hire_date": "2024-01-01",
        },
    )

    body = response.json()["user"]
    assert body["extension_number"] == "999"
    assert body["hire_date"] == "2024-01-01"


async def test_partial_update_preserves_extension_number(client):
    """PUT /users/{id} 不傳 extension_number 時原值必須保留，不得覆蓋成 NULL
    （見 docs/PITFALLS.md A2；REBUILD-TASKS.md 批 5 明確要求的驗收項）。"""
    headers = await login_headers(client, "admin@demo.com")
    await client.put(
        f"/api/users/{EMPLOYEE_ID}", headers=headers,
        json={
            "name": "陳小華", "email": "employee@demo.com", "role": "employee", "department_id": 1,
            "extension_number": "888",
        },
    )

    response = await client.put(
        f"/api/users/{EMPLOYEE_ID}", headers=headers,
        json={"name": "陳小華改名", "email": "employee@demo.com", "role": "employee", "department_id": 1},
    )

    assert response.status_code == 200
    assert response.json()["user"]["extension_number"] == "888"


async def test_admin_delete_user_then_cannot_login(client):
    admin_headers = await login_headers(client, "admin@demo.com")

    delete_res = await client.delete(f"/api/users/{EMPLOYEE_ID}", headers=admin_headers)
    assert delete_res.status_code == 200

    login_res = await client.post("/api/auth/login", json={"email": "employee@demo.com", "password": "Demo1234"})
    assert login_res.status_code == 401


async def test_admin_delete_self_returns_400(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.delete(f"/api/users/{ADMIN_ID}", headers=headers)

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "CANNOT_DELETE_SELF"


async def test_delete_nonexistent_returns_404(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.delete("/api/users/999999", headers=headers)

    assert response.status_code == 404


async def test_admin_list_users_no_password_hash(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.get("/api/users", headers=headers)

    assert response.status_code == 200
    for user in response.json()["users"]:
        assert "password_hash" not in user


async def test_manager_and_employee_list_users_sees_all_company(client):
    manager_headers = await login_headers(client, "manager@demo.com")
    employee_headers = await login_headers(client, "employee@demo.com")

    manager_res = await client.get("/api/users", headers=manager_headers)
    employee_res = await client.get("/api/users", headers=employee_headers)

    assert len(manager_res.json()["users"]) == 6
    assert len(employee_res.json()["users"]) == 6


async def test_filter_by_department(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.get("/api/users?department_id=2", headers=headers)

    assert response.status_code == 200
    assert all(u["department_id"] == 2 for u in response.json()["users"])
    assert len(response.json()["users"]) == 2


async def test_department_list_includes_manager_and_member_count(client):
    headers = await login_headers(client, "admin@demo.com")
    await client.put(
        "/api/departments/1", headers=headers, json={"name": "研發部", "manager_id": MANAGER_ID},
    )

    response = await client.get("/api/departments", headers=headers)

    dept = next(d for d in response.json()["departments"] if d["id"] == 1)
    assert dept["manager_name"] == "王小明"
    assert dept["member_count"] == 2


async def test_employee_as_manager_returns_400(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.put(
        "/api/departments/1", headers=headers, json={"name": "研發部", "manager_id": EMPLOYEE_ID},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "INVALID_MANAGER_ROLE"


async def test_admin_create_department(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post("/api/departments", headers=headers, json={"name": "行銷部", "manager_id": None})

    assert response.status_code == 201
    assert response.json()["department"]["name"] == "行銷部"


async def test_delete_department_with_members_keeps_members(client, db):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.delete("/api/departments/1", headers=headers)

    assert response.status_code == 200
    row = await db.fetchrow("SELECT department_id FROM users WHERE id = $1", EMPLOYEE_ID)
    assert row["department_id"] is None


async def test_non_admin_department_maintenance_forbidden(client):
    headers = await login_headers(client, "manager@demo.com")

    response = await client.post("/api/departments", headers=headers, json={"name": "x", "manager_id": None})

    assert response.status_code == 403


async def test_new_user_gets_auto_generated_employee_no(client):
    """即使前端夾帶 employee_no 也一律忽略，員編由資料庫序列產生（不接受前端傳入）。"""
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/users", headers=headers,
        json={
            "name": "x", "email": "new7@demo.com", "role": "employee", "department_id": 1,
            "password": "Demo1234", "employee_no": "HACKED999",
        },
    )

    assert response.json()["user"]["employee_no"].startswith("EMP")
    assert response.json()["user"]["employee_no"] != "HACKED999"


async def test_employee_no_increments_and_is_unique(client):
    headers = await login_headers(client, "admin@demo.com")

    first = await client.post(
        "/api/users", headers=headers,
        json={"name": "x", "email": "new8@demo.com", "role": "employee", "department_id": 1, "password": "Demo1234"},
    )
    second = await client.post(
        "/api/users", headers=headers,
        json={"name": "y", "email": "new9@demo.com", "role": "employee", "department_id": 1, "password": "Demo1234"},
    )

    first_no = first.json()["user"]["employee_no"]
    second_no = second.json()["user"]["employee_no"]
    assert first_no != second_no


async def test_seed_users_have_stable_employee_no(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.get("/api/users", headers=headers)

    by_id = {u["id"]: u["employee_no"] for u in response.json()["users"]}
    assert by_id[ADMIN_ID] == "EMP2019001"
    assert by_id[EMPLOYEE_ID] == "EMP2025001"
