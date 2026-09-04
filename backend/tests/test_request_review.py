"""三種申請單共用的審核狀態機（SPEC.md §3.3 §4.5）。

manager 審跨部門單 403、任何人審自己的單 403（admin 豁免）、admin 待審清單含
自己送出的申請、並行審核只有一筆生效——三種申請單各驗證一次，確認共用的
services/request_review.py 行為一致。
"""

import asyncio

import pytest

from tests.helpers import ADMIN_ID, EMPLOYEE_ID, MANAGER_ID, OTHER_EMPLOYEE_ID, login_headers

REQUEST_TYPES = [
    {
        "name": "punch_requests",
        "create_path": "/api/punch-requests",
        "pending_path": "/api/punch-requests/pending",
        "review_path": lambda rid: f"/api/punch-requests/{rid}/review",
        "body": {
            "type": "in", "target_date": "2026-08-24",
            "requested_in_time": "2026-08-24T09:00:00+08:00", "reason": "忘記打卡",
        },
        "insert_sql": (
            "INSERT INTO punch_requests (user_id, target_date, type, requested_in_time, reason) "
            "VALUES ($1, '2026-08-24', 'in', '2026-08-24T09:00:00+08:00', '忘記打卡') RETURNING id"
        ),
    },
    {
        "name": "leave_requests",
        "create_path": "/api/leave-requests",
        "pending_path": "/api/leave-requests/pending",
        "review_path": lambda rid: f"/api/leave-requests/{rid}/review",
        "body": {
            "leave_type": "事假", "start_time": "2026-08-24T09:00:00+08:00",
            "end_time": "2026-08-24T18:00:00+08:00", "reason": "個人事務",
        },
        "insert_sql": (
            "INSERT INTO leave_requests (user_id, leave_type, start_time, end_time, hours, reason) "
            "VALUES ($1, '事假', '2026-08-24T09:00:00+08:00', '2026-08-24T18:00:00+08:00', 8, '個人事務') "
            "RETURNING id"
        ),
    },
    {
        "name": "overtime_requests",
        "create_path": "/api/overtime-requests",
        "pending_path": "/api/overtime-requests/pending",
        "review_path": lambda rid: f"/api/overtime-requests/{rid}/review",
        "body": {"start_time": "2026-08-24T20:00:00+08:00", "end_time": "2026-08-24T22:00:00+08:00", "reason": "加班"},
        "insert_sql": (
            "INSERT INTO overtime_requests (user_id, start_time, end_time, hours, reason) "
            "VALUES ($1, '2026-08-24T20:00:00+08:00', '2026-08-24T22:00:00+08:00', 2, '加班') RETURNING id"
        ),
    },
]


async def _insert_raw_request(db, request_type, user_id):
    row = await db.fetchrow(request_type["insert_sql"], user_id)
    return row["id"]


