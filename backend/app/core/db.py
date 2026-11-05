"""MySQL 连接池（aiomysql）与表结构初始化。不用 ORM，SQL 集中在 app/repositories。"""

import logging
import warnings
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

import aiomysql

from app.core.config import Settings

logger = logging.getLogger(__name__)

SCHEMA_FILE = Path(__file__).resolve().parent.parent / "resources" / "schema.sql"
TABLES = ("users", "quiz_sessions", "answer_records", "reports", "review_items")


class Database:
    def __init__(self, pool: aiomysql.Pool):
        self._pool = pool

    @classmethod
    async def connect(cls, settings: Settings) -> "Database":
        pool = await aiomysql.create_pool(
            minsize=settings.mysql_pool_min,
            maxsize=settings.mysql_pool_max,
            host=settings.mysql_host,
            port=settings.mysql_port,
            user=settings.mysql_user,
            password=settings.mysql_password,
            db=settings.mysql_database,
            charset="utf8mb4",
            autocommit=False,
            # 库里统一存 UTC；CURRENT_TIMESTAMP 也按 UTC 写入
            init_command="SET time_zone = '+00:00'",
            # MySQL 默认 8 小时断开空闲连接，提前回收
            pool_recycle=3600,
            connect_timeout=5,
        )
        return cls(pool)

    @asynccontextmanager
    async def transaction(self) -> AsyncIterator[aiomysql.DictCursor]:
        """一个事务：正常退出提交，异常回滚。游标返回 dict 行。"""
        async with self._pool.acquire() as conn:
            await conn.begin()
            try:
                async with conn.cursor(aiomysql.DictCursor) as cur:
                    yield cur
                await conn.commit()
            except BaseException:
                await conn.rollback()
                raise

    async def close(self) -> None:
        self._pool.close()
        await self._pool.wait_closed()


def schema_statements() -> list[str]:
    lines = [ln for ln in SCHEMA_FILE.read_text(encoding="utf-8").splitlines() if not ln.lstrip().startswith("--")]
    return [s.strip() for s in "\n".join(lines).split(";") if s.strip()]


async def init_schema(db: Database) -> None:
    with warnings.catch_warnings():
        # CREATE TABLE IF NOT EXISTS 在表已存在时会带一条 MySQL Note（被 PyMySQL 转成 Warning）
        warnings.filterwarnings("ignore", message=r".*already exists")
        async with db.transaction() as cur:
            for stmt in schema_statements():
                await cur.execute(stmt)
    logger.info("database schema ready")
