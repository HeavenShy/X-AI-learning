"""出题 / 报告接口落库（批次二）：登录才落库，匿名照常可用；结算幂等；服务端题目为准。"""

import json

QUIZ_REQ = {"user_input": "我想学习什么是 RAG，以及它和传统搜索有什么区别", "question_count": 5, "difficulty": "easy"}


def generate(api, token=None) -> dict:
    body = api.post("/quiz/generate", QUIZ_REQ, token).json()
    assert body["code"] == 0, body
    return body["data"]


def report_payload(quiz: dict, wrong: tuple[str, ...] = ("q4",)) -> dict:
    """默认第 4 题（多选，正确答案 A、C）答错，其余答对；每题 3 秒。"""
    records = []
    for q in quiz["questions"]:
        selected = ["B", "C"] if q["id"] in wrong else q["answer"]
        records.append({"question_id": q["id"], "selected_answers": selected, "is_correct": q["id"] not in wrong,
                        "duration_ms": 3000})
    return {"quiz_id": quiz["quiz_id"], "topic": quiz["title"], "questions": quiz["questions"], "answer_records": records}


def submit(api, quiz: dict, token=None, **kw) -> dict:
    return api.post("/report/generate", report_payload(quiz, **kw), token).json()


# ---------- 出题 ----------

def test_anonymous_generate_is_not_persisted(api, sql):
    generate(api)
    assert sql.all("SELECT * FROM quiz_sessions") == []


def test_invalid_token_generate_still_works_anonymously(api, sql):
    quiz = generate(api, token="broken-token")
    assert quiz["quiz_id"].startswith("quiz_")
    assert sql.all("SELECT * FROM quiz_sessions") == []


def test_logged_in_generate_saves_quiz_session(api, sql):
    token, user = api.login()
    quiz = generate(api, token)
    row = sql.one("SELECT * FROM quiz_sessions")
    assert row["quiz_id"] == quiz["quiz_id"]
    assert row["user_id"] == user["id"]
    assert row["title"] == quiz["title"]
    assert row["summary"] == quiz["summary"]
    assert row["user_input"] == quiz["user_input"]
    assert row["difficulty"] == "easy"
    assert row["question_count"] == 5
    assert json.loads(row["questions_json"]) == quiz["questions"]


def test_generate_response_shape_is_unchanged(api):
    token, _ = api.login()
    assert set(generate(api, token)) == {"quiz_id", "title", "summary", "source_type", "user_input", "questions"}


# ---------- 报告 ----------

def test_anonymous_report_is_not_persisted(api, sql):
    body = submit(api, generate(api))
    assert body["code"] == 0
    assert body["data"]["accuracy"] == 80
    for t in ("answer_records", "reports"):
        assert sql.all(f"SELECT * FROM {t}") == []


def test_logged_in_report_saves_answers_report_and_rewards(api, sql):
    token, user = api.login()
    quiz = generate(api, token)
    body = submit(api, quiz, token)
    assert body["code"] == 0
    rec = sql.one("SELECT * FROM answer_records")
    assert rec["user_id"] == user["id"]
    assert rec["quiz_id"] == quiz["quiz_id"]
    assert (rec["total_questions"], rec["correct_count"], float(rec["accuracy"])) == (5, 4, 80.0)
    assert rec["total_duration_ms"] == 15000
    # 每答对一题 +10 经验、+5 金币（与前端 / 原型一致）
    assert (rec["xp_gained"], rec["coins_gained"]) == (40, 20)
    results = json.loads(rec["records_json"])
    assert [r["is_correct"] for r in results] == [True, True, True, False, True]
    u = sql.one("SELECT total_xp, total_coins FROM users")
    assert (u["total_xp"], u["total_coins"]) == (40, 20)
    rep = sql.one("SELECT * FROM reports")
    assert rep["quiz_id"] == quiz["quiz_id"]
    assert json.loads(rep["report_json"]) == body["data"]


