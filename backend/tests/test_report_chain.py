from app.llm.langchain_factory import create_chat_model
from app.llm.output_schemas import GeneratedReport
from app.llm.report_chain import LangChainReportGenerator
from app.services.scoring_service import score
from tests.llm_mock import MockDeepSeek, test_settings, tool_call_response
from tests.report_factories import generated_report_dict, report_request


async def test_report_chain_contract():
    mock = MockDeepSeek([tool_call_response("GeneratedReport", generated_report_dict())])
    settings = test_settings()
    llm = create_chat_model(
        temperature=settings.report_temperature,
        max_tokens=settings.report_max_tokens,
        settings=settings,
        http_async_client=mock.client(),
    )
    req = report_request()
    summary = score(req.questions, req.answer_records)
    result = await LangChainReportGenerator(llm).generate(
        topic=req.topic, questions=req.questions, summary=summary, prompt_version="report_prompt_v1"
    )
    assert isinstance(result, GeneratedReport)
    assert len(result.three_line_summary) == 3

    body = mock.requests[0]
    assert body["temperature"] == 0.5
    assert body["max_tokens"] == 2000
    assert body["thinking"] == {"type": "disabled"}
    assert body["tool_choice"]["function"]["name"] == "GeneratedReport"
    assert "RAG 入门" in body["messages"][-1]["content"]
