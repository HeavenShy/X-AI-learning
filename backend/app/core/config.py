from functools import lru_cache
from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI 闯关学习后端"
    app_env: str = "dev"
    api_prefix: str = "/api/v1"
    log_level: str = "INFO"

    # DeepSeek（OpenAI 兼容接口，经 LangChain ChatOpenAI 调用）
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    # deepseek-flash 默认开启思考模式；思考模式不支持命名 tool_choice，结构化输出必须关闭
    deepseek_thinking: Literal["enabled", "disabled"] = "disabled"
    llm_timeout_seconds: int = 60
    # SDK 层对网络错误的重试次数（业务层另有“换保守 Prompt 重试”）
    llm_http_max_retries: int = 1
    llm_top_p: float = 0.9

    quiz_temperature: float = 0.4
    quiz_max_tokens: int = 8000
    # 首次 + 换保守 Prompt 重试 2 次
    quiz_max_attempts: int = 3

    report_temperature: float = 0.5
    report_max_tokens: int = 2000
    report_max_attempts: int = 2

    input_min_chars: int = 4
    input_max_chars: int = 2000

    # H5 本地调试地址；微信小程序请求不受 CORS 限制
    cors_origins: list[str] = ["http://localhost:10086"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
