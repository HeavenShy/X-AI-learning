from fastapi.testclient import TestClient

from app.api.deps import get_report_service
from app.main import create_app
from app.services.report_service import ReportService
from app.utils.content_filter import ContentFilter
from tests.llm_mock import test_settings
from tests.report_factories import report_request
from tests.test_report_service import FakeReportGenerator, gr


def client_with(outcomes: list) -> TestClient:
    app = create_app()
    service = ReportService(FakeReportGenerator(outcomes), settings=test_settings(), content_filter=ContentFilter([]))
    app.dependency_overrides[get_report_service] = lambda: service
    return TestClient(app)


def payload() -> dict:
    return report_request().model_dump()


def test_generate_report_success():
    resp = client_with([gr()]).post("/api/v1/report/generate", json=payload())
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert set(data) == {
        "accuracy", "correct_count", "total_count", "total_duration_ms",
        "mastered_points", "weak_points", "knowledge_mastery",
        "three_line_summary", "advice", "share_quote",
    }
    assert data["accuracy"] == 80
    assert data["knowledge_mastery"][3] == {"point": "多选知识点4", "correct": 0, "total": 1, "accuracy": 0}


def test_report_requires_questions():
    p = payload()
    p["questions"] = []
    resp = client_with([gr()]).post("/api/v1/report/generate", json=p)
    assert resp.json()["code"] == 4000


def test_negative_duration_is_rejected():
    p = payload()
    p["answer_records"][0]["duration_ms"] = -1
    resp = client_with([gr()]).post("/api/v1/report/generate", json=p)
    assert resp.json()["code"] == 4000


def test_report_failure_code():
    resp = client_with([ValueError("a"), ValueError("b")]).post("/api/v1/report/generate", json=payload())
    assert resp.json() == {"code": 4004, "message": "复盘报告生成失败，请稍后重试", "data": None}
