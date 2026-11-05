import httpx
import openai
import pytest

from app.core.exceptions import BizError, ErrorCode
from app.llm.output_schemas import GeneratedQuiz
from app.models.quiz import QuizGenerateRequest
from app.services.quiz_service import SEARCH_QUERY_MAX_CHARS, QuizService
from app.services.web_search import SearchSnippet, WebSearchError
from app.utils.content_filter import ContentFilter
from tests.factories import generated_quiz, quiz_dict
from tests.llm_mock import test_settings


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
