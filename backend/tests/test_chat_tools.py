"""AI 助理查詢工具的執行層。

這支測試直接打 `chat_tools.execute()`，不經過模型——模型只負責決定「呼叫哪支工具、
帶什麼參數」，工具拿到參數之後的行為必須自己可驗證，不能只靠對話測試。
"""

from datetime import date

from app.services import attendance as attendance_service
from app.services import chat_tools
from app.utils.pg_types import pg_date
from tests.helpers import EMPLOYEE_ID, MANAGER_ID, OTHER_EMPLOYEE_ID, taipei

EMPLOYEE = {"id": EMPLOYEE_ID, "role": "employee", "department_id": 1}
MANAGER = {"id": MANAGER_ID, "role": "manager", "department_id": 1}

WEDNESDAY = date(2026, 8, 19)
THURSDAY = date(2026, 8, 20)
FRIDAY = date(2026, 8, 21)


async def _insert(db, user_id, day, punch_in=None, punch_out=None, status="normal"):
    await db.execute(
        """
        INSERT INTO attendances (
            user_id, punch_date, punch_in_time, punch_out_time, status, created_at, updated_at
        )
        VALUES ($1, $2, $3, $4, $5, now(), now())
        ON CONFLICT (user_id, punch_date) DO UPDATE
        SET punch_in_time = EXCLUDED.punch_in_time,
            punch_out_time = EXCLUDED.punch_out_time,
            status = EXCLUDED.status
        """,
        user_id,
        pg_date(day),
        punch_in,
        punch_out,
        status,
    )


async def test_attendance_summary_counts_match_the_service(pool, db):
    """工具算出來的數字必須與直接呼叫既有 service 的結果一致。"""
    await _insert(db, EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 0), taipei(2026, 8, 19, 18, 0))
    await _insert(db, EMPLOYEE_ID, THURSDAY, taipei(2026, 8, 20, 9, 30), taipei(2026, 8, 20, 18, 0), "late")

    result = await chat_tools.execute(
        pool, EMPLOYEE, "get_my_attendance_summary",
        {"start_date": "2026-08-19", "end_date": "2026-08-21"},
    )

    expected = await attendance_service.get_my_records(
        pool, EMPLOYEE_ID, start_date=WEDNESDAY, end_date=FRIDAY, status="late", page_size=1000
    )
    assert result["ok"] is True
    assert result["遲到次數"] == expected["total"]


async def test_normal_excludes_early_leave_and_missing_punch_out(pool, db):
    """「正常」的定義有個很容易錯的細節：狀態是 normal 但當天早退或沒打下班卡的
    日子不算正常。工具若自己重寫判定就會跟出勤頁的篩選結果對不起來。"""
    # 早退（18:00 是表定下班，17:00 下班即早退），status 欄位仍是 normal。
    await _insert(db, EMPLOYEE_ID, THURSDAY, taipei(2026, 8, 20, 9, 0), taipei(2026, 8, 20, 17, 0))
    # 未打下班卡。
    await _insert(db, EMPLOYEE_ID, FRIDAY, taipei(2026, 8, 21, 9, 0))

    result = await chat_tools.execute(
        pool, EMPLOYEE, "get_my_attendance_summary",
        {"start_date": "2026-08-20", "end_date": "2026-08-21"},
    )

    from_service = await attendance_service.get_my_records(
        pool, EMPLOYEE_ID, start_date=THURSDAY, end_date=FRIDAY, status="normal", page_size=1000
    )
    assert result["正常出勤天數"] == from_service["total"]
    assert result["早退次數"] >= 1
    assert result["未打下班卡天數"] >= 1


async def test_long_range_lists_every_abnormal_date_even_early_in_the_range(pool, db):
    """**守的是 09-13 實測的 bug**：舊版明細只取「最近 10 天」，7 月的異常都在月初，
    模型拿得到次數卻拿不到日期（PITFALLS I17）。異常日期必須完整，與位置無關。"""
    await db.execute("DELETE FROM attendances WHERE user_id = $1 AND punch_date BETWEEN $2 AND $3",
                     EMPLOYEE_ID, pg_date(date(2026, 7, 1)), pg_date(date(2026, 7, 31)))
    for day in range(1, 32):
        if date(2026, 7, day).weekday() >= 5:
            continue
        # 9:30 遲到的那天正常工時結束會往後推，18:30 下班才不會同時算早退。
        punch_in = taipei(2026, 7, day, 9, 30) if day == 2 else taipei(2026, 7, day, 9, 0)
        punch_out = taipei(2026, 7, day, 18, 30) if day == 2 else taipei(2026, 7, day, 18, 0)
        status = "late" if day == 2 else "normal"
        await _insert(db, EMPLOYEE_ID, date(2026, 7, day), punch_in, punch_out, status)

    result = await chat_tools.execute(
        pool, EMPLOYEE, "get_my_attendance_summary",
        {"start_date": "2026-07-01", "end_date": "2026-07-31"},
    )

    assert result["總天數"] > 10
    assert "2026-07-02" in result["異常日期"]["遲到"]
    # 區間長時明細只列異常的日子，而且那一天一定在裡面。
    assert result["明細範圍"] == "只列有異常的日子"
    assert [row["日期"] for row in result["明細"]] == ["2026-07-02"]
    assert result["明細"][0]["異常"] == ["遲到"]