@pytest.mark.parametrize("request_type", REQUEST_TYPES, ids=lambda t: t["name"])
class TestReviewStateMachine:
    async def test_approve_pending(self, client, request_type):
        employee_headers = await login_headers(client, "employee@demo.com")
        manager_headers = await login_headers(client, "manager@demo.com")

        create_res = await client.post(request_type["create_path"], headers=employee_headers, json=request_type["body"])
        request_id = create_res.json()["request"]["id"]

        res = await client.patch(
            request_type["review_path"](request_id), headers=manager_headers, json={"action": "approve"}
        )
        assert res.status_code == 200
        assert res.json()["request"]["status"] == "approved"
        assert res.json()["request"]["reviewer_id"] == MANAGER_ID
        assert res.json()["request"]["reviewed_at"]

    async def test_reject_with_note(self, client, request_type):
        employee_headers = await login_headers(client, "employee@demo.com")
        manager_headers = await login_headers(client, "manager@demo.com")

        create_res = await client.post(request_type["create_path"], headers=employee_headers, json=request_type["body"])
        request_id = create_res.json()["request"]["id"]

        res = await client.patch(
            request_type["review_path"](request_id), headers=manager_headers,
            json={"action": "reject", "review_note": "證明文件不足"},
        )
        assert res.status_code == 200
        assert res.json()["request"]["status"] == "rejected"
        assert res.json()["request"]["review_note"] == "證明文件不足"

    async def test_reject_without_note_returns_400(self, client, request_type):
        employee_headers = await login_headers(client, "employee@demo.com")
        manager_headers = await login_headers(client, "manager@demo.com")

        create_res = await client.post(request_type["create_path"], headers=employee_headers, json=request_type["body"])
        request_id = create_res.json()["request"]["id"]

        res = await client.patch(
            request_type["review_path"](request_id), headers=manager_headers, json={"action": "reject"}
        )
        assert res.status_code == 400

    async def test_double_approve_returns_409_and_unchanged(self, client, db, request_type):
        employee_headers = await login_headers(client, "employee@demo.com")
        manager_headers = await login_headers(client, "manager@demo.com")

        create_res = await client.post(request_type["create_path"], headers=employee_headers, json=request_type["body"])
        request_id = create_res.json()["request"]["id"]

        await client.patch(request_type["review_path"](request_id), headers=manager_headers, json={"action": "approve"})
        second = await client.patch(
            request_type["review_path"](request_id), headers=manager_headers,
            json={"action": "reject", "review_note": "想改成駁回"},
        )
        assert second.status_code == 409

        check = await db.fetchrow(f"SELECT status FROM {request_type['name']} WHERE id = $1", request_id)
        assert check["status"] == "approved"

    async def test_double_reject_returns_409(self, client, request_type):
        employee_headers = await login_headers(client, "employee@demo.com")
        manager_headers = await login_headers(client, "manager@demo.com")

        create_res = await client.post(request_type["create_path"], headers=employee_headers, json=request_type["body"])
        request_id = create_res.json()["request"]["id"]

        await client.patch(
            request_type["review_path"](request_id), headers=manager_headers,
            json={"action": "reject", "review_note": "不核准"},
        )
        second = await client.patch(
            request_type["review_path"](request_id), headers=manager_headers, json={"action": "approve"}
        )
        assert second.status_code == 409

    async def test_review_nonexistent_id_returns_404(self, client, request_type):
        manager_headers = await login_headers(client, "manager@demo.com")

        res = await client.patch(request_type["review_path"](999999), headers=manager_headers, json={"action": "approve"})

        assert res.status_code == 404

    async def test_invalid_action_returns_400(self, client, request_type):
        employee_headers = await login_headers(client, "employee@demo.com")
        manager_headers = await login_headers(client, "manager@demo.com")

        create_res = await client.post(request_type["create_path"], headers=employee_headers, json=request_type["body"])
        request_id = create_res.json()["request"]["id"]

        res = await client.patch(
            request_type["review_path"](request_id), headers=manager_headers, json={"action": "cancel"}
        )
        assert res.status_code == 400


async def test_manager_reviews_same_department_ok(client, db):
    request_type = REQUEST_TYPES[0]
    manager_headers = await login_headers(client, "manager@demo.com")
    request_id = await _insert_raw_request(db, request_type, EMPLOYEE_ID)

    res = await client.patch(request_type["review_path"](request_id), headers=manager_headers, json={"action": "approve"})

    assert res.status_code == 200


async def test_manager_reviews_cross_department_forbidden(client, db):
    """OTHER_EMPLOYEE_ID（張大同）屬業務部，manager（王小明）屬研發部——跨部門必擋。"""
    request_type = REQUEST_TYPES[0]
    manager_headers = await login_headers(client, "manager@demo.com")
    request_id = await _insert_raw_request(db, request_type, OTHER_EMPLOYEE_ID)

    res = await client.patch(request_type["review_path"](request_id), headers=manager_headers, json={"action": "approve"})

    assert res.status_code == 403
    check = await db.fetchrow(f"SELECT status FROM {request_type['name']} WHERE id = $1", request_id)
    assert check["status"] == "pending"


async def test_admin_reviews_any_department_ok(client, db):
    request_type = REQUEST_TYPES[0]
    admin_headers = await login_headers(client, "admin@demo.com")
    request_id = await _insert_raw_request(db, request_type, OTHER_EMPLOYEE_ID)

    res = await client.patch(request_type["review_path"](request_id), headers=admin_headers, json={"action": "approve"})

    assert res.status_code == 200


async def test_employee_calling_review_endpoint_forbidden(client, db):
    request_type = REQUEST_TYPES[0]
    employee_headers = await login_headers(client, "employee@demo.com")
    request_id = await _insert_raw_request(db, request_type, EMPLOYEE_ID)

    res = await client.patch(request_type["review_path"](request_id), headers=employee_headers, json={"action": "approve"})

    assert res.status_code == 403


