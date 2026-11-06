import pytest

from app.llm.output_schemas import GeneratedQuiz
from app.services.quiz_validator import QuizValidationError, normalize_quiz
from tests.factories import judge_q, multiple_q, quiz_dict, single_q


def _gen(d: dict) -> GeneratedQuiz:
    return GeneratedQuiz.model_validate(d)


@pytest.mark.parametrize("count", [3, 5, 10])
def test_valid_quiz_passes_and_assigns_ids(count):
    questions = normalize_quiz(_gen(quiz_dict(count)), count).questions
    assert [q.id for q in questions] == [f"q{i}" for i in range(1, count + 1)]


def test_strips_and_uppercases_keys_and_sorts_answers():
    d = quiz_dict(3)
    m = d["questions"][1]
    m["options"] = [{"key": " a ", "text": " 甲 "}, {"key": "b", "text": "乙"}, {"key": "c", "text": "丙"}, {"key": "d", "text": "丁"}]
    m["answer"] = ["c", "a", "A"]
    q = normalize_quiz(_gen(d), 3).questions[1]
    assert [o.key for o in q.options] == ["A", "B", "C", "D"]
    assert q.options[0].text == "甲"
    assert q.answer == ["A", "C"]


@pytest.mark.parametrize(
    "options,answer,expected",
    [
        ([{"key": "A", "text": "对"}, {"key": "B", "text": "错"}], ["B"], ["B"]),
        ([{"key": "A", "text": "正确"}, {"key": "B", "text": "错误"}], ["A"], ["A"]),
        ([{"key": "A", "text": "错误"}, {"key": "B", "text": "正确"}], ["B"], ["A"]),
        ([{"key": "T", "text": "True"}, {"key": "F", "text": "False"}], ["F"], ["B"]),
        ([{"key": "A", "text": "对"}, {"key": "B", "text": "错"}], ["对"], ["A"]),
    ],
)
def test_judge_is_canonicalized(options, answer, expected):
    d = quiz_dict(3)
    d["questions"][2]["options"] = options
    d["questions"][2]["answer"] = answer
    q = normalize_quiz(_gen(d), 3).questions[2]
    assert [(o.key, o.text) for o in q.options] == [("A", "对"), ("B", "错")]
    assert q.answer == expected


def test_title_and_summary_are_trimmed():
    d = quiz_dict(3)
    d["title"] = "  RAG 入门 "
    quiz = normalize_quiz(_gen(d), 3)
    assert quiz.title == "RAG 入门"


def _expect_invalid(d: dict, count: int = 3):
    with pytest.raises(QuizValidationError):
        normalize_quiz(_gen(d), count)


def test_rejects_wrong_question_count():
    d = quiz_dict(3)
    d["questions"].append(single_q(4))
    _expect_invalid(d)


def test_rejects_wrong_type_distribution():
    d = quiz_dict(3)
    d["questions"][1] = single_q(2)  # 两道单选、没有多选
    _expect_invalid(d)


def test_rejects_single_with_two_answers():
    d = quiz_dict(3)
    d["questions"][0]["answer"] = ["A", "B"]
    _expect_invalid(d)


def test_rejects_multiple_with_one_answer():
    d = quiz_dict(3)
    d["questions"][1] = multiple_q(2, answer=["A"])
    _expect_invalid(d)


def test_rejects_answer_not_in_options():
    d = quiz_dict(3)
    d["questions"][0]["answer"] = ["E"]
    _expect_invalid(d)


def test_rejects_duplicate_option_keys():
    d = quiz_dict(3)
    d["questions"][0]["options"][1]["key"] = "A"
    _expect_invalid(d)


def test_rejects_choice_question_without_four_options():
    d = quiz_dict(3)
    d["questions"][0]["options"] = d["questions"][0]["options"][:3]
    _expect_invalid(d)


def test_rejects_non_sequential_option_keys():
    d = quiz_dict(3)
    d["questions"][0]["options"][3]["key"] = "E"
    _expect_invalid(d)


def test_rejects_empty_explanation():
    d = quiz_dict(3)
    d["questions"][0]["explanation"] = "   "
    _expect_invalid(d)


def test_rejects_empty_option_text():
    d = quiz_dict(3)
    d["questions"][0]["options"][2]["text"] = ""
    _expect_invalid(d)


def test_rejects_unrecognizable_judge():
    d = quiz_dict(3)
    d["questions"][2] = judge_q(3)
    d["questions"][2]["options"] = [{"key": "A", "text": "也许"}, {"key": "B", "text": "不一定"}]
    _expect_invalid(d)


def test_rejects_empty_title():
    d = quiz_dict(3)
    d["title"] = " "
    _expect_invalid(d)


# ---------- 主题 ----------


def test_topic_is_normalized_and_never_fails():
    from app.llm.output_schemas import GeneratedQuiz
    from tests.factories import quiz_dict

    assert normalize_quiz(GeneratedQuiz.model_validate({**quiz_dict(5), "topic": " 理财 "}), 5).topic == "理财"
    assert normalize_quiz(GeneratedQuiz.model_validate({**quiz_dict(5), "topic": ""}), 5).topic == "其他"
    assert normalize_quiz(GeneratedQuiz.model_validate(quiz_dict(5)), 5).topic == "其他"


def test_strip_sources_keeps_topic():
    from app.llm.output_schemas import GeneratedKbQuiz
    from app.services.kb_materials import strip_sources
    from tests.factories import kb_quiz_dict

    g = GeneratedKbQuiz.model_validate({**kb_quiz_dict(5), "topic": "职场"})
    plain = strip_sources(g.title, g.summary, g.questions, topic=g.topic)
    assert normalize_quiz(plain, 5).topic == "职场"
