"""闯关记录：题库、答题记录、报告落库，经验结算，历史查询。

结算规则（与前端 core/level.ts、原型一致）：每答对一题 +10 经验、+5 金币，答错不加。
同一用户同一题库只结算一次（answer_records 上 user_id + quiz_id 唯一）。
"""

import logging
from datetime import datetime

from app.core.db import Database
from app.core.exceptions import BizError, ErrorCode
from app.models.quiz import Question, Quiz
from app.models.report import AnswerRecord, Report, ScoreSummary
from app.models.user import HistoryItem, HistoryPage, QuizDetail, Reward
from app.repositories import quiz_repository as quizzes
from app.repositories import user_repository as users
from app.services.quiz_validator import DEFAULT_TOPIC
from app.utils.timeutil import iso_utc, utcnow

logger = logging.getLogger(__name__)

XP_PER_CORRECT = 10
COINS_PER_CORRECT = 5
MSG_NOT_FOUND = "没找到这一话的记录"


def source_type_of(questions: list[Question]) -> str:
    """出题响应与历史详情共用：出处带时间点即视频出题，带网址即网页出题，其余带出处即知识库出题，都没有为文本出题。"""
    sources = [s for q in questions for s in q.sources]
    if any(s.start_seconds is not None for s in sources):
        return "video"
    if any(s.url for s in sources):
        return "web"
    return "knowledge_base" if sources else "text"


def reward_for(correct_count: int) -> Reward:
    return Reward(xp=correct_count * XP_PER_CORRECT, coins=correct_count * COINS_PER_CORRECT)


class HistoryService:
    def __init__(self, db: Database):
        self._db = db

    async def save_quiz(self, user_id: int, quiz: Quiz, difficulty: str, *, now: datetime | None = None) -> None:
        async with self._db.transaction() as cur:
            await quizzes.insert_quiz(
                cur,
                quiz_id=quiz.quiz_id,
                user_id=user_id,
                title=quiz.title,
                summary=quiz.summary,
                user_input=quiz.user_input,
                difficulty=difficulty,
                topic=quiz.topic,
                questions=[q.model_dump() for q in quiz.questions],
                now=now or utcnow(),
            )

    async def owned_questions(self, user_id: int, quiz_id: str) -> list[Question] | None:
        """该用户自己出的题库的题目（服务端存档）；不是他的或不存在时返回 None，此时不落库。"""
        async with self._db.transaction() as cur:
            row = await quizzes.get_quiz(cur, quiz_id)
        if not row or row["user_id"] != user_id:
            return None
        return [Question.model_validate(q) for q in row["questions"]]

    async def save_answers(
        self, user_id: int, quiz_id: str, summary: ScoreSummary, *, now: datetime | None = None
    ) -> bool:
        """写答题记录并结算经验金币。已结算过则什么都不改，返回 False。"""
        reward = reward_for(summary.correct_count)
        async with self._db.transaction() as cur:
            inserted = await quizzes.insert_answer_record(
                cur,
                quiz_id=quiz_id,
                user_id=user_id,
                results=[r.model_dump() for r in summary.results],
                total_questions=summary.total_count,
                correct_count=summary.correct_count,
                accuracy=summary.accuracy,
                total_duration_ms=summary.total_duration_ms,
                xp=reward.xp,
                coins=reward.coins,
                now=now or utcnow(),
            )
            if inserted:
                await users.add_rewards(cur, user_id, xp=reward.xp, coins=reward.coins)
        if inserted:
            logger.info("user %s finished %s: +%d xp, +%d coins", user_id, quiz_id, reward.xp, reward.coins)
        return inserted

    async def save_report(self, user_id: int, quiz_id: str, report: Report, *, now: datetime | None = None) -> None:
        async with self._db.transaction() as cur:
            await quizzes.upsert_report(
                cur, quiz_id=quiz_id, user_id=user_id, report=report.model_dump(), now=now or utcnow()
            )

    async def list_quizzes(self, user_id: int, *, page: int, page_size: int) -> HistoryPage:
        async with self._db.transaction() as cur:
            total = await quizzes.count_history(cur, user_id)
            rows = await quizzes.list_history(cur, user_id, limit=page_size, offset=(page - 1) * page_size)
        items = [
            HistoryItem(
                quiz_id=r["quiz_id"],
                title=r["title"],
                question_count=r["total_questions"],
                correct_count=r["correct_count"],
                accuracy=int(r["accuracy"]),
                total_duration_ms=r["total_duration_ms"],
                has_report=bool(r["has_report"]),
                created_at=iso_utc(r["created_at"]),
            )
            for r in rows
        ]
        return HistoryPage(items=items, total=total, page=page, page_size=page_size)

    async def detail(self, user_id: int, quiz_id: str) -> QuizDetail:
        async with self._db.transaction() as cur:
            quiz = await quizzes.get_quiz(cur, quiz_id)
            record = await quizzes.get_answer_record(cur, user_id, quiz_id) if quiz else None
            report = await quizzes.get_report(cur, user_id, quiz_id) if record else None
            episode = await quizzes.episode_number(cur, user_id, record["created_at"]) if record else 0
        if not quiz or quiz["user_id"] != user_id or not record:
            raise BizError(ErrorCode.NOT_FOUND, MSG_NOT_FOUND)
        questions = [Question.model_validate(q) for q in quiz["questions"]]
        return QuizDetail(
            quiz=Quiz(
                quiz_id=quiz["quiz_id"],
                title=quiz["title"],
                summary=quiz["summary"],
                user_input=quiz["user_input"],
                questions=questions,
                topic=quiz["topic"] or DEFAULT_TOPIC,
                # quiz_sessions 没有来源列：任一题带出处即为知识库出题
                source_type=source_type_of(questions),
            ),
            difficulty=quiz["difficulty"],
            answer_records=[AnswerRecord.model_validate(r) for r in record["results"]],
            accuracy=int(record["accuracy"]),
            correct_count=record["correct_count"],
            total_count=record["total_questions"],
            total_duration_ms=record["total_duration_ms"],
            reward=Reward(xp=record["xp_gained"], coins=record["coins_gained"]),
            report=Report.model_validate(report) if report else None,
            episode=episode,
            created_at=iso_utc(record["created_at"]),
        )
