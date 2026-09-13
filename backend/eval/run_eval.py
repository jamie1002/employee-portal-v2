"""黃金題庫評估腳本。從 `employee-portal-chatbot`（第一階段原型）的 `eval/run_eval.py`
搬移，改動點：拿掉載入 v2 業務函式的 `sys.path` hack（現在是同一個專案內部，直接
import）、檢索與生成改呼叫新的 service（`policy_retrieval` / `chat_prompt` /
`app.utils.gemini`）、節流已移進 `gemini.py` 的行程級節流所以拿掉
`InMemoryRateLimiter`（429 重試邏輯保留，只是判斷條件改看例外訊息字串，因為
`gemini.py` 把所有上游例外統一包成 `GeminiUnavailable`，型別名稱不再是
`ResourceExhausted`）。`--skip-generation`、`--limit`、`--save-answers` 全部保留，
新增 `--category` 供批 B 只跑個人資料題組快速迭代。

**題目可用 `as_role` 指定提問身分**（employee／manager／admin，預設 employee）。
權限相關的行為必須用多種身分各驗一次——只用一種身分跑的 eval 對「某個角色下行為不對」
是完全盲的，這在批 B 已經實際發生過一次（見 `docs/PITFALLS.md` I14）。

量測的指標：

| 指標 | 來源 | 門檻 |
| :--- | :--- | :--- |
| hit@1 / hit@3 | 檢索層 | hit@3 ≥ 90% |
| 語料寫死的數字與 v2 業務函式一致 | ground truth | 100% |
| 章節覆蓋率 | 題庫 | 100%（只在跑完整題庫時檢查） |
| 回答附引用來源比率 | 生成 | 100% |
| 誘導題拒答率 | 生成 | 100% |
| 權限不足時正確說明 | 生成 | 100% |
| 該答有答（未過度拒答，含誤套權限拒絕句） | 生成 | 100% |
| 數字型答案與 v2 函式輸出一致 | 生成 | 100% |
| 推算型答案附上但書 | 生成 | ≥ 85%（唯一非 100% 的門檻，理由見 DISCLAIMER_THRESHOLD） |
| 越權題未洩漏他人資料 | 生成 | 100% |
| 工具使用正確（該查有查、閒聊不查） | 生成 | 100% |
| 異常日期完整 | 生成 | 100% |
| 通訊錄答案正確 | 生成 | 100% |

生成端會真的呼叫 Gemini（每題一到兩次，呼叫工具的題目兩次）。只想量檢索層、不想燒
API 額度時加 `--skip-generation`。

**引用率的分母刻意排除拒答、工具回答、權限說明與閒聊**：這些回答本來就沒有可引用的
政策來源，算進分母會讓正確的行為反而拉低引用率。它們各自的正確性由對應的指標負責。

**數字型題目的 ground truth 一律不手填**：`questions.yaml` 只宣告要呼叫哪個函式、帶
什麼參數，實際數值在這裡即時 import 本專案的業務函式算出。語料被改壞或 v2 規則變更
時，`in_corpus: true` 的一致性檢查會立刻紅。

**第二版：開放推算之後，數字檢查的方向整個反過來了。** 第一版禁止模型做任何推算，
所以「語料沒寫的數字」出現在回答裡就算失敗；實測發現這個約束過度到損害功能——語料
白紙黑字寫著「09:11:00 才算遲到」，問「9:20 算不算遲到」卻答不出來。現在改成兩個
獨立的欄位判斷：

- `in_corpus`：語料有沒有白紙黑字寫這個數字 → 決定要不要做「語料 vs v2 業務函式」
  的一致性檢查（這一項驗證的是語料本身沒寫錯，與回答無關）
- `expect_stated`：回答該不該講出這個數字 → `required`（依據都在資料裡，模型應該
  推算出來並講明）／`optional`（前提不明確，例如不知道是哪一週、中間有沒有國定假日）

**推算題另外多一道但書檢查**：語料沒寫死、由模型推算出來的答案，必須附上「以系統
實際顯示為準」這類提醒——推算的前提（當天班表、請假狀況）可能與使用者的實際情形
不同，沒有這句提醒，使用者會把推算結果當成系統的正式判定。
"""

from __future__ import annotations

import argparse
import asyncio
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, time
from pathlib import Path
from time import monotonic  # 注意：上面的 `time` 是 datetime.time，不是 time 模組

import asyncpg
import yaml

# Windows 主控台預設編碼不是 UTF-8，報告裡的「≥」等符號會直接讓 print() 拋
# UnicodeEncodeError 中斷整輪評估（見 app/db_scripts/migrate.py 的同一慣例）。
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config.database import create_pool, set_pool  # noqa: E402
from app.config.settings import app_settings  # noqa: E402
from app.repositories import policy_repository, user_repository  # noqa: E402
from app.services import attendance as attendance_service  # noqa: E402
from app.services import chat as chat_service  # noqa: E402
from app.services import chat_prompt  # noqa: E402
from app.services.leave_hours import calculate_leave_hours, calculate_overtime_hours  # noqa: E402
from app.services.leave_quota import special_leave_days  # noqa: E402
from app.services.policy_retrieval import RetrievalResult  # noqa: E402
from app.services.work_hours import WorkSettings  # noqa: E402
from app.utils.gemini import GeminiUnavailable, get_gemini_client  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parent.parent
QUESTIONS_PATH = Path(__file__).resolve().parent / "questions.yaml"

HIT3_THRESHOLD = 0.9

# 推算但書是**唯一一項刻意不設在 100% 的生成端門檻**。
#
# 理由是實測數據，不是遷就：2026-09-12 連跑四輪，這一項分別是 6/7、6/7、6/6、5/6
# （累計 23/26，約 88%），而且**每一輪失敗的題目都不同**——這是隨機性，不是某個
# 特定情境沒處理好。分母只有個位數時掉一題就是 14～17%，用 100% 去量一個實測約
# 88% 的隨機行為，數學上不可能穩定達標。先前記錄的「7/7 全綠」是單次取樣的運氣。
#
# 其餘五項維持 100%，因為它們量的是確定性行為（有沒有引用、該不該拒答、數字對不對），
# 實測每輪都穩定達標，掉下來就是真的有東西壞了。
#
# **不要把這個門檻當成「可以隨便調低」的先例**：調整任何門檻之前，要先有多輪實測
# 證明失敗是隨機分佈而不是集中在特定題型，否則只是在掩蓋退化。
DISCLAIMER_THRESHOLD = 0.85

