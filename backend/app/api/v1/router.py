from fastapi import APIRouter

from app.api.v1.routes import health, kb, quiz, report, review, user, video, web

api_router = APIRouter()
api_router.include_router(health.router)
api_router.include_router(quiz.router)
api_router.include_router(report.router)
api_router.include_router(user.router)
api_router.include_router(review.router)
api_router.include_router(kb.router)
api_router.include_router(web.router)
api_router.include_router(video.router)
