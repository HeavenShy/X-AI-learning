"""用户接口：登录、档案、更新昵称（真实测试库）。"""

from datetime import datetime, timedelta

import pytest

from app.core.auth import decode_token
from app.utils.timeutil import utcnow
from tests.conftest import db_settings


# ---------- 登录 ----------

def test_first_login_registers_user(api, sql):
    resp = api.client.post("/api/v1/user/login", json={"code": "abc"})
    body = resp.json()
    assert body["code"] == 0
    user = body["data"]["user"]
    assert user == {"id": user["id"], "nickname": "学习者", "avatar_url": "", "total_xp": 0, "total_coins": 0}
    claims = decode_token(body["data"]["token"], db_settings())
    assert claims.user_id == user["id"]
    assert claims.openid == "o-abc"
    row = sql.one("SELECT * FROM users")
    assert row["openid"] == "o-abc"
    assert row["id"] == user["id"]


def test_login_again_returns_same_user(api, sql):
    _, first = api.login("abc")
    _, second = api.login("abc")
    assert first["id"] == second["id"]
    assert sql.one("SELECT COUNT(*) AS n FROM users")["n"] == 1


def test_different_openids_are_different_users(api, sql):
    _, a = api.login("a")
    _, b = api.login("b")
    assert a["id"] != b["id"]


def test_login_keeps_existing_profile(api, sql):
    token, user = api.login("abc")
    api.put("/user/profile", {"nickname": "鱼皮同学"}, token)
    _, again = api.login("abc")
    assert again["nickname"] == "鱼皮同学"


def test_wechat_error_returns_4011(api, sql):
    resp = api.client.post("/api/v1/user/login", json={"code": "bad"})
    assert resp.json() == {"code": 4011, "message": "微信登录失败，请稍后重试", "data": None}
    assert sql.one("SELECT COUNT(*) AS n FROM users")["n"] == 0


@pytest.mark.parametrize("payload", [{}, {"code": ""}, {"code": "x" * 200}])
def test_login_validates_code(api, payload):
    assert api.client.post("/api/v1/user/login", json=payload).json()["code"] == 4000


# ---------- 档案 ----------

def test_profile_requires_login(api):
    resp = api.get("/user/profile")
    assert resp.status_code == 401
    assert resp.json()["code"] == 4010


def test_profile_rejects_token_of_deleted_user(api, sql):
    token, _ = api.login("abc")
    sql.execute("DELETE FROM users")
    assert api.get("/user/profile", token).json()["code"] == 4010


def test_new_user_profile_is_empty(api):
    token, user = api.login()
    data = api.get("/user/profile", token).json()["data"]
    assert data == {
        "id": user["id"],
        "nickname": "学习者",
        "avatar_url": "",
        "total_xp": 0,
        "total_coins": 0,
        "quiz_count": 0,
        "correct_count": 0,
        "question_count": 0,
        "average_accuracy": 0,
        "week_minutes": 0,
        "mistake_count": 0,
        "topic_count": 0,
    }


def _insert_record(sql, user_id: int, quiz_id: str, correct: int, total: int, duration_ms: int, at: datetime):
    sql.execute(
        "INSERT INTO answer_records (quiz_id, user_id, records_json, total_questions, correct_count, accuracy, "
        "total_duration_ms, xp_gained, coins_gained, created_at) VALUES (%s,%s,'[]',%s,%s,%s,%s,0,0,%s)",
        (quiz_id, user_id, total, correct, round(correct * 100 / total, 2), duration_ms, at),
    )


def test_profile_aggregates_answer_records(api, sql):
    token, user = api.login()
    uid = user["id"]
    now = utcnow()
    _insert_record(sql, uid, "q-a", 4, 5, 192_000, now)               # 本周 3 分 12 秒
    _insert_record(sql, uid, "q-b", 3, 3, 100_000, now)               # 本周 1 分 40 秒
    _insert_record(sql, uid, "q-c", 1, 5, 600_000, now - timedelta(days=8))  # 上周，不算本周分钟
    _, other = api.login("other")
    _insert_record(sql, other["id"], "q-x", 5, 5, 999_000, now)       # 别人的记录不算
    data = api.get("/user/profile", token).json()["data"]
    assert data["quiz_count"] == 3
    assert data["correct_count"] == 8
    assert data["question_count"] == 13
    assert data["average_accuracy"] == 62  # 8 / 13 = 61.5% → 62（总正确率，按题数加权）
    assert data["week_minutes"] == 5       # 292 秒 ≈ 4.87 分钟 → 5