TZ = "Asia/Taipei"

# 免費層每分鐘節流（429）是暫時性的，等一下再送就會過。gemini.py 已經主動節流，
# 這裡再加一層重試，避免整輪 72 題只因為一次暫時性節流就整份驗收變紅。
_QUOTA_RETRIES = 3
_QUOTA_RETRY_WAIT = 30

# 「異常」的四種狀態，與 chat_tools._ABNORMAL_STATUSES 相同（請假不算異常）。
_ABNORMAL_STATUS_KEYS = ("late", "early_leave", "absent", "missing_punch_out")


def _date_pattern(day: date) -> re.Pattern:
    """回答裡提到某一天的各種寫法：2026-07-02、7/2、07/02、7 月 2 日、以及同一句已經講過
    月份之後只寫「2 日」「2 號」。

    只寫日的那種刻意要求前面不是數字、斜線或「月」，否則「12 日」會被當成「2 日」。
    """
    m, d = day.month, day.day
    return re.compile(
        rf"(?<!\d)(?:{day.year}-0?{m}-0?{d}|0?{m}\s*/\s*0?{d}|0?{m}\s*月\s*0?{d}\s*[日號]"
        rf"|(?<![\d/月-])0?{d}\s*[日號])(?!\d)"
    )

# 跑政策題時模擬的身分。用 employee 是刻意的**最保守選擇**：它拿到的工具清單最小，
# 代表大多數使用者的實際情境。若日後新增以主管／管理員身分驗證的權限題組，
# 那一組必須各自帶自己的身分，不要共用這一個。
_EVAL_USER = {"id": 3, "role": "employee", "department_id": 1}

# 題目可用 `as_role` 指定要以哪一種身分提問（預設 employee）。
#
# **這個機制是補一個實際發生過的漏洞**：整份題庫原本一律以 employee 身分執行，
# 於是「主管問部門出勤被誤告知沒有權限」這個 bug 在三層測試與六項門檻全綠的情況下
# 溜了過去，最後是人工用三個角色各問一次才發現（見 docs/PITFALLS.md I14）。
# 權限相關的行為**必須用多種身分各驗一次**，只用一種身分跑的 eval 對它是盲的。
_ROLE_USERS = {
    "employee": _EVAL_USER,
    "manager": {"id": 2, "role": "manager", "department_id": 1},
    "admin": {"id": 1, "role": "admin", "department_id": None},
}

# 越權題的答案裡絕對不該出現的字串（他部門同事的姓名）。比對「有沒有洩漏」比比對
# 「有沒有正確拒答」更重要——措辭可以千變萬化，但資料外洩是二元的。
_LEAK_MARKERS = ("張大同", "林小美", "李小芳")

# 姓名**本來就出現在題目裡**時（「張大同這個月出勤狀況如何？」），正確的拒絕句也會複述
# 這個名字，比對姓名必然誤判成洩漏（09-13 實測）。這種情況改看回答有沒有出勤數字——
# 那才是真正外洩的東西，模型編造出來的數字也一樣算。刻意只認「數字＋出勤單位」而不是
# 任何數字，否則「這個月（8/1 至 8/25）」這種日期複述也會被判成洩漏。
_ATTENDANCE_FIGURE_PATTERN = re.compile(r"\d+(\.\d+)?\s*(次|天|日|小時|分鐘)")

# 「權限不足」的說法。**不併進 `chat_prompt.is_refusal()`**：兩者在文字上無法區分「正確
# 的權限說明」與「把權限句型誤套到規定問答上」——09-13 第 19 題（「主管看得到其他部門的
# 申請紀錄嗎？」）與第 83 題的回答開頭一字不差，都是「這部分你目前沒有權限查看」，但前者
# 是答錯、後者是答對。能分辨兩者的只有題目本身的期望，所以判定只能放在 eval 這一層：
# 標了 `expect_permission_denied` 的題目出現它是答對，其他題目出現它就是過度拒答。
#
# 限定第一、二人稱：「主管沒有權限看其他部門」是在陳述規定，是正常回答；「你／我這邊
# 沒有權限」才是在拒絕這次提問。以 09-12、09-13 三份存檔的全部回答離線驗證過，只命中
# 應該命中的題目。
#
# 第二種說法「不在你的權限範圍」來自 `chat_tools._refusal()` 自己的拒絕訊息，模型經常
# 照抄（09-13 第二輪，主管問他部門的張大同）。那是正確的權限說明，只認「沒有權限」會把它
# 判成失敗。
_PERMISSION_DENIAL_PATTERN = re.compile(r"(你|我)[^。！？\n]{0,6}沒有權限|不在你的權限範圍")


def _answer_body(text: str) -> str:
    """去掉結尾的「— 依據：」引用行——章節標題裡的編號（「8. 誰看得到什麼」）不是回答內容。"""
    return text.split("— 依據：", 1)[0]


def _is_leaked(question: str, text: str) -> bool:
    body = _answer_body(text)
    for name in _LEAK_MARKERS:
        if name in question:
            if name in body and _ATTENDANCE_FIGURE_PATTERN.search(body):
                return True
        elif name in body:
            return True
    return False

# 推算型答案必須附上的但書。措辭不強制統一，只要有表達「以系統實際顯示為準」
# 的意思即可，所以比對幾種常見說法而不是單一字串。
_DISCLAIMER_MARKERS = ("系統顯示為準", "系統實際顯示", "以系統為準", "系統顯示的為準", "系統實際判定")

_GROUND_TRUTH_FUNCTIONS = {
    "calculate_leave_hours": calculate_leave_hours,
    "calculate_overtime_hours": calculate_overtime_hours,
    "special_leave_days": special_leave_days,
}

# 與 v2 自己的單元測試、種子資料一致的考勤設定（見 SPEC.md §5.4 預設值）。
# v2 的 system_settings 若被調整，這裡與語料都要同步修改（語料異動紀律）。
_GROUND_TRUTH_SETTINGS = WorkSettings(
    work_start=time(9, 0),
    work_end=time(18, 0),
    lunch_start=time(12, 0),
    lunch_end=time(13, 0),
    grace_minutes=10,
)


