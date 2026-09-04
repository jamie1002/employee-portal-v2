"""asyncpg 連線池管理。

- **SSL 自動偵測**：本機 Docker（host 為 localhost/127.0.0.1）不需要 SSL；
  雲端 Neon 等代管服務需要。依 DATABASE_URL 的 host 自動判斷，不靠額外的環境變數旗標。
  DSN 的 query string（如 Neon 連線字串附帶的 `sslmode=require`、`channel_binding=require`）
  一律捨棄，改用 asyncpg 自己的 `ssl` 參數表達，避免 asyncpg 不認得的 libpq 專用參數出錯。
- **NUMERIC 型別解碼成字串**：asyncpg 預設把 NUMERIC 解成 Decimal，但前端顯示與測試斷言
  都依賴 "8.00" 這種固定小數位字串格式，不是 float 或 Decimal（見 docs/PITFALLS.md A6）。
"""

from urllib.parse import urlsplit

import asyncpg

_pool: asyncpg.Pool | None = None


def prepare_dsn(dsn: str) -> tuple[str, bool]:
    """回傳 (去除 query string 的 DSN, 是否需要 SSL)。"""
    base_dsn = dsn.split("?", 1)[0]
    host = urlsplit(base_dsn).hostname or ""
    is_local = host in ("localhost", "127.0.0.1")
    return base_dsn, not is_local


async def _init_connection(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "numeric",
        schema="pg_catalog",
        encoder=str,
        decoder=str,
        format="text",
    )


async def create_pool(dsn: str, min_size: int = 2, max_size: int = 10) -> asyncpg.Pool:
    base_dsn, needs_ssl = prepare_dsn(dsn)
    return await asyncpg.create_pool(
        dsn=base_dsn,
        ssl=True if needs_ssl else None,
        min_size=min_size,
        max_size=max_size,
        init=_init_connection,
    )


def get_pool() -> asyncpg.Pool:
    if _pool is None:
        raise RuntimeError("連線池尚未初始化，請確認 app 啟動流程已呼叫 init_pool()。")
    return _pool


async def init_pool(dsn: str) -> None:
    global _pool
    _pool = await create_pool(dsn)


def set_pool(pool: asyncpg.Pool) -> None:
    """供測試 fixture 注入獨立於 app 生命週期的連線池。"""
    global _pool
    _pool = pool


async def close_pool() -> None:
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None
