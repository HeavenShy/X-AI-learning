"""学习数据 / 知识树的纯函数：时间段、分桶、题型正确率、漏选、薄弱知识点、主题分组（离线）。"""

from datetime import datetime, timedelta

from app.models.stats import LearningStats
from app.services.quiz_validator import normalize_topic
from app.services.stats_service import build_stats, build_tree, clean_insight, insight_hash, period

# 北京时间 2026-11-05（周四）14:00
NOW = datetime(2026, 11, 5, 6, 0)


def cn(y, mo, d, h=12, mi=0) -> datetime:
    """北京时间 → 库里的 naive UTC。"""
    return datetime(y, mo, d, h, mi) - timedelta(hours=8)


def q(qid: str, type_: str = "single", kp: str = "知识点", answer=("A",)) -> dict:
    return {"id": qid, "type": type_, "knowledge_point": kp, "answer": list(answer)}


def r(qid: str, ok: bool, selected=("A",)) -> dict:
    return {"question_id": qid, "is_correct": ok, "selected_answers": list(selected), "duration_ms": 1000}


def row(at: datetime, *, ms: int = 60_000, questions=None, results=None, topic="理财", quiz_id=None, title="一话"):
    questions = questions if questions is not None else [q("q1")]
    results = results if results is not None else [r("q1", True)]
    correct = sum(1 for x in results if x["is_correct"])
    return {
        "quiz_id": quiz_id or f"quiz_{at.isoformat()}",
        "title": title,
        "topic": topic,
        "user_input": "我想学理财",
        "questions": questions,
        "results": results,
        "correct_count": correct,
        "total_questions": len(results),
        "total_duration_ms": ms,
        "created_at": at,
    }


# ---------- 时间段 ----------


def test_week_period_buckets_monday_to_sunday():
    p = period("week", NOW)
    assert p.label == "11 月 2 日 – 8 日"
    assert [b[0] for b in p.buckets] == ["一", "二", "三", "今天", "五", "六", "日"]
    assert p.current_bucket == 3
    assert p.query_since_utc == cn(2026, 10, 26, 0)


def test_week_label_across_months():
    assert period("week", cn(2026, 11, 1)).label == "10 月 26 日 – 11 月 1 日"


def test_month_period_has_week_buckets():
    p = period("month", NOW)
    assert p.label == "11 月"
    assert [b[0] for b in p.buckets] == ["第 1 周", "第 2 周", "第 3 周", "第 4 周", "第 5 周"]
    assert p.current_bucket == 0
    assert p.query_since_utc == cn(2026, 10, 1, 0)


def test_february_has_four_week_buckets():
    assert len(period("month", cn(2026, 2, 10)).buckets) == 4


def test_all_period_has_last_six_months():
    p = period("all", cn(2026, 3, 10))
    assert [b[0] for b in p.buckets] == ["10 月", "11 月", "12 月", "1 月", "2 月", "3 月"]
    assert p.current_bucket == 5
    assert p.query_since_utc is None


# ---------- 时长 ----------


def test_week_minutes_per_day_and_previous_week():
    rows = [
        row(cn(2026, 11, 5), ms=12 * 60_000),
        row(cn(2026, 11, 2), ms=8 * 60_000),
        row(cn(2026, 10, 30), ms=34 * 60_000),  # 上周五
    ]
    s = build_stats(rows, period("week", NOW))
    assert [b.minutes for b in s.bars] == [8, 0, 0, 12, 0, 0, 0]
    assert [b.is_current for b in s.bars].index(True) == 3
    assert s.total_minutes == 20
    assert s.prev_minutes == 34
    assert s.quiz_count == 2


def test_beijing_midnight_counts_into_new_week():
    # 北京时间周一 00:30 = UTC 周日 16:30
    rows = [row(cn(2026, 11, 2, 0, 30), ms=5 * 60_000)]
    s = build_stats(rows, period("week", NOW))
    assert s.bars[0].minutes == 5
    assert s.prev_minutes == 0


def test_all_range_has_no_previous_and_counts_older_than_six_months():
    rows = [row(cn(2026, 11, 3), ms=60_000), row(cn(2025, 1, 3), ms=120_000)]
    s = build_stats(rows, period("all", NOW))
    assert s.prev_minutes is None
    assert s.total_minutes == 3
    assert sum(b.minutes for b in s.bars) == 1


# ---------- 题型与知识点 ----------


