"""AI 助理的查詢工具：宣告、依角色組裝、派工、聚合。

**三條不可違反的界線**（見 `openspec/changes/add-personal-data-chat/design.md`）：

1. **業務資料一律經由既有 service 取得，這個模組不自己寫 SQL、不自行重算任何業務規則。**
   出勤的「生效值」不是 `attendances` 表讀得到的（`SPEC.md` §4.2：補打卡與請假核准
   不覆寫該表），繞過既有 service 的答案會跟畫面對不上，而且不會報錯。
   （單純的主鍵查表可以走 repository——那是 service 層的正常作法，不是繞過業務邏輯。）
2. **工具參數不含 user_id／department_id。** 模型不知道 id 是什麼，只會猜一個整數；
   猜中別人又剛好同部門時權限檢查照樣放行，於是助理拿著甲的資料回答關於乙的問題。
   指定對象一律用姓名，由後端查表解析。
3. **工具清單依角色過濾只是 UX，執行層的權限檢查才是安全邊界。** 模型有可能喊出一個
   不在它清單上的工具名稱（prompt injection 最直接的攻擊手法），`execute()` 必須自己
   擋，不能假設「模型看不到就不會呼叫」。這與「前端 RoleGate 不是安全邊界」是同一句話。
"""

from __future__ import annotations

from datetime import date, datetime

import asyncpg
import google.generativeai as genai

from app.config.settings import app_settings
from app.repositories import user_repository
from app.services import attendance as attendance_service
from app.services import department as department_service
from app.services import leave_quota as leave_quota_service
from app.services import leave_request, overtime_request, punch_request
from app.services import settings as settings_service
from app.services.work_hours import WorkSettings, daily_work_hours
from app.utils.errors import AppError
from app.utils.timezone import get_business_date
from app.utils.virtual_clock import get_virtual_now

_T = genai.protos.Type

# 回給模型的明細筆數上限。聚合過的統計才是答案，明細只是讓回答能舉例；
# 全部回去會讓第二輪的輸入暴增，延遲與配額都吃不消（design.md Decision 4）。
_MAX_DETAIL_ROWS = 10

_REQUEST_SERVICES = {
    "leave": leave_request,
    "overtime": overtime_request,
    "punch": punch_request,
}


def _string(description: str) -> genai.protos.Schema:
    return genai.protos.Schema(type=_T.STRING, description=description)


def _declaration(name: str, description: str, properties: dict | None = None,
                 required: list[str] | None = None) -> genai.protos.FunctionDeclaration:
    return genai.protos.FunctionDeclaration(
        name=name,
        description=description,
        parameters=genai.protos.Schema(
            type=_T.OBJECT,
            properties=properties or {},
            required=required or [],
        ),
    )


def _personal_declarations() -> list[genai.protos.FunctionDeclaration]:
    return [
        _declaration(
            "get_today_status",
            "查詢提問者「今天」的打卡狀態：是否已打上班卡與下班卡、打卡時間、"
            "目前工時、今天是不是工作日。不需要任何參數。",
        ),
        _declaration(
            "get_my_attendance_summary",
            "查詢提問者「自己」某一段期間的出勤統計，包含出勤天數、遲到次數、"
            "早退次數、缺勤天數、請假天數，並附上幾筆代表性的明細。"
            "只能查本人，無法查詢其他同事。",
            {
                "start_date": _string("起始日期，格式 YYYY-MM-DD"),
                "end_date": _string("結束日期，格式 YYYY-MM-DD"),
                "status": _string(
                    "只看某一種狀態時填入，可填 normal（正常）、late（遲到）、"
                    "absent（缺勤）、early_leave（早退）、on_leave（請假）、"
                    "missing_punch_out（未打下班卡）。省略表示全部狀態。"
                ),
            },
            ["start_date", "end_date"],
        ),
        _declaration(
            "get_my_leave_quota",
            "查詢提問者「自己」目前各假別的剩餘額度與已使用時數，"
            "例如特別休假還剩幾天。不需要任何參數。",
        ),
        _declaration(
            "get_my_requests",
            "查詢「提問者自己送出」的申請單及其審核進度，也就是提問者是申請人的那些單子。",
            {
                "kind": _string("申請類型，可填 leave（請假）、overtime（加班）、"
                                "punch（補打卡）。省略表示三種都查。"),
                "status": _string("審核狀態，可填 pending（待審核）、approved（已核准）、"
                                  "rejected（已駁回）。省略表示全部。"),
            },
        ),
    ]


