import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_history_service, get_quiz_service
from app.core.auth import optional_user_id
from app.models.common import ApiResponse, ok
from app.models.quiz import Quiz, QuizGenerateRequest
from app.services.history_service import HistoryService
from app.services.quiz_service import QuizService

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/generate", response_model=ApiResponse[Quiz])
async def generate(
    req: QuizGenerateRequest,
    service: QuizService = Depends(get_quiz_service),
    user_id: int | None = Depends(optional_user_id),
    history: HistoryService | None = Depends(get_history_service),
) -> ApiResponse[Quiz]:
    quiz = await service.generate(req)
    if user_id is not None and history is not None:
        try:
            await history.save_quiz(user_id, quiz, req.difficulty)
        except Exception:  # noqa: BLE001 —— 落库失败不影响本次闯关，只是之后看不到这条历史
            logger.exception("save quiz %s for user %s failed", quiz.quiz_id, user_id)
    return ok(quiz)
