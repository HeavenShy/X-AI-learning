"""测试用的数据构造器。"""

from app.llm.output_schemas import GeneratedKbQuiz, GeneratedQuiz
from app.prompts.quiz_prompt import type_plan


def single_q(n: int, answer: str = "A", kp: str = "知识点") -> dict:
    return {
        "type": "single",
        "stem": f"第 {n} 题：RAG 里的 R 指什么？",
        "options": [
            {"key": "A", "text": "检索（Retrieval）"},
            {"key": "B", "text": "推理（Reasoning）"},
            {"key": "C", "text": "排序（Ranking）"},
            {"key": "D", "text": "改写（Rewrite）"},
        ],
        "answer": [answer],
        "explanation": "RAG 全称 Retrieval-Augmented Generation，先检索再生成。",
        "knowledge_point": kp,
        "difficulty": "easy",
    }


def multiple_q(n: int, answer: list[str] | None = None, kp: str = "RAG 的优势与边界") -> dict:
    return {
        "type": "multiple",
        "stem": f"第 {n} 题：下面哪些是 RAG 的优势？",
        "options": [
            {"key": "A", "text": "能用上最新的外部资料"},
            {"key": "B", "text": "回答从此完全不会出错"},
            {"key": "C", "text": "回答可以追溯到出处"},
            {"key": "D", "text": "不需要准备任何资料"},
        ],
        "answer": answer or ["A", "C"],
        "explanation": "B 错在“完全”。\nA 该选：资料更新了，答案也跟着更新。",
        "knowledge_point": kp,
        "difficulty": "medium",
    }


def judge_q(n: int, truth: bool = False, kp: str = "RAG 和模型训练的关系") -> dict:
    return {
        "type": "judge",
        "stem": f"第 {n} 题：用了 RAG 之后，大模型就不再需要任何训练了。",
        "options": [{"key": "A", "text": "对"}, {"key": "B", "text": "错"}],
        "answer": ["A" if truth else "B"],
        "explanation": "RAG 不替代训练，模型本身仍需要预训练。",
        "knowledge_point": kp,
        "difficulty": "hard",
    }


def quiz_dict(count: int = 5) -> dict:
    plan = type_plan(count)
    questions: list[dict] = []
    n = 1
    for _ in range(plan["single"]):
        questions.append(single_q(n, kp=f"单选知识点{n}"))
        n += 1
    for _ in range(plan["multiple"]):
        questions.append(multiple_q(n, kp=f"多选知识点{n}"))
        n += 1
    for _ in range(plan["judge"]):
        questions.append(judge_q(n, kp=f"判断知识点{n}"))
        n += 1
    return {"title": "RAG 入门", "summary": "RAG 是什么、怎么分工、和搜索的区别。", "questions": questions}


def generated_quiz(count: int = 5) -> GeneratedQuiz:
    return GeneratedQuiz.model_validate(quiz_dict(count))


def kb_quiz_dict(count: int = 5, *, source_ids=None, quote: str = "") -> dict:
    """知识库出题的模型输出：在文本题基础上每题带 source_ids / source_quote。

    source_ids 为 None 时每题都标片段 1；也可以传一个函数 (题序号从 0 起) -> list[int]。
    """
    data = quiz_dict(count)
    for i, q in enumerate(data["questions"]):
        ids = [1] if source_ids is None else (source_ids(i) if callable(source_ids) else list(source_ids))
        q["source_ids"] = ids
        q["source_quote"] = quote
    return data


def generated_kb_quiz(count: int = 5, **kw) -> GeneratedKbQuiz:
    return GeneratedKbQuiz.model_validate(kb_quiz_dict(count, **kw))
