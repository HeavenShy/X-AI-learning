"""错题本：从答题记录推导错题，重做判题，答对即掌握。

- 错题 = 已完结的话里服务端判为答错（含未作答）的题；身份是 (user_id, quiz_id, question_id)。
- review_items 只存重做状态：已掌握的剔除；答错次数 = 1 + 重做又答错的次数。
- 重做不发经验金币，不改 answer_records / reports。
"""

import logging
from datetime import datetime

from app.core.db import Database
from app.core.exceptions import BizError, ErrorCode
from app.models.quiz import Question
from app.models.review import MistakeItem, MistakeList, ReviewAnswerRequest, ReviewAnswerResult
from app.repositories import quiz_repository as quizzes
from app.repositories import review_repository as reviews
from app.services.scoring_service import is_answer_correct, normalize_answers
from app.utils.timeutil import iso_utc, utcnow

logger = logging.getLogger(__name__)

MSG_NOT_A_MISTAKE = "没找到这道错题"


def merge_mistakes(sources: list[dict], items: list[dict]) -> list[MistakeItem]:
    """把答题记录（已按完结时间新到旧）与重做状态合并成错题列表。纯函数，不碰数据库。

    sources 每项：quiz_id、title、questions（题目 dict 列表）、results（每题判题结果）、created_at。
    items 每项：quiz_id、question_id、wrong_retries、last_selected（None 表示没重做答错过）、mastered_at。
    """
    state = {(i["quiz_id"], i["question_id"]): i for i in items}
    mistakes: list[MistakeItem] = []
    for src in sources:
        questions = {q["id"]: q for q in src["questions"]}
        wrong = {r["question_id"]: r for r in src["results"] if not r.get("is_correct")}
        for qid in wrong.keys() - questions.keys():
            logger.warning("mistake %s/%s skipped: question not found in quiz", src["quiz_id"], qid)
        # 话内按题目原顺序
        for qid, q in questions.items():
            record = wrong.get(qid)
            if record is None:
                continue
            item = state.get((src["quiz_id"], qid))
            if item and item["mastered_at"] is not None:
                continue
            retries = item["wrong_retries"] if item else 0
            last = item["last_selected"] if item and item["last_selected"] is not None else record["selected_answers"]
            mistakes.append(
                MistakeItem(
                    quiz_id=src["quiz_id"],
                    quiz_title=src["title"],
                    question=Question.model_validate(q),
                    last_selected_answers=last,
                    wrong_count=1 + retries,
                    first_wrong_at=iso_utc(src["created_at"]),
                )
            )
    return mistakes


async def count_mistakes(cur, user_id: int) -> int:
    """未掌握的错题数，口径与错题列表一致（“我的”页错题本入口的红色数字）。"""
    sources = await reviews.list_wrong_sources(cur, user_id)
    items = await reviews.get_review_items(cur, user_id)
    return len(merge_mistakes(sources, items))


class ReviewService:
    def __init__(self, db: Database):
        self._db = db

    async def list_mistakes(self, user_id: int) -> MistakeList:
        async with self._db.transaction() as cur:
            sources = await reviews.list_wrong_sources(cur, user_id)
            items = await reviews.get_review_items(cur, user_id)
        mistakes = merge_mistakes(sources, items)
        return MistakeList(items=mistakes, total=len(mistakes))

    async def answer(self, user_id: int, req: ReviewAnswerRequest, *, now: datetime | None = None) -> ReviewAnswerResult:
        async with self._db.transaction() as cur:
            quiz = await quizzes.get_quiz(cur, req.quiz_id)
            record = await quizzes.get_answer_record(cur, user_id, req.quiz_id) if quiz else None
            if not quiz or quiz["user_id"] != user_id or not record:
                raise BizError(ErrorCode.NOT_FOUND, MSG_NOT_A_MISTAKE)
            result = next((r for r in record["results"] if r["question_id"] == req.question_id), None)
            raw = next((q for q in quiz["questions"] if q["id"] == req.question_id), None)
            if result is None or result.get("is_correct") or raw is None:
                raise BizError(ErrorCode.NOT_FOUND, MSG_NOT_A_MISTAKE)

            question = Question.model_validate(raw)
            correct = is_answer_correct(question, req.selected_answers)
            item = await reviews.get_review_item(cur, user_id, req.quiz_id, req.question_id)
            if item and item["mastered_at"] is not None:
                # 已掌握：照常判题，不改状态（网络重试等重复提交）
                mastered = True
            elif correct:
                await reviews.mark_mastered(cur, user_id, req.quiz_id, req.question_id, now or utcnow())
                mastered = True
            else:
                await reviews.record_wrong_retry(
                    cur, user_id, req.quiz_id, req.question_id, normalize_answers(req.selected_answers)
                )
                mastered = False
        if mastered and correct:
            logger.info("user %s mastered %s/%s", user_id, req.quiz_id, req.question_id)
        return ReviewAnswerResult(is_correct=correct, correct_answers=normalize_answers(question.answer), mastered=mastered)
