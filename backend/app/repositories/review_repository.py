"""错题本的 SQL：错题从 answer_records 推导，review_items 只存重做状态。函数都接收事务游标（DictCursor）。"""

import json
from datetime import datetime

from aiomysql import DictCursor


def _review_row(row: dict) -> dict:
    raw = row.pop("last_selected_json")
    row["last_selected"] = json.loads(raw) if raw is not None else None
    return row


async def list_wrong_sources(cur: DictCursor, user_id: int) -> list[dict]:
    """该用户每条答题记录及其题库，按完结时间从新到旧。是否答错由服务层从 results 里判断。"""
    await cur.execute(
        "SELECT a.quiz_id, q.title, q.questions_json, a.records_json, a.created_at "
        "FROM answer_records a "
        "JOIN quiz_sessions q ON q.quiz_id = a.quiz_id AND q.user_id = a.user_id "
        "WHERE a.user_id = %s ORDER BY a.created_at DESC, a.id DESC",
        (user_id,),
    )
    rows = list(await cur.fetchall())
    for row in rows:
        row["questions"] = json.loads(row.pop("questions_json"))
        row["results"] = json.loads(row.pop("records_json"))
    return rows


async def get_review_items(cur: DictCursor, user_id: int) -> list[dict]:
    await cur.execute(
        "SELECT quiz_id, question_id, wrong_retries, last_selected_json, mastered_at "
        "FROM review_items WHERE user_id = %s",
        (user_id,),
    )
    return [_review_row(r) for r in await cur.fetchall()]


async def get_review_item(cur: DictCursor, user_id: int, quiz_id: str, question_id: str) -> dict | None:
    await cur.execute(
        "SELECT quiz_id, question_id, wrong_retries, last_selected_json, mastered_at "
        "FROM review_items WHERE user_id = %s AND quiz_id = %s AND question_id = %s FOR UPDATE",
        (user_id, quiz_id, question_id),
    )
    row = await cur.fetchone()
    return _review_row(row) if row else None


async def record_wrong_retry(
    cur: DictCursor, user_id: int, quiz_id: str, question_id: str, selected: list[str]
) -> None:
    """重做答错：次数 +1，并记下这次的选项。第一次重做时新建一行。"""
    await cur.execute(
        "INSERT INTO review_items (user_id, quiz_id, question_id, wrong_retries, last_selected_json) "
        "VALUES (%s, %s, %s, 1, %s) AS new "
        "ON DUPLICATE KEY UPDATE wrong_retries = review_items.wrong_retries + 1, "
        "last_selected_json = new.last_selected_json",
        (user_id, quiz_id, question_id, json.dumps(selected, ensure_ascii=False)),
    )


async def mark_mastered(cur: DictCursor, user_id: int, quiz_id: str, question_id: str, now: datetime) -> None:
    """重做答对：记为已掌握。已掌握的保留第一次掌握的时间。"""
    await cur.execute(
        "INSERT INTO review_items (user_id, quiz_id, question_id, mastered_at) VALUES (%s, %s, %s, %s) AS new "
        "ON DUPLICATE KEY UPDATE mastered_at = COALESCE(review_items.mastered_at, new.mastered_at)",
        (user_id, quiz_id, question_id, now),
    )
