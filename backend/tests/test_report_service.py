import pytest

from app.core.exceptions import BizError, ErrorCode
from app.llm.output_schemas import GeneratedReport
from app.services.report_service import ReportService
from app.utils.content_filter import ContentFilter
from tests.llm_mock import test_settings
from tests.report_factories import generated_report_dict, record, report_request


class FakeReportGenerator:
    def __init__(self, outcomes: list):
        self.outcomes = list(outcomes)
        self.calls: list[dict] = []

    async def generate(self, **kwargs) -> GeneratedReport:
        self.calls.append(kwargs)
        outcome = self.outcomes.pop(0)
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome


def gr(**overrides) -> GeneratedReport:
    return GeneratedReport.model_validate(generated_report_dict(**overrides))


def make(outcomes: list) -> tuple[ReportService, FakeReportGenerator]:
    gen = FakeReportGenerator(outcomes)
    return ReportService(gen, settings=test_settings(), content_filter=ContentFilter(["制毒"])), gen


async def test_report_combines_scoring_and_ai_content():
    service, gen = make([gr()])
    report = await service.generate(report_request())
    assert report.accuracy == 80
    assert (report.correct_count, report.total_count) == (4, 5)
    assert report.total_duration_ms == 15000
    assert report.weak_points == ["多选知识点4"]
    assert "单选知识点1" in report.mastered_points
    assert [m.point for m in report.knowledge_mastery][:2] == ["单选知识点1", "单选知识点2"]
    assert report.three_line_summary[0].startswith("RAG")
    assert report.share_quote == "把知识做成关卡，记忆会更深。"
    call = gen.calls[0]
    assert call["topic"] == "RAG 入门"
    assert call["summary"].accuracy == 80


async def test_report_changes_with_answers():
    req = report_request()
    req.answer_records = [record(q.id, ["Z"]) for q in req.questions]
    service, _ = make([gr()])
    report = await service.generate(req)
    assert report.accuracy == 0
    assert report.mastered_points == []
    assert len(report.weak_points) == 5


async def test_extra_lines_are_trimmed():
    service, _ = make([gr(three_line_summary=["一", "二", "三", "四"], advice=["a", "b", "c", "d"])])
    report = await service.generate(report_request())
    assert report.three_line_summary == ["一", "二", "三"]
    assert report.advice == ["a", "b", "c"]


async def test_blank_items_are_dropped_before_validation():
    service, _ = make([gr(three_line_summary=[" 一 ", "", "二", "三"], advice=[" a ", " "])])
    report = await service.generate(report_request())
    assert report.three_line_summary == ["一", "二", "三"]
    assert report.advice == ["a"]


async def test_retries_when_summary_is_incomplete():
    service, gen = make([gr(three_line_summary=["只有一句"]), gr()])
    report = await service.generate(report_request())
    assert len(report.three_line_summary) == 3
    assert len(gen.calls) == 2


@pytest.mark.parametrize("bad", [{"advice": []}, {"share_quote": "  "}])
async def test_retries_on_missing_fields(bad):
    service, gen = make([gr(**bad), gr()])
    await service.generate(report_request())
    assert len(gen.calls) == 2


async def test_retries_when_content_not_allowed():
    service, gen = make([gr(share_quote="制毒也是一门学问"), gr()])
    report = await service.generate(report_request())
    assert "制毒" not in report.share_quote
    assert len(gen.calls) == 2


async def test_fails_after_max_attempts():
    service, gen = make([ValueError("x"), ValueError("y")])
    with pytest.raises(BizError) as e:
        await service.generate(report_request())
    assert e.value.code == ErrorCode.REPORT_GENERATE_FAILED
    assert len(gen.calls) == 2


async def test_invalid_records_fail_fast_without_llm():
    req = report_request()
    req.answer_records.append(record("q99", ["A"]))
    service, gen = make([gr()])
    with pytest.raises(BizError) as e:
        await service.generate(req)
    assert e.value.code == ErrorCode.INVALID_PARAMS
    assert gen.calls == []
