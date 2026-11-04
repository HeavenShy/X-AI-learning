"""模型工厂：统一创建对接 DeepSeek 的 ChatOpenAI。"""

from typing import Any

from langchain_openai import ChatOpenAI

from app.core.config import Settings, get_settings


def create_chat_model(
    *,
    temperature: float,
    max_tokens: int,
    settings: Settings | None = None,
    http_async_client: Any | None = None,
) -> ChatOpenAI:
    s = settings or get_settings()
    return ChatOpenAI(
        model=s.deepseek_model,
        base_url=s.deepseek_base_url,
        api_key=s.deepseek_api_key,
        temperature=temperature,
        top_p=s.llm_top_p,
        timeout=s.llm_timeout_seconds,
        max_retries=s.llm_http_max_retries,
        # DeepSeek 走 Chat Completions，显式关闭 Responses API 的自动推断
        use_responses_api=False,
        # ChatOpenAI 会把 max_tokens 改名为 max_completion_tokens，DeepSeek 只认 max_tokens，
        # 所以放进 extra_body 原样透传；thinking 是 DeepSeek 专有参数。
        extra_body={
            "thinking": {"type": s.deepseek_thinking},
            "max_tokens": max_tokens,
        },
        http_async_client=http_async_client,
    )