def test_profile_returns_xp_and_coins(api, sql):
    token, user = api.login()
    sql.execute("UPDATE users SET total_xp = 410, total_coins = 148 WHERE id = %s", (user["id"],))
    data = api.get("/user/profile", token).json()["data"]
    assert (data["total_xp"], data["total_coins"]) == (410, 148)


# ---------- 更新档案 ----------

def test_update_nickname(api, sql):
    token, _ = api.login()
    resp = api.put("/user/profile", {"nickname": "  林小满  "}, token)
    body = resp.json()
    assert body["code"] == 0
    assert body["data"]["nickname"] == "林小满"
    assert body["data"]["quiz_count"] == 0  # 返回完整档案
    assert sql.one("SELECT nickname FROM users")["nickname"] == "林小满"


def test_update_avatar_url_keeps_nickname(api, sql):
    token, _ = api.login()
    api.put("/user/profile", {"nickname": "林小满"}, token)
    data = api.put("/user/profile", {"avatar_url": "https://example.com/a.png"}, token).json()["data"]
    assert (data["nickname"], data["avatar_url"]) == ("林小满", "https://example.com/a.png")


def test_update_requires_login(api):
    assert api.put("/user/profile", {"nickname": "x"}).json()["code"] == 4010


@pytest.mark.parametrize("nickname", ["", "   ", "一二三四五六七八九十一二三四五六七八九十一"])
def test_nickname_length_is_validated(api, nickname):
    token, _ = api.login()
    assert api.put("/user/profile", {"nickname": nickname}, token).json()["code"] == 4000


def test_nickname_of_20_chars_with_emoji_is_ok(api):
    token, _ = api.login()
    nick = "鱼" * 19 + "🐟"
    assert api.put("/user/profile", {"nickname": nick}, token).json()["data"]["nickname"] == nick


def test_sensitive_nickname_returns_4012(api, sql):
    token, _ = api.login()
    resp = api.put("/user/profile", {"nickname": "我是傻 瓜蛋"}, token)
    assert resp.json() == {"code": 4012, "message": "这个昵称不太合适，换一个试试", "data": None}
    assert sql.one("SELECT nickname FROM users")["nickname"] == "学习者"


@pytest.mark.parametrize("url", ["javascript:alert(1)", "ftp://x/a.png", "http://example.com/a.png"])
def test_avatar_url_must_be_https(api, url):
    token, _ = api.login()
    assert api.put("/user/profile", {"avatar_url": url}, token).json()["code"] == 4000


def test_empty_avatar_url_clears_it(api):
    token, _ = api.login()
    api.put("/user/profile", {"avatar_url": "https://example.com/a.png"}, token)
    assert api.put("/user/profile", {"avatar_url": ""}, token).json()["data"]["avatar_url"] == ""


def test_user_api_without_database_returns_5000():
    from fastapi.testclient import TestClient

    from app.main import create_app

    with TestClient(create_app(db_settings(mysql_database=""))) as client:
        resp = client.post("/api/v1/user/login", json={"code": "abc"})
    assert resp.json()["code"] == 5000


def test_database_down_keeps_core_flow_working():
    """库连不上：用户接口返回 5000，出题照常（匿名，不落库）。"""
    from fastapi.testclient import TestClient

    from app.api.deps import get_quiz_service
    from app.main import create_app
    from app.services.quiz_service import QuizService
    from app.utils.content_filter import ContentFilter
    from tests.conftest import AlwaysQuiz

    settings = db_settings(mysql_port=1)
    app = create_app(settings)
    service = QuizService(AlwaysQuiz(), settings=settings, content_filter=ContentFilter([]))
    app.dependency_overrides[get_quiz_service] = lambda: service
    with TestClient(app) as client:
        assert app.state.db is None
        assert client.post("/api/v1/user/login", json={"code": "abc"}).json()["code"] == 5000
        resp = client.post("/api/v1/quiz/generate", json={"user_input": "复利是怎么算的"},
                           headers={"Authorization": "Bearer whatever"})
        assert resp.json()["code"] == 0
