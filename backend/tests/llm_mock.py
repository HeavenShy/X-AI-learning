"""用 httpx.MockTransport 模拟 DeepSeek（OpenAI 兼容）接口，离线验证 LangChain 链路。"""

import json
from typing import Any

import httpx

from app.core.config import Settings


def test_settings(**overrides: Any) -> Settings:
    base = dict(
        deepseek_api_key="sk-test",
        deepseek_base_url="https://api.deepseek.com",
        deepseek_model="deepseek-flash",
        deepseek_thinking="disabled",
        llm_http_max_retries=0,
        # 测试离线运行：即使本地 .env 配了搜索 Key 也不联网检索
        tavily_api_key="",
        # 同理：本地 .env 配了 Embedding Key 时测试也不调硅基流动（知识库用例显式打开并注入假实现）
        siliconflow_api_key="",
        # 检索规划 Agent 默认关闭：现有用例按固定规则运行，Agent 用例显式打开
        agent_retrieval_enabled=False,
    )
    base.update(overrides)
    return Settings(**base)


test_settings.__test__ = False  # 不是测试用例


def tool_call_response(tool_name: str, arguments: dict) -> dict:
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": "call_1",
                            "type": "function",
                            "function": {"name": tool_name, "arguments": json.dumps(arguments, ensure_ascii=False)},
                        }
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


def tool_calls_response(calls: list[tuple[str, dict | str]]) -> dict:
    """一条消息里多个工具调用（检索规划 Agent 用）；参数是 str 时原样作为 arguments（可造不合法 JSON）。"""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "deepseek-flash",
        "choices": [
            {
                "index": 0,
                "finish_reason": "tool_calls",
                "message": {
                    "role": "assistant",
                    "content": "",
                    "tool_calls": [
                        {
                            "id": f"call_{i}",
                            "type": "function",
                            "function": {
                                "name": name,
                                "arguments": args if isinstance(args, str) else json.dumps(args, ensure_ascii=False),
                            },
                        }
                        for i, (name, args) in enumerate(calls, start=1)
                    ],
                },
            }
        ],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


def text_response(content: str = "") -> dict:
    """不调用工具、直接结束的回复。"""
    return {
        "id": "chatcmpl-test",
        "object": "chat.completion",
        "created": 0,
        "model": "deepseek-flash",
        "choices": [{"index": 0, "finish_reason": "stop", "message": {"role": "assistant", "content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 10, "total_tokens": 20},
    }


class MockDeepSeek:
    """记录请求体，按顺序返回预设响应（元素是 httpx.Response 时原样返回，可模拟 HTTP 错误）。"""

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.requests: list[dict] = []
        self.paths: list[str] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        self.requests.append(json.loads(request.content))
        response = self._responses.pop(0)
        if isinstance(response, httpx.Response):
            return response
        return httpx.Response(200, json=response)

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))
