"""学习数据、AI 结论、知识树接口与“我的”页计数（真实测试库，AI 用假实现）。"""

import pytest

from app.llm.output_schemas import GeneratedInsight
from tests.conftest import Api, build_app, db_settings
from tests.test_persistence_api import generate, submit


class ScriptedInsight:
    """结论假模型：outcomes 为空时返回固定结论；元素是异常则抛出，是字符串则作为结论。"""

    def __init__(self):
        self.outcomes: list = []
        self.calls = 0

    async def generate(self, *, stats):
        self.calls += 1
        if self.outcomes:
            o = self.outcomes.pop(0)
            if isinstance(o, BaseException):
                raise o
            return GeneratedInsight(insight=o)
        return GeneratedInsight(insight=f"多选错得最多，{stats.question_count} 题里要逐个选项判断。")


@pytest.fixture
def stats_api(sql):
    from fastapi.testclient import TestClient

    from app.api.deps import get_insight_generator

    insight = ScriptedInsight()

    def before_start(app):
        app.dependency_overrides[get_insight_generator] = lambda: insight

    app, wechat, report_gen = build_app(db_settings(), before_start=before_start)
    with TestClient(app) as client:
        api = Api(client, wechat, report_gen)
        api.insight = insight
        yield api


def finish(api, token, wrong=("q4",)) -> dict:
    quiz = generate(api, token)
    assert submit(api, quiz, token, wrong=wrong)["code"] in (0, 4004)
    return quiz


def set_topic(sql, quiz: dict, topic: str) -> None:
    sql.execute("UPDATE quiz_sessions SET topic = %s WHERE quiz_id = %s", (topic, quiz["quiz_id"]))


def data(api, path: str, token: str) -> dict:
    body = api.get(path, token).json()
    assert body["code"] == 0, body
    return body["data"]


# ---------- 出题带主题 ----------


def test_generated_quiz_saves_topic(stats_api, sql):
    token, _ = stats_api.login()
    quiz = generate(stats_api, token)
    # 假模型没给主题，归为“其他”
    assert quiz["topic"] == "其他"
    assert sql.one("SELECT topic FROM quiz_sessions")["topic"] == "其他"


def test_history_detail_maps_empty_topic_to_other(stats_api, sql):
    token, _ = stats_api.login()
    quiz = finish(stats_api, token)
    set_topic(sql, quiz, "")
    assert data(stats_api, f"/user/quizzes/{quiz['quiz_id']}", token)["quiz"]["topic"] == "其他"


# ---------- 学习数据 ----------


@pytest.mark.parametrize("path", ["/user/stats", "/user/stats/insight", "/user/knowledge-tree"])
def test_require_login(stats_api, path):
    assert stats_api.get(path).json()["code"] == 4010


def test_invalid_range(stats_api):
    token, _ = stats_api.login()
    assert stats_api.get("/user/stats?range=year", token).json()["code"] == 4000


def test_empty_stats(stats_api):
    token, _ = stats_api.login()
    for range_, bars in (("week", 7), ("all", 6)):
        s = data(stats_api, f"/user/stats?range={range_}", token)
        assert s["question_count"] == 0
        assert s["total_minutes"] == 0
        assert len(s["bars"]) == bars
        assert [t["type"] for t in s["type_accuracy"]] == ["single", "multiple", "judge"]
    assert data(stats_api, "/user/stats?range=week", token)["prev_minutes"] == 0
    assert data(stats_api, "/user/stats?range=all", token)["prev_minutes"] is None


def test_stats_after_finishing_quiz(stats_api):
    token, _ = stats_api.login()
    finish(stats_api, token)  # 5 题，第 4 题（多选，答案 A、C）选了 B、C 答错，每题 3 秒
    s = data(stats_api, "/user/stats?range=week", token)
    assert s["quiz_count"] == 1
    assert s["question_count"] == 5
    by_type = {t["type"]: (t["correct"], t["total"]) for t in s["type_accuracy"]}
    assert by_type == {"single": (3, 3), "multiple": (0, 1), "judge": (1, 1)}
    assert s["multiple_missed"] == 0
    assert s["weak_points"] == ["多选知识点4"]
    assert sum(1 for b in s["bars"] if b["is_current"]) == 1


def test_stats_only_count_finished_quizzes(stats_api):
    token, _ = stats_api.login()
    generate(stats_api, token)
    assert data(stats_api, "/user/stats?range=all", token)["question_count"] == 0


