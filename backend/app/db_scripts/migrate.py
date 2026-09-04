"""套用 db/migrations/*.sql（依檔名排序，全部重跑）。

本專案沒有 schema_migrations 版本表，每次執行都會把所有遷移檔重新套用一次，
所以每支 .sql 都必須自行保證可重複執行（見 docs/PITFALLS.md A4）。
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

MIGRATIONS_DIR = Path(__file__).resolve().parents[3] / "db" / "migrations"


async def run_migrations(dsn: str | None = None) -> None:
    target_dsn = dsn or app_settings.DATABASE_URL
    base_dsn, needs_ssl = prepare_dsn(target_dsn)
    conn = await asyncpg.connect(dsn=base_dsn, ssl=True if needs_ssl else None)
    try:
        for sql_file in sorted(MIGRATIONS_DIR.glob("*.sql")):
            print(f"套用遷移：{sql_file.name}")
            sql = sql_file.read_text(encoding="utf-8")
            await conn.execute(sql)
        print("遷移完成。")
    finally:
        await conn.close()


if __name__ == "__main__":
    asyncio.run(run_migrations())
