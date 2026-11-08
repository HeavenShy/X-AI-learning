"""视频解析任务：进程内 asyncio 任务，结果（带时间的文字稿）在内存里保留 video_job_ttl_seconds。

    上传：探测（不是视频 / 没有声音 / 超时长）→ 抽音轨切段 → 并发转写 → ready
    B 站：取信息（超时长）→ 有中文字幕用字幕；否则下载音频 → 探测 → 抽音轨切段 → 并发转写 → ready
    之后：敏感词过滤（命中的段丢弃）→ 可见字数不足判为“没识别到讲话内容”

- 每人同时只能有 1 个处理中的任务；全局并发 video_process_concurrency。
- 临时文件放 video_tmp_dir/<job_id>/，任务结束（成功或失败）即删；启动时清空目录，关闭时取消未完成的任务。
- 处理在进程内，重启即丢失（与知识库一样，后端只能单 worker 运行）；过期或重启后前端提示重新上传。
- 失败原因写进任务的 fail_reason（用户能看懂的话），不抛给接口。日志只记 job_id、来源、时长、段数和异常类型。
"""

import asyncio
import logging
import shutil
import time
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

from app.core.config import Settings
from app.core.exceptions import BizError, ErrorCode
from app.services.bilibili import BilibiliClient, BilibiliError
from app.services.transcriber import TranscribeError, Transcriber, transcribe_segments
from app.services.video_media import MESSAGES, MediaError, TimedText, extract_segments, probe
from app.utils.content_filter import ContentFilter
from app.utils.text_cleaner import clean_text, visible_length

logger = logging.getLogger(__name__)

MSG_BUSY = "上一个视频还在处理，等它处理完再传下一个。"
MSG_NO_SPEECH = "没识别到讲话内容：视频里可能只有音乐或画面。可以把要学的文字粘贴到首页出题。"
MSG_ASR_FAILED = "转文字服务暂时不可用，请稍后重试。"
MSG_NOT_ALLOWED = "这个视频涉及不适合出题的话题，换一个试试。"
MSG_INTERRUPTED = "处理被中断，请重新上传。"
# 转写出的可见字数少于这个数判为没识别到讲话
MIN_SPEECH_CHARS = 100

Status = Literal["processing", "ready", "failed"]
Stage = Literal["download", "extract", "transcribe", "done"]


def new_job_id() -> str:
    return "vj_" + uuid.uuid4().hex[:16]


@dataclass
class VideoJob:
    job_id: str
    user_id: int
    source: Literal["upload", "bilibili"]
    title: str
    url: str | None = None
    status: Status = "processing"
    stage: Stage = "download"
    duration: float = 0.0
    progress_done: int = 0
    progress_total: int = 0
    via: Literal["asr", "subtitle"] | None = None
    fail_reason: str | None = None
    segments: list[TimedText] = field(default_factory=list)
    updated_at: float = 0.0

    @property
    def char_count(self) -> int:
        return sum(visible_length(s.text) for s in self.segments)


