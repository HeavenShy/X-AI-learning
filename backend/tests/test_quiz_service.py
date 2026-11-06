import asyncio

import httpx
import openai
import pytest

from app.agent.retrieval_planner import KbChunk, PlanningError, RetrievalPlanner, RetrievalResult
from app.core.exceptions import BizError, ErrorCode
from app.llm.langchain_factory import create_chat_model
from app.llm.output_schemas import GeneratedQuiz, GeneratedQuizWithSources
from app.models.quiz import QuizGenerateRequest
from app.prompts.retrieval_agent_prompt import CatalogItem
from app.services.quiz_service import SEARCH_QUERY_MAX_CHARS, QuizService
from app.services.web_search import SearchSnippet, WebSearchError
from app.utils.content_filter import ContentFilter
from tests.factories import generated_quiz, quiz_dict
from tests.llm_mock import MockDeepSeek, test_settings, text_response, tool_calls_response


class FakeGenerator:
    """按顺序返回结果；元素是异常时抛出。"""

    def __init__(self, outcomes: list):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    async def generate(self, **kwargs) -> GeneratedQuiz:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


class FakeSearcher:
    """记录查询词；outcome 是异常则抛出，否则返回该结果列表。"""

    def __init__(self, outcome):
        self.outcome = outcome
        self.queries: list[str] = []

    async def search(self, query: str) -> list[SearchSnippet]:
        self.queries.append(query)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def make_service(
    outcomes: list, words: list[str] | None = None, searcher: FakeSearcher | None = None, **settings
) -> tuple[QuizService, FakeGenerator]:
    gen = FakeGenerator(outcomes)
    service = QuizService(
        gen, settings=test_settings(**settings), content_filter=ContentFilter(words or ["制毒"]), searcher=searcher
    )
    return service, gen


def req(text: str = "我想学习什么是 RAG", count: int = 5, difficulty: str = "mixed") -> QuizGenerateRequest:
    return QuizGenerateRequest(user_input=text, question_count=count, difficulty=difficulty)


async def test_success_returns_full_quiz():
    service, gen = make_service([generated_quiz(5)])
    quiz = await service.generate(req())
    assert quiz.quiz_id.startswith("quiz_")
    assert quiz.title == "RAG 入门"
    assert quiz.user_input == "我想学习什么是 RAG"
    assert quiz.source_type == "text"
    assert [q.id for q in quiz.questions] == ["q1", "q2", "q3", "q4", "q5"]
    assert gen.calls == [
        {
            "user_input": "我想学习什么是 RAG",
            "question_count": 5,
            "difficulty": "mixed",
            "prompt_version": "quiz_prompt_v1",
            "reference": "",
        }
    ]


async def test_input_is_cleaned_before_generation():
    service, gen = make_service([generated_quiz(3)])
    quiz = await service.generate(req("  什么是​ RAG   \n", count=3))
    assert gen.calls[0]["user_input"] == "什么是 RAG"
    assert quiz.user_input == "什么是 RAG"


async def test_retries_with_conservative_prompt_after_invalid_output():
    bad = GeneratedQuiz.model_validate({**quiz_dict(5), "questions": quiz_dict(5)["questions"][:4]})
    service, gen = make_service([bad, generated_quiz(5)])
    quiz = await service.generate(req())
    assert len(quiz.questions) == 5
    assert [c["prompt_version"] for c in gen.calls] == ["quiz_prompt_v1", "quiz_prompt_v2"]


async def test_retries_after_exception():
    service, gen = make_service([ValueError("parse error"), RuntimeError("timeout"), generated_quiz(5)])
    quiz = await service.generate(req())
    assert len(quiz.questions) == 5
    assert len(gen.calls) == 3


async def test_gives_up_after_max_attempts():
    service, gen = make_service([ValueError("x"), ValueError("y"), ValueError("z")])
    with pytest.raises(BizError) as e:
        await service.generate(req())
    assert e.value.code == ErrorCode.QUIZ_GENERATE_FAILED
    assert len(gen.calls) == 3