def _team_declarations(role: str) -> list[genai.protos.FunctionDeclaration]:
    """主管與管理員才看得到的兩支工具。

    `department_name` **只出現在 admin 的宣告裡**：主管的可見範圍恆等於自己的部門，
    給他一個部門參數只會誘導模型去填一個注定被拒絕的值，白白多一輪往返。
    """
    team_properties = {
        "start_date": _string("起始日期，格式 YYYY-MM-DD"),
        "end_date": _string("結束日期，格式 YYYY-MM-DD"),
        "employee_name": _string(
            "要查詢的同事姓名，例如「陳小華」。**用姓名，不要用任何編號。**"
            "省略表示查詢範圍內的所有人。"
        ),
        "status": _string(
            "只看某一種狀態時填入，可填 normal、late、absent、early_leave、"
            "on_leave、missing_punch_out。省略表示全部狀態。"
        ),
    }
    scope_hint = "所屬部門成員"
    if role == "admin":
        team_properties["department_name"] = _string(
            "部門名稱，例如「研發部」。**用部門名稱，不要用編號。**省略表示全公司。"
        )
        scope_hint = "全公司或指定部門的成員"

    return [
        _declaration(
            "get_pending_reviews",
            "查詢「等著提問者去審核別人」的申請單，也就是提問者是審核者的那些單子。"
            "這與提問者自己送出的申請單（get_my_requests）是不同的東西。",
            {"kind": _string("申請類型，可填 leave、overtime、punch。省略表示三種都查。")},
        ),
        _declaration(
            "get_team_attendance_summary",
            f"查詢{scope_hint}的出勤統計，會依每個人分別列出出勤天數、遲到次數、"
            "早退次數與缺勤天數，適合回答「誰遲到最多」這類問題。",
            team_properties,
            ["start_date", "end_date"],
        ),
    ]


def build_declarations(current_user: dict) -> list[genai.protos.Tool]:
    """依角色組裝工具宣告。

    這層過濾是 UX——讓模型不必去呼叫一支注定失敗的工具、白白多一輪往返。
    真正的安全邊界在 `execute()`。
    """
    declarations = _personal_declarations()
    if current_user["role"] in ("manager", "admin"):
        declarations += _team_declarations(current_user["role"])
    return [genai.protos.Tool(function_declarations=declarations)]


def _allowed_names(current_user: dict) -> set[str]:
    return {
        declaration.name
        for tool in build_declarations(current_user)
        for declaration in tool.function_declarations
    }


def _refusal(message: str) -> dict:
    """回給模型的結構化拒絕。

    刻意不拋例外中止整個請求：使用者只是問了一個他沒權限或系統查不到的問題，
    正確的產品行為是讓助理用人話說明，而不是丟一個錯誤畫面（design.md Decision 8）。
    """
    return {"ok": False, "reason": message}


def _parse_date(value: object, field: str) -> date:
    if not isinstance(value, str) or not value.strip():
        raise _ToolArgumentError(f"缺少{field}。")
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError as exc:
        raise _ToolArgumentError(f"{field}的格式不正確，需要 YYYY-MM-DD。") from exc


class _ToolArgumentError(ValueError):
    """模型給的參數有問題。轉成結構化訊息讓模型重問使用者，不要用預設值瞎猜——
    瞎猜出來的區間會產出一個看起來很合理但完全錯誤的答案。"""


def _summarize_attendance(records: list[dict]) -> dict:
    """把出勤列聚合成統計。

    狀態判定一律走 `attendance.matches_status_filter()`，不自己比對 `effective_status`。
    「正常」這個狀態帶著一個很容易錯的細節：狀態是 normal 但當天早退或未打下班卡的
    日子**不算正常**。自己重寫一遍一定會跟出勤頁的篩選結果對不起來。
    """
    counts = {
        key: sum(1 for row in records if attendance_service.matches_status_filter(row, key))
        for key in ("normal", "late", "absent", "early_leave", "on_leave", "missing_punch_out")
    }
    details = [
        {
            "日期": row["punch_date"].isoformat() if hasattr(row["punch_date"], "isoformat") else str(row["punch_date"]),
            "上班時間": _format_time(row.get("effective_punch_in_time")),
            "下班時間": _format_time(row.get("effective_punch_out_time")),
            "狀態": row.get("effective_status"),
            "工時": row.get("effective_work_hours"),
        }
        for row in records[:_MAX_DETAIL_ROWS]
    ]
    return {
        "ok": True,
        "總天數": len(records),
        "正常出勤天數": counts["normal"],
        "遲到次數": counts["late"],
        "早退次數": counts["early_leave"],
        "缺勤天數": counts["absent"],
        "請假天數": counts["on_leave"],
        "未打下班卡天數": counts["missing_punch_out"],
        "明細": details,
        "明細是否截斷": len(records) > _MAX_DETAIL_ROWS,
    }


