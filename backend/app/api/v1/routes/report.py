from fastapi import APIRouter

from app.models.common import ApiResponse, ok
from app.models.report import Report, ReportGenerateRequest
from app.services import report_service

router = APIRouter(prefix="/report", tags=["report"])


@router.post("/generate", response_model=ApiResponse[Report])
async def generate(req: ReportGenerateRequest) -> ApiResponse[Report]:
    return ok(await report_service.generate_report(req))
