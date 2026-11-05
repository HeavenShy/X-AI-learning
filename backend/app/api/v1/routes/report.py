import logging

from fastapi import APIRouter, Depends

from app.api.deps import get_history_service, get_report_service
from app.core.auth import optional_user_id
from app.models.common import ApiResponse, ok
from app.models.report import Report, ReportGenerateRequest
from app.services.history_service import HistoryService
from app.services.report_service import ReportService
from app.services.scoring_service import score

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/report", tags=["report"])


@router.post("/generate", response_model=ApiResponse[Report])
async def generate(
    req: ReportGenerateRequest,
    service: ReportService = Depends(get_report_service),
    user_id: int | None = Depends(optional_user_id),
    history: HistoryService | None = Depends(get_history_service),
) -> ApiResponse[Report]:
    """登录用户且题库是他自己出的：用服务端存档的题目判题，先落库答题记录并结算经验，再生成 AI 复盘。
    这样 AI 复盘失败时，成绩和经验也不会丢；重试只补报告，不重复结算。"""
    if user_id is None or history is None:
        return ok(await service.generate(req))

    stored = await history.owned_questions(user_id, req.quiz_id)
    if stored is None:
        return ok(await service.generate(req))

    req = req.model_copy(update={"questions": stored})
    summary = score(req.questions, req.answer_records)
    await history.save_answers(user_id, req.quiz_id, summary)
    report = await service.generate(req, summary)
    await history.save_report(user_id, req.quiz_id, report)
    return ok(report)
