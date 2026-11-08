import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_history_service, require_web_quiz_service
from app.core.auth import optional_user_id
from app.models.common import ApiResponse, ok
from app.models.quiz import Quiz
from app.models.web import WebPreview, WebPreviewRequest, WebQuizRequest
from app.services.history_service import HistoryService
from app.services.web_quiz_service import WebQuizService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/web", tags=["web"])


@router.post("/preview", response_model=ApiResponse[WebPreview])
async def preview(req: WebPreviewRequest, service: WebQuizService = Depends(require_web_quiz_service)):
    """读网页并返回标题、站点、字数，让用户确认是这篇；结果缓存，随后出题不再重复抓取。"""
    return ok(await service.preview(req.url))


@router.post("/quiz", response_model=ApiResponse[Quiz])
async def generate(
    req: WebQuizRequest,
    service: WebQuizService = Depends(require_web_quiz_service),
    user_id: int | None = Depends(optional_user_id),
    history: HistoryService | None = Depends(get_history_service),
) -> ApiResponse[Quiz]:
    quiz = await service.generate(req)
    if user_id is not None and history is not None:
        try:
            await history.save_quiz(user_id, quiz, req.difficulty)
        except Exception:  # noqa: BLE001 —— 落库失败不影响本次闯关，只是之后看不到这条历史
            logger.exception("save web quiz %s for user %s failed", quiz.quiz_id, user_id)
    return ok(quiz)
