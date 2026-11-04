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


class MockDeepSeek:
    """记录请求体，按顺序返回预设响应。"""

    def __init__(self, responses: list[dict]):
        self._responses = list(responses)
        self.requests: list[dict] = []
        self.paths: list[str] = []

    def _handle(self, request: httpx.Request) -> httpx.Response:
        self.paths.append(request.url.path)
        self.requests.append(json.loads(request.content))
        return httpx.Response(200, json=self._responses.pop(0))

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self._handle))
