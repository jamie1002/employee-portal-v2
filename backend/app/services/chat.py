"""問答服務：限流 → 檢索 → 空則短路 → 生成 → 組回應。上游例外一律轉 `AppError(503)`。

`ask()` 收整包 `current_user` 而不是只收 `user_id`——批 B 的個人查詢需要 `role` 與
`department_id` 做 deny-by-default 範圍限縮（見
`openspec/changes/add-policy-chat/design.md`「為批 B 鋪路」）。
"""

from __future__ import annotations

import asyncio
import time
from dataclasses import dataclass, field

import asyncpg
import structlog

from app.config.settings import app_settings
from app.services import chat_prompt, chat_tools, policy_retrieval, rate_limit
from app.services import settings as settings_service
from app.utils.errors import AppError
from app.utils.gemini import GeminiClient, GeminiUnavailable
from app.utils.timezone import get_business_date
from app.utils.virtual_clock import get_virtual_now

logger = structlog.get_logger()


@dataclass
class Source:
    source_file: str
    section_path: str
    score: float


@dataclass
class Answer:
    """`kind` 目前有兩種：`"policy"`（依檢索片段回答）與 `"fallback"`（檢索落空，
    走受限的寒暄／同理／引導路徑）。批 B 的個人資料查詢會再擴充這個分流欄位
    （見 design.md「為批 B 鋪路」）。"""

    kind: str
    text: str
    refused: bool
    sources: list[Source] = field(default_factory=list)


def _to_dict(answer: Answer) -> dict:
    return {
        "kind": answer.kind,
        "text": answer.text,
        "refused": answer.refused,
        "sources": [
            {"source_file": s.source_file, "section_path": s.section_path, "score": s.score}
            for s in answer.sources
        ],
    }


async def ask(pool: asyncpg.Pool, client: GeminiClient, current_user: dict, question: str) -> dict:
    rate_key = f"chat:{current_user['id']}"
    if not rate_limit.check_and_record(rate_key, app_settings.CHAT_RATE_LIMIT_PER_MINUTE):
        raise AppError(429, "提問太頻繁，請稍後再試。", "CHAT_RATE_LIMITED")

    started_at = time.monotonic()

    try:
        results = await policy_retrieval.retrieve(pool, client, question)
        text, tool_names = await asyncio.wait_for(
            answer_question(pool, client, current_user, question, results),
            timeout=app_settings.CHAT_TOTAL_TIMEOUT_SECONDS,
        )
    except TimeoutError as exc:
        # 整趟上限，與 GEMINI_TIMEOUT_SECONDS（單次呼叫）不同：帶工具時一次提問會有
        # 兩次呼叫，沒有這一層就會變成讓使用者等兩倍的單次逾時才看到失敗。
        logger.warning("chat_total_timeout", user_id=current_user["id"])
        raise AppError(503, "AI 助理目前無法使用，請稍後再試。", "CHAT_UNAVAILABLE") from exc
    except GeminiUnavailable as exc:
        logger.warning("chat_upstream_unavailable", user_id=current_user["id"], error=str(exc))
        raise AppError(503, "AI 助理目前無法使用，請稍後再試。", "CHAT_UNAVAILABLE") from exc
    except Exception as exc:  # noqa: BLE001 — 涵蓋資料庫層例外（例如表／extension 不存在）
        logger.warning("chat_upstream_error", user_id=current_user["id"], error=str(exc))
        raise AppError(503, "AI 助理目前無法使用，請稍後再試。", "CHAT_UNAVAILABLE") from exc

    if tool_names:
        # 有呼叫工具就是個人資料查詢。不套用政策拒答的字串比對：那組 marker 認的是
        # 「文件裡沒有」這類措辭，對「你這個月沒有遲到」這種正常答案會誤判成拒答。
        answer = Answer(kind="personal", text=text, refused=False, sources=[])
    elif not results:
        # 檢索落空又沒有呼叫工具：寒暄、情緒、或文件沒有涵蓋的問題，一律視為拒答。
        answer = Answer(kind="fallback", text=text, refused=True, sources=[])
    else:
        answer = Answer(
            kind="policy",
            text=text,
            refused=chat_prompt.is_refusal(text),
            sources=[Source(r.source_file, r.section_path, r.score) for r in results],
        )
    _log(current_user["id"], question, answer, started_at, tool_names)
    return _to_dict(answer)


