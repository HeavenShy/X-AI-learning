import pytest

from app.prompts.quiz_prompt import QUIZ_PROMPT_VERSIONS, build_quiz_messages, type_plan


@pytest.mark.parametrize(
    "count,expected",
    [
        (3, {"single": 1, "multiple": 1, "judge": 1}),
        (5, {"single": 3, "multiple": 1, "judge": 1}),
        (10, {"single": 6, "multiple": 2, "judge": 2}),
    ],
)
def test_type_plan(count, expected):
    assert type_plan(count) == expected


def test_type_plan_rejects_unsupported_count():
    with pytest.raises(ValueError):
        type_plan(7)


def test_versions_are_registered():
    assert "quiz_prompt_v1" in QUIZ_PROMPT_VERSIONS
    assert "quiz_prompt_v2" in QUIZ_PROMPT_VERSIONS


@pytest.mark.parametrize("version", ["quiz_prompt_v1", "quiz_prompt_v2"])
def test_quiz_prompt_renders_all_requirements(version):
    messages = build_quiz_messages(
        version, user_input="我想学习什么是 RAG", question_count=5, difficulty="mixed"
    )
    assert [m.type for m in messages] == ["system", "human"]
    text = "\n".join(m.content for m in messages)
    assert "我想学习什么是 RAG" in text
    assert "5 道" in text
    assert "单选 3 道" in text and "多选 1 道" in text and "判断 1 道" in text
    assert "A=对" in text and "B=错" in text
    assert "Markdown" in text


def test_user_input_is_delimited_and_not_template_parsed():
    # 用户输入里带花括号不能被当成模板变量
    messages = build_quiz_messages(
        "quiz_prompt_v1", user_input="讲讲 {python} 字典 {{x}}", question_count=3, difficulty="easy"
    )
    human = messages[-1].content
    assert "<material>" in human and "</material>" in human
    assert "讲讲 {python} 字典 {{x}}" in human


def test_conservative_prompt_lists_question_sequence():
    messages = build_quiz_messages("quiz_prompt_v2", user_input="复利", question_count=3, difficulty="mixed")
    text = "\n".join(m.content for m in messages)
    assert "第 1 题：single" in text
    assert "第 2 题：multiple" in text
    assert "第 3 题：judge" in text


@pytest.mark.parametrize(
    "difficulty,needle", [("mixed", "混合"), ("easy", "easy"), ("hard", "hard")]
)
def test_difficulty_hint(difficulty, needle):
    messages = build_quiz_messages("quiz_prompt_v1", user_input="复利", question_count=5, difficulty=difficulty)
    assert needle in messages[0].content
