"""attach_sources：出处编号对回本次材料、摘录校验（离线）。"""

import pytest

from app.llm.output_schemas import GeneratedKbQuiz, GeneratedQuestion, GeneratedQuiz
from app.prompts.kb_quiz_prompt import MaterialPiece
from app.services.kb_materials import attach_sources
from app.services.quiz_validator import QuizValidationError, normalize_quiz
from tests.factories import kb_quiz_dict

PIECES = [
    MaterialPiece(1, 101, "doc_a", "员工手册.pdf", 3, "员工出差后 30 天内提交报销申请。超过期限的不予报销。"),
    MaterialPiece(2, 102, "doc_a", "员工手册.pdf", 4, "5000 元以下由部门经理审批。"),
    MaterialPiece(3, 103, "doc_b", "考勤.docx", None, "每天九点前打卡，迟到三次扣半天工资。" + "补充说明" * 60),
    MaterialPiece(4, 104, "doc_b", "考勤.docx", None, "请假需提前一天在系统里申请。"),
]


def attach(count: int = 3, **kw):
    generated = GeneratedKbQuiz.model_validate(kb_quiz_dict(count, **kw))
    plain = GeneratedQuiz(
        title=generated.title,
        summary=generated.summary,
        questions=[GeneratedQuestion.model_validate(q.model_dump(exclude={"source_ids", "source_quote"})) for q in generated.questions],
    )
    return attach_sources(normalize_quiz(plain, count), generated.questions, PIECES)


def test_valid_source_maps_to_document_and_page():
    content = attach(source_ids=[2], quote="5000 元以下由部门经理审批。")
    src = content.questions[0].sources
    assert [s.model_dump() for s in src] == [
        {"document_id": "doc_a", "document_name": "员工手册.pdf", "page": 4, "quote": "5000 元以下由部门经理审批。"}
    ]
    # 题目其余字段不变
    assert content.questions[0].stem.startswith("第 1 题")


def test_docx_source_has_no_page():
    assert attach(source_ids=[4]).questions[0].sources[0].page is None


def test_all_invalid_ids_fail():
    with pytest.raises(QuizValidationError):
        attach(source_ids=[9])
    with pytest.raises(QuizValidationError):
        attach(source_ids=[])


def test_one_question_without_valid_source_fails_whole_quiz():
    with pytest.raises(QuizValidationError):
        attach(source_ids=lambda i: [1] if i != 2 else [0, 99])


def test_partially_invalid_ids_are_dropped_dedup_and_capped():
    content = attach(source_ids=[9, 2, 2, 1, 0, 3, 4])
    assert [(s.document_id, s.page) for s in content.questions[0].sources] == [
        ("doc_a", 4), ("doc_a", 3), ("doc_b", None),
    ]


def test_quote_matching_ignores_whitespace():
    content = attach(source_ids=[1], quote="员工出差后30天内 提交报销申请。")
    assert content.questions[0].sources[0].quote == "员工出差后30天内 提交报销申请。"


def test_quote_not_in_material_falls_back_to_chunk_start():
    content = attach(source_ids=[1], quote="这句话资料里根本没有")
    assert content.questions[0].sources[0].quote == PIECES[0].text[:120]


def test_too_short_or_empty_quote_falls_back():
    assert attach(source_ids=[1], quote="").questions[0].sources[0].quote == PIECES[0].text
    assert attach(source_ids=[1], quote="报销").questions[0].sources[0].quote == PIECES[0].text


def test_quote_is_at_most_120_chars():
    content = attach(source_ids=[3], quote="不匹配的摘录")
    assert len(content.questions[0].sources[0].quote) == 120
    long_quote = PIECES[2].text[:200]
    assert len(attach(source_ids=[3], quote=long_quote).questions[0].sources[0].quote) == 120


def test_additional_sources_get_their_own_quote():
    content = attach(source_ids=[1, 2], quote="超过期限的不予报销。")
    first, second = content.questions[0].sources
    assert first.quote == "超过期限的不予报销。"
    assert second.quote == PIECES[1].text
