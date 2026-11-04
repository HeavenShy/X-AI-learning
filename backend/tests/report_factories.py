from app.models.quiz import Question
from app.models.report import AnswerRecord, ReportGenerateRequest
from app.services.quiz_validator import normalize_quiz
from tests.factories import generated_quiz


def questions(count: int = 5) -> list[Question]:
    return normalize_quiz(generated_quiz(count), count).questions


def record(qid: str, selected: list[str], duration_ms: int = 3000, is_correct: bool = True) -> AnswerRecord:
    return AnswerRecord(question_id=qid, selected_answers=selected, is_correct=is_correct, duration_ms=duration_ms)


def report_request(records: list[AnswerRecord] | None = None, count: int = 5) -> ReportGenerateRequest:
    qs = questions(count)
    if records is None:
        # 默认：第 4 题（多选）答错，其余答对
        records = [record(q.id, list(q.answer)) for q in qs]
        records[3] = record("q4", ["B", "C"], is_correct=False)
    return ReportGenerateRequest(quiz_id="quiz_test", topic="RAG 入门", questions=qs, answer_records=records)


def generated_report_dict(**overrides) -> dict:
    data = {
        "three_line_summary": [
            "RAG 是先检索资料，再让大模型组织回答。",
            "所以答案能更新，也能追溯出处。",
            "但资料本身有错时，它也会跟着错。",
        ],
        "advice": ["再闯一轮“优势与边界”，专挑多选题。", "试着用自己的话讲清 RAG 和搜索引擎的区别。"],
        "share_quote": "把知识做成关卡，记忆会更深。",
    }
    data.update(overrides)
    return data
