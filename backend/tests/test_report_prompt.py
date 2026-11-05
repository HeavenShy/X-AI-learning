from app.prompts.report_prompt import REPORT_PROMPT_VERSIONS, build_report_messages
from app.services.scoring_service import score
from tests.report_factories import report_request


def _messages():
    req = report_request()
    summary = score(req.questions, req.answer_records)
    return build_report_messages("report_prompt_v1", topic=req.topic, questions=req.questions, summary=summary)


def test_version_registered():
    assert "report_prompt_v1" in REPORT_PROMPT_VERSIONS


def test_report_prompt_contains_real_answer_data():
    messages = _messages()
    assert [m.type for m in messages] == ["system", "human"]
    human = messages[-1].content
    assert "RAG 入门" in human
    assert "正确率：80%" in human
    assert "答对 4 题，共 5 题" in human
    # 逐题记录：题干、正确答案、用户选择、对错
    assert "下面哪些是 RAG 的优势" in human
    assert "正确答案：A、C" in human
    assert "你的选择：B、C" in human
    assert "答错" in human and "答对" in human
    # 知识点掌握度
    assert "多选知识点4：0%" in human


def test_report_prompt_rules():
    system = _messages()[0].content
    assert "鼓励" in system
    assert "不要编造" in system
    assert "Markdown" in system


def test_braces_in_user_content_are_safe():
    req = report_request()
    req.topic = "讲讲 {python} 字典"
    summary = score(req.questions, req.answer_records)
    messages = build_report_messages("report_prompt_v1", topic=req.topic, questions=req.questions, summary=summary)
    assert "讲讲 {python} 字典" in messages[-1].content
