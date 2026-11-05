"""出题链路契约测试：真实的 ChatPromptTemplate + ChatOpenAI + with_structured_output，只把 HTTP 换成模拟。"""

from app.llm.langchain_factory import create_chat_model
from app.llm.output_schemas import GeneratedQuiz
from app.llm.quiz_chain import LangChainQuizGenerator
from tests.factories import quiz_dict
from tests.llm_mock import MockDeepSeek, test_settings, tool_call_response


async def _run(mock: MockDeepSeek, reference: str = "", **settings_overrides):
    settings = test_settings(**settings_overrides)
    llm = create_chat_model(
        temperature=settings.quiz_temperature,
        max_tokens=settings.quiz_max_tokens,
        settings=settings,
        http_async_client=mock.client(),
    )
    generator = LangChainQuizGenerator(llm)
    return await generator.generate(
        user_input="我想学习什么是 RAG",
        question_count=3,
        difficulty="mixed",
        prompt_version="quiz_prompt_v1",
        reference=reference,
    )


async def test_parses_tool_call_into_schema():
    mock = MockDeepSeek([tool_call_response("GeneratedQuiz", quiz_dict(3))])
    result = await _run(mock)
    assert isinstance(result, GeneratedQuiz)
    assert result.title == "RAG 入门"
    assert len(result.questions) == 3


async def test_request_payload_matches_deepseek_contract():
    mock = MockDeepSeek([tool_call_response("GeneratedQuiz", quiz_dict(3))])
    await _run(mock)
    body = mock.requests[0]
    # 走 Chat Completions，不走 Responses API
    assert mock.paths[0].endswith("/chat/completions")
    assert body["model"] == "deepseek-flash"
    # 思考模式必须关闭，否则命名 tool_choice 会被 DeepSeek 拒绝
    assert body["thinking"] == {"type": "disabled"}
    # DeepSeek 只认 max_tokens
    assert body["max_tokens"] == 8000
    assert "max_completion_tokens" not in body
    assert body["temperature"] == 0.4
    assert body["top_p"] == 0.9
    assert body["tool_choice"]["function"]["name"] == "GeneratedQuiz"
    assert body["tools"][0]["function"]["name"] == "GeneratedQuiz"
    assert body["messages"][0]["role"] == "system"
    assert "我想学习什么是 RAG" in body["messages"][-1]["content"]


async def test_thinking_mode_is_configurable():
    mock = MockDeepSeek([tool_call_response("GeneratedQuiz", quiz_dict(3))])
    await _run(mock, deepseek_thinking="enabled")
    assert mock.requests[0]["thinking"] == {"type": "enabled"}


async def test_reference_is_sent_to_deepseek():
    mock = MockDeepSeek([tool_call_response("GeneratedQuiz", quiz_dict(3))])
    await _run(mock, reference="[1] RAG 简介\n检索增强生成 {先检索} 再生成")
    human = mock.requests[0]["messages"][-1]["content"]
    assert "<reference>" in human
    assert "[1] RAG 简介" in human
    assert "检索增强生成 {先检索} 再生成" in human


async def test_no_reference_by_default():
    mock = MockDeepSeek([tool_call_response("GeneratedQuiz", quiz_dict(3))])
    await _run(mock)
    assert "<reference>" not in mock.requests[0]["messages"][-1]["content"]
