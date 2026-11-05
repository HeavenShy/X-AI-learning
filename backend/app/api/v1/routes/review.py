from fastapi import APIRouter, Depends

from app.api.deps import require_review_service
from app.core.auth import require_user_id
from app.models.common import ApiResponse, ok
from app.models.review import MistakeList, ReviewAnswerRequest, ReviewAnswerResult
from app.services.review_service import ReviewService

router = APIRouter(prefix="/review", tags=["review"])


@router.get("/mistakes", response_model=ApiResponse[MistakeList])
async def list_mistakes(
    user_id: int = Depends(require_user_id), service: ReviewService = Depends(require_review_service)
) -> ApiResponse[MistakeList]:
    return ok(await service.list_mistakes(user_id))


@router.post("/answer", response_model=ApiResponse[ReviewAnswerResult])
async def answer(
    req: ReviewAnswerRequest,
    user_id: int = Depends(require_user_id),
    service: ReviewService = Depends(require_review_service),
) -> ApiResponse[ReviewAnswerResult]:
    return ok(await service.answer(user_id, req))
