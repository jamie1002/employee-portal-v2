"""migrate + seed 的組合入口，對應 `npm run db:reset`。"""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from app.db_scripts.migrate import run_migrations  # noqa: E402
from app.db_scripts.seed import run_seed  # noqa: E402


async def run_reset() -> None:
    await run_migrations()
    await run_seed()


if __name__ == "__main__":
    asyncio.run(run_reset())
