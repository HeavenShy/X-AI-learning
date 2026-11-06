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

    # 出题前联网检索（Tavily Search）。Key 为空即关闭检索，按原流程出题
    tavily_api_key: str = ""
    tavily_base_url: str = "https://api.tavily.com"
    # basic 每次 1 credit，advanced 2 credits
    tavily_search_depth: Literal["basic", "advanced"] = "basic"
    tavily_max_results: int = 5
    tavily_timeout_seconds: float = 8.0
    # 进入出题 Prompt 的参考资料：单条摘要上限 / 总长度上限（字符）
    web_reference_item_max_chars: int = 600
    web_reference_max_chars: int = 3000

    # 知识库（RAG）。硅基流动 Key 为空即关闭知识库功能，所有知识库接口返回 5000 / 503
    siliconflow_api_key: str = ""
    siliconflow_base_url: str = "https://api.siliconflow.cn/v1"
    embedding_model: str = "BAAI/bge-m3"
    # bge-m3 输出 1024 维；返回维度不符视为 Embedding 失败
    embedding_dimensions: int = 1024
    # 单次请求的文本条数（硅基流动 /embeddings 的 input 数组上限为 32）
    embedding_batch_size: int = 32
    embedding_timeout_seconds: float = 30.0
    # 相对后端工作目录；backend/data/ 不纳入版本管理
    chroma_path: str = "data/chroma"
    # 上传文件的临时目录，处理结束即删除；启动时清空
    kb_upload_dir: str = "data/uploads"
    kb_max_bases: int = 10
    # 每个用户所有知识库合计的资料数上限
    kb_max_documents: int = 50
    kb_max_file_bytes: int = 20 * 1024 * 1024
    # 提取出的可见字符上限，超过判为“内容太长”
    kb_max_chars: int = 300000
    kb_chunk_chars: int = 500
    kb_chunk_overlap: int = 80
    # 带重点出题时向量检索的片段数
    kb_retrieve_top_k: int = 12
    # 交给模型的材料总长度上限（字符）
    kb_material_max_chars: int = 6000
    # 同时处理的资料数（解析 + 向量化）
    kb_process_concurrency: int = 2

    # 出题前的检索规划 Agent：由模型决定查知识库 / 联网 / 都查 / 都不查。关掉即回到固定规则
    # （首页出题固定联网一次、不查知识库；知识库出题固定取材、不联网）
    agent_retrieval_enabled: bool = True
    # 知识库出题时是否允许 Agent 联网查背景资料（只作背景，不作出题依据）
    agent_web_in_kb_quiz: bool = True
    # 一次请求内：模型调用轮数 / 工具执行总次数 / 其中联网次数（控制 Tavily 用量）
    agent_max_rounds: int = 3
    agent_max_tool_calls: int = 4
    agent_max_web_searches: int = 2
    # 每次知识库检索取的片段数
    agent_kb_top_k: int = 6
    # 整个检索规划的总超时（秒），超时按规划失败处理、退回固定规则
    agent_timeout_seconds: float = 20.0
    agent_temperature: float = 0.1
    agent_max_tokens: int = 800
    # Agent 写的查询词长度上限（字符）
    agent_web_query_max_chars: int = 100
    agent_kb_query_max_chars: int = 200

    # wx.request 不受 CORS 限制，但 wx.loadFontFace 加载字体要求 CORS，小程序来源是 servicewechat.com；
    # localhost:10086 是 H5 本地调试地址
    cors_origins: list[str] = ["https://servicewechat.com", "http://localhost:10086"]

    # MySQL（用户系统持久化）。mysql_database 为空时不连库，所有接口按匿名模式工作
    mysql_host: str = "127.0.0.1"
    mysql_port: int = 3307
    mysql_user: str = "yhyd"
    mysql_password: str = ""
    mysql_database: str = ""
    mysql_pool_min: int = 1
    mysql_pool_max: int = 10
    # 启动时执行 CREATE TABLE IF NOT EXISTS
    mysql_auto_init: bool = True

    # 微信小程序登录（code2Session）
    wechat_app_id: str = ""
    wechat_app_secret: str = ""
    wechat_api_base: str = "https://api.weixin.qq.com"
    wechat_timeout_seconds: float = 8.0

    # JWT
    jwt_secret: str = ""
    jwt_expire_days: int = 30

    @property
    def db_enabled(self) -> bool:
        return bool(self.mysql_database)

    @property
    def web_search_enabled(self) -> bool:
        return bool(self.tavily_api_key)

    @property
    def kb_enabled(self) -> bool:
        """配置了 Embedding Key 才开启知识库；接口可用还要求数据库可用（见 require_kb）。"""
        return bool(self.siliconflow_api_key)

    @property
    def wechat_mock_login(self) -> bool:
        """开发环境没配 AppSecret 时用模拟登录：所有 code 都登录成同一个开发用户。生产环境永远走微信。"""
        return self.app_env == "dev" and not self.wechat_app_secret

    @property
    def jwt_signing_key(self) -> str:
        if self.jwt_secret:
            return self.jwt_secret
        if self.app_env == "dev":
            return "dev-only-insecure-jwt-secret-change-me"
        raise RuntimeError("JWT_SECRET 未配置")


@lru_cache
def get_settings() -> Settings:
    return Settings()