async def test_retries_when_generated_content_is_not_allowed():
    dirty = quiz_dict(5)
    dirty["questions"][0]["explanation"] = "这里讲一下制毒流程"
    service, gen = make_service([GeneratedQuiz.model_validate(dirty), generated_quiz(5)])
    quiz = await service.generate(req())
    assert "制毒" not in quiz.questions[0].explanation
    assert len(gen.calls) == 2


async def test_auth_error_is_not_retried():
    resp = httpx.Response(401, request=httpx.Request("POST", "https://api.deepseek.com/chat/completions"))
    err = openai.AuthenticationError("bad key", response=resp, body=None)
    service, gen = make_service([err, generated_quiz(5)])
    with pytest.raises(BizError) as e:
        await service.generate(req())
    assert e.value.code == ErrorCode.QUIZ_GENERATE_FAILED
    assert len(gen.calls) == 1


@pytest.mark.parametrize("text", ["", "   ", "RAG", "R A G"])
async def test_too_short_input_is_rejected_without_calling_llm(text):
    service, gen = make_service([generated_quiz(5)])
    with pytest.raises(BizError) as e:
        await service.generate(req(text))
    assert e.value.code == ErrorCode.INPUT_TOO_SHORT
    assert "至少写 4 个字" in e.value.message
    assert gen.calls == []


async def test_sensitive_input_is_rejected_without_calling_llm():
    service, gen = make_service([generated_quiz(5)])
    with pytest.raises(BizError) as e:
        await service.generate(req("教我制 毒的方法"))
    assert e.value.code == ErrorCode.CONTENT_NOT_ALLOWED
    assert e.value.message == "这段内容涉及不适合出题的话题，换个主题试试。"
    assert gen.calls == []


# ---------- 联网检索 ----------

SNIPPETS = [
    SearchSnippet(title="RAG 简介", url="https://a", content="检索增强生成先检索再生成。"),
    SearchSnippet(title="向量库", url="https://b", content="用来存 embedding。"),
]


async def test_search_results_are_passed_to_generator():
    searcher = FakeSearcher(SNIPPETS)
    service, gen = make_service([generated_quiz(5)], searcher=searcher)
    quiz = await service.generate(req("  我想学习什么是​ RAG  "))
    assert searcher.queries == ["我想学习什么是 RAG"]
    assert gen.calls[0]["reference"] == "[1] RAG 简介\n检索增强生成先检索再生成。\n\n[2] 向量库\n用来存 embedding。"
    # 用户看到的结果不带检索来源
    assert "https://a" not in quiz.model_dump_json()


async def test_query_is_truncated():
    searcher = FakeSearcher([])
    service, _ = make_service([generated_quiz(5)], searcher=searcher)
    await service.generate(req("学" * 1000))
    assert searcher.queries == ["学" * SEARCH_QUERY_MAX_CHARS]


async def test_reference_respects_length_settings():
    long = [SearchSnippet(title=f"T{i}", content="字" * 500) for i in range(5)]
    service, gen = make_service(
        [generated_quiz(5)], searcher=FakeSearcher(long), web_reference_item_max_chars=100, web_reference_max_chars=250
    )
    await service.generate(req())
    assert 0 < len(gen.calls[0]["reference"]) <= 250


async def test_empty_results_mean_no_reference():
    service, gen = make_service([generated_quiz(5)], searcher=FakeSearcher([]))
    await service.generate(req())
    assert gen.calls[0]["reference"] == ""


@pytest.mark.parametrize(
    "error",
    [
        WebSearchError("Tavily HTTP 401", status=401),
        WebSearchError("Tavily HTTP 432", status=432),
        WebSearchError("Tavily 检索超时（ReadTimeout）"),
        TimeoutError(),
        RuntimeError("unexpected"),
    ],
)
async def test_search_failure_does_not_break_quiz(error, caplog):
    searcher = FakeSearcher(error)
    service, gen = make_service([generated_quiz(5)], searcher=searcher)
    quiz = await service.generate(req())
    assert len(quiz.questions) == 5
    assert len(searcher.queries) == 1
    assert gen.calls[0]["reference"] == ""
    assert "web search" in caplog.text
    if isinstance(error, WebSearchError) and error.status:
        assert f"status={error.status}" in caplog.text