async def answer_question(
    pool: asyncpg.Pool, client: GeminiClient, current_user: dict, question: str, results: list
) -> tuple[str, list[str]]:
    """依檢索結果組提示，帶工具清單回答。檢索落空與否**都帶工具**。

    09-13 以前檢索落空時直接走不帶工具的 `FALLBACK_PROMPT`，於是個人資料題能不能查，
    取決於問法碰巧像不像某份規章（「異常」查得到、「異動」查不到，見 PITFALLS I17）。
    現在兩條路徑只差在系統提示的底（有文件依據用 SYSTEM_PROMPT、沒有用受限的
    FALLBACK_PROMPT），工具清單一律相同。

    **刻意是公開函式**：`backend/eval/run_eval.py` 必須呼叫這支，檢索落空的題目也要走
    同一條路徑，否則 eval 看不到落空路徑的行為——那正是 I17 當初沒被抓到的原因之一。
    """
    if results:
        settings = await _load_settings(pool, current_user["id"])
        user_content = chat_prompt.build_user_content(results, question, settings)
    else:
        # 沒有文件片段也沒有推算需求，不必讀考勤設定；原樣送出問題即可。
        user_content = question
    return await answer_with_tools(
        pool, client, current_user, user_content, question=question, has_context=bool(results)
    )


async def answer_with_tools(
    pool: asyncpg.Pool,
    client: GeminiClient,
    current_user: dict,
    user_content: str,
    *,
    question: str,
    has_context: bool = True,
) -> tuple[str, list[str]]:
    """帶工具清單問一次；模型要求呼叫工具就執行後再問一次，取得最終文字。

    模型沒有呼叫任何工具時這裡只有一次呼叫，延遲與批 A 完全相同——**這是「一律帶工具、
    不做意圖分流」這個決策成立的前提**（design.md Decision 7）。

    `has_context=False` 代表檢索落空，系統提示改以受限的 FALLBACK_PROMPT 為底。
    """
    today = get_business_date(await get_virtual_now(), tz=app_settings.APP_TIMEZONE)
    tools = chat_tools.build_declarations(current_user)
    # 提示詞裡「能不能查團隊資料」這件事，直接讀**實際發出去的工具清單**，不另外用角色
    # 判斷一次——兩處各自判斷遲早會分歧，而分歧的後果是模型收到一份與它手上工具不符的
    # 說明（實測會讓主管被告知「你沒有權限」，即使他明明有那支工具）。
    has_team_tools = any(
        declaration.name == "get_team_attendance_summary"
        for tool in tools
        for declaration in tool.function_declarations
    )
    system_prompt = chat_prompt.build_system_prompt(
        today, has_team_tools=has_team_tools, has_context=has_context
    )

    turn = await client.generate_with_tools(system_prompt, user_content, tools)
    if not turn.calls:
        return turn.text, []

    # **結構上就只有一輪**：拿到結果後直接要文字回答，不再給模型第二次呼叫工具的機會。
    # 本批次的工具都是單步可答的，需要的資訊 current_user 裡都有。沒有這個上界時，
    # lite 模型偶爾會重複呼叫同一支工具，變成配額絞肉機而且使用者一直等不到答案。
    #
    # 同一輪內模型可以要求呼叫多支工具，但最多就是每支工具各一次——再多必然是重複，
    # 執行它們只是白白多打幾次資料庫。
    max_calls = len(tools[0].function_declarations)
    calls = turn.calls[:max_calls]
    results = [
        (
            call.name,
            await chat_tools.execute(pool, current_user, call.name, call.args, question=question),
        )
        for call in calls
    ]
    # 第二輪才附加「工具數字不加但書」那段規則。放在第一輪會讓政策問答的推算但書
    # 整片消失（77 題 eval 實測從 7/7 掉到 1/7），見 chat_prompt.TOOL_RESULT_RULES。
    text = await client.continue_with_tool_results(
        chat_prompt.build_system_prompt(
            today, has_team_tools=has_team_tools, with_tool_results=True, has_context=has_context
        ),
        tools,
        turn,
        results,
    )
    return text, [call.name for call in calls]


async def _load_settings(pool: asyncpg.Pool, user_id: int) -> dict | None:
    """讀取系統目前生效的考勤設定供推算使用。

    刻意不讓這裡的失敗影響問答本身：拿不到設定時回 `None`，`format_settings()`
    會在 prompt 裡明講「這次沒有即時設定」，模型仍能依文件片段回答（只是要提醒
    使用者以系統顯示為準）。為了一個輔助性的參考值讓整個問答回 503 並不划算。"""
    try:
        return await settings_service.get_settings(pool)
    except Exception as exc:  # noqa: BLE001
        logger.warning("chat_settings_unavailable", user_id=user_id, error=str(exc))
        return None


def _log(
    user_id: int, question: str, answer: Answer, started_at: float, tool_names: list[str] | None = None
) -> None:
    """不把提問全文寫進 log——只記 user_id、問題長度、命中數、是否拒答、耗時
    （見 design.md 風險 15：log 隱私）。

    批 B 只多記**工具名稱**。工具的參數含同事姓名、回傳含出勤明細，兩者一律不進 log：
    這是一個公開展示站，任何訪客都能登入操作，把個人出勤散佈到日誌系統風險太高。
    """
    logger.info(
        "chat_answered",
        user_id=user_id,
        question_length=len(question),
        source_count=len(answer.sources),
        refused=answer.refused,
        tools=tool_names or [],
        elapsed_ms=round((time.monotonic() - started_at) * 1000),
    )