def test_report_response_shape_is_unchanged(api):
    token, _ = api.login()
    data = submit(api, generate(api, token), token)["data"]
    assert set(data) == {
        "accuracy", "correct_count", "total_count", "total_duration_ms",
        "mastered_points", "weak_points", "knowledge_mastery",
        "three_line_summary", "advice", "share_quote",
    }


def test_submitting_twice_rewards_only_once(api, sql):
    token, _ = api.login()
    quiz = generate(api, token)
    submit(api, quiz, token)
    submit(api, quiz, token)
    assert sql.one("SELECT COUNT(*) AS n FROM answer_records")["n"] == 1
    assert sql.one("SELECT COUNT(*) AS n FROM reports")["n"] == 1
    assert sql.one("SELECT total_xp FROM users")["total_xp"] == 40


def test_resubmitting_different_answers_does_not_change_first_result(api, sql):
    token, _ = api.login()
    quiz = generate(api, token)
    submit(api, quiz, token)
    submit(api, quiz, token, wrong=())  # 第二次全对：不应改写已结算的成绩和经验
    rec = sql.one("SELECT correct_count, xp_gained FROM answer_records")
    assert (rec["correct_count"], rec["xp_gained"]) == (4, 40)
    assert sql.one("SELECT total_xp FROM users")["total_xp"] == 40


def test_answers_and_rewards_saved_even_if_ai_report_fails(api, sql):
    token, _ = api.login()
    quiz = generate(api, token)
    api.report_gen.outcomes = [ValueError("a"), ValueError("b")]
    assert submit(api, quiz, token)["code"] == 4004
    assert sql.one("SELECT correct_count FROM answer_records")["correct_count"] == 4
    assert sql.one("SELECT total_xp FROM users")["total_xp"] == 40
    assert sql.all("SELECT * FROM reports") == []
    # 重试成功：补上报告，经验不重复加
    assert submit(api, quiz, token)["code"] == 0
    assert sql.one("SELECT COUNT(*) AS n FROM reports")["n"] == 1
    assert sql.one("SELECT total_xp FROM users")["total_xp"] == 40


def test_score_uses_stored_questions_not_client_copy(api, sql):
    token, _ = api.login()
    quiz = generate(api, token)
    payload = report_payload(quiz)
    # 客户端把第 4 题答案改成自己选的 B、C，企图“全对”
    payload["questions"][3]["answer"] = ["B", "C"]
    body = api.post("/report/generate", payload, token).json()
    assert body["data"]["accuracy"] == 80
    assert sql.one("SELECT correct_count FROM answer_records")["correct_count"] == 4


def test_records_not_matching_stored_questions_are_rejected(api, sql):
    token, _ = api.login()
    quiz = generate(api, token)
    payload = report_payload(quiz)
    payload["answer_records"][0]["question_id"] = "q99"
    assert api.post("/report/generate", payload, token).json()["code"] == 4000
    assert sql.all("SELECT * FROM answer_records") == []


def test_report_for_other_users_quiz_is_not_persisted(api, sql):
    owner_token, _ = api.login("owner")
    quiz = generate(api, owner_token)
    intruder_token, _ = api.login("intruder")
    assert submit(api, quiz, intruder_token)["code"] == 0
    assert sql.all("SELECT * FROM answer_records") == []
    assert sql.one("SELECT SUM(total_xp) AS xp FROM users")["xp"] == 0


def test_report_for_anonymously_generated_quiz_is_not_persisted(api, sql):
    quiz = generate(api)  # 出题时没登录，库里没有这份题库
    token, _ = api.login()
    assert submit(api, quiz, token)["code"] == 0
    assert sql.all("SELECT * FROM answer_records") == []


def test_unanswered_questions_count_as_wrong(api, sql):
    token, _ = api.login()
    quiz = generate(api, token)
    payload = report_payload(quiz, wrong=())
    payload["answer_records"] = payload["answer_records"][:3]
    body = api.post("/report/generate", payload, token).json()
    assert body["data"]["correct_count"] == 3
    assert sql.one("SELECT xp_gained FROM answer_records")["xp_gained"] == 30
