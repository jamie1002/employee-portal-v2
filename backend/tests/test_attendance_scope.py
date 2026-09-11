"""可見範圍解析：出勤明細與出勤異動共用的權限判斷。

這支測試直接打 service 函式而不是 HTTP 端點，因為它要驗證的是「即使呼叫端不是
router（例如未來的 AI 查詢工具），限縮依然成立」——限縮若只存在於 router，
這裡就會抓不到。
"""

import pytest

from app.services import attendance_scope
from app.utils.errors import AppError
from tests.helpers import (
    ADMIN_ID,
    EMPLOYEE_ID,
    MANAGER_ID,
    OTHER_EMPLOYEE_ID,
    OTHER_MANAGER_ID,
)

ADMIN = {"id": ADMIN_ID, "role": "admin", "department_id": None}
MANAGER = {"id": MANAGER_ID, "role": "manager", "department_id": 1}
EMPLOYEE = {"id": EMPLOYEE_ID, "role": "employee", "department_id": 1}


async def test_admin_sees_everyone(db):
    user_ids = await attendance_scope.resolve_visible_user_ids(db, ADMIN)

    assert {MANAGER_ID, EMPLOYEE_ID, OTHER_EMPLOYEE_ID} <= set(user_ids)


async def test_admin_can_filter_by_any_department(db):
    user_ids = await attendance_scope.resolve_visible_user_ids(db, ADMIN, department_id=2)

    assert OTHER_EMPLOYEE_ID in user_ids
    assert EMPLOYEE_ID not in user_ids


async def test_manager_is_narrowed_to_own_department(db):
    user_ids = await attendance_scope.resolve_visible_user_ids(db, MANAGER)

    assert set(user_ids) <= {MANAGER_ID, EMPLOYEE_ID}
    assert OTHER_EMPLOYEE_ID not in user_ids


async def test_manager_specifying_own_department_is_allowed(db):
    user_ids = await attendance_scope.resolve_visible_user_ids(db, MANAGER, department_id=1)

    assert set(user_ids) <= {MANAGER_ID, EMPLOYEE_ID}


async def test_manager_specifying_other_department_is_forbidden(db):
    with pytest.raises(AppError) as exc:
        await attendance_scope.resolve_visible_user_ids(db, MANAGER, department_id=2)

    assert exc.value.status_code == 403


async def test_manager_specifying_other_department_member_is_forbidden(db):
    with pytest.raises(AppError) as exc:
        await attendance_scope.resolve_visible_user_ids(db, MANAGER, user_id=OTHER_EMPLOYEE_ID)

    assert exc.value.status_code == 403


async def test_manager_specifying_own_member_is_allowed(db):
    user_ids = await attendance_scope.resolve_visible_user_ids(db, MANAGER, user_id=EMPLOYEE_ID)

    assert user_ids == [EMPLOYEE_ID]


async def test_manager_specifying_nonexistent_user_is_forbidden(db):
    """查不到的 user_id 一律視為越權，不回空清單——否則越權查詢看起來會像
    「這個人剛好沒資料」，把 403 與 200 空結果混為一談。"""
    with pytest.raises(AppError) as exc:
        await attendance_scope.resolve_visible_user_ids(db, MANAGER, user_id=999999)

    assert exc.value.status_code == 403


async def test_manager_without_department_is_forbidden(db):
    """沒有部門可限縮時必須擋下。若讓它往下走，find_all(department_id=None)
    會被解讀成「不篩選部門」，主管反而看到全公司。"""
    orphan_manager = {"id": OTHER_MANAGER_ID, "role": "manager", "department_id": None}

    with pytest.raises(AppError) as exc:
        await attendance_scope.resolve_visible_user_ids(db, orphan_manager)

    assert exc.value.status_code == 403


async def test_employee_only_sees_self(db):
    user_ids = await attendance_scope.resolve_visible_user_ids(db, EMPLOYEE)

    assert user_ids == [EMPLOYEE_ID]


async def test_employee_cannot_widen_scope_via_parameters(db):
    """查詢對象取自 token，不取自請求參數——員工傳任何 user_id／department_id
    都只會拿到自己。"""
    user_ids = await attendance_scope.resolve_visible_user_ids(
        db, EMPLOYEE, user_id=OTHER_EMPLOYEE_ID, department_id=2
    )

    assert user_ids == [EMPLOYEE_ID]


async def test_unknown_role_falls_back_to_self_only(db):
    """deny-by-default：未來新增的身分在沒有人特別處理的情況下，只能看到自己。"""
    auditor = {"id": EMPLOYEE_ID, "role": "auditor", "department_id": 1}

    user_ids = await attendance_scope.resolve_visible_user_ids(db, auditor)

    assert user_ids == [EMPLOYEE_ID]
