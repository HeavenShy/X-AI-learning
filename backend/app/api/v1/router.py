from fastapi import APIRouter

from app.api.v1.routes import health, quiz, report, user

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(quiz.router)
api_router.include_router(report.router)
api_router.include_router(user.router)