@pytest.mark.parametrize("text", ["RAG", "教我制 毒的方法"])
async def test_invalid_input_does_not_search(text):
    searcher = FakeSearcher(SNIPPETS)
    service, _ = make_service([generated_quiz(5)], searcher=searcher)
    with pytest.raises(BizError):
        await service.generate(req(text))
    assert searcher.queries == []


async def test_retries_reuse_one_search():
    searcher = FakeSearcher(SNIPPETS)
    service, gen = make_service([ValueError("a"), ValueError("b"), generated_quiz(5)], searcher=searcher)
    await service.generate(req())
    assert len(searcher.queries) == 1
    assert [c["prompt_version"] for c in gen.calls] == ["quiz_prompt_v1", "quiz_prompt_v2", "quiz_prompt_v2"]
    refs = {c["reference"] for c in gen.calls}
    assert len(refs) == 1 and refs != {""}


async def test_without_searcher_reference_is_empty():
    service, gen = make_service([generated_quiz(5)])
    await service.generate(req())
    assert gen.calls[0]["reference"] == ""


# ---------- 检索规划 Agent ----------

KB_TOOL, WEB_TOOL = "search_knowledge_base", "web_search"
PAY_CHUNKS = [
    KbChunk(id=11, document_id="doc_pay", document_name="报销制度.pdf", seq=0, page=2, text="报销需部门经理审批，五个工作日内完成。"),
    KbChunk(id=12, document_id="doc_pay", document_name="报销制度.pdf", seq=1, page=3, text="单笔超过五千元需财务总监复核。"),
]
PAY_DOCS = [{"document_id": "doc_pay", "filename": "报销制度.pdf", "kb_name": "新人考核"}]


class FakeKbRetriever:
    def __init__(self, documents=None, chunks=None):
        self._documents = PAY_DOCS if documents is None else documents
        self.chunks = PAY_CHUNKS if chunks is None else chunks
        self.queries: list[str] = []

    async def documents(self):
        return self._documents

    async def catalog(self):
        return [CatalogItem(d["kb_name"], d["filename"]) for d in await self.documents()]

    async def search(self, query: str):
        self.queries.append(query)
        return self.chunks


class FakePlanner:
    """outcome 是异常则抛出，否则作为规划结果；记录收到的 PlanContext。"""

    def __init__(self, outcome=None):
        self.outcome = outcome if outcome is not None else RetrievalResult()
        self.contexts = []

    async def plan(self, ctx):
        self.contexts.append(ctx)
        if isinstance(self.outcome, BaseException):
            raise self.outcome
        return self.outcome


def real_planner(mock: MockDeepSeek, **overrides) -> RetrievalPlanner:
    settings = test_settings(agent_retrieval_enabled=True, **overrides)
    llm = create_chat_model(temperature=0.1, max_tokens=800, settings=settings, http_async_client=mock.client())
    return RetrievalPlanner(llm, settings=settings, content_filter=ContentFilter(["制毒"]))


def agent_service(outcomes, *, planner, searcher=None, kb=None, **settings):
    gen = FakeGenerator(outcomes)
    service = QuizService(
        gen,
        settings=test_settings(**{"agent_retrieval_enabled": True, **settings}),
        content_filter=ContentFilter(["制毒"]),
        searcher=searcher,
        planner=planner,
        kb_retriever=kb,
    )
    return service, gen


def quiz_with_sources(source_ids_by_index: dict[int, list[int]], count: int = 5) -> GeneratedQuizWithSources:
    data = quiz_dict(count)
    for i, q in enumerate(data["questions"]):
        q["source_ids"] = source_ids_by_index.get(i, [])
        q["source_quote"] = ""
    return GeneratedQuizWithSources.model_validate(data)


