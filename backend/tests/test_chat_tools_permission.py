"""團隊查詢工具的權限邊界（批 B 第二階段）。

這支測試的重點不是「功能會不會動」，而是**越權的每一條路徑都被擋住**：
偽造的工具呼叫、跨部門的姓名指定、員工試圖使用主管的工具。這些都不經過模型，
直接打 `chat_tools.execute()`——限縮若只存在於模型看不看得到工具，就不是安全邊界。
"""

from datetime import date

import pytest

from app.services import chat_tools
from app.utils.pg_types import pg_date
from tests.helpers import (
    ADMIN_ID,
    EMPLOYEE_ID,
    MANAGER_ID,
    OTHER_EMPLOYEE_ID,
    OTHER_MANAGER_ID,
    taipei,
)

EMPLOYEE = {"id": EMPLOYEE_ID, "role": "employee", "department_id": 1}
MANAGER = {"id": MANAGER_ID, "role": "manager", "department_id": 1}
ADMIN = {"id": ADMIN_ID, "role": "admin", "department_id": None}

WEDNESDAY = date(2026, 8, 19)
RANGE = {"start_date": "2026-08-19", "end_date": "2026-08-19"}


async def _insert(db, user_id, day, punch_in=None, status="normal"):
    await db.execute(
        """
        INSERT INTO attendances (user_id, punch_date, punch_in_time, status, created_at, updated_at)
        VALUES ($1, $2, $3, $4, now(), now())
        ON CONFLICT (user_id, punch_date) DO UPDATE
        SET punch_in_time = EXCLUDED.punch_in_time, status = EXCLUDED.status
        """,
        user_id, pg_date(day), punch_in, status,
    )


def _tool_names(current_user) -> set[str]:
    return {
        declaration.name
        for tool in chat_tools.build_declarations(current_user)
        for declaration in tool.function_declarations
    }


# ── 工具清單依角色組裝（第一層，UX） ────────────────────────────────────────

async def test_employee_declarations_exclude_team_tools(pool):
    names = _tool_names(EMPLOYEE)

    assert "get_team_attendance_summary" not in names
    assert "get_pending_reviews" not in names
    assert "get_my_attendance_summary" in names


async def test_manager_and_admin_get_team_tools(pool):
    for role_user in (MANAGER, ADMIN):
        names = _tool_names(role_user)
        assert "get_team_attendance_summary" in names
        assert "get_pending_reviews" in names


async def test_only_admin_declaration_has_department_parameter(pool):
    """主管的可見範圍恆等於自己的部門，給他部門參數只會誘導模型填一個注定被拒絕的值。"""

    def params_of(current_user):
        for tool in chat_tools.build_declarations(current_user):
            for declaration in tool.function_declarations:
                if declaration.name == "get_team_attendance_summary":
                    return set(declaration.parameters.properties.keys())
        return set()

    assert "department_name" not in params_of(MANAGER)
    assert "department_name" in params_of(ADMIN)


async def test_team_declarations_use_names_not_ids(pool):
    for role_user in (MANAGER, ADMIN):
        for tool in chat_tools.build_declarations(role_user):
            for declaration in tool.function_declarations:
                names = set(declaration.parameters.properties.keys())
                assert "user_id" not in names
                assert "department_id" not in names


# ── 執行層自己擋（第二層，安全邊界） ────────────────────────────────────────

async def test_employee_forging_team_tool_is_refused(pool):
    """prompt injection 最直接的手法：誘導模型喊出一個不在它清單上的工具名稱。
    第一層（清單過濾）完全沒有攔截能力，擋下來的必須是這一層。"""
    result = await chat_tools.execute(pool, EMPLOYEE, "get_team_attendance_summary", RANGE)

    assert result["ok"] is False
    assert "各人統計" not in result


async def test_employee_forging_pending_reviews_is_refused(pool):
    result = await chat_tools.execute(pool, EMPLOYEE, "get_pending_reviews", {})

    assert result["ok"] is False


# ── 主管：限所屬部門 ────────────────────────────────────────────────────────

async def test_manager_team_summary_covers_own_department_only(pool, db):
    await _insert(db, EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 30), "late")
    await _insert(db, OTHER_EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 30), "late")

    result = await chat_tools.execute(pool, MANAGER, "get_team_attendance_summary", RANGE)

    assert result["ok"] is True
    names = {row["姓名"] for row in result["各人統計"]}
    assert "張大同" not in names


async def test_manager_naming_other_department_member_is_refused(pool, db):
    """姓名解析出 id 之後仍然要走 attendance_scope——姓名只是輸入格式，
    不是繞過權限的管道。"""
    await _insert(db, OTHER_EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 30), "late")

    result = await chat_tools.execute(
        pool, MANAGER, "get_team_attendance_summary", {**RANGE, "employee_name": "張大同"}
    )

    assert result["ok"] is False
    assert "各人統計" not in result


async def test_manager_naming_own_department_member_works(pool, db):
    await _insert(db, EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 30), "late")

    result = await chat_tools.execute(
        pool, MANAGER, "get_team_attendance_summary", {**RANGE, "employee_name": "陳小華"}
    )

    assert result["ok"] is True
    assert {row["姓名"] for row in result["各人統計"]} == {"陳小華"}


async def test_manager_department_parameter_is_ignored_not_honoured(pool, db):
    """主管的宣告裡沒有 department_name，但模型仍可能硬塞一個。
    這時必須沿用他自己的部門，不能照著查別人的部門。"""
    await _insert(db, OTHER_EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 0))

    result = await chat_tools.execute(
        pool, MANAGER, "get_team_attendance_summary", {**RANGE, "department_name": "業務部"}
    )

    assert result["ok"] is True
    assert "張大同" not in {row["姓名"] for row in result["各人統計"]}