def _taipei(value: str) -> datetime:
    """把 questions.yaml 裡的本地時間字串轉成帶台北時區的 datetime。"""
    return datetime.fromisoformat(f"{value}+08:00")


def _format_number(value: float | int) -> str:
    """把 ground truth 數值格式化成語料中會出現的寫法（3.0 → 3、14 → 14）。"""
    return f"{value:g}"


# 單位的同義寫法。語料的級距表寫「14 日」，但模型在自然對話時會講「14 天」——
# 第一版語氣生硬時模型傾向照抄語料用字，語氣改自然之後就改用口語說法了。
# 只比對單一字串會把「答對了但換個說法」誤判成失敗（實測一輪因此假紅 4 題）。
_UNIT_SYNONYMS = {
    "日": ("日", "天"),
    "天": ("日", "天"),
    "小時": ("小時", "個小時"),
}


def _number_variants(value: float | int, unit: str) -> tuple[str, ...]:
    """產生可接受的數值寫法（含單位同義詞與有無空格的差異）。"""
    number = _format_number(value)
    units = _UNIT_SYNONYMS.get(unit, (unit,)) if unit else ("",)
    variants: list[str] = []
    for candidate in units:
        variants.append(f"{number} {candidate}".strip())
        variants.append(f"{number}{candidate}")
    return tuple(dict.fromkeys(variants))


@dataclass
class QuestionResult:
    question: str
    expected_section_path: str | None
    expect_refusal: bool
    as_role: str = "employee"
    """以哪一種身分提問（employee／manager／admin）。權限題必須用多種身分各驗一次。"""

    forbid_leak: bool = False
    """這題是否為越權題：回答裡不得出現他部門同事的姓名。"""

    answer_leaked: bool | None = None

    expect_permission_denied: bool = False
    """這題的正確行為是說明「權限不足」。**與 `expect_refusal` 是兩回事**：誘導題是
    文件裡真的沒有答案，權限題是系統有這份資料、只是這個身分看不到——答成「文件裡沒有」
    反而是錯的（見 questions.yaml 權限題組的期望要點）。"""

    answer_permission_denied: bool | None = None

    category: str = "policy"

    expect_tools: list[str] | None = None
    """這題應該呼叫哪些工具（呼叫其中任一支即算對）。空清單代表**不得**呼叫任何工具
    （閒聊、情緒）。`None` 代表不檢查。

    09-13 以前 eval 只記錄有沒有呼叫工具、不判斷該不該呼叫，於是「列出日期」被分到
    沒有工具的路徑、回「沒有權限」這種失敗，就算題目在題庫裡也看不出來（PITFALLS I17）。"""

    answer_tools_ok: bool | None = None

    expected_dates: list[date] | None = None
    """異常日期的 ground truth，執行時用出勤 service 即時算出（跟數字題一樣不手填）。"""

    answer_dates_missing: list[date] = field(default_factory=list)

    expected_mentions: list[str] | None = None
    """回答必須提到的字串（通訊錄題的分機、部門成員姓名），執行時查資料庫即時取得。"""

    answer_mentions_missing: list[str] = field(default_factory=list)

    answer_tools: list[str] = field(default_factory=list)
    """這題實際呼叫了哪些查詢工具。**工具回答沒有文件出處可引用**，所以要排除在
    引用率的分母之外——這與「拒答不計入引用率」是同一個道理。"""
    top_paths: list[str] = field(default_factory=list)
    top_scores: list[float] = field(default_factory=list)
    hit_at_1: bool | None = None
    hit_at_3: bool | None = None
    passed_filter_count: int = 0
    number_label: str | None = None
    number_ok: bool | None = None
    number_detail: str = ""
    number_in_corpus: bool | None = None
    """這個數字有沒有寫在語料裡，決定要不要做「語料 vs v2 函式」一致性檢查。"""

    expect_stated: str = "required"
    """回答該不該講出這個數字：`required`（依據都在資料裡，應該推算出來）／
    `optional`（前提不明確，例如不知道是哪一週、中間有沒有國定假日）。"""

    answer_has_disclaimer: bool | None = None
    """推算出來的答案有沒有加上「以系統顯示為準」這類但書（系統提示規則 2 的硬性要求）。"""

    should_be_answered: bool = True
    """這題是否「必須答得出來」。誘導題（expect_refusal）、權限題與閒聊題除外——語料真的沒有答案，
    本來就該拒答。第二版開放推算之後，推算題也必須答得出來（第一版把它們排除在這項
    檢查之外，等於默許助理對「9:20 算不算遲到」這類問題擺爛）。"""

    # --- 以下為生成端，--skip-generation 時全部維持 None ---
    answer_text: str | None = None
    answer_refused: bool | None = None
    answer_has_citation: bool | None = None
    answer_number_ok: bool | None = None
    answer_error: str | None = None


def _compute_ground_truth(spec: dict) -> float | int:
    """依 questions.yaml 的宣告，即時呼叫 v2 業務函式算出期望數值。"""
    function_name = spec["function"]
    kwargs = spec.get("kwargs", {})

    if function_name not in _GROUND_TRUTH_FUNCTIONS:
        raise SystemExit(f"questions.yaml 指定了未知的 ground truth 函式：{function_name}")
    function = _GROUND_TRUTH_FUNCTIONS[function_name]

    if function_name == "special_leave_days":
        return function(total_months=kwargs["total_months"])
    # calculate_leave_hours / calculate_overtime_hours 的簽名相同
    return function(_taipei(kwargs["start"]), _taipei(kwargs["end"]), _GROUND_TRUTH_SETTINGS, TZ)


async def _user_id_by_name(pool: asyncpg.Pool, name: str) -> int:
    matched = [row["id"] for row in await user_repository.find_all(pool) if row["name"] == name]
    if len(matched) != 1:
        raise SystemExit(f"questions.yaml 指定的同事「{name}」在資料庫裡不是恰好一位")
    return matched[0]