def test_stats_do_not_include_other_users(stats_api):
    a, _ = stats_api.login("a")
    finish(stats_api, a)
    b, _ = stats_api.login("b")
    assert data(stats_api, "/user/stats?range=all", b)["question_count"] == 0
    assert data(stats_api, "/user/knowledge-tree", b)["topics"] == []


# ---------- AI 结论 ----------


def test_insight_without_data_does_not_call_ai(stats_api):
    token, _ = stats_api.login()
    assert data(stats_api, "/user/stats/insight?range=week", token) == {"insight": None}
    assert stats_api.insight.calls == 0


def test_insight_is_cached_until_data_changes(stats_api, sql):
    token, _ = stats_api.login()
    finish(stats_api, token)
    first = data(stats_api, "/user/stats/insight?range=week", token)["insight"]
    assert first
    assert data(stats_api, "/user/stats/insight?range=week", token)["insight"] == first
    assert stats_api.insight.calls == 1
    assert sql.one("SELECT COUNT(*) AS n FROM stats_insights")["n"] == 1

    # 换一档单独生成
    data(stats_api, "/user/stats/insight?range=all", token)
    assert stats_api.insight.calls == 2

    # 新完结一话：本周数据变了，重新生成并覆盖缓存
    finish(stats_api, token)
    again = data(stats_api, "/user/stats/insight?range=week", token)["insight"]
    assert stats_api.insight.calls == 3
    assert again != first
    assert sql.one("SELECT COUNT(*) AS n FROM stats_insights")["n"] == 2


def test_insight_failure_returns_null_and_retries_next_time(stats_api, sql):
    token, _ = stats_api.login()
    finish(stats_api, token)
    stats_api.insight.outcomes = [TimeoutError("slow")]
    assert data(stats_api, "/user/stats/insight?range=week", token) == {"insight": None}
    assert sql.one("SELECT COUNT(*) AS n FROM stats_insights")["n"] == 0
    assert data(stats_api, "/user/stats/insight?range=week", token)["insight"]
    assert stats_api.insight.calls == 2


@pytest.mark.parametrize("text", ["   ", "多选题像个傻瓜蛋一样难"])
def test_empty_or_sensitive_insight_is_hidden(stats_api, sql, text):
    token, _ = stats_api.login()
    finish(stats_api, token)
    stats_api.insight.outcomes = [text]
    assert data(stats_api, "/user/stats/insight?range=week", token) == {"insight": None}
    assert sql.one("SELECT COUNT(*) AS n FROM stats_insights")["n"] == 0


# ---------- 知识树 ----------


def test_knowledge_tree_groups_by_topic(stats_api, sql):
    token, _ = stats_api.login()
    old = finish(stats_api, token)
    set_topic(sql, old, "")  # 上线前的旧数据
    f1 = finish(stats_api, token)
    set_topic(sql, f1, "理财")
    ai = finish(stats_api, token, wrong=("q1", "q2", "q4"))
    set_topic(sql, ai, "AI 技术")
    generate(stats_api, token)  # 没完结的不出现

    tree = data(stats_api, "/user/knowledge-tree", token)
    assert tree["topic_count"] == 3
    assert [t["topic"] for t in tree["topics"]] == ["AI 技术", "理财", "其他"]
    ai_topic = tree["topics"][0]
    assert (ai_topic["correct"], ai_topic["total"], ai_topic["accuracy"]) == (2, 5, 40)
    node = ai_topic["quizzes"][0]
    assert node["quiz_id"] == ai["quiz_id"]
    assert node["weak_points"] == ["单选知识点1", "单选知识点2", "多选知识点4"]
    assert node["user_input"] == ai["user_input"]


# ---------- “我的”页计数 ----------


def test_profile_counts_mistakes_and_topics(stats_api, sql):
    token, _ = stats_api.login()
    quiz = finish(stats_api, token, wrong=("q2", "q4"))
    other = finish(stats_api, token)
    set_topic(sql, other, "理财")
    profile = data(stats_api, "/user/profile", token)
    assert profile["mistake_count"] == data(stats_api, "/review/mistakes", token)["total"] == 3
    assert profile["topic_count"] == 2

    stats_api.post("/review/answer", {"quiz_id": quiz["quiz_id"], "question_id": "q2", "selected_answers": ["A"]}, token)
    assert data(stats_api, "/user/profile", token)["mistake_count"] == 2
