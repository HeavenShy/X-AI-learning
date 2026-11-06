"""学习数据与知识树的 SQL：只读已完结的话（answer_records）。函数都接收事务游标（DictCursor）。"""

import json
from datetime import datetime

from aiomysql import DictCursor


async def list_finished(cur: DictCursor, user_id: int, since: datetime | None = None) -> list[dict]:
    """该用户已完结的每一话（含题目与判题结果），按完结时间从新到旧；since 为 UTC 起点（含）。"""
    where, args = "a.user_id = %s", [user_id]
    if since is not None:
        where += " AND a.created_at >= %s"
        args.append(since)
    await cur.execute(
        "SELECT a.quiz_id, q.title, q.topic, q.user_input, q.questions_json, a.records_json, "
        "a.correct_count, a.total_questions, a.total_duration_ms, a.created_at "
        "FROM answer_records a "
        "JOIN quiz_sessions q ON q.quiz_id = a.quiz_id AND q.user_id = a.user_id "
        f"WHERE {where} ORDER BY a.created_at DESC, a.id DESC",
        tuple(args),
    )
    rows = list(await cur.fetchall())
    for row in rows:
        row["questions"] = json.loads(row.pop("questions_json"))
        row["results"] = json.loads(row.pop("records_json"))
    return rows


async def count_topics(cur: DictCursor, user_id: int) -> int:
    """已完结的话涉及几个主题；没有主题的旧数据合并算作一个“其他”。"""
    await cur.execute(
        "SELECT COUNT(DISTINCT CASE WHEN q.topic = '' THEN '其他' ELSE q.topic END) AS n "
        "FROM answer_records a "
        "JOIN quiz_sessions q ON q.quiz_id = a.quiz_id AND q.user_id = a.user_id "
        "WHERE a.user_id = %s",
        (user_id,),
    )
    return int((await cur.fetchone())["n"])


async def get_insight(cur: DictCursor, user_id: int, range_key: str) -> dict | None:
    await cur.execute(
        "SELECT data_hash, insight FROM stats_insights WHERE user_id = %s AND range_key = %s",
        (user_id, range_key),
    )
    return await cur.fetchone()


async def save_insight(cur: DictCursor, user_id: int, range_key: str, data_hash: str, insight: str) -> None:
    await cur.execute(
        "INSERT INTO stats_insights (user_id, range_key, data_hash, insight) VALUES (%s, %s, %s, %s) AS new "
        "ON DUPLICATE KEY UPDATE data_hash = new.data_hash, insight = new.insight",
        (user_id, range_key, data_hash, insight),
    )