async def _compute_expected_dates(pool: asyncpg.Pool, spec: dict, as_role: str) -> list[date]:
    """異常日期的 ground truth：走出勤頁同一支 service 與同一個狀態判定。

    **刻意不經過 chat_tools**：拿工具自己的輸出當答案，工具算錯時 eval 也跟著錯，
    等於沒有檢查。這裡直接用出勤頁的篩選邏輯，量的是「AI 講的跟畫面一不一致」。
    """
    user_id = (
        await _user_id_by_name(pool, spec["employee_name"])
        if spec.get("employee_name")
        else _ROLE_USERS[as_role]["id"]
    )
    page = await attendance_service.get_my_records(
        pool, user_id,
        start_date=date.fromisoformat(spec["start"]), end_date=date.fromisoformat(spec["end"]),
        page_size=1000,
    )
    return sorted({
        row["punch_date"] for row in page["records"]
        if any(attendance_service.matches_status_filter(row, key) for key in _ABNORMAL_STATUS_KEYS)
    })


async def _compute_expected_mentions(pool: asyncpg.Pool, spec: dict, as_role: str) -> list[str]:
    """通訊錄題的 ground truth，查資料庫即時取得（展示資料重置後分機可能不同）。"""
    if spec.get("extension_of"):
        user_id = await _user_id_by_name(pool, spec["extension_of"])
        user = await user_repository.find_public_by_id(pool, user_id)
        return [user["extension_number"]]
    if spec.get("members_of_my_department"):
        # 提問者本人不列入：「除了你之外還有王小明」是完全正確的回答。
        requester = _ROLE_USERS[as_role]
        return [
            row["name"] for row in await user_repository.find_all(pool, requester["department_id"])
            if row["id"] != requester["id"]
        ]
    raise SystemExit(f"questions.yaml 的 expected_mentions 無法解析：{spec}")


async def _load_corpus_by_section_path(pool: asyncpg.Pool) -> dict[str, str]:
    """把資料庫裡的語料依 section_path 聚合，供「語料寫死的數字是否與 v2 一致」的檢查使用。"""
    rows = await pool.fetch("SELECT section_path, raw_content FROM policy_embeddings")
    corpus: dict[str, str] = {}
    for row in rows:
        corpus[row["section_path"]] = corpus.get(row["section_path"], "") + "\n" + row["raw_content"]
    return corpus


def _scrub(text: str) -> str:
    """把 API Key 從錯誤訊息裡抹掉——評估報告常常會被貼到別的地方。"""
    api_key = app_settings.GOOGLE_API_KEY.strip()
    return text.replace(api_key, "***") if api_key else text


async def _search_unfiltered(pool: asyncpg.Pool, client, question: str, top_k: int) -> list[RetrievalResult]:
    """量 hit@k 用的「未過濾的完整排序」，繞過 `policy_retrieval.retrieve()` 的門檻過濾——
    hit@k 衡量的是排序品質，門檻過濾屬於系統行為，另外以 passed_filter_count 記錄。"""
    vector = await client.embed_query(question)
    rows = await policy_repository.search_similar(pool, vector, top_k)
    return [RetrievalResult(**row) for row in rows]