async def test_anonymous_user_only_gets_web_tool():
    mock = MockDeepSeek([text_response()])
    service, _ = agent_service([generated_quiz(5)], planner=real_planner(mock), searcher=FakeSearcher(SNIPPETS))
    await service.generate(req())
    assert [t["function"]["name"] for t in mock.requests[0]["tools"]] == [WEB_TOOL]


async def test_logged_in_user_with_documents_gets_both_tools():
    mock = MockDeepSeek([text_response()])
    service, _ = agent_service(
        [generated_quiz(5)], planner=real_planner(mock), searcher=FakeSearcher(SNIPPETS), kb=FakeKbRetriever()
    )
    await service.generate(req("报销审批流程"))
    body = mock.requests[0]
    assert [t["function"]["name"] for t in body["tools"]] == [KB_TOOL, WEB_TOOL]
    assert "新人考核 / 报销制度.pdf" in body["messages"][-1]["content"]


async def test_user_without_ready_documents_has_no_kb_tool():
    planner = FakePlanner()
    service, _ = agent_service(
        [generated_quiz(5)], planner=planner, searcher=FakeSearcher(SNIPPETS), kb=FakeKbRetriever(documents=[])
    )
    await service.generate(req())
    assert planner.contexts[0].kb_search is None and planner.contexts[0].web_search is not None


async def test_no_data_source_skips_planning(caplog):
    caplog.set_level("INFO")
    planner = FakePlanner()
    service, gen = agent_service([generated_quiz(5)], planner=planner, kb=FakeKbRetriever(documents=[]))
    quiz = await service.generate(req())
    assert planner.contexts == []
    assert gen.calls[0]["reference"] == "" and "materials" not in gen.calls[0]
    assert quiz.source_type == "text"
    assert "retrieval plan entry=home skipped fallback=no_tools" in caplog.text


async def test_agent_choosing_nothing_means_no_reference_and_no_materials():
    mock = MockDeepSeek([text_response()])
    searcher, kb = FakeSearcher(SNIPPETS), FakeKbRetriever()
    service, gen = agent_service([generated_quiz(5)], planner=real_planner(mock), searcher=searcher, kb=kb)
    quiz = await service.generate(req("勾股定理"))
    assert searcher.queries == [] and kb.queries == []
    assert gen.calls[0]["reference"] == ""
    assert "materials" not in gen.calls[0]
    assert quiz.source_type == "text"


async def test_agent_web_results_become_reference():
    mock = MockDeepSeek(
        [tool_calls_response([(WEB_TOOL, {"query": "RAG 最新进展"}), (WEB_TOOL, {"query": "向量库"})]), text_response()]
    )
    searcher = FakeSearcher(SNIPPETS)
    service, gen = agent_service([generated_quiz(5)], planner=real_planner(mock), searcher=searcher)
    await service.generate(req())
    assert searcher.queries == ["RAG 最新进展", "向量库"]
    # 两次结果按 url 去重后合并为一份参考资料
    assert gen.calls[0]["reference"] == "[1] RAG 简介\n检索增强生成先检索再生成。\n\n[2] 向量库\n用来存 embedding。"


async def test_agent_kb_hits_give_some_questions_sources():
    mock = MockDeepSeek([tool_calls_response([(KB_TOOL, {"query": "报销审批"})]), text_response()])
    kb = FakeKbRetriever()
    service, gen = agent_service([quiz_with_sources({0: [1], 2: [2, 1]})], planner=real_planner(mock), kb=kb)
    quiz = await service.generate(req("报销审批流程"))
    assert kb.queries == ["报销审批"]
    materials = gen.calls[0]["materials"]
    assert materials.startswith("[1] 《报销制度.pdf》第 2 页\n报销需部门经理审批")
    assert "[2] 《报销制度.pdf》第 3 页" in materials
    assert gen.calls[0]["reference"] == ""
    sources = [q.sources for q in quiz.questions]
    assert [s.page for s in sources[0]] == [2]
    assert [s.page for s in sources[2]] == [3, 2]
    assert sources[1] == [] and sources[3] == [] and sources[4] == []
    assert sources[0][0].document_name == "报销制度.pdf" and sources[0][0].document_id == "doc_pay"
    assert quiz.source_type == "knowledge_base"


