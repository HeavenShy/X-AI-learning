"""题库三级校验：字段完整、题量与题型配比、选项与答案合法；同时做规范化。"""

from collections import Counter

from app.llm.output_schemas import GeneratedQuestion, GeneratedQuiz
from app.models.quiz import Option, Question, QuizContent
from app.prompts.quiz_prompt import type_plan

CHOICE_KEYS = ["A", "B", "C", "D"]
_TRUE_WORDS = {"对", "正确", "是", "√", "✓", "true", "t", "yes", "y", "right"}
_FALSE_WORDS = {"错", "错误", "否", "×", "✗", "x", "false", "f", "no", "n", "wrong"}


TOPIC_MAX_CHARS = 8
DEFAULT_TOPIC = "其他"


class QuizValidationError(ValueError):
    pass


def normalize_topic(raw: str | None) -> str:
    """主题只用于知识树分组：压缩空白、去掉引号书名号、截断，空则归“其他”。从不因主题触发重试。"""
    topic = " ".join((raw or "").split()).strip("“”‘’\"'《》「」")
    return topic[:TOPIC_MAX_CHARS].strip() or DEFAULT_TOPIC


def _require_text(value: str, field: str, where: str) -> str:
    text = (value or "").strip()
    if not text:
        raise QuizValidationError(f"{where}: {field} is empty")
    return text


def _classify_truth(text: str) -> bool | None:
    t = text.strip().lower()
    if t in _TRUE_WORDS:
        return True
    if t in _FALSE_WORDS:
        return False
    return None


def _normalize_choice(q: GeneratedQuestion, where: str) -> tuple[list[Option], list[str]]:
    options = [Option(key=o.key.strip().upper(), text=_require_text(o.text, "option text", where)) for o in q.options]
    keys = [o.key for o in options]
    if sorted(keys) != CHOICE_KEYS:
        raise QuizValidationError(f"{where}: option keys must be A-D, got {keys}")
    if len({o.text for o in options}) != len(options):
        raise QuizValidationError(f"{where}: duplicate option text")
    options.sort(key=lambda o: o.key)

    answer = sorted({a.strip().upper() for a in q.answer})
    if not set(answer) <= set(CHOICE_KEYS):
        raise QuizValidationError(f"{where}: answer {answer} not in options")
    if q.type == "single" and len(answer) != 1:
        raise QuizValidationError(f"{where}: single choice needs exactly 1 answer, got {answer}")
    if q.type == "multiple" and len(answer) < 2:
        raise QuizValidationError(f"{where}: multiple choice needs at least 2 answers, got {answer}")
    return options, answer


def _normalize_judge(q: GeneratedQuestion, where: str) -> tuple[list[Option], list[str]]:
    """判断题统一为 A=对、B=错，并把答案映射过去。"""
    by_key = {o.key.strip().upper(): o.text for o in q.options}
    raw = list(dict.fromkeys(a.strip() for a in q.answer if a.strip()))
    if len(raw) != 1:
        raise QuizValidationError(f"{where}: judge needs exactly 1 answer, got {q.answer}")
    picked = raw[0]
    truth = _classify_truth(by_key[picked.upper()]) if picked.upper() in by_key else _classify_truth(picked)
    if truth is None:
        raise QuizValidationError(f"{where}: cannot tell whether judge answer {picked!r} means true or false")
    return [Option(key="A", text="对"), Option(key="B", text="错")], ["A" if truth else "B"]


def normalize_quiz(quiz: GeneratedQuiz, expected_count: int) -> QuizContent:
    title = _require_text(quiz.title, "title", "quiz")
    summary = _require_text(quiz.summary, "summary", "quiz")

    if len(quiz.questions) != expected_count:
        raise QuizValidationError(f"expected {expected_count} questions, got {len(quiz.questions)}")
    counts = Counter(q.type for q in quiz.questions)
    expected = type_plan(expected_count)
    if {t: counts.get(t, 0) for t in expected} != expected:
        raise QuizValidationError(f"type distribution {dict(counts)} != {expected}")

    questions: list[Question] = []
    for i, q in enumerate(quiz.questions, start=1):
        where = f"q{i}"
        options, answer = _normalize_judge(q, where) if q.type == "judge" else _normalize_choice(q, where)
        questions.append(
            Question(
                id=where,
                type=q.type,
                stem=_require_text(q.stem, "stem", where),
                options=options,
                answer=answer,
                explanation=_require_text(q.explanation, "explanation", where),
                knowledge_point=_require_text(q.knowledge_point, "knowledge_point", where),
                difficulty=q.difficulty,
            )
        )
    return QuizContent(title=title, summary=summary, questions=questions, topic=normalize_topic(quiz.topic))
