"""学习数据结论 Prompt（版本化）：只喂确定性统计数字，让模型写一句结论。"""

from langchain_core.prompts import ChatPromptTemplate

from app.models.stats import LearningStats

_TYPE_NAMES = {"single": "单选", "multiple": "多选", "judge": "判断"}
_RANGE_NAMES = {"week": "本周", "month": "本月", "all": "全部时间"}
_PREV_NAMES = {"week": "上周", "month": "上月"}

_V1_SYSTEM = """你是一名学习教练。下面是用户一段时间内用碎片时间做知识问答的统计数据，请写一句放在图表下面的学习结论。

要求：
- 通过调用工具提交结果，不要输出 Markdown 或任何额外说明。
- 一到两句话，不超过 60 字。先点出最容易错的题型或知识点，可以引用给出的数字；再给一个下次马上能做的具体做法（例如多选题把每个选项单独判断一遍）。
- 只依据给出的数字，不要编造没有出现的数据、题目或知识点。
- 各题型都答得很好时，就肯定这一点并给一个进阶方向。
- 语气像朋友提醒，不说空话套话，不出现“加油”“继续努力”之类的口号。"""

_HUMAN = """统计时间段：{range_name}（{period_label}）
完结 {quiz_count} 话，共 {question_count} 题
学习时长：{minutes_text}

各题型正确率：
{types_text}

多选题漏选（只选对了一部分）次数：{multiple_missed}
正确率最低的知识点：{weak_text}"""

INSIGHT_PROMPT_VERSIONS: dict[str, ChatPromptTemplate] = {
    "insight_prompt_v1": ChatPromptTemplate.from_messages([("system", _V1_SYSTEM), ("human", _HUMAN)]),
}

DEFAULT_INSIGHT_PROMPT = "insight_prompt_v1"


def insight_prompt_variables(stats: LearningStats) -> dict[str, str | int]:
    minutes = f"{stats.total_minutes} 分钟"
    if stats.prev_minutes is not None:
        minutes += f"，{_PREV_NAMES[stats.range]} {stats.prev_minutes} 分钟"
    types = "\n".join(
        f"- {_TYPE_NAMES[t.type]}：答对 {t.correct} / {t.total} 题，正确率 {t.accuracy}%"
        if t.total
        else f"- {_TYPE_NAMES[t.type]}：没有做过"
        for t in stats.type_accuracy
    )
    return {
        "range_name": _RANGE_NAMES[stats.range],
        "period_label": stats.period_label,
        "quiz_count": stats.quiz_count,
        "question_count": stats.question_count,
        "minutes_text": minutes,
        "types_text": types,
        "multiple_missed": stats.multiple_missed,
        "weak_text": "、".join(stats.weak_points) or "无",
    }
