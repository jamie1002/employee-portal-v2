"""Ingest CLI 入口，對應 `npm run db:ingest`。仿 `migrate.py` 的慣例。

**這是唯一會打 embedding API 的批次作業**，刻意不併進 `db:reset`（e2e 前的例行動作，
每次跑都會呼叫 API，見 `openspec/changes/add-policy-chat/design.md` Decision 10）。
"""

import asyncio
import sys
from pathlib import Path

# Windows 主控台預設編碼不是 UTF-8，繁體中文的 print() 輸出會變成亂碼。
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config.database import create_pool  # noqa: E402
from app.config.settings import app_settings  # noqa: E402
from app.services.policy_ingest import format_summary, run_ingest  # noqa: E402
from app.utils.gemini import get_gemini_client  # noqa: E402


async def run_ingest_cli(dsn: str | None = None) -> None:
    client = get_gemini_client()  # 沒有金鑰時直接讓 GeminiUnavailable 往外拋，訊息足夠清楚
    pool = await create_pool(dsn or app_settings.DATABASE_URL)
    try:
        print("開始 ingest：切段 → 比對 content_hash → 只對變更的 chunk 呼叫 embedding API")
        summary = await run_ingest(pool, client)
        print(format_summary(summary))
    finally:
        await pool.close()


if __name__ == "__main__":
    asyncio.run(run_ingest_cli())
