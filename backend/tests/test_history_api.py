"""闯关历史（批次四）：列表、详情、权限。"""

import pytest

from tests.test_persistence_api import generate, submit


def finish(api, token, **kw) -> dict:
    quiz = generate(api, token)
    assert submit(api, quiz, token, **kw)["code"] in (0, 4004)
    return quiz


def test_history_requires_login(api):
    assert api.get("/user/quizzes").json()["code"] == 4010
    assert api.get("/user/quizzes/quiz_x").json()["code"] == 4010


def test_empty_history(api):
    token, _ = api.login()
    assert api.get("/user/quizzes", token).json()["data"] == {"items": [], "total": 0, "page": 1, "page_size": 10}


def test_history_lists_finished_quizzes_newest_first(api, sql):
    token, _ = api.login()
    first = finish(api, token)
    second = finish(api, token, wrong=())
    generate(api, token)  # 只出题没答完：不进历史
    data = api.get("/user/quizzes", token).json()["data"]
    assert data["total"] == 2
    assert [i["quiz_id"] for i in data["items"]] == [second["quiz_id"], first["quiz_id"]]
    item = data["items"][1]
    assert item == {
        "quiz_id": first["quiz_id"],
        "title": "RAG 入门",
        "question_count": 5,
        "correct_count": 4,
        "accuracy": 80,
        "total_duration_ms": 15000,
        "has_report": True,
        "created_at": item["created_at"],
    }
    assert item["created_at"].endswith("Z") and "T" in item["created_at"]
    assert data["items"][0]["accuracy"] == 100


def test_history_only_shows_own_records(api):
    a, _ = api.login("a")
    finish(api, a)
    b, _ = api.login("b")
    assert api.get("/user/quizzes", b).json()["data"]["total"] == 0


def test_history_pagination(api):
    token, _ = api.login()
    ids = [finish(api, token)["quiz_id"] for _ in range(3)]
    data = api.get("/user/quizzes", token, params={"page": 2, "page_size": 2}).json()["data"]
    assert (data["total"], data["page"], data["page_size"]) == (3, 2, 2)
    assert [i["quiz_id"] for i in data["items"]] == [ids[0]]


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 0}, {"page_size": 51}])
def test_history_validates_paging(api, params):
    token, _ = api.login()
    assert api.get("/user/quizzes", token, params=params).json()["code"] == 4000


def test_history_marks_missing_report(api):
    token, _ = api.login()
    api.report_gen.outcomes = [ValueError("a"), ValueError("b")]
    finish(api, token)
    assert api.get("/user/quizzes", token).json()["data"]["items"][0]["has_report"] is False


def test_detail_returns_quiz_answers_reward_and_report(api):
    token, _ = api.login()
    quiz = generate(api, token)
    report = submit(api, quiz, token)["data"]
    data = api.get(f"/user/quizzes/{quiz['quiz_id']}", token).json()["data"]
    assert data["quiz"] == quiz
    assert data["difficulty"] == "easy"
    assert (data["accuracy"], data["correct_count"], data["total_count"]) == (80, 4, 5)
    assert data["total_duration_ms"] == 15000
    assert data["reward"] == {"xp": 40, "coins": 20}
    assert data["report"] == report
    rec = data["answer_records"][3]
    assert rec == {"question_id": "q4", "selected_answers": ["B", "C"], "is_correct": False, "duration_ms": 3000}
    assert data["created_at"].endswith("Z")


def test_detail_episode_counts_finished_quizzes_up_to_this_one(api):
    token, _ = api.login()
    first = finish(api, token)
    second = finish(api, token)
    other, _ = api.login("other")
    finish(api, other)
    assert api.get(f"/user/quizzes/{first['quiz_id']}", token).json()["data"]["episode"] == 1
    assert api.get(f"/user/quizzes/{second['quiz_id']}", token).json()["data"]["episode"] == 2


def test_detail_report_is_null_when_ai_failed(api):
    token, _ = api.login()
    api.report_gen.outcomes = [ValueError("a"), ValueError("b")]
    quiz = finish(api, token)
    data = api.get(f"/user/quizzes/{quiz['quiz_id']}", token).json()["data"]
    assert data["report"] is None
    assert data["accuracy"] == 80


def test_detail_of_other_users_quiz_is_not_found(api):
    a, _ = api.login("a")
    quiz = finish(api, a)
    b, _ = api.login("b")
    assert api.get(f"/user/quizzes/{quiz['quiz_id']}", b).json() == {
        "code": 4040, "message": "没找到这一话的记录", "data": None
    }


def test_detail_of_unknown_or_unfinished_quiz_is_not_found(api):
    token, _ = api.login()
    unfinished = generate(api, token)
    assert api.get("/user/quizzes/quiz_nope", token).json()["code"] == 4040
    assert api.get(f"/user/quizzes/{unfinished['quiz_id']}", token).json()["code"] == 4040


def test_profile_reflects_finished_quizzes(api):
    token, _ = api.login()
    finish(api, token)
    finish(api, token, wrong=())
    data = api.get("/user/profile", token).json()["data"]
    assert (data["quiz_count"], data["correct_count"], data["question_count"]) == (2, 9, 10)
    assert data["average_accuracy"] == 90
    assert (data["total_xp"], data["total_coins"]) == (90, 45)
    assert data["week_minutes"] == 1  # 30 秒 → 四舍五入 1 分钟


# ---------- 来源与出处 ----------

SOURCE = {"document_id": "doc_1", "document_name": "员工手册.pdf", "page": 3, "quote": "报销需在 30 天内提交。"}


def rewrite_questions(sql, quiz_id: str, change) -> None:
    import json

    row = sql.one("SELECT questions_json FROM quiz_sessions WHERE quiz_id = %s", (quiz_id,))
    questions = json.loads(row["questions_json"])
    for q in questions:
        change(q)
    sql.execute(
        "UPDATE quiz_sessions SET questions_json = %s WHERE quiz_id = %s",
        (json.dumps(questions, ensure_ascii=False), quiz_id),
    )


def test_detail_of_text_quiz_is_text_source(api):
    token, _ = api.login()
    quiz = finish(api, token)
    data = api.get(f"/user/quizzes/{quiz['quiz_id']}", token).json()["data"]
    assert data["quiz"]["source_type"] == "text"
    assert all(q["sources"] == [] for q in data["quiz"]["questions"])


def test_detail_with_sources_is_knowledge_base(api, sql):
    token, _ = api.login()
    quiz = finish(api, token)
    rewrite_questions(sql, quiz["quiz_id"], lambda q: q.update(sources=[SOURCE]))
    data = api.get(f"/user/quizzes/{quiz['quiz_id']}", token).json()["data"]
    assert data["quiz"]["source_type"] == "knowledge_base"
    assert data["quiz"]["questions"][0]["sources"] == [SOURCE]


def test_detail_restores_old_questions_without_sources(api, sql):
    token, _ = api.login()
    quiz = finish(api, token)
    # 本期之前存下的 questions_json 没有 sources 字段
    rewrite_questions(sql, quiz["quiz_id"], lambda q: q.pop("sources", None))
    data = api.get(f"/user/quizzes/{quiz['quiz_id']}", token).json()["data"]
    assert data["quiz"]["source_type"] == "text"
    assert [q["sources"] for q in data["quiz"]["questions"]] == [[]] * 5
    assert data["quiz"]["questions"][0]["stem"] == quiz["questions"][0]["stem"]