def _format_time(value: object) -> str | None:
    if value is None:
        return None
    if hasattr(value, "strftime"):
        return value.strftime("%H:%M")
    return str(value)


async def execute(pool: asyncpg.Pool, current_user: dict, name: str, args: dict) -> dict:
    """執行一支工具並回傳要餵回模型的結構化結果。

    **這裡是安全邊界**：不在該角色允許清單內的名稱一律拒絕，不管模型為什麼會喊出它。
    """
    if name not in _allowed_names(current_user):
        return _refusal("這項資料不在你的權限範圍內，我無法查詢。")

    try:
        return await _dispatch(pool, current_user, name, args)
    except _ToolArgumentError as exc:
        return _refusal(str(exc))
    except AppError as exc:
        # 既有 service 的範圍限縮擋下來的（例如跨部門）。轉成拒絕訊息讓助理用人話說明，
        # 不讓它變成整個請求的 HTTP 錯誤。
        if exc.status_code == 403:
            return _refusal("這項資料不在你的權限範圍內，我無法查詢。")
        raise


async def _dispatch(pool: asyncpg.Pool, current_user: dict, name: str, args: dict) -> dict:
    user_id = current_user["id"]

    if name == "get_today_status":
        today = await attendance_service.get_today(pool, user_id)
        return {
            "ok": True,
            "日期": str(today["punch_date"]),
            "是否為工作日": today["is_workday"],
            "已打上班卡": today["has_punched_in"],
            "已打下班卡": today["has_punched_out"],
            "上班時間": _format_time(today["punch_in_time"]),
            "下班時間": _format_time(today["punch_out_time"]),
            "狀態": today["status"],
            "工時": today["work_hours"],
        }

    if name == "get_my_attendance_summary":
        start_date = _parse_date(args.get("start_date"), "起始日期")
        end_date = _parse_date(args.get("end_date"), "結束日期")
        if start_date > end_date:
            raise _ToolArgumentError("起始日期不能晚於結束日期。")
        status = _clean_optional(args.get("status"))
        # page_size 給足，確保聚合看到的是整個區間而不是第一頁。
        result = await attendance_service.get_my_records(
            pool, user_id, start_date=start_date, end_date=end_date, status=status,
            page=1, page_size=1000,
        )
        summary = _summarize_attendance(result["records"])
        summary["查詢區間"] = f"{start_date.isoformat()} 至 {end_date.isoformat()}"
        return summary

    if name == "get_my_leave_quota":
        today = get_business_date(await get_virtual_now(), tz=app_settings.APP_TIMEZONE)
        # `current_user` 只帶 id／role／department_id／permissions，沒有 `hire_date`，
        # 而特休額度要靠到職日算年資。這裡與 `routers/leave_quota.py` 一樣重查完整
        # 使用者資料——直接把 current_user 傳進去會 KeyError。
        user = await user_repository.find_public_by_id(pool, current_user["id"])
        quotas = await leave_quota_service.get_my_leave_quota(pool, user, today)
        # 假別額度存的是「時數」，但使用者問的幾乎都是「還剩幾天」。天數換算在這裡做
        # 而不是丟給模型除：每日工時是設定值（可能不是 8 小時），模型不知道也不該猜。
        settings = WorkSettings.from_row(await settings_service.get_settings(pool))
        hours_per_day = daily_work_hours(settings)
        return {
            "ok": True,
            "每日工時": hours_per_day,
            "假別": [
                {
                    "名稱": row["leave_type"],
                    "額度時數": row["quota_hours"],
                    "已使用時數": row["used_hours"],
                    "剩餘時數": row["remaining_hours"],
                    "剩餘天數": _to_days(row["remaining_hours"], hours_per_day),
                    "計算週期": f"{row['period_start']} 至 {row['period_end']}",
                }
                for row in quotas
            ],
        }

    if name == "get_my_requests":
        kind = _clean_optional(args.get("kind"))
        status = _clean_optional(args.get("status"))
        kinds = [kind] if kind in _REQUEST_SERVICES else list(_REQUEST_SERVICES)
        items = []
        for one in kinds:
            rows = await _REQUEST_SERVICES[one].get_my_requests(pool, user_id, status)
            items.extend({**_project_request(row), "類型": one} for row in rows)
        return {"ok": True, "申請單": items[:_MAX_DETAIL_ROWS * 2], "總筆數": len(items)}

    if name == "get_pending_reviews":
        kind = _clean_optional(args.get("kind"))
        kinds = [kind] if kind in _REQUEST_SERVICES else list(_REQUEST_SERVICES)
        items = []
        for one in kinds:
            # get_pending() 自己依 reviewer 的角色限縮（admin 全公司、manager 同部門
            # 且排除自己送出的單），這裡不再自行判斷範圍。
            rows = await _REQUEST_SERVICES[one].get_pending(pool, current_user)
            items.extend(
                {**_project_request(row), "類型": one, "申請人": row.get("applicant_name"),
                 "部門": row.get("department_name")}
                for row in rows
            )
        return {"ok": True, "待審申請單": items[: _MAX_DETAIL_ROWS * 2], "總筆數": len(items)}

    if name == "get_team_attendance_summary":
        start_date = _parse_date(args.get("start_date"), "起始日期")
        end_date = _parse_date(args.get("end_date"), "結束日期")
        if start_date > end_date:
            raise _ToolArgumentError("起始日期不能晚於結束日期。")

        target_user_id = await _resolve_employee_name(pool, _clean_optional(args.get("employee_name")))
        department_id = None
        if current_user["role"] == "admin":
            department_id = await _resolve_department_name(
                pool, _clean_optional(args.get("department_name"))
            )

        # 範圍限縮完全交給 attendance.get_all()（內部走 attendance_scope）：主管指定
        # 他部門的同事時會在這裡拋 403，被 execute() 轉成拒絕訊息。姓名只是輸入格式，
        # 不是繞過權限的管道。
        records = await attendance_service.get_all(
            pool, current_user, user_id=target_user_id, department_id=department_id,
            start_date=start_date, end_date=end_date, status=_clean_optional(args.get("status")),
        )
        summary = _summarize_team_attendance(records)
        summary["查詢區間"] = f"{start_date.isoformat()} 至 {end_date.isoformat()}"
        return summary

    return _refusal("我目前沒有辦法查詢這項資料。")


