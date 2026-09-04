"""匯出報表（SPEC.md §4.8 §6.7）。

範圍限縮一律 deny-by-default：這裡的測試矩陣刻意涵蓋 manager 與「被授予
exports.run 的一般員工」兩種可匯出身分，確保兩者遵守完全相同的限縮規則
（見 docs/PITFALLS.md C1）。
"""

import io

import openpyxl

from tests.helpers import EMPLOYEE_ID, MANAGER_ID, OTHER_EMPLOYEE_ID, login_headers

MONDAY = "2026-08-24"
TUESDAY = "2026-08-25"


async def _grant_exports_run(client, admin_headers, user_id):
    await client.put(
        f"/api/users/{user_id}/permissions", headers=admin_headers, json={"permissions": ["exports.run"]},
    )


async def test_column_selection_returns_only_selected_columns(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/exports/employees", headers=headers, json={"columns": ["name", "email"]},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["columns"] == [{"key": "name", "label": "姓名"}, {"key": "email", "label": "電子郵件"}]
    assert all(len(row) == 2 for row in body["rows"])


async def test_employees_export_includes_employee_no_by_default(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post("/api/exports/employees", headers=headers, json={})

    keys = [c["key"] for c in response.json()["columns"]]
    assert "employee_no" in keys


async def test_manager_department_scope_forced_ignores_client_filter(client):
    headers = await login_headers(client, "manager@demo.com")

    response = await client.post(
        "/api/exports/employees", headers=headers, json={"filters": {"department_id": 2}},
    )

    assert response.status_code == 200
    rows = response.json()["rows"]
    department_name_index = [c["key"] for c in response.json()["columns"]].index("department_name")
    assert all(row[department_name_index] == "研發部" for row in rows)
    assert len(rows) == 2  # 王小明、陳小華


async def test_employee_without_exports_permission_returns_403(client):
    headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/exports/employees", headers=headers, json={})

    assert response.status_code == 403


async def test_invalid_column_rejected(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/exports/employees", headers=headers, json={"columns": ["password_hash"]},
    )

    assert response.status_code == 400


async def test_unknown_kind_returns_400(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post("/api/exports/unknown-kind", headers=headers, json={})

    assert response.status_code == 400


async def test_xlsx_download_readable_by_openpyxl(client):
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/exports/employees?format=xlsx", headers=headers, json={"columns": ["employee_no", "name"]},
    )

    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    assert 'attachment; filename="employees.xlsx"' in response.headers["content-disposition"]

    workbook = openpyxl.load_workbook(io.BytesIO(response.content))
    sheet = workbook.active
    assert [cell.value for cell in sheet[1]] == ["員工編號", "姓名"]
    assert sheet.max_row >= 7  # 表頭 + 6 個種子使用者


async def test_room_bookings_export(client, db):
    await db.execute(
        "INSERT INTO room_bookings (room_id, user_id, title, start_time, end_time) "
        f"VALUES (1, {EMPLOYEE_ID}, '部門會議', '{MONDAY}T09:00:00+08:00', '{MONDAY}T10:00:00+08:00')"
    )
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post("/api/exports/room-bookings", headers=headers, json={})

    assert response.status_code == 200
    keys = [c["key"] for c in response.json()["columns"]]
    assert keys == ["room_name", "booked_by_name", "department_name", "title", "start_time", "end_time", "status"]
    assert response.json()["total"] == 1


async def test_manager_room_bookings_export_not_department_restricted(client, db):
    await db.execute(
        "INSERT INTO room_bookings (room_id, user_id, title, start_time, end_time) "
        f"VALUES (2, {OTHER_EMPLOYEE_ID}, '業務部會議', '{MONDAY}T09:00:00+08:00', '{MONDAY}T10:00:00+08:00')"
    )
    headers = await login_headers(client, "manager@demo.com")

    response = await client.post(
        "/api/exports/room-bookings", headers=headers, json={"filters": {"department_id": 2}},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 1


async def test_manager_attendance_export_department_scope_forced(client, db):
    await db.execute(
        f"INSERT INTO attendances (user_id, punch_date, punch_in_time, status) "
        f"VALUES ({OTHER_EMPLOYEE_ID}, '{MONDAY}', '{MONDAY}T09:00:00+08:00', 'normal')"
    )
    headers = await login_headers(client, "manager@demo.com")

    response = await client.post(
        "/api/exports/attendance", headers=headers, json={"filters": {"department_id": 2}},
    )

    assert response.status_code == 200
    # 強制限縮回研發部（部門 1），業務部（部門 2）的出勤列不得外洩。
    assert response.json()["total"] == 0


async def test_manager_without_department_forbidden_on_employees_and_attendance(client, db):
    await db.execute(f"UPDATE users SET department_id = NULL WHERE id = {MANAGER_ID}")
    headers = await login_headers(client, "manager@demo.com")

    employees_res = await client.post("/api/exports/employees", headers=headers, json={})
    attendance_res = await client.post("/api/exports/attendance", headers=headers, json={})
    room_bookings_res = await client.post("/api/exports/room-bookings", headers=headers, json={})

    assert employees_res.status_code == 403
    assert attendance_res.status_code == 403
    assert room_bookings_res.status_code == 200


async def test_manager_attendance_user_id_outside_department_forbidden(client):
    headers = await login_headers(client, "manager@demo.com")

    response = await client.post(
        "/api/exports/attendance", headers=headers, json={"filters": {"user_id": OTHER_EMPLOYEE_ID}},
    )

    assert response.status_code == 403


async def test_manager_attendance_user_id_within_department_allowed(client):
    headers = await login_headers(client, "manager@demo.com")

    response = await client.post(
        "/api/exports/attendance", headers=headers, json={"filters": {"user_id": EMPLOYEE_ID}},
    )

    assert response.status_code == 200


async def test_attendance_export_reflects_effective_value_after_approved_punch_request(client, db):
    await db.execute(
        f"INSERT INTO punch_requests (user_id, target_date, type, requested_in_time, reason, status, reviewer_id, reviewed_at) "
        f"VALUES ({EMPLOYEE_ID}, '{MONDAY}', 'in', '{MONDAY}T09:00:00+08:00', '補正', 'approved', {MANAGER_ID}, now())"
    )
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/exports/attendance",
        headers=headers,
        json={"filters": {"start_date": MONDAY, "end_date": MONDAY, "user_id": EMPLOYEE_ID}},
    )

    assert response.status_code == 200
    columns = [c["key"] for c in response.json()["columns"]]
    rows = response.json()["rows"]
    assert len(rows) == 1
    assert rows[0][columns.index("effective_punch_in_time")] == "2026-08-24 09:00:00"


async def test_attendance_raw_export_shows_original_punch_times_unaffected_by_approval(client, db):
    """同一筆已核准補打卡在 attendance-raw 不應該合成任何原始出勤列（見 SPEC.md §4.2）。"""
    await db.execute(
        f"INSERT INTO punch_requests (user_id, target_date, type, requested_in_time, reason, status, reviewer_id, reviewed_at) "
        f"VALUES ({EMPLOYEE_ID}, '{MONDAY}', 'in', '{MONDAY}T09:00:00+08:00', '補正', 'approved', {MANAGER_ID}, now())"
    )
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/exports/attendance-raw",
        headers=headers,
        json={"filters": {"start_date": MONDAY, "end_date": MONDAY, "user_id": EMPLOYEE_ID}},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 0


async def test_attendance_changes_export_includes_reviewer_and_period(client, db):
    await db.execute(
        f"INSERT INTO punch_requests (user_id, target_date, type, requested_in_time, reason, status, reviewer_id, reviewed_at) "
        f"VALUES ({EMPLOYEE_ID}, '{MONDAY}', 'in', '{MONDAY}T09:00:00+08:00', '忘記打卡', 'approved', {MANAGER_ID}, now())"
    )
    headers = await login_headers(client, "admin@demo.com")

    response = await client.post(
        "/api/exports/attendance-changes",
        headers=headers,
        json={"filters": {"start_date": MONDAY, "end_date": MONDAY, "user_id": EMPLOYEE_ID}},
    )

    assert response.status_code == 200
    columns = [c["key"] for c in response.json()["columns"]]
    row = response.json()["rows"][0]
    assert row[columns.index("request_type")] == "補上班卡"
    assert row[columns.index("reviewer_name")] == "王小明"
    assert row[columns.index("status")] == "已核准"
    assert row[columns.index("period")] == MONDAY


async def test_manager_scope_forced_on_new_attendance_kinds(client, db):
    """新增匯出類型時容易漏改 _scope_filters，這裡逐一防呆（見 docs/PITFALLS.md C1）。"""
    await db.execute(
        f"INSERT INTO attendances (user_id, punch_date, punch_in_time, status) "
        f"VALUES ({OTHER_EMPLOYEE_ID}, '{MONDAY}', '{MONDAY}T09:00:00+08:00', 'normal')"
    )
    await db.execute(
        f"INSERT INTO punch_requests (user_id, target_date, type, requested_in_time, reason) "
        f"VALUES ({OTHER_EMPLOYEE_ID}, '{TUESDAY}', 'in', '{TUESDAY}T09:00:00+08:00', '忘記打卡')"
    )
    headers = await login_headers(client, "manager@demo.com")

    raw_res = await client.post(
        "/api/exports/attendance-raw", headers=headers, json={"filters": {"department_id": 2}},
    )
    changes_res = await client.post(
        "/api/exports/attendance-changes", headers=headers, json={"filters": {"user_id": OTHER_EMPLOYEE_ID}},
    )

    assert raw_res.json()["total"] == 0
    assert changes_res.status_code == 403


async def test_employee_granted_exports_run_scope_forced_to_own_department(client):
    """SPEC.md §3.4：被授予 exports.run 的一般員工，匯出範圍與 manager 相同。"""
    admin_headers = await login_headers(client, "admin@demo.com")
    await _grant_exports_run(client, admin_headers, EMPLOYEE_ID)
    grantee_headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/exports/employees", headers=grantee_headers, json={"filters": {"department_id": 2}},
    )

    assert response.status_code == 200
    assert response.json()["total"] == 2  # 研發部：王小明、陳小華


async def test_employee_granted_exports_run_user_id_outside_department_forbidden(client):
    admin_headers = await login_headers(client, "admin@demo.com")
    await _grant_exports_run(client, admin_headers, EMPLOYEE_ID)
    grantee_headers = await login_headers(client, "employee@demo.com")

    response = await client.post(
        "/api/exports/attendance", headers=grantee_headers, json={"filters": {"user_id": OTHER_EMPLOYEE_ID}},
    )

    assert response.status_code == 403


async def test_employee_granted_exports_run_department_id_null_forbidden(client, db):
    admin_headers = await login_headers(client, "admin@demo.com")
    await _grant_exports_run(client, admin_headers, EMPLOYEE_ID)
    await db.execute(f"UPDATE users SET department_id = NULL WHERE id = {EMPLOYEE_ID}")
    grantee_headers = await login_headers(client, "employee@demo.com")

    response = await client.post("/api/exports/employees", headers=grantee_headers, json={})

    assert response.status_code == 403


async def test_other_manager_existing_export_permission_unaffected(client):
    """迴歸點：exports.run 的細粒度授權機制不得影響既有角色型 manager 的匯出權。"""
    headers = await login_headers(client, "manager@demo.com")

    response = await client.post("/api/exports/employees", headers=headers, json={})

    assert response.status_code == 200
