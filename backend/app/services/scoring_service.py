"""统计与评分：服务端重新判题，计算正确率、用时、每个知识点的掌握度。"""

from typing import Literal

from app.core.exceptions import BizError, ErrorCode
from app.models.quiz import Question
from app.models.report import AnswerRecord, KnowledgeMastery, QuestionResult, ScoreSummary

MASTERED_THRESHOLD = 80
WEAK_THRESHOLD = 60


def percent(correct: int, total: int) -> int:
    """四舍五入到整数百分比（half-up）。"""
    if total <= 0:
        return 0
    return (correct * 200 + total) // (total * 2)


def classify_mastery(accuracy: int) -> Literal["mastered", "normal", "weak"]:
    if accuracy >= MASTERED_THRESHOLD:
        return "mastered"
    if accuracy < WEAK_THRESHOLD:
        return "weak"
    return "normal"


def _normalize(keys: list[str]) -> list[str]:
    return sorted({k.strip().upper() for k in keys if k.strip()})


def score(questions: list[Question], records: list[AnswerRecord]) -> ScoreSummary:
    ids = {q.id for q in questions}
    by_id: dict[str, AnswerRecord] = {}
    for r in records:
        if r.question_id not in ids:
            raise BizError(ErrorCode.INVALID_PARAMS, f"答题记录与题目不匹配：{r.question_id}")
        if r.question_id in by_id:
            raise BizError(ErrorCode.INVALID_PARAMS, f"答题记录重复：{r.question_id}")
        by_id[r.question_id] = r

    results: list[QuestionResult] = []
    kp_stats: dict[str, list[int]] = {}  # point -> [correct, total]，dict 保持首次出现顺序
    for q in questions:
        r = by_id.get(q.id)
        selected = _normalize(r.selected_answers) if r else []
        correct = bool(selected) and selected == _normalize(q.answer)
        results.append(
            QuestionResult(
                question_id=q.id, selected_answers=selected, is_correct=correct, duration_ms=r.duration_ms if r else 0
            )
        )
        stat = kp_stats.setdefault(q.knowledge_point, [0, 0])
        stat[0] += int(correct)
        stat[1] += 1

    mastery = [
        KnowledgeMastery(point=p, correct=c, total=t, accuracy=percent(c, t)) for p, (c, t) in kp_stats.items()
    ]
    correct_count = sum(r.is_correct for r in results)
    return ScoreSummary(
        total_count=len(questions),
        correct_count=correct_count,
        accuracy=percent(correct_count, len(questions)),
        total_duration_ms=sum(r.duration_ms for r in results),
        results=results,
        knowledge_mastery=mastery,
        mastered_points=[m.point for m in mastery if classify_mastery(m.accuracy) == "mastered"],
        weak_points=[m.point for m in mastery if classify_mastery(m.accuracy) == "weak"],
    )