async def _resolve_employee_name(pool: asyncpg.Pool, employee_name: str | None) -> int | None:
    """把姓名解析成 user_id。

    查無此人與同名多筆**各自回不同的訊息，絕不任選一筆**——任選一筆會讓助理拿著
    甲的資料回答關於乙的問題，數字全錯而且不會有任何錯誤訊息。
    """
    if employee_name is None:
        return None

    members = await user_repository.find_all(pool)
    matched = [row for row in members if row["name"] == employee_name]
    if not matched:
        raise _ToolArgumentError(f"找不到名字是「{employee_name}」的同事。")
    if len(matched) > 1:
        raise _ToolArgumentError(
            f"有多位同事都叫「{employee_name}」，請改用系統的出勤查詢頁指定是哪一位。"
        )
    return matched[0]["id"]


async def _resolve_department_name(pool: asyncpg.Pool, department_name: str | None) -> int | None:
    if department_name is None:
        return None

    departments = await department_service.list_departments(pool)
    matched = [row for row in departments if row["name"] == department_name]
    if not matched:
        raise _ToolArgumentError(f"找不到名稱是「{department_name}」的部門。")
    return matched[0]["id"]


def _summarize_team_attendance(records: list[dict]) -> dict:
    """依「人」聚合，讓「誰遲到最多」這類問題有得答。

    不回原始列：一個部門一個月就有數百列，全部餵回模型會讓第二輪的輸入暴增，
    而且模型自己數一定會跟畫面上的統計對不起來（見 design.md Decision 4）。
    """
    by_person: dict[str, dict] = {}
    for row in records:
        person = row.get("user_name") or "（未知）"
        entry = by_person.setdefault(
            person,
            {"姓名": person, "部門": row.get("department_name"), "出勤天數": 0,
             "遲到次數": 0, "早退次數": 0, "缺勤天數": 0, "請假天數": 0},
        )
        entry["出勤天數"] += 1
        for label, key in (("遲到次數", "late"), ("早退次數", "early_leave"),
                           ("缺勤天數", "absent"), ("請假天數", "on_leave")):
            if attendance_service.matches_status_filter(row, key):
                entry[label] += 1

    people = sorted(by_person.values(), key=lambda e: e["遲到次數"], reverse=True)
    return {"ok": True, "人數": len(people), "總筆數": len(records), "各人統計": people}


def _clean_optional(value: object) -> str | None:
    if isinstance(value, str) and value.strip():
        return value.strip()
    return None


def _to_days(hours: object, hours_per_day: float) -> float | None:
    """時數換算成天數。額度為 None 代表該假別不限額（例如無上限的假別），不做換算。"""
    if hours is None or not hours_per_day:
        return None
    return round(float(hours) / hours_per_day * 100) / 100


def _project_request(row: dict) -> dict:
    return {
        "狀態": row.get("status"),
        "申請日期": str(row["created_at"].date()) if row.get("created_at") else None,
        "假別或事由": row.get("leave_type") or row.get("reason"),
        "時數": row.get("hours"),
        "審核者": row.get("reviewer_name"),
        "審核備註": row.get("review_note"),
    }
