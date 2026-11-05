"""手动建表（应用启动时也会自动执行，幂等）。

用法（在 backend 目录）：python -m scripts.init_db
"""

import asyncio

from app.core.config import get_settings
from app.core.db import TABLES, Database, init_schema


async def main() -> None:
    settings = get_settings()
    if not settings.db_enabled:
        raise SystemExit("未配置 MYSQL_DATABASE")
    db = await Database.connect(settings)
    try:
        await init_schema(db)
    finally:
        await db.close()
    print(f"OK：{settings.mysql_host}:{settings.mysql_port}/{settings.mysql_database} -> {', '.join(TABLES)}")


if __name__ == "__main__":
    asyncio.run(main())