async def run_eval(
    pool: asyncpg.Pool, questions: list[dict], with_generation: bool = True
) -> tuple[list[QuestionResult], dict[str, str]]:
    client = get_gemini_client()
    corpus = await _load_corpus_by_section_path(pool)
    results: list[QuestionResult] = []

    started_at = monotonic()
    for index, item in enumerate(questions, start=1):
        # 進度印到 stderr：報告本體走 stdout，重導向存檔時不會被進度訊息汙染。
        elapsed = monotonic() - started_at
        eta = ""
        if index > 1:
            remaining = elapsed / (index - 1) * (len(questions) - index + 1)
            eta = f" 預估剩餘 {remaining / 60:.1f} 分"
        print(
            f"[{datetime.now():%H:%M:%S}] [{index}/{len(questions)}]{eta} {item['question'][:36]}",
            file=sys.stderr,
            flush=True,
        )
        expected_path = item.get("expected_section_path")
        result = QuestionResult(
            question=item["question"],
            expected_section_path=expected_path,
            expect_refusal=bool(item.get("expect_refusal", False)),
            should_be_answered=not (
                item.get("expect_refusal", False)
                or item.get("expect_permission_denied", False)
                or item.get("category") == "chitchat"
            ),
            as_role=item.get("as_role", "employee"),
            forbid_leak=bool(item.get("forbid_leak", False)),
            expect_permission_denied=bool(item.get("expect_permission_denied", False)),
            expect_tools=item.get("expect_tools"),
            category=item.get("category", "policy"),
        )
        if item.get("expected_dates"):
            result.expected_dates = await _compute_expected_dates(
                pool, item["expected_dates"], result.as_role
            )
        if item.get("expected_mentions"):
            result.expected_mentions = await _compute_expected_mentions(
                pool, item["expected_mentions"], result.as_role
            )

        retrieved = await _search_unfiltered(pool, client, item["question"], max(3, app_settings.RETRIEVAL_TOP_K))
        result.top_paths = [r.section_path for r in retrieved]
        result.top_scores = [r.score for r in retrieved]
        result.passed_filter_count = sum(1 for r in retrieved if r.score >= app_settings.RETRIEVAL_MIN_SCORE)

        if expected_path:
            result.hit_at_1 = expected_path in result.top_paths[:1]
            result.hit_at_3 = expected_path in result.top_paths[:3]

        number_spec = item.get("expected_number")
        needle: str | None = None
        if number_spec:
            value = _compute_ground_truth(number_spec)
            unit = number_spec.get("unit", "")
            variants = _number_variants(value, unit)
            needle = variants[0]
            result.number_label = f"{number_spec['function']}{number_spec.get('kwargs', {})} = {needle}"
            result.number_in_corpus = bool(number_spec.get("in_corpus"))
            # `expect_stated` 與 `in_corpus` 是兩件獨立的事，第二版刻意拆開：
            #   in_corpus     語料有沒有白紙黑字寫這個數字 → 決定要不要做「語料 vs
            #                 v2 業務函式」的一致性檢查（驗證語料沒寫錯）
            #   expect_stated 回答該不該講出這個數字 → required（依據都在資料裡，
            #                 應該推算出來）／optional（前提不明確，講不講都可以）
            # 第一版只有 in_corpus，且語料沒寫就等於「回答不可出現」——那正是讓
            # 助理連「9:20 晚於 9:11」都不敢回答的根源。
            result.expect_stated = number_spec.get("expect_stated", "required")

            if number_spec.get("in_corpus") and expected_path:
                section_text = corpus.get(expected_path, "")
                result.number_ok = any(v in section_text for v in variants)
                result.number_detail = (
                    f"語料章節「{expected_path}」{'有' if result.number_ok else '找不到'}「{needle}」"
                )

        if with_generation:
            usable = [r for r in retrieved if r.score >= app_settings.RETRIEVAL_MIN_SCORE][
                : app_settings.RETRIEVAL_TOP_K
            ]

            generated_text: str | None = None
            for attempt in range(_QUOTA_RETRIES):
                try:
                    # **必須走正式環境的同一支函式**，包含檢索落空的題目。
                    #
                    # 09-13 以前這裡遇到檢索落空就直接標記拒答、不呼叫生成，理由是「落空
                    # 路徑必定是拒答」——那在落空路徑不帶工具時成立。它同時讓 eval 完全看不到
                    # 「個人資料題搜不到文件就查不到」這個 bug（PITFALLS I17）。現在落空路徑也帶
                    # 工具，必須實際跑一次才知道模型有沒有去查。
                    #
                    # 考勤設定的注入、工具清單、提示詞的選擇都在 answer_question() 裡，
                    # eval 自己組任何一段都可能跟正式路徑分歧。
                    generated_text, called_tools = await chat_service.answer_question(
                        pool,
                        client,
                        _ROLE_USERS[item.get("as_role", "employee")],
                        item["question"],
                        usable,
                    )
                    result.answer_tools = called_tools
                    break
                except GeminiUnavailable as exc:
                    # 這個迴圈內能拋出 GeminiUnavailable 的原因（逾時、429、網路暫時性錯誤）
                    # 全部屬於外部依賴的暫時性問題——沒有金鑰的情況在迴圈外的
                    # get_gemini_client() 就已經先失敗，不會走到這裡。原本只針對 429／quota
                    # 字樣重試，漏掉了「呼叫 Gemini API 逾時。」這個訊息，導致偶發的單題逾時
                    # 直接判定失敗、整輪 72 題就地變紅（實測一輪 3 題因此失敗，不重試就沒有
                    # 機會證明只是暫時性延遲）。這裡只放寬 eval 腳本自己的重試範圍，
                    # 不影響正式環境 chat.py 的 25 秒逾時設定（那是刻意配合使用者體驗的值）。
                    is_transient_error = True
                    if is_transient_error and attempt < _QUOTA_RETRIES - 1:
                        print(
                            f"    撞到配額限制，{_QUOTA_RETRY_WAIT} 秒後重試（{attempt + 1}/{_QUOTA_RETRIES - 1}）",
                            file=sys.stderr,
                            flush=True,
                        )
                        await asyncio.sleep(_QUOTA_RETRY_WAIT)
                        continue
                    result.answer_error = _scrub(f"{type(exc).__name__}: {exc}")[:200]
                    break

            if generated_text is not None:
                result.answer_text = generated_text
                if result.forbid_leak:
                    # 措辭可以千變萬化，資料有沒有外洩卻是二元的——這一項比「拒答
                    # 的句子寫得對不對」重要得多，所以獨立成一個硬性門檻。
                    result.answer_leaked = _is_leaked(item["question"], generated_text)
                result.answer_permission_denied = (
                    _PERMISSION_DENIAL_PATTERN.search(_answer_body(generated_text)) is not None
                )
                # 與 chat.ask() 的 kind 判定一致：檢索落空又沒有呼叫工具就是拒答（寒暄、
                # 文件沒涵蓋的主題），不靠字串比對；有呼叫工具則是個人資料回答，不算拒答。
                if result.answer_tools:
                    result.answer_refused = False
                elif not usable:
                    result.answer_refused = True
                else:
                    result.answer_refused = chat_prompt.is_refusal(generated_text)

                if result.expect_tools is not None:
                    if result.expect_tools:
                        result.answer_tools_ok = any(t in result.answer_tools for t in result.expect_tools)
                    else:
                        # 閒聊不得呼叫工具，也不得冒出「你沒有權限」這種莫名其妙的回答。
                        result.answer_tools_ok = (
                            not result.answer_tools and not result.answer_permission_denied
                        )
                if result.expected_dates is not None:
                    result.answer_dates_missing = [
                        day for day in result.expected_dates
                        if not _date_pattern(day).search(_answer_body(generated_text))
                    ]
                if result.expected_mentions is not None:
                    result.answer_mentions_missing = [
                        text for text in result.expected_mentions if text and text not in generated_text
                    ]
                source_files = {source.source_file for source in usable}
                result.answer_has_citation = "依據：" in generated_text and any(
                    source_file in generated_text for source_file in source_files
                )
                if needle:
                    stated = any(v in generated_text for v in variants)
                    # required：依據都在資料裡，回答必須講出這個數字（且必須正確——
                    #           ground truth 是 v2 業務函式即時算出的，不是手填）
                    # optional：前提不明確，講不講都可以；但若講了就必須是對的
                    if result.expect_stated == "optional":
                        result.answer_number_ok = True
                    else:
                        result.answer_number_ok = stated

                    # 推算出來的答案必須附上但書。推算的前提（當天班表、請假狀況、
                    # 是哪一週）可能與使用者的實際情形不同，沒有這句提醒，使用者會
                    # 把推算結果當成系統的正式判定。
                    #
                    # **但前提是回答真的講出了推算結果。** 系統提示規則 2 的原文是
                    # 「只要答案是你推算出來的（不是原文照抄的數字）」——沒講出任何
                    # 推算數字時，就沒有東西需要標註。`expect_stated: optional` 的題目
                    # （前提不明確，例如不知道是哪一週）模型合理地選擇只解釋規則、
                    # 不給數字，這是規則 3 期望的行為，不該因此被判失敗。
                    # 留 None 代表「這題不納入但書分母」。
                    if not number_spec.get("in_corpus") and stated:
                        result.answer_has_disclaimer = any(
                            marker in generated_text for marker in _DISCLAIMER_MARKERS
                        )

        results.append(result)

    return results, corpus