def test_type_accuracy_and_multiple_missed():
    questions = [
        q("q1", "single", "费率"),
        q("q2", "multiple", "定投优势", answer=("A", "C")),
        q("q3", "multiple", "定投优势", answer=("A", "C")),
        q("q4", "judge", "复利"),
    ]
    results = [
        r("q1", True),
        r("q2", False, ("A",)),  # 漏选
        r("q3", False, ("A", "B")),  # 选错，不算漏选
        r("q4", False, ("B",)),
    ]
    s = build_stats([row(cn(2026, 11, 4), questions=questions, results=results)], period("week", NOW))
    by_type = {t.type: (t.correct, t.total, t.accuracy) for t in s.type_accuracy}
    assert by_type == {"single": (1, 1, 100), "multiple": (0, 2, 0), "judge": (0, 1, 0)}
    assert s.question_count == 4
    assert s.multiple_missed == 1
    # 只取有答错的知识点，正确率低的在前；同为 0% 时题多的在前
    assert s.weak_points == ["定投优势", "复利"]


def test_unanswered_multiple_is_not_missed():
    questions = [q("q1", "multiple", answer=("A", "C"))]
    s = build_stats([row(cn(2026, 11, 4), questions=questions, results=[r("q1", False, ())])], period("week", NOW))
    assert s.multiple_missed == 0


def test_weak_points_capped_at_three():
    questions = [q(f"q{i}", kp=f"点{i}") for i in range(5)]
    results = [r(f"q{i}", False, ("B",)) for i in range(5)]
    s = build_stats([row(cn(2026, 11, 4), questions=questions, results=results)], period("week", NOW))
    assert s.weak_points == ["点0", "点1", "点2"]


def test_previous_period_rows_not_in_type_stats():
    s = build_stats([row(cn(2026, 10, 28))], period("week", NOW))
    assert s.question_count == 0
    assert s.quiz_count == 0
    assert all(t.total == 0 and t.accuracy == 0 for t in s.type_accuracy)


def test_missing_question_is_skipped():
    s = build_stats([row(cn(2026, 11, 4), questions=[], results=[r("q9", True)])], period("week", NOW))
    assert s.question_count == 0


# ---------- 知识树 ----------


def test_tree_groups_by_topic_newest_first_and_other_last():
    rows = [
        row(cn(2026, 11, 5), topic="", quiz_id="old"),
        row(cn(2026, 11, 4), topic="AI 技术", quiz_id="ai"),
        row(cn(2026, 11, 3), topic="理财", quiz_id="f2"),
        row(cn(2026, 11, 2), topic="理财", quiz_id="f1"),
        row(cn(2026, 11, 1), topic="其他", quiz_id="other"),
    ]
    tree = build_tree(rows)
    assert [t.topic for t in tree.topics] == ["AI 技术", "理财", "其他"]
    assert tree.topic_count == 3
    assert [q.quiz_id for q in tree.topics[1].quizzes] == ["f2", "f1"]
    assert [q.quiz_id for q in tree.topics[2].quizzes] == ["old", "other"]


def test_tree_topic_accuracy_sums_questions():
    full = [q(f"q{i}") for i in range(5)]
    rows = [
        row(cn(2026, 11, 3), questions=full, results=[r(f"q{i}", True) for i in range(5)]),
        row(cn(2026, 11, 2), questions=full, results=[r(f"q{i}", i < 2) for i in range(5)]),
    ]
    topic = build_tree(rows).topics[0]
    assert (topic.correct, topic.total, topic.accuracy, topic.quiz_count) == (7, 10, 70, 2)
    assert topic.quizzes[1].accuracy == 40


def test_tree_weak_points_are_wrong_knowledge_points_in_order():
    questions = [q("q1", kp="申购费率"), q("q2", kp="复利"), q("q3", kp="申购费率")]
    results = [r("q1", False, ("B",)), r("q2", True), r("q3", False, ("B",))]
    quiz = build_tree([row(cn(2026, 11, 3), questions=questions, results=results)]).topics[0].quizzes[0]
    assert quiz.weak_points == ["申购费率"]
    assert quiz.finished_at == "2026-11-03T04:00:00Z"


def test_empty_tree():
    tree = build_tree([])
    assert (tree.topic_count, tree.topics) == (0, [])


# ---------- 主题清洗、结论 ----------


def test_normalize_topic():
    assert normalize_topic(" AI  技术 ") == "AI 技术"
    assert normalize_topic("“理财”") == "理财"
    assert normalize_topic("") == "其他"
    assert normalize_topic(None) == "其他"
    assert normalize_topic("一二三四五六七八九十") == "一二三四五六七八"


def _stats(**kw) -> LearningStats:
    return build_stats([row(cn(2026, 11, 4), **kw)], period("week", NOW))


def test_insight_hash_changes_only_with_prompt_input():
    a = _stats()
    assert insight_hash(a) == insight_hash(_stats())
    assert insight_hash(a) != insight_hash(_stats(ms=10 * 60_000))
    # 同样的数据，换一个时间段也要重新生成
    assert insight_hash(a) != insight_hash(build_stats([row(cn(2026, 11, 4))], period("month", NOW)))


def test_clean_insight():
    assert clean_insight("  多选题错得多\n\n下次逐个判断 ") == "多选题错得多 下次逐个判断"
    assert len(clean_insight("字" * 200)) == 80
