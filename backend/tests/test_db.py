import pytest

from app.core.db import TABLES, Database, init_schema
from tests.conftest import db_settings


async def test_schema_creates_all_tables(sql):
    rows = sql.all("SELECT table_name AS t FROM information_schema.tables WHERE table_schema = DATABASE()")
    assert set(TABLES) <= {r["t"] for r in rows}
    assert "review_items" in {r["t"] for r in rows}


async def test_schema_creates_knowledge_base_tables(sql):
    rows = sql.all("SELECT table_name AS t FROM information_schema.tables WHERE table_schema = DATABASE()")
    assert {"knowledge_bases", "kb_documents", "kb_chunks"} <= {r["t"] for r in rows}
    # 重复执行幂等，且不清掉已有数据
    sql.execute("INSERT INTO knowledge_bases (kb_id, user_id, name) VALUES ('kb_x', 1, '甲')")
    db = await Database.connect(db_settings())
    try:
        await init_schema(db)
    finally:
        await db.close()
    assert sql.one("SELECT name FROM knowledge_bases WHERE kb_id = 'kb_x'")["name"] == "甲"


async def test_init_schema_is_idempotent(sql):
    db = await Database.connect(db_settings())
    try:
        await init_schema(db)
        await init_schema(db)
    finally:
        await db.close()


async def test_transaction_commits_and_rolls_back(sql):
    db = await Database.connect(db_settings())
    try:
        async with db.transaction() as cur:
            await cur.execute("INSERT INTO users (openid, nickname) VALUES ('o-commit', '甲')")
        with pytest.raises(RuntimeError):
            async with db.transaction() as cur:
                await cur.execute("INSERT INTO users (openid, nickname) VALUES ('o-rollback', '乙')")
                raise RuntimeError("boom")
    finally:
        await db.close()
    assert [r["openid"] for r in sql.all("SELECT openid FROM users")] == ["o-commit"]


async def test_connection_uses_utc_and_utf8mb4(sql):
    db = await Database.connect(db_settings())
    try:
        async with db.transaction() as cur:
            await cur.execute("SELECT @@session.time_zone AS tz")
            assert (await cur.fetchone())["tz"] == "+00:00"
            await cur.execute("INSERT INTO users (openid, nickname) VALUES ('o-emoji', '鱼皮🐟')")
    finally:
        await db.close()
    assert sql.one("SELECT nickname FROM users")["nickname"] == "鱼皮🐟"


def test_user_tables_have_expected_unique_keys(sql):
    def uniques(table: str) -> set[str]:
        rows = sql.all(
            "SELECT index_name, GROUP_CONCAT(column_name ORDER BY seq_in_index) AS cols "
            "FROM information_schema.statistics WHERE table_schema = DATABASE() AND table_name = %s "
            "AND non_unique = 0 AND index_name <> 'PRIMARY' GROUP BY index_name",
            (table,),
        )
        return {r["cols"] for r in rows}

    assert uniques("users") == {"openid"}
    assert uniques("quiz_sessions") == {"quiz_id"}
    # 同一用户同一题库只记一次，防止重复结算经验
    assert uniques("answer_records") == {"user_id,quiz_id"}
    assert uniques("reports") == {"user_id,quiz_id"}
    # 错题身份：question_id 只在一话内唯一
    assert uniques("review_items") == {"user_id,quiz_id,question_id"}
    assert uniques("knowledge_bases") == {"kb_id"}
    assert uniques("kb_documents") == {"document_id"}
    assert uniques("kb_chunks") == set()

