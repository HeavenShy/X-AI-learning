from fastapi import APIRouter, Depends

from app.api.deps import get_report_service
from app.models.common import ApiResponse, ok
from app.models.report import Report, ReportGenerateRequest
from app.services.report_service import ReportService

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/generate", response_model=ApiResponse[Report])
async def generate(
    req: ReportGenerateRequest, service: ReportService = Depends(get_report_service)
) -> ApiResponse[Report]:
    return ok(await service.generate(req))
