"""视频出题接口（都要求登录）：上传视频 / 贴 B 站链接 → 后台解析（轮询状态）→ 出题。"""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, Request, UploadFile

from app.api.deps import get_history_service, require_video_jobs, require_video_quiz_service
from app.core.auth import require_user_id
from app.core.exceptions import BizError, ErrorCode
from app.models.common import ApiResponse, ok
from app.models.quiz import Quiz
from app.models.video import VideoJobOut, VideoLinkRequest, VideoQuizRequest
from app.services.bilibili import BilibiliError
from app.services.history_service import HistoryService
from app.services.video_jobs import VideoJobManager
from app.services.video_quiz_service import MSG_JOB_NOT_FOUND, VideoQuizService, to_job_out

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/video", tags=["video"])

UPLOAD_READ_BYTES = 64 * 1024
VIDEO_EXTENSIONS = {".mp4", ".mov", ".m4v", ".webm", ".mkv", ".3gp", ".avi", ".flv"}
MSG_TYPE_NOT_SUPPORTED = "只支持常见的视频文件（mp4、mov、m4v、webm、mkv、3gp 等）。"
MSG_FILE_EMPTY = "这个文件是空的，换一个视频试试。"


def msg_too_large(max_bytes: int) -> str:
    return f"视频超过 {max_bytes // (1024 * 1024)} MB 了：先剪出想学的一段，或在微信里压缩后再上传。"


@router.post("/uploads", response_model=ApiResponse[VideoJobOut])
async def upload_video(
    request: Request,
    file: UploadFile = File(...),
    # 原始文件名（小程序上传时临时路径里没有原名，前端另外传），用作视频名
    name: str | None = Form(default=None, max_length=200),
    user_id: int = Depends(require_user_id),
    jobs: VideoJobManager = Depends(require_video_jobs),
) -> ApiResponse[VideoJobOut]:
    """收下视频立即返回 processing 的任务；探测、抽音轨、转写在后台进行。"""
    settings = request.app.state.settings
    jobs.check_idle(user_id)
    filename = file.filename or ""
    suffix = Path(filename).suffix.lower()
    if suffix not in VIDEO_EXTENSIONS:
        await file.close()
        raise BizError(ErrorCode.VIDEO_TYPE_NOT_SUPPORTED, MSG_TYPE_NOT_SUPPORTED)
    path = jobs.upload_path(suffix)
    try:
        # 自己计数，不信任 Content-Length；超限立刻停止写入
        size = 0
        with open(path, "wb") as out:
            while chunk := await file.read(UPLOAD_READ_BYTES):
                size += len(chunk)
                if size > settings.video_max_upload_bytes:
                    raise BizError(ErrorCode.VIDEO_TOO_LARGE, msg_too_large(settings.video_max_upload_bytes))
                out.write(chunk)
        if size == 0:
            raise BizError(ErrorCode.VIDEO_TYPE_NOT_SUPPORTED, MSG_FILE_EMPTY)
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    finally:
        await file.close()
    job = jobs.start_upload(user_id, path, name or filename)
    logger.info("video upload %s from user %s: %d bytes", job.job_id, user_id, size)
    return ok(to_job_out(job))


@router.post("/links", response_model=ApiResponse[VideoJobOut])
async def submit_link(
    req: VideoLinkRequest,
    user_id: int = Depends(require_user_id),
    jobs: VideoJobManager = Depends(require_video_jobs),
) -> ApiResponse[VideoJobOut]:
    """B 站链接（或分享文案、BV 号）：规范化后立即返回 processing 的任务，取信息 / 字幕 / 音频在后台进行。"""
    if not jobs.bilibili_enabled:
        raise BizError(ErrorCode.VIDEO_LINK_INVALID, "暂时不支持 B 站链接，可以把视频保存到手机后上传。")
    jobs.check_idle(user_id)
    try:
        url = await jobs.resolve_bilibili(req.url)
    except BilibiliError as exc:
        raise BizError(ErrorCode.VIDEO_LINK_INVALID, exc.message) from None
    return ok(to_job_out(jobs.start_bilibili(user_id, url)))


@router.get("/jobs/{job_id}", response_model=ApiResponse[VideoJobOut])
async def get_job(
    job_id: str,
    user_id: int = Depends(require_user_id),
    jobs: VideoJobManager = Depends(require_video_jobs),
) -> ApiResponse[VideoJobOut]:
    job = jobs.get(user_id, job_id)
    if job is None:
        raise BizError(ErrorCode.NOT_FOUND, MSG_JOB_NOT_FOUND)
    return ok(to_job_out(job))


@router.post("/quiz", response_model=ApiResponse[Quiz])
async def generate(
    req: VideoQuizRequest,
    user_id: int = Depends(require_user_id),
    service: VideoQuizService = Depends(require_video_quiz_service),
    history: HistoryService | None = Depends(get_history_service),
) -> ApiResponse[Quiz]:
    quiz = await service.generate(user_id, req)
    if history is not None:
        try:
            await history.save_quiz(user_id, quiz, req.difficulty)
        except Exception:  # noqa: BLE001 —— 落库失败不影响本次闯关，只是之后看不到这条历史
            logger.exception("save video quiz %s for user %s failed", quiz.quiz_id, user_id)
    return ok(quiz)
