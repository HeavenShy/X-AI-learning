"""错题合并逻辑（离线）：merge_mistakes 不碰数据库。"""

import logging
from datetime import datetime

from app.services.review_service import merge_mistakes
from tests.report_factories import questions


def source(quiz_id: str, wrong: dict[str, list[str]], *, finished: datetime, count: int = 5, title: str = "RAG 入门"):
    """一条答题记录：wrong 里的题判为答错（值为当时选的选项），其余答对。"""
    qs = [q.model_dump() for q in questions(count)]
    results = [
        {
            "question_id": q["id"],
            "selected_answers": wrong.get(q["id"], q["answer"]),
            "is_correct": q["id"] not in wrong,
            "duration_ms": 3000,
        }
        for q in qs
    ]
    return {"quiz_id": quiz_id, "title": title, "questions": qs, "results": results, "created_at": finished}


def state(quiz_id: str, qid: str, *, retries: int = 0, last=None, mastered=None) -> dict:
    return {"quiz_id": quiz_id, "question_id": qid, "wrong_retries": retries, "last_selected": last,
            "mastered_at": mastered}


T1 = datetime(2026, 11, 1, 2, 3, 4)
T2 = datetime(2026, 11, 2, 2, 3, 4)


def keys(mistakes) -> list[tuple[str, str]]:
    return [(m.quiz_id, m.question.id) for m in mistakes]


def test_only_wrong_questions_are_mistakes():
    got = merge_mistakes([source("quiz_a", {"q2": ["B"], "q4": ["B", "C"]}, finished=T1)], [])
    assert keys(got) == [("quiz_a", "q2"), ("quiz_a", "q4")]
    m = got[1]
    assert m.quiz_title == "RAG 入门"
    assert m.question.type == "multiple"
    assert m.question.answer == ["A", "C"]
    assert m.first_wrong_at == "2026-11-01T02:03:04Z"


def test_all_correct_quiz_has_no_mistakes():
    assert merge_mistakes([source("quiz_a", {}, finished=T1)], []) == []


def test_unanswered_question_counts_as_mistake():
    got = merge_mistakes([source("quiz_a", {"q3": []}, finished=T1)], [])
    assert keys(got) == [("quiz_a", "q3")]
    assert got[0].last_selected_answers == []


def test_mastered_items_are_removed():
    src = source("quiz_a", {"q2": ["B"], "q4": ["B"]}, finished=T1)
    got = merge_mistakes([src], [state("quiz_a", "q2", mastered=T2)])
    assert keys(got) == [("quiz_a", "q4")]


def test_wrong_count_is_one_plus_retries():
    src = source("quiz_a", {"q2": ["B"], "q4": ["B"]}, finished=T1)
    got = merge_mistakes([src], [state("quiz_a", "q4", retries=2, last=["A"])])
    assert [m.wrong_count for m in got] == [1, 3]


def test_last_selected_prefers_latest_retry_then_quiz_answer():
    src = source("quiz_a", {"q2": ["B"], "q4": ["B", "C"]}, finished=T1)
    # q2：只在闯关时答错 → 用闯关时的选项；q4：重做答错过 → 用最近一次重做的选项
    # 只有 review_items 行但没重做答错过（last 为 None）时也退回闯关选项
    got = merge_mistakes([src], [state("quiz_a", "q4", retries=1, last=["A", "D"]), state("quiz_a", "q2")])
    assert [m.last_selected_answers for m in got] == [["B"], ["A", "D"]]
    assert [m.wrong_count for m in got] == [1, 2]


def test_order_newest_quiz_first_and_question_order_within_quiz():
    # 记录的结果顺序与题目顺序不一致时，话内仍按题目原顺序
    newer = source("quiz_new", {"q5": ["A"], "q1": ["B"]}, finished=T2)
    newer["results"].reverse()
    older = source("quiz_old", {"q3": ["A"]}, finished=T1)
    got = merge_mistakes([newer, older], [])
    assert keys(got) == [("quiz_new", "q1"), ("quiz_new", "q5"), ("quiz_old", "q3")]


def test_state_is_scoped_to_quiz():
    # question_id 只在一话内唯一：别的话的同号题已掌握，不影响这一话
    a = source("quiz_a", {"q2": ["B"]}, finished=T2)
    b = source("quiz_b", {"q2": ["B"]}, finished=T1)
    got = merge_mistakes([a, b], [state("quiz_b", "q2", mastered=T2)])
    assert keys(got) == [("quiz_a", "q2")]


def test_missing_question_is_skipped_with_warning(caplog):
    src = source("quiz_a", {"q2": ["B"], "q4": ["B"]}, finished=T1)
    src["questions"] = [q for q in src["questions"] if q["id"] != "q2"]
    with caplog.at_level(logging.WARNING, logger="app.services.review_service"):
        got = merge_mistakes([src], [])
    assert keys(got) == [("quiz_a", "q4")]
    assert "quiz_a/q2" in caplog.text
