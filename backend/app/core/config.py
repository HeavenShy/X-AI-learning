from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "AI 闯关学习后端"
    app_env: str = "dev"
    api_prefix: str = "/api/v1"

    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"
    llm_timeout_seconds: int = 60

    # H5 本地调试地址；微信小程序请求不受 CORS 限制
    cors_origins: list[str] = ["http://localhost:10086"]


@lru_cache
def get_settings() -> Settings:
    return Settings()
