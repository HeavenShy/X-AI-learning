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
    assert data["source_type"] == "text"
    q = data["questions"][0]
    assert set(q) == {
        "id", "type", "stem", "options", "answer", "explanation", "knowledge_point", "difficulty", "sources",
    }
    # 文本出题没有出处：每题 sources 为空列表
    assert all(question["sources"] == [] for question in data["questions"])


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


# ---------- 联网检索：生命周期与注入 ----------

QUIZ_FIELDS = {"quiz_id", "title", "summary", "topic", "source_type", "user_input", "questions"}


def _app_settings(**overrides):
    # 不连库，只看检索相关的 lifespan 行为
    return test_settings(mysql_database="", **overrides)


def test_no_key_means_no_web_searcher():
    from app.api.deps import get_quiz_generator

    app = create_app(_app_settings())
    gen = FakeGenerator([generated_quiz(5)])
    app.dependency_overrides[get_quiz_generator] = lambda: gen
    with TestClient(app) as client:
        assert app.state.web_searcher is None
        resp = client.post("/api/v1/quiz/generate", json={"user_input": "复利是怎么算的"})
    body = resp.json()
    assert body["code"] == 0
    assert set(body["data"]) == QUIZ_FIELDS
    assert gen.calls[0]["reference"] == ""


def test_key_creates_tavily_searcher():
    from app.services.web_search import TavilySearcher

    app = create_app(_app_settings(tavily_api_key="tvly-test"))
    with TestClient(app):
        assert isinstance(app.state.web_searcher, TavilySearcher)


def test_web_searcher_reference_reaches_generator_and_response_is_unchanged():
    from app.api.deps import get_quiz_generator
    from app.services.web_search import SearchSnippet
    from tests.test_quiz_service import FakeSearcher

    app = create_app(_app_settings())
    gen = FakeGenerator([generated_quiz(5)])
    app.dependency_overrides[get_quiz_generator] = lambda: gen
    searcher = FakeSearcher([SearchSnippet(title="RAG", url="https://src.example", content="检索增强生成")])
    with TestClient(app) as client:
        app.state.web_searcher = searcher
        resp = client.post("/api/v1/quiz/generate", json={"user_input": "我想学习什么是 RAG"})
        app.state.web_searcher = None
    body = resp.json()
    assert body["code"] == 0
    assert set(body["data"]) == QUIZ_FIELDS
    assert "src.example" not in resp.text
    assert searcher.queries == ["我想学习什么是 RAG"]
    assert "检索增强生成" in gen.calls[0]["reference"]


# ---------- 检索规划 Agent 端到端：MockDeepSeek 依次返回规划响应和出题响应 ----------


def _agent_kb_api(kb_api, responses: list[dict]):
    """kb_api 上改用真实的 get_quiz_service：检索规划与出题都走 LangChain + 同一个 MockDeepSeek。"""
    from app.api.deps import get_quiz_generator, get_retrieval_llm
    from app.llm.langchain_factory import create_chat_model
    from app.llm.quiz_chain import LangChainQuizGenerator
    from tests.llm_mock import MockDeepSeek

    mock = MockDeepSeek(responses)
    settings = kb_api.app.state.settings
    settings.agent_retrieval_enabled = True
    client = mock.client()
    llm = create_chat_model(temperature=0.1, max_tokens=800, settings=settings, http_async_client=client)
    overrides = kb_api.app.dependency_overrides
    overrides.pop(get_quiz_service)
    overrides[get_retrieval_llm] = lambda: llm
    overrides[get_quiz_generator] = lambda: LangChainQuizGenerator(llm)
    return mock


def _quiz_with_sources(first_source_ids: list[int]) -> dict:
    from tests.factories import quiz_dict

    data = quiz_dict(5)
    for i, q in enumerate(data["questions"]):
        q["source_ids"] = first_source_ids if i == 0 else []
        q["source_quote"] = ""
    return data


def test_home_quiz_using_kb_materials_has_consistent_source_type(kb_api):
    from tests.llm_mock import text_response, tool_call_response, tool_calls_response
    from tests.test_kb_api import ready_kb
    from tests.test_persistence_api import submit

    token, _ = kb_api.login("u1")
    ready_kb(kb_api, token)
    mock = _agent_kb_api(
        kb_api,
        [
            tool_calls_response([("search_knowledge_base", {"query": "报销审批"})]),
            text_response(),
            tool_call_response("GeneratedQuizWithSources", _quiz_with_sources([1])),
        ],
    )
    body = kb_api.post("/quiz/generate", {"user_input": "报销审批流程是怎样的", "question_count": 5}, token).json()
    assert body["code"] == 0, body
    quiz = body["data"]
    assert quiz["source_type"] == "knowledge_base"
    assert quiz["questions"][0]["sources"][0]["document_name"] == "报销制度.txt"
    assert all(q["sources"] == [] for q in quiz["questions"][1:])
    # 规划 2 轮 + 出题 1 次；第 1 次请求绑定的是知识库工具（没配搜索 Key，不能联网）
    assert len(mock.requests) == 3
    assert [t["function"]["name"] for t in mock.requests[0]["tools"]] == ["search_knowledge_base"]
    assert "<materials>" in mock.requests[2]["messages"][-1]["content"]
    assert submit(kb_api, quiz, token)["code"] == 0
    detail = kb_api.get(f"/user/quizzes/{quiz['quiz_id']}", token).json()["data"]
    assert detail["quiz"]["source_type"] == quiz["source_type"] == "knowledge_base"
    assert detail["quiz"]["questions"][0]["sources"] == quiz["questions"][0]["sources"]


def test_home_quiz_not_using_materials_stays_text(kb_api):
    from tests.factories import quiz_dict
    from tests.llm_mock import text_response, tool_call_response
    from tests.test_kb_api import ready_kb
    from tests.test_persistence_api import submit

    token, _ = kb_api.login("u1")
    ready_kb(kb_api, token)
    mock = _agent_kb_api(kb_api, [text_response(), tool_call_response("GeneratedQuiz", quiz_dict(5))])
    body = kb_api.post("/quiz/generate", {"user_input": "勾股定理是什么", "question_count": 5}, token).json()
    assert body["code"] == 0, body
    quiz = body["data"]
    assert quiz["source_type"] == "text"
    assert [t["function"]["name"] for t in mock.requests[1]["tools"]] == ["GeneratedQuiz"]
    assert submit(kb_api, quiz, token)["code"] == 0
    detail = kb_api.get(f"/user/quizzes/{quiz['quiz_id']}", token).json()["data"]
    assert detail["quiz"]["source_type"] == "text"


def test_anonymous_home_quiz_never_touches_kb(kb_api):
    from tests.factories import quiz_dict
    from tests.llm_mock import tool_call_response
    from tests.test_kb_api import ready_kb

    token, _ = kb_api.login("u1")
    ready_kb(kb_api, token)
    embed_calls = len(kb_api.embedder.calls)
    # 未登录且没配搜索 Key：没有可用数据源，不运行规划，直接出题
    mock = _agent_kb_api(kb_api, [tool_call_response("GeneratedQuiz", quiz_dict(5))])
    body = kb_api.post("/quiz/generate", {"user_input": "报销审批流程是怎样的", "question_count": 5}).json()
    assert body["code"] == 0, body
    assert body["data"]["source_type"] == "text"
    assert len(mock.requests) == 1
    assert len(kb_api.embedder.calls) == embed_calls
