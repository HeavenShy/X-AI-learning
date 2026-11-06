"""学习数据与知识树：从已完结的话（answer_records + 题目）推导统计；AI 结论按统计指纹缓存。

- 时间段按北京时间：本周从周一 0 点、本月从 1 日 0 点算起；一话按完结时间归入时间段。
- 统计与分组都是纯函数（period / build_stats / build_tree），不碰数据库就能单测。
- AI 结论：没有题不调 AI；指纹不变直接用缓存；失败、命中敏感词都返回 null，不报错。
"""

import hashlib
import json
import logging
from collections import OrderedDict
from dataclasses import dataclass
from datetime import datetime, timedelta

from app.core.db import Database
from app.llm.insight_chain import InsightGenerator
from app.models.stats import (
    KnowledgeTree,
    LearningStats,
    StatsBar,
    StatsInsight,
    StatsRange,
    TreeQuiz,
    TreeTopic,
    TypeAccuracy,
)
from app.prompts.insight_prompt import insight_prompt_variables
from app.repositories import stats_repository as stats_repo
from app.services.quiz_validator import DEFAULT_TOPIC
from app.services.scoring_service import normalize_answers, percent
from app.utils.content_filter import ContentFilter
from app.utils.text_cleaner import clean_text
from app.utils.timeutil import iso_utc, to_cn, to_utc_naive, utcnow

logger = logging.getLogger(__name__)

QUESTION_TYPES = ("single", "multiple", "judge")
WEEKDAY_LABELS = ("一", "二", "三", "四", "五", "六", "日")
ALL_RANGE_MONTHS = 6
WEAK_POINTS_MAX = 3
INSIGHT_MAX_CHARS = 80


def ms_to_minutes(ms: int) -> int:
    return (ms + 30_000) // 60_000