async def test_invalid_source_ids_are_only_dropped_on_home():
    planner = FakePlanner(RetrievalResult(kb_chunks=PAY_CHUNKS, kb_calls=1))
    service, gen = agent_service([quiz_with_sources({0: [99], 1: [1, 42]})], planner=planner, kb=FakeKbRetriever())
    quiz = await service.generate(req("报销审批流程"))
    assert len(gen.calls) == 1  # 不因无效编号重试
    assert quiz.questions[0].sources == []
    assert [s.page for s in quiz.questions[1].sources] == [2]
    assert quiz.source_type == "knowledge_base"


async def test_unused_materials_mean_text_source_type():
    planner = FakePlanner(RetrievalResult(kb_chunks=PAY_CHUNKS, kb_calls=1))
    service, _ = agent_service([quiz_with_sources({})], planner=planner, kb=FakeKbRetriever())
    quiz = await service.generate(req("报销审批流程"))
    assert all(q.sources == [] for q in quiz.questions)
    assert quiz.source_type == "text"


@pytest.mark.parametrize("reason", ["timeout", "model_error"])
async def test_planning_failure_falls_back_to_one_fixed_search(reason):
    searcher, kb = FakeSearcher(SNIPPETS), FakeKbRetriever()
    planner = FakePlanner(PlanningError(reason))
    service, gen = agent_service([generated_quiz(5)], planner=planner, searcher=searcher, kb=kb)
    quiz = await service.generate(req("  我想学习什么是​ RAG  "))
    assert searcher.queries == ["我想学习什么是 RAG"]
    assert kb.queries == []
    assert gen.calls[0]["reference"].startswith("[1] RAG 简介")
    assert "materials" not in gen.calls[0]
    assert quiz.source_type == "text"


async def test_planning_timeout_with_real_planner_falls_back():
    class SlowKb(FakeKbRetriever):
        async def search(self, query):
            await asyncio.sleep(1)
            return []

    mock = MockDeepSeek([tool_calls_response([(KB_TOOL, {"query": "报销"})])])
    searcher = FakeSearcher(SNIPPETS)
    service, gen = agent_service(
        [generated_quiz(5)],
        planner=real_planner(mock, agent_timeout_seconds=0.05),
        searcher=searcher,
        kb=SlowKb(),
    )
    await service.generate(req())
    assert searcher.queries == ["我想学习什么是 RAG"]
    assert gen.calls[0]["reference"] != ""


async def test_switch_off_uses_fixed_rule():
    planner, searcher, kb = FakePlanner(), FakeSearcher(SNIPPETS), FakeKbRetriever()
    service, gen = agent_service(
        [generated_quiz(5)], planner=planner, searcher=searcher, kb=kb, agent_retrieval_enabled=False
    )
    await service.generate(req())
    assert planner.contexts == []
    assert searcher.queries == ["我想学习什么是 RAG"] and kb.queries == []
    assert gen.calls[0]["reference"] != ""


async def test_retries_plan_only_once():
    mock = MockDeepSeek(
        [tool_calls_response([(KB_TOOL, {"query": "报销"}), (WEB_TOOL, {"query": "差旅"})]), text_response()]
    )
    searcher, kb = FakeSearcher(SNIPPETS), FakeKbRetriever()
    service, gen = agent_service(
        [ValueError("bad"), ValueError("bad"), quiz_with_sources({0: [1]})],
        planner=real_planner(mock),
        searcher=searcher,
        kb=kb,
    )
    quiz = await service.generate(req())
    assert len(mock.requests) == 2  # 规划只跑了一次（2 轮）
    assert kb.queries == ["报销"] and searcher.queries == ["差旅"]
    assert [c["prompt_version"] for c in gen.calls] == ["quiz_prompt_v1", "quiz_prompt_v2", "quiz_prompt_v2"]
    assert len({(c["reference"], c["materials"]) for c in gen.calls}) == 1
    assert quiz.questions[0].sources


