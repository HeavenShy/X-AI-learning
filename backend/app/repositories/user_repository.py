"""users 表与用户统计的 SQL。函数都接收事务游标（DictCursor），由服务层控制事务边界。"""

from datetime import datetime

from aiomysql import DictCursor

_USER_COLS = "id, openid, nickname, avatar_url, total_xp, total_coins"


async def upsert_by_openid(cur: DictCursor, openid: str, default_nickname: str) -> dict:
    """首次登录自动注册；已存在则原样返回（不覆盖用户改过的昵称）。"""
    await cur.execute(
        "INSERT INTO users (openid, nickname) VALUES (%s, %s) ON DUPLICATE KEY UPDATE openid = openid",
        (openid, default_nickname),
    )
    await cur.execute(f"SELECT {_USER_COLS} FROM users WHERE openid = %s", (openid,))
    return await cur.fetchone()


async def get_by_id(cur: DictCursor, user_id: int) -> dict | None:
    await cur.execute(f"SELECT {_USER_COLS} FROM users WHERE id = %s", (user_id,))
    return await cur.fetchone()


async def update_profile(cur: DictCursor, user_id: int, *, nickname: str | None, avatar_url: str | None) -> None:
    sets, args = [], []
    if nickname is not None:
        sets.append("nickname = %s")
        args.append(nickname)
    if avatar_url is not None:
        sets.append("avatar_url = %s")
        args.append(avatar_url)
    if not sets:
        return
    await cur.execute(f"UPDATE users SET {', '.join(sets)} WHERE id = %s", (*args, user_id))


async def add_rewards(cur: DictCursor, user_id: int, *, xp: int, coins: int) -> None:
    await cur.execute(
        "UPDATE users SET total_xp = total_xp + %s, total_coins = total_coins + %s WHERE id = %s",
        (xp, coins, user_id),
    )


async def stats(cur: DictCursor, user_id: int, week_start: datetime) -> dict:
    await cur.execute(
        "SELECT COUNT(*) AS quiz_count, "
        "COALESCE(SUM(correct_count), 0) AS correct_count, "
        "COALESCE(SUM(total_questions), 0) AS question_count, "
        "COALESCE(SUM(CASE WHEN created_at >= %s THEN total_duration_ms ELSE 0 END), 0) AS week_ms "
        "FROM answer_records WHERE user_id = %s",
        (week_start, user_id),
    )
    row = await cur.fetchone()
    return {k: int(v) for k, v in row.items()}
