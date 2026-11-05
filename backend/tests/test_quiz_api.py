import pytest
from fastapi.testclient import TestClient

from app.api.deps import get_quiz_service
from app.main import create_app
from app.services.quiz_service import QuizService
from app.utils.content_filter import ContentFilter
from tests.factories import generated_quiz
from tests.llm_mock import test_settings
from tests.test_quiz_service import FakeGenerator


def client_with(outcomes: list) -> tuple[TestClient, FakeGenerator]:
    app = create_app()
    gen = FakeGenerator(outcomes)
    service = QuizService(gen, settings=test_settings(), content_filter=ContentFilter(["制毒"]))
    app.dependency_overrides[get_quiz_service] = lambda: service
    return TestClient(app), gen


def test_generate_quiz_success():
    client, gen = client_with([generated_quiz(5)])
    resp = client.post(
        "/api/v1/quiz/generate",
        json={"user_input": "我想学习什么是 RAG，以及它和传统搜索有什么区别", "question_count": 5, "difficulty": "mixed"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["quiz_id"].startswith("quiz_")
    assert data["title"] == "RAG 入门"
    assert len(data["questions"]) == 5
    q = data["questions"][0]
    assert set(q) == {"id", "type", "stem", "options", "answer", "explanation", "knowledge_point", "difficulty"}


def test_default_question_count_is_five():
    client, gen = client_with([generated_quiz(5)])
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "复利是怎么算的"})
    assert resp.json()["code"] == 0
    assert gen.calls[0]["question_count"] == 5


@pytest.mark.parametrize("count", [3, 10])
def test_supported_question_counts(count):
    client, _ = client_with([generated_quiz(count)])
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "复利是怎么算的", "question_count": count})
    assert len(resp.json()["data"]["questions"]) == count


@pytest.mark.parametrize("count", [0, 4, 11])
def test_unsupported_question_count_is_rejected(count):
    client, gen = client_with([])
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "复利是怎么算的", "question_count": count})
    assert resp.json()["code"] == 4000
    assert gen.calls == []


def test_too_long_input_is_rejected():
    client, gen = client_with([])
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "字" * 2001})
    assert resp.json()["code"] == 4000


def test_short_input_error_code():
    client, _ = client_with([])
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "RAG"})
    assert resp.status_code == 200
    assert resp.json()["code"] == 4002
    assert resp.json()["data"] is None


def test_sensitive_input_error_code():
    client, _ = client_with([])
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "怎么制毒最快"})
    assert resp.json()["code"] == 4003


def test_generation_failure_error_code():
    client, _ = client_with([ValueError("a"), ValueError("b"), ValueError("c")])
    resp = client.post("/api/v1/quiz/generate", json={"user_input": "复利是怎么算的"})
    assert resp.json() == {"code": 4001, "message": "题库生成失败，请稍后重试", "data": None}
