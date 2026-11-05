"""测试用的数据构造器。"""

from app.llm.output_schemas import GeneratedQuiz
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
