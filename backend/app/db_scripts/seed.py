"""載入種子資料：業務資料表全部清空後重新載入，確保可重複執行（見 SPEC.md §4.11）。

種子資料的所有日期一律相對於 DATE '2026-08-24'（虛擬時鐘的重置起點），不使用
CURRENT_DATE（見 docs/PITFALLS.md E2）。目前只涵蓋部門／使用者／場地／國定假日等
靜態參考資料；出勤／請假／加班的示範資料要等對應批次把業務函式建好後，
由本腳本呼叫那些函式算出符合規則的時刻再插入，不得寫死時刻字面值（見 docs/PITFALLS.md E1）。
"""

import asyncio
import sys
from pathlib import Path

import asyncpg

# Windows 主控台預設編碼不是 UTF-8，繁體中文的 print() 輸出會變成亂碼。
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.config.database import prepare_dsn  # noqa: E402
from app.config.settings import app_settings  # noqa: E402
from app.config.tables import BUSINESS_TABLES  # noqa: E402

SEED_DIR = Path(__file__).resolve().parents[3] / "db" / "seed"


async def apply_seed(conn) -> dict[str, int]:
    """在既有連線上把業務資料還原成種子狀態，回傳各表筆數。

    CLI（`npm run db:seed`）、展示資料重置 API 與測試的每測試重置 fixture 共用
    這一份定義——「種子狀態」只能有一個說法，否則測試綠燈不代表展示環境正確。
    """
    await conn.execute(f"TRUNCATE {', '.join(BUSINESS_TABLES)} RESTART IDENTITY CASCADE")

    for sql_file in sorted(SEED_DIR.glob("*.sql")):
        await conn.execute(sql_file.read_text(encoding="utf-8"))

    return {table: await conn.fetchval(f"SELECT count(*) FROM {table}") for table in BUSINESS_TABLES}


async def run_seed(dsn: str | None = None) -> None:
    target_dsn = dsn or app_settings.DATABASE_URL
    base_dsn, needs_ssl = prepare_dsn(target_dsn)
    conn = await asyncpg.connect(dsn=base_dsn, ssl=True if needs_ssl else None)
    try:
        counts = await apply_seed(conn)
        print("種子資料筆數：", counts)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_seed())