async def test_manager_without_department_is_refused(pool, db):
    await db.execute("UPDATE users SET department_id = NULL WHERE id = $1", MANAGER_ID)
    orphan = {"id": MANAGER_ID, "role": "manager", "department_id": None}

    result = await chat_tools.execute(pool, orphan, "get_team_attendance_summary", RANGE)

    assert result["ok"] is False


# ── 管理員：全公司與指定部門 ────────────────────────────────────────────────

async def test_admin_can_query_whole_company(pool, db):
    await _insert(db, EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 0))
    await _insert(db, OTHER_EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 0))

    result = await chat_tools.execute(pool, ADMIN, "get_team_attendance_summary", RANGE)

    names = {row["姓名"] for row in result["各人統計"]}
    assert {"陳小華", "張大同"} <= names


async def test_admin_can_filter_by_department_name(pool, db):
    await _insert(db, EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 0))
    await _insert(db, OTHER_EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 0))

    result = await chat_tools.execute(
        pool, ADMIN, "get_team_attendance_summary", {**RANGE, "department_name": "業務部"}
    )

    names = {row["姓名"] for row in result["各人統計"]}
    assert "張大同" in names
    assert "陳小華" not in names


# ── 姓名與部門解析的失敗情境 ────────────────────────────────────────────────

async def test_unknown_employee_name_is_reported_not_guessed(pool):
    result = await chat_tools.execute(
        pool, MANAGER, "get_team_attendance_summary", {**RANGE, "employee_name": "王大鎚"}
    )

    assert result["ok"] is False
    assert "王大鎚" in result["reason"]


async def test_duplicate_employee_names_are_never_auto_picked(pool, db):
    """同名時任選一筆會讓助理拿著甲的資料回答關於乙的問題，數字全錯又沒有錯誤訊息。"""
    await db.execute(
        """
        INSERT INTO users (name, email, password_hash, role, department_id, is_first_login,
                           hire_date, employee_no)
        VALUES ('陳小華', 'dup@demo.com', 'x', 'employee', 1, false, '2025-01-01', 'EMPDUP1')
        """
    )

    result = await chat_tools.execute(
        pool, MANAGER, "get_team_attendance_summary", {**RANGE, "employee_name": "陳小華"}
    )

    assert result["ok"] is False
    assert "多位" in result["reason"]


async def test_unknown_department_name_is_reported(pool):
    result = await chat_tools.execute(
        pool, ADMIN, "get_team_attendance_summary", {**RANGE, "department_name": "火星分公司"}
    )

    assert result["ok"] is False
    assert "火星分公司" in result["reason"]


# ── 待審清單 ────────────────────────────────────────────────────────────────

async def test_manager_pending_reviews_are_scoped_by_service(pool):
    result = await chat_tools.execute(pool, MANAGER, "get_pending_reviews", {})

    assert result["ok"] is True
    departments = {item["部門"] for item in result["待審申請單"] if item.get("部門")}
    assert departments <= {"研發部"}


async def test_pending_reviews_can_filter_by_kind(pool):
    result = await chat_tools.execute(pool, MANAGER, "get_pending_reviews", {"kind": "leave"})

    assert all(item["類型"] == "leave" for item in result["待審申請單"])


# ── 點名同事卻呼叫「只查本人」的工具 ─────────────────────────────────────────

async def test_self_only_tool_is_not_run_when_question_names_colleague(pool):
    """09-13 實測：員工問「張大同這週有沒有請假？」，模型呼叫 get_my_requests 拿到自己的
    申請單，再講成「張大同這週沒有請假」。擋在這裡，模型就拿不到那份會被張冠李戴的結果。"""
    for name in ("get_my_requests", "get_my_attendance_summary", "get_my_leave_quota", "get_today_status"):
        result = await chat_tools.execute(
            pool, EMPLOYEE, name, RANGE, question="張大同這週有沒有請假？"
        )

        assert result["ok"] is False, name
        assert "張大同" in result["reason"]
        assert "沒有權限" in result["reason"]


async def test_self_only_tool_still_runs_when_question_names_only_self(pool):
    """陳小華（EMPLOYEE）提到自己的名字不是在問別人。"""
    result = await chat_tools.execute(
        pool, EMPLOYEE, "get_my_requests", {}, question="我陳小華這週有請假嗎？"
    )

    assert result["ok"] is True


async def test_self_only_tool_runs_for_plain_personal_question(pool):
    result = await chat_tools.execute(pool, EMPLOYEE, "get_my_requests", {}, question="我這週有請假嗎？")

    assert result["ok"] is True


async def test_manager_gets_non_permission_wording_for_misrouted_self_tool(pool):
    """主管其實查得到部門同事，只是模型選錯了工具——不能對他說「沒有權限」，
    那正是 PITFALLS I14 修掉的錯誤訊息。"""
    result = await chat_tools.execute(
        pool, MANAGER, "get_my_attendance_summary", RANGE, question="陳小華這週遲到幾次？"
    )

    assert result["ok"] is False
    assert "沒有權限" not in result["reason"]


async def test_pending_reviews_is_not_blocked_by_colleague_name(pool):
    """待審清單回的本來就是別人的單子，題目點名同事是正常用法。"""
    result = await chat_tools.execute(
        pool, MANAGER, "get_pending_reviews", {}, question="陳小華的請假單我審了沒？"
    )

    assert result["ok"] is True