async def test_short_range_lists_every_day(pool, db):
    """只查一兩天時全列，讓「我 8/19 幾點打卡」這種不是在問異常的問題也答得出來。"""
    await _insert(db, EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 0), taipei(2026, 8, 19, 18, 0))

    result = await chat_tools.execute(
        pool, EMPLOYEE, "get_my_attendance_summary",
        {"start_date": "2026-08-19", "end_date": "2026-08-19"},
    )

    assert result["明細範圍"] == "區間內每一天"
    assert result["明細"][0]["上班時間"] == "09:00"


async def test_abnormal_dates_agree_with_the_attendance_page_filter(pool, db):
    """異常日期必須跟出勤頁的狀態篩選逐日一致——一樣走 matches_status_filter。"""
    await _insert(db, EMPLOYEE_ID, THURSDAY, taipei(2026, 8, 20, 9, 0), taipei(2026, 8, 20, 17, 0))  # 早退
    await _insert(db, EMPLOYEE_ID, FRIDAY, taipei(2026, 8, 21, 9, 0))  # 未打下班卡

    result = await chat_tools.execute(
        pool, EMPLOYEE, "get_my_attendance_summary",
        {"start_date": "2026-08-01", "end_date": "2026-08-31"},
    )

    for status, label in (("early_leave", "早退"), ("missing_punch_out", "未打下班卡"), ("late", "遲到")):
        page = await attendance_service.get_my_records(
            pool, EMPLOYEE_ID, start_date=date(2026, 8, 1), end_date=date(2026, 8, 31),
            status=status, page_size=1000,
        )
        expected = sorted(str(row["punch_date"]) for row in page["records"])
        assert result["異常日期"].get(label, []) == expected, label


async def test_team_summary_includes_each_members_abnormal_dates(pool, db):
    await _insert(db, EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 30), taipei(2026, 8, 19, 18, 0), "late")

    result = await chat_tools.execute(
        pool, MANAGER, "get_team_attendance_summary",
        {"start_date": "2026-08-19", "end_date": "2026-08-19", "employee_name": "陳小華"},
    )

    person = result["各人統計"][0]
    assert person["姓名"] == "陳小華"
    assert person["異常日期"]["遲到"] == ["2026-08-19"]


# ── 通訊錄 ─────────────────────────────────────────────────────────────────

async def test_directory_is_company_wide_for_every_role(pool):
    """範圍比照前端「員工資訊」頁：一般員工也看得到全公司（SPEC 權限矩陣）。"""
    result = await chat_tools.execute(pool, EMPLOYEE, "search_directory", {}, question="業務部有誰？")

    assert result["ok"] is True
    names = {row["姓名"] for row in result["名單"]}
    assert {"陳小華", "張大同"} <= names


async def test_directory_fields_match_the_employee_page(pool):
    """欄位與頁面上顯示的一致，不多給（沒有密碼雜湊、沒有權限清單）。"""
    result = await chat_tools.execute(pool, EMPLOYEE, "search_directory", {"employee_name": "王小明"})

    row = result["名單"][0]
    assert set(row) == {"姓名", "員工編號", "部門", "角色", "分機", "email", "到職日"}
    assert row["角色"] == "部門主管"


async def test_directory_only_my_department(pool):
    result = await chat_tools.execute(
        pool, EMPLOYEE, "search_directory", {"only_my_department": True}
    )

    assert result["提問者所屬部門"] == "研發部"
    assert {row["部門"] for row in result["名單"]} == {"研發部"}


async def test_directory_is_not_blocked_by_colleague_name_guard(pool):
    """查同事的分機本來就是點名同事，不能被 I16 那道擋法攔下。"""
    result = await chat_tools.execute(
        pool, EMPLOYEE, "search_directory", {"employee_name": "張大同"}, question="張大同的分機幾號？"
    )

    assert result["ok"] is True
    assert result["名單"][0]["姓名"] == "張大同"


