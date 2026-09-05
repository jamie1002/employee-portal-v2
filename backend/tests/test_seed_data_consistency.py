"""展示種子資料本身不存在邏輯矛盾（比照前一版 test_seed_data_consistency.py，
改用 v2 `seed_business_data.py` 實際的近兩週劇本情境斷言，而非照搬前一版的
情境日期——兩版的劇本內容不完全相同）。

跟 `test_seed_business_rules.py` 的分工不同：那個檔案是全表掃描、逐筆重算
業務規則是否自洽；這裡針對特定劇本斷言具體案例，確保「已核准」一定有審核者、
「待審」不會提前反映到生效值、駁回一定有備註、回填資料真的涵蓋管理者帳號——
這些是 seed_business_data.py 手寫敘事本身該滿足的最低限度，不是重算公式。
"""
import pytest_asyncio

from app.db_scripts.seed import apply_demo_seed
from app.services import attendance_effective
from app.utils.pg_types import pg_date

ADMIN_ID = 1
EMPLOYEE_ID = 3
OTHER_EMPLOYEE_ID = 5


@pytest_asyncio.fixture(autouse=True)
async def _demo_seeded(db):
    """這個檔案專屬：疊加示範用業務資料（見 app/db_scripts/seed_business_data.py）。
    其他測試檔沿用的每測試重置 fixture 只還原靜態參考資料，業務資料表刻意
    保持乾淨（見 app/db_scripts/seed.py 模組說明）。"""
    await apply_demo_seed(db)


async def test_approved_punch_request_has_reviewer_and_effective_attendance_matches(pool, db):
    """08/18：陳小華忘記準時打卡的補打卡申請已核准，生效值必須改用申請內容，
    且 is_adjusted 要能反映「已核准且真的改動了生效值」。"""
    request = await db.fetchrow(
        "SELECT * FROM punch_requests WHERE user_id = $1 AND type = 'in' AND status = 'approved'",
        EMPLOYEE_ID,
    )
    assert request is not None
    assert request["reviewer_id"] is not None
    assert request["reviewed_at"] is not None
    assert request["created_at"] < request["reviewed_at"]

    resolved = await attendance_effective.resolve_one(pool, EMPLOYEE_ID, request["target_date"])
    assert resolved is not None
    assert resolved["effective_punch_in_time"] == request["requested_in_time"]
    assert resolved["effective_status"] == "normal"
    assert resolved["is_adjusted"] is True


async def test_pending_punch_request_does_not_affect_effective_values(pool, db):
    """08/21：忘記打下班卡的補打卡申請仍待審核，不該提前反映到生效值——
    is_adjusted 應為 False，且這天仍要被標記未打下班卡。"""
    request = await db.fetchrow(
        "SELECT * FROM punch_requests WHERE user_id = $1 AND type = 'out' AND status = 'pending'",
        OTHER_EMPLOYEE_ID,
    )
    assert request is not None
    assert request["reviewer_id"] is None
    assert request["reviewed_at"] is None

    resolved = await attendance_effective.resolve_one(pool, OTHER_EMPLOYEE_ID, request["target_date"])
    assert resolved is not None
    assert resolved["effective_punch_out_time"] is None
    assert resolved["is_adjusted"] is False
    assert resolved["is_missing_punch_out"] is True


async def test_rejected_leave_request_has_reviewer_and_review_note(db):
    """08/18：病假被駁回，仍須有審核者／審核時間／駁回備註——駁回不代表
    「不用留審核紀錄」，被駁回的人有權知道理由。"""
    request = await db.fetchrow("SELECT * FROM leave_requests WHERE leave_type = '病假' AND status = 'rejected'")
    assert request is not None
    assert request["reviewer_id"] is not None
    assert request["reviewed_at"] is not None
    assert request["review_note"]
    assert request["created_at"] < request["reviewed_at"]


async def test_all_reviewed_requests_created_before_reviewed(db):
    """所有申請單一律明確指定 created_at，且必須早於 reviewed_at——種子資料
    刻意繞過 request_review.py 直接呼叫 repository（見 seed_business_data.py
    模組說明），漏指定就會落到真實牆鐘時間，出現「送出時間晚於審核時間」的矛盾。"""
    for table in ("punch_requests", "leave_requests", "overtime_requests"):
        rows = await db.fetch(f"SELECT created_at, reviewed_at FROM {table} WHERE reviewed_at IS NOT NULL")
        assert len(rows) > 0, table
        for row in rows:
            assert row["created_at"] < row["reviewed_at"], table


async def test_overtime_requests_have_all_three_statuses(db):
    """加班申請涵蓋 pending／approved／rejected 三種狀態，審核中心與篩選才有
    完整情境可展示，不會每次重置都只看得到單一狀態。"""
    statuses = {row["status"] for row in await db.fetch("SELECT DISTINCT status FROM overtime_requests")}
    assert statuses == {"pending", "approved", "rejected"}


async def test_admin_has_backfilled_attendance(db):
    """管理者帳號也該有歷史回填的出勤紀錄可供展示，不是只有一般員工才看得到
    半年份的出勤紀錄（見 db_scripts/backfill_history.py）。"""
    count = await db.fetchval(
        "SELECT COUNT(*) FROM attendances WHERE user_id = $1 AND punch_date <= $2",
        ADMIN_ID,
        pg_date("2026-08-23"),
    )
    assert count > 0