async def test_manager_reviewing_own_request_forbidden(client, db):
    request_type = REQUEST_TYPES[0]
    manager_headers = await login_headers(client, "manager@demo.com")
    request_id = await _insert_raw_request(db, request_type, MANAGER_ID)

    res = await client.patch(request_type["review_path"](request_id), headers=manager_headers, json={"action": "approve"})

    assert res.status_code == 403


async def test_admin_reviewing_own_request_ok_no_deputy_exemption(client, db):
    """唯一管理者無代理人審核自己的申請，豁免自審限制 → 200。"""
    request_type = REQUEST_TYPES[0]
    admin_headers = await login_headers(client, "admin@demo.com")
    request_id = await _insert_raw_request(db, request_type, ADMIN_ID)

    res = await client.patch(request_type["review_path"](request_id), headers=admin_headers, json={"action": "approve"})

    assert res.status_code == 200
    check = await db.fetchrow(f"SELECT status, reviewer_id FROM {request_type['name']} WHERE id = $1", request_id)
    assert check["status"] == "approved"
    assert check["reviewer_id"] == ADMIN_ID


async def test_manager_pending_list_scoped_to_department_excludes_self(client, db):
    request_type = REQUEST_TYPES[0]
    manager_headers = await login_headers(client, "manager@demo.com")
    await _insert_raw_request(db, request_type, EMPLOYEE_ID)
    await _insert_raw_request(db, request_type, OTHER_EMPLOYEE_ID)
    await _insert_raw_request(db, request_type, MANAGER_ID)

    res = await client.get(request_type["pending_path"], headers=manager_headers)

    assert res.status_code == 200
    assert len(res.json()["requests"]) == 1
    assert res.json()["requests"][0]["user_id"] == EMPLOYEE_ID


async def test_admin_pending_list_includes_all_including_self(client, db):
    request_type = REQUEST_TYPES[0]
    admin_headers = await login_headers(client, "admin@demo.com")
    await _insert_raw_request(db, request_type, EMPLOYEE_ID)
    await _insert_raw_request(db, request_type, OTHER_EMPLOYEE_ID)
    await _insert_raw_request(db, request_type, ADMIN_ID)

    res = await client.get(request_type["pending_path"], headers=admin_headers)

    assert res.status_code == 200
    user_ids = sorted(row["user_id"] for row in res.json()["requests"])
    assert user_ids == sorted([EMPLOYEE_ID, OTHER_EMPLOYEE_ID, ADMIN_ID])


async def test_pending_list_includes_applicant_name_and_department(client, db):
    request_type = REQUEST_TYPES[0]
    manager_headers = await login_headers(client, "manager@demo.com")
    await _insert_raw_request(db, request_type, EMPLOYEE_ID)

    res = await client.get(request_type["pending_path"], headers=manager_headers)

    assert res.json()["requests"][0]["applicant_name"] == "陳小華"
    assert res.json()["requests"][0]["department_name"] == "研發部"


async def test_employee_calling_pending_list_forbidden(client):
    request_type = REQUEST_TYPES[0]
    employee_headers = await login_headers(client, "employee@demo.com")

    res = await client.get(request_type["pending_path"], headers=employee_headers)

    assert res.status_code == 403


async def test_empty_pending_list_returns_200_empty_array(client):
    request_type = REQUEST_TYPES[0]
    manager_headers = await login_headers(client, "manager@demo.com")

    res = await client.get(request_type["pending_path"], headers=manager_headers)

    assert res.status_code == 200
    assert res.json()["requests"] == []


async def test_concurrent_review_exactly_one_succeeds(client, db):
    """並行審核只有一筆真正生效，另一筆回 409——repo.update_review() 的
    `WHERE status = 'pending'` 是防止 race 的最終防線（見 services/request_review.py）。
    """
    request_type = REQUEST_TYPES[0]
    manager_headers = await login_headers(client, "manager@demo.com")
    request_id = await _insert_raw_request(db, request_type, EMPLOYEE_ID)

    first, second = await asyncio.gather(
        client.patch(request_type["review_path"](request_id), headers=manager_headers, json={"action": "approve"}),
        client.patch(
            request_type["review_path"](request_id), headers=manager_headers,
            json={"action": "reject", "review_note": "搶審"},
        ),
    )

    assert sorted([first.status_code, second.status_code]) == [200, 409]
