"""错题本接口：错题列表、重做判题、掌握与重复提交、权限、不发奖励。"""

import json

from tests.test_persistence_api import generate, submit


def finish(api, token, wrong=("q2", "q4")) -> dict:
    """完结一话。默认第 2 题（单选，答案 A）和第 4 题（多选，答案 A、C）答错，都选了 B、C。"""
    quiz = generate(api, token)
    assert submit(api, quiz, token, wrong=wrong)["code"] in (0, 4004)
    return quiz


def mistakes(api, token) -> dict:
    body = api.get("/review/mistakes", token).json()
    assert body["code"] == 0, body
    return body["data"]


def redo(api, token, quiz_id: str, question_id: str, selected: list[str], **extra) -> dict:
    payload = {"quiz_id": quiz_id, "question_id": question_id, "selected_answers": selected, **extra}
    return api.post("/review/answer", payload, token).json()


# ---------- 错题列表 ----------


def test_mistakes_require_login(api):
    assert api.get("/review/mistakes").json()["code"] == 4010
    assert api.get("/review/mistakes", "broken-token").json()["code"] == 4010


def test_empty_mistakes(api):
    token, _ = api.login()
    assert mistakes(api, token) == {"items": [], "total": 0}


def test_all_correct_quiz_has_no_mistakes(api):
    token, _ = api.login()
    finish(api, token, wrong=())
    assert mistakes(api, token)["total"] == 0


def test_wrong_questions_of_finished_quiz_appear(api):
    token, _ = api.login()
    quiz = finish(api, token)
    data = mistakes(api, token)
    assert data["total"] == 2
    assert [(i["quiz_id"], i["question"]["id"]) for i in data["items"]] == [
        (quiz["quiz_id"], "q2"),
        (quiz["quiz_id"], "q4"),
    ]
    item = data["items"][1]
    assert item == {
        "quiz_id": quiz["quiz_id"],
        "quiz_title": "RAG 入门",
        "question": quiz["questions"][3],
        "last_selected_answers": ["B", "C"],
        "wrong_count": 1,
        "first_wrong_at": item["first_wrong_at"],
    }
    assert item["first_wrong_at"].endswith("Z") and "T" in item["first_wrong_at"]


def test_mistakes_newest_quiz_first(api):
    token, _ = api.login()
    older = finish(api, token, wrong=("q1",))
    newer = finish(api, token, wrong=("q3",))
    got = [(i["quiz_id"], i["question"]["id"]) for i in mistakes(api, token)["items"]]
    assert got == [(newer["quiz_id"], "q3"), (older["quiz_id"], "q1")]


def test_unfinished_quiz_has_no_mistakes(api):
    token, _ = api.login()
    generate(api, token)
    assert mistakes(api, token)["total"] == 0


def test_cannot_see_other_users_mistakes(api):
    a, _ = api.login("a")
    finish(api, a)
    b, _ = api.login("b")
    assert mistakes(api, b) == {"items": [], "total": 0}


# ---------- 重做判题与状态 ----------


def test_correct_redo_removes_mistake(api, sql):
    token, _ = api.login()
    quiz = finish(api, token)
    body = redo(api, token, quiz["quiz_id"], "q4", ["c", " a"])
    assert body == {"code": 0, "message": "ok",
                    "data": {"is_correct": True, "correct_answers": ["A", "C"], "mastered": True}}
    data = mistakes(api, token)
    assert data["total"] == 1
    assert [i["question"]["id"] for i in data["items"]] == ["q2"]
    assert sql.one("SELECT mastered_at FROM review_items")["mastered_at"] is not None


def test_wrong_redo_increments_count_and_updates_last_answer(api, sql):
    token, _ = api.login()
    quiz = finish(api, token)
    body = redo(api, token, quiz["quiz_id"], "q2", ["d"])
    assert body["data"] == {"is_correct": False, "correct_answers": ["A"], "mastered": False}
    item = next(i for i in mistakes(api, token)["items"] if i["question"]["id"] == "q2")
    assert (item["wrong_count"], item["last_selected_answers"]) == (2, ["D"])
    redo(api, token, quiz["quiz_id"], "q2", ["B"])
    item = next(i for i in mistakes(api, token)["items"] if i["question"]["id"] == "q2")
    assert (item["wrong_count"], item["last_selected_answers"]) == (3, ["B"])
    row = sql.one("SELECT wrong_retries, last_selected_json, mastered_at FROM review_items")
    assert (row["wrong_retries"], json.loads(row["last_selected_json"]), row["mastered_at"]) == (2, ["B"], None)