class VideoJobManager:
    def __init__(
        self,
        settings: Settings,
        *,
        transcriber: Transcriber,
        bilibili: BilibiliClient | None,
        content_filter: ContentFilter,
        clock=time.monotonic,
    ):
        self._settings = settings
        self._transcriber = transcriber
        self._bilibili = bilibili
        self._filter = content_filter
        self._clock = clock
        self._jobs: dict[str, VideoJob] = {}
        self._tasks: dict[str, asyncio.Task] = {}
        self._sem = asyncio.Semaphore(max(1, settings.video_process_concurrency))
        self.tmp_dir = Path(settings.video_tmp_dir)

    # ---------- 生命周期 ----------

    def clear_tmp(self) -> None:
        """启动时清空临时目录（上次进程留下的上传文件和中间文件）。"""
        if self.tmp_dir.is_dir():
            for p in self.tmp_dir.iterdir():
                try:
                    shutil.rmtree(p) if p.is_dir() else p.unlink()
                except OSError:
                    logger.warning("remove stale video tmp %s failed", p.name)
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    async def aclose(self) -> None:
        tasks = list(self._tasks.values())
        for t in tasks:
            t.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        for obj in (self._transcriber, self._bilibili):
            if obj is not None and hasattr(obj, "aclose"):
                await obj.aclose()

    @property
    def bilibili_enabled(self) -> bool:
        return self._bilibili is not None

    # ---------- 查询 ----------

    def _purge(self) -> None:
        now = self._clock()
        ttl = self._settings.video_job_ttl_seconds
        for job_id in [j.job_id for j in self._jobs.values() if j.status != "processing" and j.updated_at + ttl < now]:
            self._jobs.pop(job_id, None)

    def get(self, user_id: int, job_id: str) -> VideoJob | None:
        self._purge()
        job = self._jobs.get(job_id)
        return job if job is not None and job.user_id == user_id else None

    def _check_idle(self, user_id: int) -> None:
        self._purge()
        if any(j.user_id == user_id and j.status == "processing" for j in self._jobs.values()):
            raise BizError(ErrorCode.LIMIT_EXCEEDED, MSG_BUSY)

    def upload_path(self, suffix: str) -> Path:
        """上传文件的落盘位置（路由写完再调 start_upload）。"""
        self.tmp_dir.mkdir(parents=True, exist_ok=True)
        return self.tmp_dir / f"upload_{uuid.uuid4().hex}{suffix}"

    # ---------- 启动任务 ----------

    def _new(self, user_id: int, source: str, title: str, url: str | None = None) -> VideoJob:
        self._check_idle(user_id)
        job = VideoJob(job_id=new_job_id(), user_id=user_id, source=source, title=title, url=url)
        job.updated_at = self._clock()
        self._jobs[job.job_id] = job
        return job

    def _spawn(self, job: VideoJob, coro) -> None:
        task = asyncio.create_task(self._run(job, coro))
        self._tasks[job.job_id] = task
        task.add_done_callback(lambda _t, jid=job.job_id: self._tasks.pop(jid, None))

    def check_idle(self, user_id: int) -> None:
        """路由在接收上传前先检查，避免传完 200 MB 才被拒。"""
        self._check_idle(user_id)

    def start_upload(self, user_id: int, path: Path, filename: str) -> VideoJob:
        title = self._title_from_filename(filename)
        try:
            job = self._new(user_id, "upload", title)
        except BaseException:
            path.unlink(missing_ok=True)
            raise
        job.stage = "extract"
        self._spawn(job, self._process_upload(job, path))
        return job

    async def resolve_bilibili(self, raw: str) -> str:
        """分享文案 / 链接 / BV 号 → 规范的视频链接（b23.tv 短链在这里解析一跳）。"""
        if self._bilibili is None:
            raise BilibiliError(kind="invalid")
        return await self._bilibili.resolve(raw)

    def start_bilibili(self, user_id: int, url: str) -> VideoJob:
        if self._bilibili is None:
            raise BizError(ErrorCode.VIDEO_LINK_INVALID, "暂时不支持 B 站链接，可以把视频保存到手机后上传。")
        job = self._new(user_id, "bilibili", "B 站视频", url=url)
        self._spawn(job, self._process_bilibili(job))
        return job

    def _title_from_filename(self, filename: str) -> str:
        stem = Path(filename or "").stem
        title = " ".join(clean_text(stem.replace("<", "").replace(">", "")).split())[:60]
        if not title or self._filter.find(title):
            return "上传的视频"
        return title

    # ---------- 处理 ----------

    def _touch(self, job: VideoJob, **changes) -> None:
        for k, v in changes.items():
            setattr(job, k, v)
        job.updated_at = self._clock()

    async def _run(self, job: VideoJob, coro) -> None:
        start = time.perf_counter()
        work_dir = self.tmp_dir / job.job_id
        try:
            async with self._sem:
                segments = await coro
            self._finish(job, segments)
        except asyncio.CancelledError:
            self._touch(job, status="failed", fail_reason=MSG_INTERRUPTED)
            raise
        except MediaError as exc:
            self._touch(job, status="failed", fail_reason=exc.message)
        except BilibiliError as exc:
            self._touch(job, status="failed", fail_reason=exc.message)
        except TranscribeError as exc:
            logger.warning("video job %s transcribe failed: status=%s", job.job_id, exc.status)
            self._touch(job, status="failed", fail_reason=MSG_ASR_FAILED)
        except _JobFailed as exc:
            self._touch(job, status="failed", fail_reason=exc.message)
        except Exception as exc:  # noqa: BLE001
            logger.exception("video job %s failed: %s", job.job_id, type(exc).__name__)
            self._touch(job, status="failed", fail_reason=MESSAGES["failed"])
        finally:
            shutil.rmtree(work_dir, ignore_errors=True)
            logger.info(
                "video job %s source=%s status=%s via=%s duration=%.0fs segments=%d chars=%d %.1fs",
                job.job_id, job.source, job.status, job.via, job.duration, len(job.segments), job.char_count,
                time.perf_counter() - start,
            )

    def _check_duration(self, job: VideoJob, duration: float) -> None:
        self._touch(job, duration=duration)
        limit = self._settings.video_max_seconds
        if duration > limit + 1:
            raise _JobFailed(MESSAGES["too_long"].format(minutes=max(1, round(limit / 60))))

    async def _transcribe_file(self, job: VideoJob, path: Path) -> list[TimedText]:
        """探测 → 抽音轨切段 → 并发转写。"""
        s = self._settings
        self._touch(job, stage="extract")
        info = await asyncio.to_thread(probe, path)
        self._check_duration(job, info.duration)
        work_dir = self.tmp_dir / job.job_id / "segments"
        segments = await asyncio.to_thread(
            extract_segments, path, work_dir, duration=info.duration, segment_seconds=s.video_segment_seconds
        )
        self._touch(job, stage="transcribe", progress_done=0, progress_total=len(segments), via="asr")
        return await transcribe_segments(
            self._transcriber,
            segments,
            concurrency=s.video_transcribe_concurrency,
            on_progress=lambda n: self._touch(job, progress_done=n),
        )

    async def _process_upload(self, job: VideoJob, path: Path) -> list[TimedText]:
        work = self.tmp_dir / job.job_id
        work.mkdir(parents=True, exist_ok=True)
        moved = work / f"source{path.suffix}"
        try:
            path.replace(moved)
        except OSError:
            moved = path
        try:
            return await self._transcribe_file(job, moved)
        finally:
            moved.unlink(missing_ok=True)

    async def _process_bilibili(self, job: VideoJob) -> list[TimedText]:
        assert self._bilibili is not None and job.url
        self._touch(job, stage="download")
        info = await self._bilibili.info(job.url)
        if self._filter.find(info.title):
            raise _JobFailed(MSG_NOT_ALLOWED)
        self._touch(job, title=info.title)
        self._check_duration(job, info.duration)
        subtitles = await self._bilibili.subtitles(info)
        if subtitles:
            self._touch(job, via="subtitle", progress_total=1, progress_done=1)
            return subtitles
        audio = await self._bilibili.download_audio(job.url, self.tmp_dir / job.job_id / "download")
        return await self._transcribe_file(job, audio)

    def _finish(self, job: VideoJob, segments: list[TimedText]) -> None:
        clean = [s for s in segments if s.text and not self._filter.find(s.text)]
        if sum(visible_length(s.text) for s in clean) < MIN_SPEECH_CHARS:
            self._touch(job, status="failed", fail_reason=MSG_NO_SPEECH, segments=[])
            return
        self._touch(job, status="ready", stage="done", segments=clean)


class _JobFailed(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message
