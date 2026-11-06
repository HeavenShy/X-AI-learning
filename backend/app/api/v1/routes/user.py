from fastapi import APIRouter, Depends, Query

from app.api.deps import get_user_service, get_wechat_auth, require_history_service, require_stats_service
from app.core.auth import require_user_id
from app.models.common import ApiResponse, ok
from app.models.user import HistoryPage, LoginRequest, LoginResponse, Profile, ProfileUpdate, QuizDetail
from app.models.stats import KnowledgeTree, LearningStats, StatsInsight, StatsRange
from app.services.history_service import HistoryService
from app.services.stats_service import StatsService
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


@router.get("/stats", response_model=ApiResponse[LearningStats])
async def learning_stats(
    range: StatsRange = Query("week"),
    user_id: int = Depends(require_user_id),
    service: StatsService = Depends(require_stats_service),
) -> ApiResponse[LearningStats]:
    return ok(await service.stats(user_id, range))


@router.get("/stats/insight", response_model=ApiResponse[StatsInsight])
async def learning_insight(
    range: StatsRange = Query("week"),
    user_id: int = Depends(require_user_id),
    service: StatsService = Depends(require_stats_service),
) -> ApiResponse[StatsInsight]:
    return ok(await service.insight(user_id, range))


@router.get("/knowledge-tree", response_model=ApiResponse[KnowledgeTree])
async def knowledge_tree(
    user_id: int = Depends(require_user_id), service: StatsService = Depends(require_stats_service)
) -> ApiResponse[KnowledgeTree]:
    return ok(await service.knowledge_tree(user_id))
