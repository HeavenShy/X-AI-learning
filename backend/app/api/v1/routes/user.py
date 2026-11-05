from fastapi import APIRouter, Depends, Query

from app.api.deps import get_user_service, get_wechat_auth, require_history_service
from app.core.auth import require_user_id
from app.models.common import ApiResponse, ok
from app.models.user import HistoryPage, LoginRequest, LoginResponse, Profile, ProfileUpdate, QuizDetail
from app.services.history_service import HistoryService
from app.services.user_service import UserService
from app.services.wechat_auth import WeChatAuthClient

router = APIRouter(prefix="/user", tags=["user"])


@router.post("/login", response_model=ApiResponse[LoginResponse])
async def login(
    req: LoginRequest,
    service: UserService = Depends(get_user_service),
    wechat: WeChatAuthClient = Depends(get_wechat_auth),
) -> ApiResponse[LoginResponse]:
    return ok(await service.login(req.code, wechat))


@router.get("/profile", response_model=ApiResponse[Profile])
async def get_profile(
    user_id: int = Depends(require_user_id), service: UserService = Depends(get_user_service)
) -> ApiResponse[Profile]:
    return ok(await service.profile(user_id))


@router.put("/profile", response_model=ApiResponse[Profile])
async def update_profile(
    req: ProfileUpdate, user_id: int = Depends(require_user_id), service: UserService = Depends(get_user_service)
) -> ApiResponse[Profile]:
    return ok(await service.update_profile(user_id, req))


@router.get("/quizzes", response_model=ApiResponse[HistoryPage])
async def list_quizzes(
    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=50),
    user_id: int = Depends(require_user_id),
    history: HistoryService = Depends(require_history_service),
) -> ApiResponse[HistoryPage]:
    return ok(await history.list_quizzes(user_id, page=page, page_size=page_size))


@router.get("/quizzes/{quiz_id}", response_model=ApiResponse[QuizDetail])
async def quiz_detail(
    quiz_id: str, user_id: int = Depends(require_user_id), history: HistoryService = Depends(require_history_service)
) -> ApiResponse[QuizDetail]:
    return ok(await history.detail(user_id, quiz_id))
