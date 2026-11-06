"""quiz_sessions / answer_records / reports 的 SQL。函数都接收事务游标（DictCursor）。"""

import json
from datetime import datetime

from aiomysql import DictCursor


def _dumps(value) -> str:
    return json.dumps(value, ensure_ascii=False)


async def insert_quiz(
    cur: DictCursor,
    *,
    quiz_id: str,
    user_id: int,
    title: str,
    summary: str,
    user_input: str,
    difficulty: str,
    questions: list[dict],
    now: datetime,
    topic: str = "",
) -> None:
    await cur.execute(
        "INSERT INTO quiz_sessions (quiz_id, user_id, title, summary, user_input, difficulty, topic, question_count, "
        "questions_json, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        (quiz_id, user_id, title, summary, user_input, difficulty, topic, len(questions), _dumps(questions), now),
    )


async def get_quiz(cur: DictCursor, quiz_id: str) -> dict | None:
    await cur.execute(
        "SELECT quiz_id, user_id, title, summary, user_input, difficulty, topic, questions_json, created_at "
        "FROM quiz_sessions WHERE quiz_id = %s",
        (quiz_id,),
    )
    row = await cur.fetchone()
    if row:
        row["questions"] = json.loads(row.pop("questions_json"))
    return row


async def insert_answer_record(
    cur: DictCursor,
    *,
    quiz_id: str,
    user_id: int,
    results: list[dict],
    total_questions: int,
    correct_count: int,
    accuracy: int,
    total_duration_ms: int,
    xp: int,
    coins: int,
    now: datetime,
) -> bool:
    """同一用户同一题库只记一次。返回 True 表示本次新写入（需要结算奖励）。"""
    await cur.execute(
        "INSERT INTO answer_records (quiz_id, user_id, records_json, total_questions, correct_count, accuracy, "
        "total_duration_ms, xp_gained, coins_gained, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
        "ON DUPLICATE KEY UPDATE id = id",
        (quiz_id, user_id, _dumps(results), total_questions, correct_count, accuracy, total_duration_ms, xp, coins, now),
    )
    return cur.rowcount == 1


async def get_answer_record(cur: DictCursor, user_id: int, quiz_id: str) -> dict | None:
    await cur.execute(
        "SELECT records_json, total_questions, correct_count, accuracy, total_duration_ms, xp_gained, coins_gained, "
        "created_at FROM answer_records WHERE user_id = %s AND quiz_id = %s",
        (user_id, quiz_id),
    )
    row = await cur.fetchone()
    if row:
        row["results"] = json.loads(row.pop("records_json"))
    return row


async def episode_number(cur: DictCursor, user_id: int, finished_at: datetime) -> int:
    """这是该用户完结的第几话（按完结时间）。"""
    await cur.execute(
        "SELECT COUNT(*) AS n FROM answer_records WHERE user_id = %s AND created_at <= %s", (user_id, finished_at)
    )
    return int((await cur.fetchone())["n"])


async def upsert_report(cur: DictCursor, *, quiz_id: str, user_id: int, report: dict, now: datetime) -> None:
    await cur.execute(
        "INSERT INTO reports (quiz_id, user_id, report_json, created_at) VALUES (%s, %s, %s, %s) AS new "
        "ON DUPLICATE KEY UPDATE report_json = new.report_json",
        (quiz_id, user_id, _dumps(report), now),
    )


async def get_report(cur: DictCursor, user_id: int, quiz_id: str) -> dict | None:
    await cur.execute("SELECT report_json FROM reports WHERE user_id = %s AND quiz_id = %s", (user_id, quiz_id))
    row = await cur.fetchone()
    return json.loads(row["report_json"]) if row else None


async def count_history(cur: DictCursor, user_id: int) -> int:
    await cur.execute("SELECT COUNT(*) AS n FROM answer_records WHERE user_id = %s", (user_id,))
    return int((await cur.fetchone())["n"])


async def list_history(cur: DictCursor, user_id: int, *, limit: int, offset: int) -> list[dict]:
    await cur.execute(
        "SELECT a.quiz_id, q.title, a.total_questions, a.correct_count, a.accuracy, a.total_duration_ms, "
        "a.created_at, (r.id IS NOT NULL) AS has_report "
        "FROM answer_records a "
        "JOIN quiz_sessions q ON q.quiz_id = a.quiz_id "
        "LEFT JOIN reports r ON r.user_id = a.user_id AND r.quiz_id = a.quiz_id "
        "WHERE a.user_id = %s ORDER BY a.created_at DESC, a.id DESC LIMIT %s OFFSET %s",
        (user_id, limit, offset),
    )
    return list(await cur.fetchall())
