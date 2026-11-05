import pytest

from app.core.exceptions import BizError, ErrorCode
from app.services.scoring_service import score
from tests.report_factories import questions, record


def all_correct(count=5):
    qs = questions(count)
    return qs, [record(q.id, list(q.answer)) for q in qs]


def test_all_correct():
    qs, recs = all_correct()
    s = score(qs, recs)
    assert (s.correct_count, s.total_count, s.accuracy) == (5, 5, 100)
    assert s.weak_points == []
    assert len(s.mastered_points) == 5


def test_server_side_judging_ignores_client_flag():
    qs, recs = all_correct(3)
    recs[0] = record("q1", ["B"], is_correct=True)  # 前端说对了，实际选错
    recs[1] = record("q2", ["C", "A"], is_correct=False)  # 多选顺序不同，实际是对的
    s = score(qs, recs)
    results = {r.question_id: r.is_correct for r in s.results}
    assert results == {"q1": False, "q2": True, "q3": True}
    assert s.correct_count == 2
    assert s.accuracy == 67


def test_multiple_choice_requires_exact_set():
    qs, recs = all_correct(3)
    recs[1] = record("q2", ["A"])  # 漏选
    assert score(qs, recs).results[1].is_correct is False
    recs[1] = record("q2", ["A", "B", "C"])  # 多选
    assert score(qs, recs).results[1].is_correct is False


def test_selected_answers_are_normalized():
    qs, recs = all_correct(3)
    recs[0] = record("q1", [" a "])
    assert score(qs, recs).results[0].is_correct is True


def test_missing_record_counts_as_wrong():
    qs, recs = all_correct(5)
    s = score(qs, recs[:4])
    assert s.correct_count == 4
    assert s.results[4].is_correct is False
    assert s.results[4].selected_answers == []


def test_durations_are_summed():
    qs = questions(3)
    recs = [record("q1", ["A"], 1000), record("q2", ["A", "C"], 2500), record("q3", ["B"], 500)]
    assert score(qs, recs).total_duration_ms == 4000


def test_knowledge_mastery_groups_by_point_in_order():
    qs = questions(5)
    # 让第 4 题（多选）和第 1 题同一知识点
    qs[3] = qs[3].model_copy(update={"knowledge_point": qs[0].knowledge_point})
    recs = [record(q.id, list(q.answer)) for q in qs]
    recs[3] = record("q4", ["B"])
    s = score(qs, recs)
    first = s.knowledge_mastery[0]
    assert (first.point, first.correct, first.total, first.accuracy) == (qs[0].knowledge_point, 1, 2, 50)
    assert [m.point for m in s.knowledge_mastery] == [qs[0].knowledge_point, qs[1].knowledge_point, qs[2].knowledge_point, qs[4].knowledge_point]
    assert qs[0].knowledge_point in s.weak_points
    assert qs[0].knowledge_point not in s.mastered_points


def test_mastery_thresholds():
    # >=80 掌握，<60 薄弱，60–79 两边都不算
    from app.services.scoring_service import classify_mastery

    assert classify_mastery(100) == "mastered"
    assert classify_mastery(80) == "mastered"
    assert classify_mastery(79) == "normal"
    assert classify_mastery(60) == "normal"
    assert classify_mastery(59) == "weak"
    assert classify_mastery(0) == "weak"


def test_unknown_question_id_is_rejected():
    qs, recs = all_correct(3)
    recs.append(record("q99", ["A"]))
    with pytest.raises(BizError) as e:
        score(qs, recs)
    assert e.value.code == ErrorCode.INVALID_PARAMS


def test_duplicate_record_is_rejected():
    qs, recs = all_correct(3)
    recs.append(record("q1", ["A"]))
    with pytest.raises(BizError) as e:
        score(qs, recs)
    assert e.value.code == ErrorCode.INVALID_PARAMS


def test_accuracy_rounds_half_up():
    qs = questions(10)
    recs = [record(q.id, list(q.answer)) for q in qs]
    for i in range(10):
        if i >= 5:
            recs[i] = record(qs[i].id, ["Z"])
    assert score(qs, recs).accuracy == 50
