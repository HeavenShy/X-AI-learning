"""复盘报告 Prompt（版本化）。"""

from langchain_core.messages import BaseMessage
from langchain_core.prompts import ChatPromptTemplate

from app.models.quiz import Question
from app.models.report import ScoreSummary

_TYPE_NAMES = {"single": "单选", "multiple": "多选", "judge": "判断"}

_V1_SYSTEM = """你是一名学习复盘教练。用户刚用碎片时间闯完一话知识问答，请根据他真实的答题情况写一份简短复盘。

要求：
- 通过调用工具提交结果，内容是合法 JSON，不要输出 Markdown、代码块或任何额外说明。
- three_line_summary：恰好 3 句，把这一话最该记住的知识串起来，像三格漫画一样有先后，每句不超过 30 字。
- advice：2–3 条下一步建议，必须针对答错的知识点或题型（例如漏选），具体到可以马上去做；全部答对时给进阶方向。
- share_quote：一句适合印在分享海报上的学习金句，不超过 20 字，不要出现分数和排名。
- 语气清晰、鼓励式，但不要空泛的套话。
- 只依据下面给出的题目和答题记录，不要编造没有出现的知识点或结论。"""

_HUMAN = """主题：{topic}
统计结果：答对 {correct_count} 题，共 {total_count} 题，正确率：{accuracy}%，用时 {duration_text}

知识点掌握度：
{mastery_text}

逐题答题记录：
{records_text}"""

REPORT_PROMPT_VERSIONS: dict[str, ChatPromptTemplate] = {
    "report_prompt_v1": ChatPromptTemplate.from_messages([("system", _V1_SYSTEM), ("human", _HUMAN)]),
}

DEFAULT_REPORT_PROMPT = "report_prompt_v1"


def format_duration(ms: int) -> str:
    seconds = round(ms / 1000)
    minutes, sec = divmod(seconds, 60)
    return f"{minutes} 分 {sec} 秒" if minutes else f"{sec} 秒"


def _keys_text(keys: list[str], q: Question) -> str:
    if not keys:
        return "未作答"
    texts = {o.key: o.text for o in q.options}
    if q.type == "judge":
        return "、".join(texts.get(k, k) for k in keys)
    return "、".join(keys)


def _records_text(questions: list[Question], summary: ScoreSummary) -> str:
    by_id = {r.question_id: r for r in summary.results}
    blocks = []
    for i, q in enumerate(questions, start=1):
        r = by_id[q.id]
        options = "；".join(f"{o.key}. {o.text}" for o in q.options)
        blocks.append(
            f"{i}.【{_TYPE_NAMES[q.type]}】{q.stem}\n"
            f"   选项：{options}\n"
            f"   知识点：{q.knowledge_point}\n"
            f"   正确答案：{_keys_text(q.answer, q)}；你的选择：{_keys_text(r.selected_answers, q)}；"
            f"{'答对' if r.is_correct else '答错'}；用时 {format_duration(r.duration_ms)}"
        )
    return "\n".join(blocks)


def report_prompt_variables(*, topic: str, questions: list[Question], summary: ScoreSummary) -> dict[str, str | int]:
    return {
        "topic": topic,
        "correct_count": summary.correct_count,
        "total_count": summary.total_count,
        "accuracy": summary.accuracy,
        "duration_text": format_duration(summary.total_duration_ms),
        "mastery_text": "\n".join(f"- {m.point}：{m.accuracy}%" for m in summary.knowledge_mastery),
        "records_text": _records_text(questions, summary),
    }


def build_report_messages(
    version: str, *, topic: str, questions: list[Question], summary: ScoreSummary
) -> list[BaseMessage]:
    variables = report_prompt_variables(topic=topic, questions=questions, summary=summary)
    return REPORT_PROMPT_VERSIONS[version].format_messages(**variables)
