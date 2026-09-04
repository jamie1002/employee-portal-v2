"""載入種子資料：業務資料表全部清空後重新載入，確保可重複執行（見 SPEC.md §4.11）。

種子資料的所有日期一律相對於 DATE '2026-08-24'（虛擬時鐘的重置起點），不使用
CURRENT_DATE（見 docs/PITFALLS.md E2）。

兩層刻意分開：
- `apply_seed()`：只載入靜態參考資料（部門／使用者／場地／國定假日／設定／
  虛擬時鐘）。CLI、展示資料重置 API、測試的每測試重置 fixture 共用這一份
  定義——這層「種子狀態」只能有一個說法，否則測試綠燈不代表展示環境正確。
- `apply_demo_seed()`：在 `apply_seed()` 之上疊加示範用業務資料（出勤／請假／
  加班／補打卡／場地預約，見 seed_business_data.py，時刻一律呼叫正式業務函式
  算出，不寫死字面值，見 docs/PITFALLS.md E1）。**只有 CLI 與展示資料重置需要
  這層**——測試的每測試重置 fixture 刻意不疊加，因為這批示範資料佔用了測試
  大量使用的錨點（例如 2026-08-24 的場地預約），混進每個測試只會製造脆弱的
  隱性耦合，業務資料表對測試而言維持乾淨可預期更重要。
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
from app.db_scripts.seed_business_data import seed_business_data  # noqa: E402

SEED_DIR = Path(__file__).resolve().parents[3] / "db" / "seed"


async def apply_seed(conn) -> dict[str, int]:
    """在既有連線上把業務資料還原成只有靜態參考資料的種子狀態，回傳各表筆數。"""
    await conn.execute(f"TRUNCATE {', '.join(BUSINESS_TABLES)} RESTART IDENTITY CASCADE")

    for sql_file in sorted(SEED_DIR.glob("*.sql")):
        await conn.execute(sql_file.read_text(encoding="utf-8"))

    return {table: await conn.fetchval(f"SELECT count(*) FROM {table}") for table in BUSINESS_TABLES}


async def apply_demo_seed(conn) -> dict[str, int]:
    """`apply_seed()` 之外疊加示範用業務資料，供 CLI 與展示資料重置使用。"""
    await apply_seed(conn)
    await seed_business_data(conn)
    return {table: await conn.fetchval(f"SELECT count(*) FROM {table}") for table in BUSINESS_TABLES}


async def run_seed(dsn: str | None = None) -> None:
    target_dsn = dsn or app_settings.DATABASE_URL
    base_dsn, needs_ssl = prepare_dsn(target_dsn)
    conn = await asyncpg.connect(dsn=base_dsn, ssl=True if needs_ssl else None)
    try:
        counts = await apply_demo_seed(conn)
        print("種子資料筆數：", counts)
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_seed())