def _report(
    results: list[QuestionResult], corpus: dict[str, str], *, is_full_run: bool = True
) -> bool:
    """列印評估報告，回傳是否通過驗收門檻。"""
    total = len(results)
    refusal_questions = [r for r in results if r.expect_refusal]
    scored = [r for r in results if r.expected_section_path]

    hit1 = sum(1 for r in scored if r.hit_at_1)
    hit3 = sum(1 for r in scored if r.hit_at_3)
    hit1_rate = hit1 / len(scored) if scored else 0.0
    hit3_rate = hit3 / len(scored) if scored else 0.0

    print("=" * 78)
    print("黃金題庫評估報告")
    print("=" * 78)
    print(f"題庫總題數：{total}（其中誘導題 {len(refusal_questions)} 題）")
    print(f"納入 hit@k 計算的題數：{len(scored)}（有標註 expected_section_path 的題目）")
    print()

    print("--- 檢索指標（不含生成）---")
    print(f"hit@1：{hit1}/{len(scored)} = {hit1_rate:.1%}")
    print(f"hit@3：{hit3}/{len(scored)} = {hit3_rate:.1%}  （門檻 ≥ {HIT3_THRESHOLD:.0%}）")
    print()

    misses = [r for r in scored if not r.hit_at_3]
    if misses:
        print(f"--- hit@3 未命中的 {len(misses)} 題（診斷用）---")
        for r in misses:
            print(f"Q：{r.question}")
            print(f"   期望：{r.expected_section_path}")
            for path, score in zip(r.top_paths[:3], r.top_scores[:3]):
                print(f"   實際：{score:.4f}  {path}")
            print()

    rank_misses = [r for r in scored if r.hit_at_3 and not r.hit_at_1]
    if rank_misses:
        print(f"--- hit@1 未命中但 hit@3 命中的 {len(rank_misses)} 題（章節內容重疊的線索）---")
        for r in rank_misses:
            print(f"Q：{r.question}")
            print(f"   期望：{r.expected_section_path}")
            print(f"   實際 top-1：{r.top_scores[0]:.4f}  {r.top_paths[0]}")
        print()

    print("--- 誘導題（語料沒有答案，期望拒答）---")
    filtered_empty = sum(1 for r in refusal_questions if r.passed_filter_count == 0)
    print(
        f"檢索層就被過濾成空的：{filtered_empty}/{len(refusal_questions)}"
        f"（門檻 RETRIEVAL_MIN_SCORE={app_settings.RETRIEVAL_MIN_SCORE}）"
    )
    for r in refusal_questions:
        top_score = r.top_scores[0] if r.top_scores else 0.0
        status = "檢索層已擋下" if r.passed_filter_count == 0 else "進入生成步驟，需靠生成端硬約束拒答"
        print(f"  [{top_score:.4f}] {status}｜{r.question}")
    print()

    number_results = [r for r in results if r.number_label]
    print(f"--- 數字型 ground truth（{len(number_results)} 題，一律由 v2 業務函式即時算出）---")
    corpus_failures = []
    for r in number_results:
        line = f"  {r.number_label}"
        if r.number_ok is True:
            line += f"　OK {r.number_detail}"
        elif r.number_ok is False:
            line += f"　FAIL {r.number_detail}"
            corpus_failures.append(r)
        else:
            line += "　（語料未寫死此數字，不做一致性檢查）"
        print(line)
    print()

    print("--- 章節覆蓋率 ---")
    covered = {r.expected_section_path for r in results if r.expected_section_path}
    all_paths = set(corpus.keys())
    uncovered = sorted(all_paths - covered)
    print(f"語料共 {len(all_paths)} 個 section_path，題庫涵蓋 {len(covered & all_paths)} 個")
    if uncovered:
        print(f"未被任何題目涵蓋的章節（{len(uncovered)} 個）：")
        for path in uncovered:
            print(f"  - {path}")
    print()

    generated = [r for r in results if r.answer_text is not None or r.answer_error]
    generation_failures: list[str] = []

    if not generated:
        print("--- 生成端指標 ---")
        print("（本次以 --skip-generation 執行，未呼叫 LLM）")
        print()
    else:
        errored = [r for r in generated if r.answer_error]
        answered = [r for r in generated if r.answer_text is not None]

        print(f"--- 生成端指標（實際呼叫 Gemini，{len(generated)} 題）---")
        if errored:
            print(f"呼叫失敗 {len(errored)} 題：")
            for r in errored[:5]:
                print(f"  {r.question} → {r.answer_error}")
            generation_failures.append(f"{len(errored)} 題呼叫 LLM 失敗")

        # 排除拒答（沒有可引用的來源）、工具回答（答案來自系統資料，不是文件）與權限不足的
        # 說明（「你沒有權限查看」不是政策內容，沒有東西可引用；09-13 第二輪同一題有時附、
        # 有時不附，照舊計入只會讓這一項隨機紅）。權限句型若出現在該答的題目上，
        # 「該答有答」那一項會抓到，不會因為這裡排除而漏掉。
        #
        # 閒聊題也排除：「這個系統有夠難用，每次打卡都卡住」會因為「打卡」命中出勤規則而走
        # 政策路徑，但正確的回應是同理與引導，本來就沒有引用任何規定（09-13 第三輪）。
        citable = [
            r
            for r in answered
            if not r.answer_refused
            and not r.answer_tools
            and not r.answer_permission_denied
            and r.category != "chitchat"
        ]
        cited = sum(1 for r in citable if r.answer_has_citation)
        citation_rate = cited / len(citable) if citable else 1.0
        print(f"回答附引用來源比率：{cited}/{len(citable)} = {citation_rate:.1%}（門檻 100%，分母排除拒答）")
        for r in citable:
            if not r.answer_has_citation:
                print(f"  FAIL 未附引用：{r.question}")
        if cited != len(citable):
            generation_failures.append("有回答沒有附上引用來源")

        refusal_answered = [r for r in answered if r.expect_refusal]
        refused_ok = sum(1 for r in refusal_answered if r.answer_refused)
        refusal_rate = refused_ok / len(refusal_answered) if refusal_answered else 1.0
        print(f"誘導題拒答率：{refused_ok}/{len(refusal_answered)} = {refusal_rate:.1%}（門檻 100%）")
        for r in refusal_answered:
            if not r.answer_refused:
                print(f"  FAIL 該拒答卻回答了：{r.question}")
                print(f"     回答：{(r.answer_text or '')[:120]}")
        if refused_ok != len(refusal_answered):
            generation_failures.append("有誘導題沒有正確拒答")

        permission_answered = [r for r in answered if r.expect_permission_denied]
        if permission_answered:
            # 要同時滿足兩件事：有說出權限不足，而且**沒有**說成「文件裡沒有」——
            # 後者會讓使用者以為系統沒有這個功能，而不是自己的權限看不到。
            denied_ok = [
                r for r in permission_answered if r.answer_permission_denied and not r.answer_refused
            ]
            print(
                f"權限不足時正確說明：{len(denied_ok)}/{len(permission_answered)} "
                f"= {len(denied_ok) / len(permission_answered):.1%}（門檻 100%）\n"
                "  （必須說明是權限看不到，不得說成文件裡沒有寫）"
            )
            for r in permission_answered:
                if r not in denied_ok:
                    print(f"  FAIL 沒有正確說明權限不足（以 {r.as_role} 身分）：{r.question}")
                    print(f"     回答：{(r.answer_text or '')[:160]}")
            if len(denied_ok) != len(permission_answered):
                generation_failures.append("有權限題沒有正確說明權限不足")

        should_answer = [r for r in answered if r.should_be_answered]
        # 「你目前沒有權限查看」也算過度拒答：`is_refusal()` 認不得這種句型，於是模型把權限
        # 說明誤套到規定問答上時（09-13 第 19 題），這一項照樣全綠。主管被誤告知沒有權限
        # 那個 bug（PITFALLS I14）當初能溜過去，也是同一個盲點。
        over_refused = [
            r for r in should_answer if r.answer_refused or r.answer_permission_denied
        ]
        answer_rate = (len(should_answer) - len(over_refused)) / len(should_answer) if should_answer else 1.0
        print(
            f"該答有答（未過度拒答）：{len(should_answer) - len(over_refused)}/{len(should_answer)} "
            f"= {answer_rate:.1%}（門檻 100%）"
        )
        for r in over_refused:
            print(f"  FAIL 語料有答案卻拒答了：{r.question}")
            print(f"     回答：{(r.answer_text or '')[:120]}")
        if over_refused:
            generation_failures.append(f"{len(over_refused)} 題語料有答案卻被拒答（過度拒答）")

        numeric_answered = [r for r in answered if r.answer_number_ok is not None]
        numeric_ok = sum(1 for r in numeric_answered if r.answer_number_ok)
        numeric_rate = numeric_ok / len(numeric_answered) if numeric_answered else 1.0
        print(
            f"數字型答案正確：{numeric_ok}/{len(numeric_answered)} = {numeric_rate:.1%}（門檻 100%）\n"
            "  （ground truth 一律由 v2 業務函式即時算出；expect_stated=required 的題目\n"
            "   回答必須講出這個數字，optional 的題目前提不明確、講不講都可以）"
        )
        for r in numeric_answered:
            if not r.answer_number_ok:
                print(f"  FAIL 回答沒有講出正確的推算結果（{r.number_label}）：{r.question}")
                print(f"     回答：{(r.answer_text or '')[:160]}")
        if numeric_ok != len(numeric_answered):
            generation_failures.append("有數字型答案與 v2 函式輸出不一致")

        # 推算題的但書檢查：推算的前提（當天班表、請假狀況、是哪一週）可能與使用者的
        # 實際情形不同，沒有這句提醒，使用者會把推算結果當成系統的正式判定。
        derived = [r for r in answered if r.answer_has_disclaimer is not None]
        with_disclaimer = sum(1 for r in derived if r.answer_has_disclaimer)
        disclaimer_rate = with_disclaimer / len(derived) if derived else 1.0
        print(
            f"推算型答案附上但書：{with_disclaimer}/{len(derived)} = {disclaimer_rate:.1%}"
            f"（門檻 {DISCLAIMER_THRESHOLD:.0%}）\n"
            "  （語料沒有寫死、由模型推算出來的答案，必須提醒以系統實際顯示為準）"
        )
        for r in derived:
            if not r.answer_has_disclaimer:
                print(f"  FAIL 推算結果沒有附上「以系統顯示為準」的提醒：{r.question}")
                print(f"     回答：{(r.answer_text or '')[:160]}")
        if disclaimer_rate < DISCLAIMER_THRESHOLD:
            generation_failures.append(
                f"推算型答案附上但書的比率低於 {DISCLAIMER_THRESHOLD:.0%}"
            )

        # 越權題：措辭可以千變萬化，資料有沒有外洩卻是二元的，門檻永遠是 100%。
        leak_checked = [r for r in answered if r.answer_leaked is not None]
        if leak_checked:
            leaked = [r for r in leak_checked if r.answer_leaked]
            clean = len(leak_checked) - len(leaked)
            print(
                f"越權題未洩漏他人資料：{clean}/{len(leak_checked)} "
                f"= {clean / len(leak_checked):.1%}（門檻 100%）\n"
                "  （以各自的角色身分提問，回答裡不得出現權限範圍外同事的姓名；\n"
                "   姓名本來就在題目裡時，改看回答有沒有他的出勤數字）"
            )
            for r in leaked:
                print(f"  FAIL 越權題洩漏了他人資料（以 {r.as_role} 身分）：{r.question}")
                print(f"     回答：{(r.answer_text or '')[:160]}")
            if leaked:
                generation_failures.append("越權題洩漏了權限範圍外的他人資料")

        tool_checked = [r for r in answered if r.answer_tools_ok is not None]
        if tool_checked:
            tool_ok = sum(1 for r in tool_checked if r.answer_tools_ok)
            print(
                f"工具使用正確：{tool_ok}/{len(tool_checked)} = {tool_ok / len(tool_checked):.1%}（門檻 100%）\n"
                "  （個人資料題不論問法有沒有搜到文件都要去查；閒聊題不得呼叫工具）"
            )
            for r in tool_checked:
                if not r.answer_tools_ok:
                    expected = "、".join(r.expect_tools) if r.expect_tools else "不呼叫任何工具"
                    actual = "、".join(r.answer_tools) or "沒有呼叫"
                    print(f"  FAIL 工具使用錯誤（期望 {expected}，實際 {actual}）：{r.question}")
                    print(f"     回答：{(r.answer_text or '')[:160]}")
            if tool_ok != len(tool_checked):
                generation_failures.append("有題目沒有正確使用查詢工具")

        dated = [r for r in answered if r.expected_dates is not None]
        if dated:
            dated_ok = [r for r in dated if not r.answer_dates_missing]
            print(
                f"異常日期完整：{len(dated_ok)}/{len(dated)} = {len(dated_ok) / len(dated):.1%}（門檻 100%）\n"
                "  （ground truth 由出勤頁同一支 service 即時算出，回答必須逐日講到）"
            )
            for r in dated:
                if r.answer_dates_missing:
                    missing = "、".join(day.isoformat() for day in r.answer_dates_missing)
                    print(f"  FAIL 漏講的日期（{missing}）：{r.question}")
                    print(f"     回答：{(r.answer_text or '')[:200]}")
            if len(dated_ok) != len(dated):
                generation_failures.append("有異常日期沒有講出來")

        mentioned = [r for r in answered if r.expected_mentions is not None]
        if mentioned:
            mention_ok = [r for r in mentioned if not r.answer_mentions_missing]
            print(
                f"通訊錄答案正確：{len(mention_ok)}/{len(mentioned)} = "
                f"{len(mention_ok) / len(mentioned):.1%}（門檻 100%）"
            )
            for r in mentioned:
                if r.answer_mentions_missing:
                    print(f"  FAIL 沒有講到（{'、'.join(r.answer_mentions_missing)}）：{r.question}")
                    print(f"     回答：{(r.answer_text or '')[:160]}")
            if len(mention_ok) != len(mentioned):
                generation_failures.append("有通訊錄題沒有答出正確資料")
        print()

    # hit@3 與章節覆蓋率只在「跑完整題庫」時才有意義。用 --category／--limit 跑子集時，
    # 子集本來就不可能涵蓋 54 個章節，權限題組更是刻意沒有 expected_section_path
    # （答案來自工具與權限判斷，不是語料的某一節）。不排除的話，單獨迭代某個題組
    # 永遠是紅的，下一個人會以為題組寫壞了。
    passed = (
        (hit3_rate >= HIT3_THRESHOLD if scored else True)
        and not corpus_failures
        and (not uncovered if is_full_run else True)
        and not generation_failures
    )
    print("=" * 78)
    if passed:
        print("PASS 全部驗收項目通過")
    else:
        if hit3_rate < HIT3_THRESHOLD:
            print(f"FAIL hit@3 {hit3_rate:.1%} 未達門檻 {HIT3_THRESHOLD:.0%}")
        if corpus_failures:
            print(f"FAIL 有 {len(corpus_failures)} 題的語料數字與 v2 業務函式算出來的不一致")
        if uncovered:
            print(f"FAIL 有 {len(uncovered)} 個章節沒有被任何題目涵蓋")
        for failure in generation_failures:
            print(f"FAIL {failure}")
    print("=" * 78)
    return passed


