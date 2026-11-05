from fastapi import APIRouter
from fastapi.testclient import TestClient

from app.core.exceptions import BizError, ErrorCode
from app.main import create_app


def test_health():
    client = TestClient(create_app())
    resp = client.get("/api/v1/health")
    assert resp.status_code == 200
    assert resp.json() == {"code": 0, "message": "ok", "data": {"status": "up"}}


def _app_with_probe_routes():
    app = create_app()
    router = APIRouter()

    @router.get("/_probe/biz")
    async def biz():
        raise BizError(ErrorCode.QUIZ_GENERATE_FAILED, "题库生成失败，请稍后重试")

    @router.get("/_probe/boom")
    async def boom():
        raise RuntimeError("secret internal detail")

    app.include_router(router)
    return app


def test_biz_error_uses_unified_envelope():
    client = TestClient(_app_with_probe_routes())
    resp = client.get("/_probe/biz")
    assert resp.status_code == 200
    assert resp.json() == {"code": 4001, "message": "题库生成失败，请稍后重试", "data": None}


def test_unexpected_error_hides_details():
    client = TestClient(_app_with_probe_routes(), raise_server_exceptions=False)
    resp = client.get("/_probe/boom")
    assert resp.status_code == 500
    body = resp.json()
    assert body["code"] == 5000
    assert body["data"] is None
    assert "secret" not in body["message"]


def test_validation_error_uses_unified_envelope():
    client = TestClient(create_app())
    resp = client.post("/api/v1/quiz/generate", json={"question_count": 5})
    assert resp.status_code == 422
    body = resp.json()
    assert body["code"] == 4000
    assert body["data"] is None
    assert body["message"]


def test_error_code_values_are_stable():
    assert ErrorCode.INVALID_PARAMS == 4000
    assert ErrorCode.QUIZ_GENERATE_FAILED == 4001
    assert ErrorCode.INPUT_TOO_SHORT == 4002
    assert ErrorCode.CONTENT_NOT_ALLOWED == 4003
    assert ErrorCode.REPORT_GENERATE_FAILED == 4004
    assert ErrorCode.UNAUTHORIZED == 4010
    assert ErrorCode.LOGIN_FAILED == 4011
    assert ErrorCode.NICKNAME_NOT_ALLOWED == 4012
    assert ErrorCode.NOT_FOUND == 4040
    assert ErrorCode.INTERNAL_ERROR == 5000
