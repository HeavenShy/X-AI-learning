"""学习结论链：结构化输出契约与提示词里的统计数字（离线 Mock）。"""

from app.llm.insight_chain import LangChainInsightGenerator
from app.llm.langchain_factory import create_chat_model
from app.llm.output_schemas import GeneratedInsight
from app.models.stats import LearningStats, TypeAccuracy
from app.prompts.insight_prompt import insight_prompt_variables
from tests.llm_mock import MockDeepSeek, test_settings, tool_call_response


def _stats(**kw) -> LearningStats:
    base = dict(
        range="week",
        period_label="11 月 2 日 – 8 日",
        total_minutes=46,
        prev_minutes=34,
        bars=[],
        quiz_count=3,
        question_count=15,
        type_accuracy=[
            TypeAccuracy(type="single", correct=8, total=9, accuracy=89),
            TypeAccuracy(type="multiple", correct=1, total=3, accuracy=33),
            TypeAccuracy(type="judge", correct=0, total=0, accuracy=0),
        ],
        multiple_missed=2,
        weak_points=["申购费率", "复利周期"],
    )
    base.update(kw)
    return LearningStats(**base)


def test_prompt_variables_carry_the_numbers():
    v = insight_prompt_variables(_stats())
    assert v["minutes_text"] == "46 分钟，上周 34 分钟"
    assert "多选：答对 1 / 3 题，正确率 33%" in v["types_text"]
    assert "判断：没有做过" in v["types_text"]
    assert v["weak_text"] == "申购费率、复利周期"
    assert insight_prompt_variables(_stats(range="all", prev_minutes=None, weak_points=[]))["minutes_text"] == "46 分钟"
    assert insight_prompt_variables(_stats(weak_points=[]))["weak_text"] == "无"


async def test_insight_chain_contract():
    mock = MockDeepSeek([tool_call_response("GeneratedInsight", {"insight": "多选 3 题错 2 题，都是漏选。"})])
    settings = test_settings()
    llm = create_chat_model(temperature=0.5, max_tokens=400, settings=settings, http_async_client=mock.client())
    result = await LangChainInsightGenerator(llm).generate(stats=_stats())
    assert result == GeneratedInsight(insight="多选 3 题错 2 题，都是漏选。")
    body = mock.requests[0]
    assert body["tool_choice"]["function"]["name"] == "GeneratedInsight"
    assert "多选题漏选（只选对了一部分）次数：2" in body["messages"][-1]["content"]