def _format_answers_for_review(results: list[QuestionResult], questions: list[dict]) -> str:
    """把每題的期望要點與實際回答並排輸出，供人工／AI 逐句對照驗收使用。"""
    lines: list[str] = []
    for index, (result, item) in enumerate(zip(results, questions), start=1):
        lines.append("=" * 78)
        if result.expect_refusal:
            kind = "誘導題"
        elif result.expect_permission_denied:
            kind = "權限不足題"
        elif item.get("category") == "chitchat":
            kind = "閒聊題"
        elif item.get("category") == "personal":
            kind = "個人資料題"
        elif result.number_label and not result.number_in_corpus:
            kind = "推算題"
        else:
            kind = "一般"
        lines.append(f"第 {index} 題　[{kind}]　{result.question}")
        lines.append(f"期望章節：{result.expected_section_path or '（語料無對應章節）'}")
        lines.append("期望要點：")
        for point in item.get("expected_points", []):
            lines.append(f"  - {point}")
        if result.number_label:
            direction = "回答必須講出" if result.expect_stated == "required" else "講不講都可以（前提不明確）"
            lines.append(f"數字 ground truth：{result.number_label}（{direction}）")
        lines.append("-" * 78)
        lines.append(result.answer_text or f"（無回答：{result.answer_error or '未執行生成'}）")
        lines.append("")
    return "\n".join(lines)


