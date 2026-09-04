"""測試基礎設施。

每個 pytest process 啟動時自動 DROP SCHEMA 重建，保證每次執行都從空 schema
開始，不依賴「記得先手動清空」（見 docs/PITFALLS.md A1）。DROP 前一定要再驗證一次
資料庫名稱以 `_test` 結尾——這是砍掉整個 schema 的操作，防線要貼著危險動作寫，
不能只靠模組載入時那一次檢查。
"""

import sys
from pathlib import Path
from urllib.parse import urlsplit

import asyncpg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.config import database  # noqa: E402
from app.config.settings import app_settings  # noqa: E402
from app.db_scripts.migrate import run_migrations  # noqa: E402
from app.db_scripts.seed import apply_seed  # noqa: E402


def pytest_collection_modifyitems(items: list[pytest.Item]) -> None:
    """讓每個測試都跑在與 session 級 fixture（連線池）相同的事件迴圈。

    `asyncio_mode = auto` 在收集階段（早於這個 hook）就已經替每個測試函式加上
    一個沒有 loop_scope 的預設 "asyncio" marker（等同 function 級）。單純用
    `item.add_marker()` 疊加只會把新的 marker 排在後面，`get_closest_marker()`
    仍然會先找到那個沒有 loop_scope 的舊 marker，新的等於沒加。
    必須直接把舊的換掉，測試才會跟連線池用同一個 session 級事件迴圈——
    否則測試會在跟連線池不同的迴圈執行，asyncpg 連線因此拋出
    ConnectionDoesNotExistError（見 docs/PITFALLS.md A1 同類問題的教訓：先查證再下結論）。
    """
    session_scoped_asyncio_mark = pytest.mark.asyncio(loop_scope="session").mark
    for item in items:
        # auto 模式只會替 async def 的測試加上 "asyncio" marker，同步測試沒有；
        # 只換掉已經有的，不要替同步測試硬加一個（那會噴一堆警告）。
        if not any(marker.name == "asyncio" for marker in item.own_markers):
            continue
        item.own_markers = [m for m in item.own_markers if m.name != "asyncio"]
        item.own_markers.append(session_scoped_asyncio_mark)


def _assert_test_database(dsn: str) -> None:
    db_name = urlsplit(dsn.split("?", 1)[0]).path.lstrip("/")
    if not db_name.endswith("_test"):
        raise RuntimeError(f"拒絕對非測試資料庫執行破壞性操作：{db_name!r} 不是以 _test 結尾。")


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _reset_schema():
    dsn = app_settings.TEST_DATABASE_URL
    _assert_test_database(dsn)

    base_dsn, needs_ssl = database.prepare_dsn(dsn)
    conn = await asyncpg.connect(dsn=base_dsn, ssl=True if needs_ssl else None)
    try:
        await conn.execute("DROP SCHEMA public CASCADE; CREATE SCHEMA public;")
    finally:
        await conn.close()

    await run_migrations(dsn=dsn)
    yield


@pytest_asyncio.fixture(scope="session", autouse=True)
async def _test_pool(_reset_schema):
    dsn = app_settings.TEST_DATABASE_URL
    pool = await database.create_pool(dsn)
    database.set_pool(pool)
    yield pool
    await pool.close()


@pytest_asyncio.fixture(autouse=True)
async def reset_business_data(_test_pool):
    """每個測試前把業務資料還原成種子狀態。

    schema 重置是 session 級的（夠用且省時），但**資料**必須逐測試還原：出勤這類
    測試會在同一個虛擬營業日重複打卡，沒有隔離的話第二個測試就會撞到前一個測試
    留下的紀錄而拿到 409。沿用 `apply_seed()`——「種子狀態」只有一份定義。

    順帶把虛擬時鐘錨回種子的起點（2026-08-24 09:00，週一），讓每個測試的
    「現在」都是固定的；需要別的時刻的測試自行呼叫 set_virtual_clock()。
    """
    async with _test_pool.acquire() as conn:
        await apply_seed(conn)
    yield


@pytest_asyncio.fixture
async def db(_test_pool):
    """供測試直接下 SQL 佈置前置資料或驗證資料庫狀態。"""
    async with _test_pool.acquire() as conn:
        yield conn


@pytest_asyncio.fixture
async def pool(_test_pool):
    """供測試直接呼叫需要連線池的 service／job 函式。"""
    return _test_pool


@pytest_asyncio.fixture
async def client(_test_pool):
    from app.main import app

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac
