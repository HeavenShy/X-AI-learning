"""视频出题：取解析好的文字稿 → 按时间段筛选 → 按时间顺序拼块 → MaterialQuizEngine 出题（出处带时间点）。

    校验重点（4003）→ 任务不存在 / 不是自己的 / 已过期（4040）→ 还没处理完或失败（4053）
    → 选了时间段：只留和时间段有重叠的文字稿段，一段都没有（4054）
    → 相邻的段拼到约 kb_chunk_chars 字为一块，记起止秒数
    → MaterialQuizEngine（material_quiz.py，kind=video）：范围判断、取材料（[n] 《视频名》02:10–03:05）、
      出题、出处（start_seconds、B 站链接）

结果 source_type=video；user_input 为重点，没填为视频名。
"""

import hashlib
import logging
import time

from app.core.config import Settings
from app.core.exceptions import BizError, ErrorCode
from app.llm.web_quiz_chain import WebQuizGenerator
from app.llm.web_scope_chain import WebScopeJudge
from app.models.quiz import Quiz
from app.models.video import VideoJobOut, VideoQuizRequest
from app.services.material_quiz import Block, MaterialQuizEngine, SourceDoc
from app.services.video_jobs import VideoJob, VideoJobManager
from app.services.video_media import TimedText
from app.services.web_quiz_service import check_focus
from app.utils.content_filter import ContentFilter
from app.utils.id_generator import new_quiz_id

logger = logging.getLogger(__name__)

MSG_JOB_NOT_FOUND = "没找到这个视频的解析结果，可能已经过期了，请重新上传。"
MSG_NOT_READY = "视频还没处理完，等转文字完成再出题。"
MSG_JOB_FAILED = "这个视频没处理成功，请重新上传。"
MSG_RANGE_EMPTY = "所选的这段时间里没有识别到讲话内容，换一段试试，或者不填时间按整段视频出题。"


def to_job_out(job: VideoJob) -> VideoJobOut:
    return VideoJobOut(
        job_id=job.job_id,
        source=job.source,
        title=job.title,
        url=job.url,
        status=job.status,
        stage=job.stage,
        progress_done=job.progress_done,
        progress_total=job.progress_total,
        duration_seconds=int(round(job.duration)),
        via=job.via,
        char_count=job.char_count,
        fail_reason=job.fail_reason,
    )


def video_document_id(job: VideoJob) -> str:
    key = job.url or job.job_id
    return "video_" + hashlib.sha1(key.encode("utf-8")).hexdigest()[:12]


def select_range(segments: list[TimedText], start: int | None, end: int | None) -> list[TimedText]:
    """只留和 [start, end) 有重叠的段；都不填为全部。"""
    lo = start if start is not None else 0
    hi = end if end is not None else float("inf")
    return [s for s in segments if s.end > lo and s.start < hi]


def _block(cur: list[TimedText]) -> Block:
    return Block(
        "\n".join(c.text for c in cur), cur[0].start, cur[-1].end, parts=tuple((c.start, c.text) for c in cur)
    )


def group_blocks(segments: list[TimedText], *, chunk_chars: int) -> list[Block]:
    """按时间顺序把相邻的段拼到约 chunk_chars 字为一块（单段超长也不拆），记起止秒数和各段的起始秒数。

    出处按摘录落在哪一段取那一段的时间：转写的段是 1 分钟，字幕是一行。
    """
    blocks: list[Block] = []
    cur: list[TimedText] = []
    size = 0
    for seg in segments:
        if cur and size + len(seg.text) > chunk_chars:
            blocks.append(_block(cur))
            cur, size = [], 0
        cur.append(seg)
        size += len(seg.text)
    if cur:
        blocks.append(_block(cur))
    return blocks


class VideoQuizService:
    def __init__(
        self,
        manager: VideoJobManager,
        judge: WebScopeJudge,
        generator: WebQuizGenerator,
        *,
        settings: Settings,
        content_filter: ContentFilter,
    ):
        self._manager = manager
        self._settings = settings
        self._filter = content_filter
        self._engine = MaterialQuizEngine(
            judge,
            generator,
            settings=settings,
            content_filter=content_filter,
            material_max_chars=settings.video_material_max_chars,
        )

    def _ready_job(self, user_id: int, job_id: str) -> VideoJob:
        job = self._manager.get(user_id, job_id)
        if job is None:
            raise BizError(ErrorCode.NOT_FOUND, MSG_JOB_NOT_FOUND)
        if job.status == "processing":
            raise BizError(ErrorCode.VIDEO_NOT_READY, MSG_NOT_READY)
        if job.status == "failed":
            raise BizError(ErrorCode.VIDEO_NOT_READY, job.fail_reason or MSG_JOB_FAILED)
        return job

    async def generate(self, user_id: int, req: VideoQuizRequest) -> Quiz:
        start = time.perf_counter()
        focus = check_focus(req.focus, self._filter)
        job = self._ready_job(user_id, req.job_id)
        segments = select_range(job.segments, req.start_seconds, req.end_seconds)
        if not segments:
            raise BizError(ErrorCode.VIDEO_RANGE_EMPTY, MSG_RANGE_EMPTY)
        blocks = group_blocks(segments, chunk_chars=self._settings.kb_chunk_chars)
        doc = SourceDoc(
            kind="video",
            doc_id=video_document_id(job),
            title=job.title,
            site="B 站" if job.source == "bilibili" else "上传的视频",
            blocks=blocks,
            url=job.url,
        )
        result = await self._engine.generate(
            doc, focus=focus, question_count=req.question_count, difficulty=req.difficulty
        )
        logger.info(
            "video quiz %s source=%s via=%s range=%s-%s blocks=%d pieces=%d scope=%s points=%d scope_s=%.1f total_s=%.1f",
            job.job_id, job.source, job.via, req.start_seconds, req.end_seconds, len(blocks), len(result.pieces),
            result.scope.mode, len(result.scope.knowledge_points), result.scope_seconds, time.perf_counter() - start,
        )
        return Quiz(
            quiz_id=new_quiz_id(),
            user_input=focus or job.title,
            source_type="video",
            **result.content.model_dump(),
        )