@pytest.mark.parametrize("text", ["RAG", "教我制 毒的方法"])
async def test_invalid_input_does_not_plan(text):
    planner = FakePlanner()
    service, _ = agent_service(
        [generated_quiz(5)], planner=planner, searcher=FakeSearcher(SNIPPETS), kb=FakeKbRetriever()
    )
    with pytest.raises(BizError):
        await service.generate(req(text))
    assert planner.contexts == []


async def test_kb_document_listing_failure_plans_without_kb():
    class BrokenKb(FakeKbRetriever):
        async def documents(self):
            raise RuntimeError("db down")

    planner = FakePlanner()
    service, _ = agent_service([generated_quiz(5)], planner=planner, searcher=FakeSearcher(SNIPPETS), kb=BrokenKb())
    await service.generate(req())
    assert planner.contexts[0].kb_search is None


# ---------- 只检索当前用户的资料（yhyd_test + 内存向量库）----------


async def test_home_kb_retriever_only_sees_current_user(sql):
    from app.core.db import Database
    from app.rag.vector_store import InMemoryVectorStore, VectorMeta
    from app.services.kb_retrieval import KbRetriever
    from tests.conftest import db_settings
    from tests.kb_files import FakeEmbedder, keyword_vector

    vectors = InMemoryVectorStore()

    async def add(user_id, kb_id, kb_name, document_id, filename, status, text):
        sql.execute(
            "INSERT IGNORE INTO knowledge_bases (kb_id, user_id, name) VALUES (%s, %s, %s)", (kb_id, user_id, kb_name)
        )
        sql.execute(
            "INSERT INTO kb_documents (document_id, kb_id, user_id, filename, file_type, size_bytes, status, "
            "chunk_count) VALUES (%s, %s, %s, %s, 'txt', 1, %s, 1)",
            (document_id, kb_id, user_id, filename, status),
        )
        cid = sql.execute(
            "INSERT INTO kb_chunks (document_id, user_id, seq, page, text, flagged) VALUES (%s, %s, 0, NULL, %s, 0)",
            (document_id, user_id, text),
        )
        meta = VectorMeta(user_id=user_id, kb_id=kb_id, document_id=document_id)
        await vectors.upsert([cid], [keyword_vector(text, FakeEmbedder.KEYWORDS)], [meta])

    await add(1, "kb_a1", "新人考核", "doc_a1", "报销制度.txt", "ready", "报销审批由部门经理负责。")
    await add(1, "kb_a2", "PMP 备考", "doc_a2", "风险管理.txt", "ready", "报销审批的风险登记。")
    await add(1, "kb_a2", "PMP 备考", "doc_a3", "处理中.txt", "processing", "报销审批处理中的资料。")
    await add(2, "kb_b1", "别人的库", "doc_b1", "别人的报销.txt", "ready", "报销审批报销审批报销审批。")

    db = await Database.connect(db_settings())
    try:
        retriever = KbRetriever(db, user_id=1, embedder=FakeEmbedder(), vector_store=vectors, top_k=6)
        assert [d["document_id"] for d in await retriever.documents()] == ["doc_a1", "doc_a2"]
        assert [(c.kb_name, c.filename) for c in await retriever.catalog()] == [
            ("新人考核", "报销制度.txt"),
            ("PMP 备考", "风险管理.txt"),
        ]
        chunks = await retriever.search("报销审批")
        assert {c.document_id for c in chunks} == {"doc_a1", "doc_a2"}
        assert {c.document_name for c in chunks} == {"报销制度.txt", "风险管理.txt"}

        # 整条首页出题链路：Agent 查库后交给出题的材料里没有别人的资料
        mock = MockDeepSeek([tool_calls_response([(KB_TOOL, {"query": "报销审批"})]), text_response()])
        service, gen = agent_service([quiz_with_sources({0: [1]})], planner=real_planner(mock), kb=retriever)
        quiz = await service.generate(req("报销审批流程"))
        assert "别人的报销" not in gen.calls[0]["materials"]
        assert "《报销制度.txt》" in gen.calls[0]["materials"]
        assert quiz.source_type == "knowledge_base"
    finally:
        await db.close()