async def _main_async(args: argparse.Namespace) -> bool:
    data = yaml.safe_load(args.questions.read_text(encoding="utf-8"))
    questions = data["questions"]
    is_full_run = not args.category and not args.limit
    if args.category:
        questions = [q for q in questions if q.get("category") == args.category]
    if args.limit:
        questions = questions[: args.limit]

    pool = await create_pool(app_settings.DATABASE_URL)
    # 同時註冊成全域連線池：正式路徑的 `answer_with_tools()` 會經由 `get_virtual_now()`
    # 取用它來解析「今天」。少了這行，eval 會在第一題就因為連線池未初始化而中止。
    set_pool(pool)
    try:
        results, corpus = await run_eval(pool, questions, with_generation=not args.skip_generation)
    finally:
        await pool.close()

    if args.save_answers:
        args.save_answers.write_text(_format_answers_for_review(results, questions), encoding="utf-8")
        print(f"已將 {len(results)} 題的回答寫入 {args.save_answers}（供逐句對照驗收）\n")

    return _report(results, corpus, is_full_run=is_full_run)


def main() -> None:
    parser = argparse.ArgumentParser(description="對黃金題庫跑檢索評估，輸出 hit@1 / hit@3 等指標")
    parser.add_argument("--questions", type=Path, default=QUESTIONS_PATH, help="題庫 YAML 路徑")
    parser.add_argument(
        "--skip-generation", action="store_true", help="只量檢索層指標，不呼叫 LLM（不想燒額度時用）"
    )
    parser.add_argument("--limit", type=int, help="只跑前 N 題，用於快速煙霧測試")
    parser.add_argument("--category", type=str, help="只跑指定 category 的題目（例如 policy、personal）")
    parser.add_argument("--save-answers", type=Path, help="把每題的問題、期望要點、實際回答寫成文字檔")
    args = parser.parse_args()

    passed = asyncio.run(_main_async(args))
    sys.exit(0 if passed else 1)


if __name__ == "__main__":
    main()
