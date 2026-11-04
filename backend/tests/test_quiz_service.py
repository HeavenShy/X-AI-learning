import httpx
import openai
import pytest

from app.core.exceptions import BizError, ErrorCode
from app.llm.output_schemas import GeneratedQuiz
from app.models.quiz import QuizGenerateRequest
from app.services.quiz_service import QuizService
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


def make_service(outcomes: list, words: list[str] | None = None) -> tuple[QuizService, FakeGenerator]:
    gen = FakeGenerator(outcomes)
    service = QuizService(gen, settings=test_settings(), content_filter=ContentFilter(words or ["制毒"]))
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
        {"user_input": "我想学习什么是 RAG", "question_count": 5, "difficulty": "mixed", "prompt_version": "quiz_prompt_v1"}
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