def test_multiple_choice_missing_option_is_wrong(api):
    token, _ = api.login()
    quiz = finish(api, token)
    assert redo(api, token, quiz["quiz_id"], "q4", ["A"])["data"]["is_correct"] is False
    assert mistakes(api, token)["total"] == 2


def test_client_correctness_flag_is_ignored(api):
    token, _ = api.login()
    quiz = finish(api, token)
    body = redo(api, token, quiz["quiz_id"], "q4", ["B", "C"], is_correct=True, correct_answers=["B", "C"])
    assert body["data"]["is_correct"] is False


def test_empty_selection_is_wrong(api):
    token, _ = api.login()
    quiz = finish(api, token)
    assert redo(api, token, quiz["quiz_id"], "q2", [])["data"] == {
        "is_correct": False, "correct_answers": ["A"], "mastered": False
    }


def test_resubmitting_mastered_question_is_idempotent(api, sql):
    token, _ = api.login()
    quiz = finish(api, token)
    redo(api, token, quiz["quiz_id"], "q4", ["A", "C"])
    mastered_at = sql.one("SELECT mastered_at FROM review_items")["mastered_at"]
    # 网络重试：再交一次对的，或者交一次错的，都只判题不改状态
    assert redo(api, token, quiz["quiz_id"], "q4", ["A", "C"])["data"] == {
        "is_correct": True, "correct_answers": ["A", "C"], "mastered": True
    }
    assert redo(api, token, quiz["quiz_id"], "q4", ["B"])["data"] == {
        "is_correct": False, "correct_answers": ["A", "C"], "mastered": True
    }
    row = sql.one("SELECT wrong_retries, mastered_at FROM review_items")
    assert (row["wrong_retries"], row["mastered_at"]) == (0, mastered_at)
    assert [i["question"]["id"] for i in mistakes(api, token)["items"]] == ["q2"]


# ---------- 重做提交：权限与边界 ----------


def test_redo_requires_login(api, sql):
    token, _ = api.login()
    quiz = finish(api, token)
    assert redo(api, None, quiz["quiz_id"], "q4", ["A", "C"])["code"] == 4010
    assert sql.all("SELECT * FROM review_items") == []


def test_redo_of_non_mistakes_is_not_found(api, sql):
    a, _ = api.login("a")
    quiz = finish(api, a)
    unfinished = generate(api, a)
    b, _ = api.login("b")
    not_found = {"code": 4040, "message": "没找到这道错题", "data": None}
    assert redo(api, b, quiz["quiz_id"], "q4", ["A", "C"]) == not_found  # 别人的题
    assert redo(api, a, "quiz_nope", "q4", ["A", "C"]) == not_found  # 不存在的话
    assert redo(api, a, quiz["quiz_id"], "q99", ["A"]) == not_found  # 不存在的题
    assert redo(api, a, quiz["quiz_id"], "q1", ["A"]) == not_found  # 闯关时答对的题
    assert redo(api, a, unfinished["quiz_id"], "q1", ["A"]) == not_found  # 未完结的话
    assert sql.all("SELECT * FROM review_items") == []


def test_redo_validates_payload(api):
    token, _ = api.login()
    assert api.post("/review/answer", {"quiz_id": "x"}, token).json()["code"] == 4000


def test_redo_gives_no_rewards_and_keeps_history(api):
    token, _ = api.login()
    quiz = finish(api, token)
    before_profile = api.get("/user/profile", token).json()["data"]
    before_history = api.get("/user/quizzes", token).json()["data"]
    before_detail = api.get(f"/user/quizzes/{quiz['quiz_id']}", token).json()["data"]
    redo(api, token, quiz["quiz_id"], "q2", ["B"])
    redo(api, token, quiz["quiz_id"], "q2", ["A"])
    redo(api, token, quiz["quiz_id"], "q4", ["A", "C"])
    assert mistakes(api, token)["total"] == 0
    profile = api.get("/user/profile", token).json()["data"]
    assert (profile["total_xp"], profile["total_coins"]) == (before_profile["total_xp"], before_profile["total_coins"])
    assert profile == before_profile
    assert api.get("/user/quizzes", token).json()["data"] == before_history
    assert api.get(f"/user/quizzes/{quiz['quiz_id']}", token).json()["data"] == before_detail
