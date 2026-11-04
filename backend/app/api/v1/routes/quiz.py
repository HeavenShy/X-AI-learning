from fastapi import APIRouter

from app.models.common import ApiResponse, ok
from app.models.quiz import Quiz, QuizGenerateRequest
from app.services import quiz_service

router = APIRouter(prefix="/quiz", tags=["quiz"])


@router.post("/generate", response_model=ApiResponse[Quiz])
async def generate(req: QuizGenerateRequest) -> ApiResponse[Quiz]:
    return ok(await quiz_service.generate_quiz(req))