def _add_months(dt: datetime, months: int) -> datetime:
    """dt 必须是某月 1 日。"""
    total = dt.year * 12 + dt.month - 1 + months
    return dt.replace(year=total // 12, month=total % 12 + 1)


@dataclass(frozen=True)
class Period:
    """一个统计时间段（时间都是带时区的北京时间）。"""

    range: StatsRange
    label: str
    # 本期起点；全部时为 None
    start: datetime | None
    # 上一期起点（上周一 / 上月 1 日）；全部时为 None
    prev_start: datetime | None
    # 柱状图每格：(标签, 起点, 终点)，左闭右开
    buckets: list[tuple[str, datetime, datetime]]
    current_bucket: int

    @property
    def query_since_utc(self) -> datetime | None:
        """查库起点：本周 / 本月要连上一期一起查出来做对比。"""
        return to_utc_naive(self.prev_start) if self.prev_start else None


def period(range_: StatsRange, now_utc: datetime) -> Period:
    local = to_cn(now_utc)
    today = local.replace(hour=0, minute=0, second=0, microsecond=0)
    if range_ == "week":
        start = today - timedelta(days=today.weekday())
        end = start + timedelta(days=6)
        if start.month == end.month:
            label = f"{start.month} 月 {start.day} 日 – {end.day} 日"
        else:
            label = f"{start.month} 月 {start.day} 日 – {end.month} 月 {end.day} 日"
        current = today.weekday()
        buckets = [
            ("今天" if i == current else WEEKDAY_LABELS[i], start + timedelta(days=i), start + timedelta(days=i + 1))
            for i in range(7)
        ]
        return Period(range_, label, start, start - timedelta(days=7), buckets, current)
    if range_ == "month":
        start = today.replace(day=1)
        next_month = _add_months(start, 1)
        buckets = []
        day = start
        while day < next_month:
            end = min(day + timedelta(days=7), next_month)
            buckets.append((f"第 {len(buckets) + 1} 周", day, end))
            day = end
        return Period(range_, f"{start.month} 月", start, _add_months(start, -1), buckets, (today.day - 1) // 7)
    this_month = today.replace(day=1)
    buckets = []
    for back in range(ALL_RANGE_MONTHS - 1, -1, -1):
        m = _add_months(this_month, -back)
        buckets.append((f"{m.month} 月", m, _add_months(m, 1)))
    return Period(range_, "全部", None, None, buckets, ALL_RANGE_MONTHS - 1)


def _question_results(row: dict):
    """一话里每道题与它的判题结果（题目缺失的结果跳过）。"""
    questions = {q["id"]: q for q in row["questions"]}
    for r in row["results"]:
        q = questions.get(r["question_id"])
        if q is not None:
            yield q, r


def _is_missed(q: dict, r: dict) -> bool:
    """多选漏选：答错，且选的都是正确选项、只是没选全。"""
    if q["type"] != "multiple" or r.get("is_correct"):
        return False
    selected = set(normalize_answers(r.get("selected_answers") or []))
    return bool(selected) and selected < set(normalize_answers(q["answer"]))


def build_stats(rows: list[dict], p: Period) -> LearningStats:
    """rows：list_finished 的结果（至少覆盖本期与上一期）。"""
    def local_of(row: dict) -> datetime:
        return to_cn(row["created_at"])

    current = [r for r in rows if p.start is None or local_of(r) >= p.start]
    prev_ms = (
        sum(r["total_duration_ms"] for r in rows if p.prev_start <= local_of(r) < p.start)
        if p.prev_start is not None and p.start is not None
        else None
    )

    bucket_ms = [0] * len(p.buckets)
    for row in current:
        t = local_of(row)
        for i, (_, lo, hi) in enumerate(p.buckets):
            if lo <= t < hi:
                bucket_ms[i] += row["total_duration_ms"]
                break

    type_counts = {t: [0, 0] for t in QUESTION_TYPES}
    points: OrderedDict[str, list[int]] = OrderedDict()
    missed = 0
    for row in current:
        for q, r in _question_results(row):
            ok = bool(r.get("is_correct"))
            counts = type_counts[q["type"]]
            counts[0] += ok
            counts[1] += 1
            point = points.setdefault(q["knowledge_point"], [0, 0])
            point[0] += ok
            point[1] += 1
            missed += _is_missed(q, r)

    order = {name: i for i, name in enumerate(points)}
    weak = sorted(
        (name for name, (c, t) in points.items() if c < t),
        key=lambda name: (percent(*points[name]), -points[name][1], order[name]),
    )[:WEAK_POINTS_MAX]

    return LearningStats(
        range=p.range,
        period_label=p.label,
        total_minutes=ms_to_minutes(sum(r["total_duration_ms"] for r in current)),
        prev_minutes=ms_to_minutes(prev_ms) if prev_ms is not None else None,
        bars=[
            StatsBar(label=label, minutes=ms_to_minutes(ms), is_current=i == p.current_bucket)
            for i, ((label, _, _), ms) in enumerate(zip(p.buckets, bucket_ms))
        ],
        quiz_count=len(current),
        question_count=sum(t for _, t in type_counts.values()),
        type_accuracy=[
            TypeAccuracy(type=t, correct=c, total=n, accuracy=percent(c, n)) for t, (c, n) in type_counts.items()
        ],
        multiple_missed=missed,
        weak_points=weak,
    )


def topic_of(row: dict) -> str:
    return (row.get("topic") or "").strip() or DEFAULT_TOPIC


def build_tree(rows: list[dict]) -> KnowledgeTree:
    """rows：list_finished 的结果（完结时间新到旧）。主题按最近完结排，“其他”最后；主题内的话新到旧。"""
    groups: OrderedDict[str, list[TreeQuiz]] = OrderedDict()
    for row in rows:
        weak = list(dict.fromkeys(q["knowledge_point"] for q, r in _question_results(row) if not r.get("is_correct")))
        groups.setdefault(topic_of(row), []).append(
            TreeQuiz(
                quiz_id=row["quiz_id"],
                title=row["title"],
                user_input=row["user_input"],
                correct=row["correct_count"],
                total=row["total_questions"],
                accuracy=percent(row["correct_count"], row["total_questions"]),
                weak_points=weak,
                finished_at=iso_utc(row["created_at"]),
            )
        )
    if DEFAULT_TOPIC in groups:
        groups.move_to_end(DEFAULT_TOPIC)
    topics = []
    for name, quizzes in groups.items():
        correct = sum(q.correct for q in quizzes)
        total = sum(q.total for q in quizzes)
        topics.append(
            TreeTopic(
                topic=name,
                quiz_count=len(quizzes),
                correct=correct,
                total=total,
                accuracy=percent(correct, total),
                quizzes=quizzes,
            )
        )
    return KnowledgeTree(topic_count=len(topics), topics=topics)


def insight_hash(stats: LearningStats) -> str:
    """AI 结论的输入指纹：喂给模型的内容不变，结论就不用重写。"""
    payload = json.dumps([stats.range, insight_prompt_variables(stats)], ensure_ascii=False, sort_keys=True)
    return hashlib.sha1(payload.encode("utf-8")).hexdigest()


def clean_insight(raw: str) -> str:
    text = " ".join(clean_text(raw or "").split())
    if len(text) > INSIGHT_MAX_CHARS:
        logger.warning("insight too long (%d chars), truncated", len(text))
        text = text[:INSIGHT_MAX_CHARS]
    return text


class StatsService:
    def __init__(self, db: Database, generator: InsightGenerator, *, content_filter: ContentFilter):
        self._db = db
        self._generator = generator
        self._filter = content_filter

    async def stats(self, user_id: int, range_: StatsRange, *, now: datetime | None = None) -> LearningStats:
        p = period(range_, now or utcnow())
        async with self._db.transaction() as cur:
            rows = await stats_repo.list_finished(cur, user_id, p.query_since_utc)
        return build_stats(rows, p)

    async def knowledge_tree(self, user_id: int) -> KnowledgeTree:
        async with self._db.transaction() as cur:
            rows = await stats_repo.list_finished(cur, user_id)
        return build_tree(rows)

    async def insight(self, user_id: int, range_: StatsRange, *, now: datetime | None = None) -> StatsInsight:
        stats = await self.stats(user_id, range_, now=now)
        if stats.question_count == 0:
            return StatsInsight(insight=None)
        data_hash = insight_hash(stats)
        async with self._db.transaction() as cur:
            cached = await stats_repo.get_insight(cur, user_id, range_)
        if cached and cached["data_hash"] == data_hash:
            return StatsInsight(insight=cached["insight"])

        # LLM 调用不放在数据库事务里，免得长时间占着连接
        try:
            generated = await self._generator.generate(stats=stats)
        except Exception as exc:  # noqa: BLE001
            logger.warning("insight generation failed for user %s (%s): %r", user_id, range_, exc)
            return StatsInsight(insight=None)
        text = clean_insight(generated.insight)
        if not text:
            logger.warning("insight for user %s (%s) is empty", user_id, range_)
            return StatsInsight(insight=None)
        if hit := self._filter.find(text):
            logger.warning("insight for user %s hit sensitive word %r", user_id, hit)
            return StatsInsight(insight=None)
        async with self._db.transaction() as cur:
            await stats_repo.save_insight(cur, user_id, range_, data_hash, text)
        return StatsInsight(insight=text)