async def test_today_status_uses_virtual_clock(pool, db):
    result = await chat_tools.execute(pool, EMPLOYEE, "get_today_status", {})

    today = await attendance_service.get_today(pool, EMPLOYEE_ID)
    assert result["ok"] is True
    assert result["日期"] == str(today["punch_date"])


async def test_leave_quota_converts_hours_to_days(pool, db):
    """使用者問的是「還剩幾天」，資料存的是時數。換算必須在工具層做，
    因為每日工時是設定值，模型不知道也不該猜。"""
    result = await chat_tools.execute(pool, EMPLOYEE, "get_my_leave_quota", {})

    assert result["ok"] is True
    special = next(row for row in result["假別"] if row["名稱"] == "特別休假")
    assert special["剩餘天數"] == round(
        special["剩餘時數"] / result["每日工時"] * 100
    ) / 100


async def test_my_requests_returns_own_requests_only(pool, db):
    result = await chat_tools.execute(pool, EMPLOYEE, "get_my_requests", {"kind": "leave"})

    assert result["ok"] is True
    assert all(item["類型"] == "leave" for item in result["申請單"])


async def test_unknown_tool_is_refused_not_raised(pool, db):
    result = await chat_tools.execute(pool, EMPLOYEE, "drop_all_tables", {})

    assert result["ok"] is False
    assert "權限" in result["reason"] or "無法" in result["reason"]


async def test_tool_outside_role_allowlist_is_refused(pool, db):
    """第二層防線：模型可能喊出一個不在它清單上的工具名稱（prompt injection 最直接的
    手法）。工具層必須自己擋，不能假設「模型看不到就不會呼叫」。"""
    result = await chat_tools.execute(pool, EMPLOYEE, "get_team_attendance_summary", {})

    assert result["ok"] is False


async def test_bad_date_format_returns_structured_error(pool, db):
    result = await chat_tools.execute(
        pool, EMPLOYEE, "get_my_attendance_summary",
        {"start_date": "八月一號", "end_date": "2026-08-31"},
    )

    assert result["ok"] is False
    assert "YYYY-MM-DD" in result["reason"]


async def test_missing_required_date_returns_structured_error(pool, db):
    """缺參數時回結構化錯誤讓模型重問，不用預設值瞎猜——瞎猜的區間會產出一個
    看起來合理但完全錯誤的答案。"""
    result = await chat_tools.execute(pool, EMPLOYEE, "get_my_attendance_summary", {"end_date": "2026-08-31"})

    assert result["ok"] is False


async def test_reversed_date_range_returns_structured_error(pool, db):
    result = await chat_tools.execute(
        pool, EMPLOYEE, "get_my_attendance_summary",
        {"start_date": "2026-08-31", "end_date": "2026-08-01"},
    )

    assert result["ok"] is False


async def test_declarations_contain_no_id_parameters(pool, db):
    """工具參數不得出現 user_id／department_id：模型不知道 id 是什麼，只會猜一個整數，
    猜中別人又剛好同部門時權限檢查照樣放行（design.md Decision 3）。"""
    for role_user in (EMPLOYEE, MANAGER):
        for tool in chat_tools.build_declarations(role_user):
            for declaration in tool.function_declarations:
                names = set(declaration.parameters.properties.keys())
                assert "user_id" not in names
                assert "department_id" not in names


async def test_employee_cannot_reach_other_users_data(pool, db):
    """工具永遠只回提問者自己的資料——沒有任何參數可以指定別人。"""
    await _insert(db, OTHER_EMPLOYEE_ID, WEDNESDAY, taipei(2026, 8, 19, 9, 30), status="late")

    result = await chat_tools.execute(
        pool, EMPLOYEE, "get_my_attendance_summary",
        {"start_date": "2026-08-19", "end_date": "2026-08-19"},
    )

    mine = await attendance_service.get_my_records(
        pool, EMPLOYEE_ID, start_date=WEDNESDAY, end_date=WEDNESDAY, page_size=1000
    )
    assert result["總天數"] == mine["total"]


async def test_tool_layer_writes_no_sql(pool):
    """工具層不得自行撰寫查詢。業務資料一律經既有 service 取得——出勤的「生效值」
    不是 attendances 表讀得到的，繞過去的答案會跟畫面對不上而且不會報錯。

    （單純的主鍵查表走 repository 是 service 層的正常作法，不在此限。）
    """
    import inspect

    source = inspect.getsource(chat_tools)

    for forbidden in ("pool.fetch", "pool.execute", "pool.fetchrow", "pool.fetchval", "SELECT "):
        assert forbidden not in source, f"chat_tools 不應出現 {forbidden}"
