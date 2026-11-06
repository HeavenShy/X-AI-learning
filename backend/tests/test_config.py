from pathlib import Path

from app.core.config import Settings

BACKEND_DIR = Path(__file__).resolve().parent.parent


def test_web_search_is_off_by_default(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    s = Settings(_env_file=None)
    assert s.tavily_api_key == ""
    assert s.web_search_enabled is False
    assert s.tavily_base_url == "https://api.tavily.com"
    assert s.tavily_search_depth == "basic"
    assert s.tavily_max_results == 5
    assert s.tavily_timeout_seconds == 8.0
    assert s.web_reference_item_max_chars == 600
    assert s.web_reference_max_chars == 3000


def test_web_search_turns_on_with_key(monkeypatch):
    monkeypatch.delenv("TAVILY_API_KEY", raising=False)
    assert Settings(_env_file=None, tavily_api_key="tvly-x").web_search_enabled is True


def test_env_example_has_empty_tavily_key():
    lines = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "TAVILY_API_KEY=" in lines


def test_knowledge_base_is_off_by_default(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    s = Settings(_env_file=None)
    assert s.siliconflow_api_key == ""
    assert s.kb_enabled is False
    assert s.siliconflow_base_url == "https://api.siliconflow.cn/v1"
    assert s.embedding_model == "BAAI/bge-m3"
    assert s.embedding_batch_size == 32
    assert s.chroma_path == "data/chroma"
    assert s.kb_upload_dir == "data/uploads"
    assert (s.kb_max_bases, s.kb_max_documents) == (10, 50)
    assert s.kb_max_file_bytes == 20 * 1024 * 1024
    assert s.kb_max_chars == 300000
    assert (s.kb_chunk_chars, s.kb_chunk_overlap) == (500, 80)
    assert (s.kb_retrieve_top_k, s.kb_material_max_chars) == (12, 6000)
    assert s.kb_process_concurrency == 2


def test_knowledge_base_turns_on_with_key(monkeypatch):
    monkeypatch.delenv("SILICONFLOW_API_KEY", raising=False)
    assert Settings(_env_file=None, siliconflow_api_key="sk-sf").kb_enabled is True


def test_env_example_has_empty_siliconflow_key():
    lines = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "SILICONFLOW_API_KEY=" in lines


def test_retrieval_agent_defaults(monkeypatch):
    for name in ("AGENT_RETRIEVAL_ENABLED", "AGENT_WEB_IN_KB_QUIZ"):
        monkeypatch.delenv(name, raising=False)
    s = Settings(_env_file=None)
    assert s.agent_retrieval_enabled is True
    assert s.agent_web_in_kb_quiz is True
    assert (s.agent_max_rounds, s.agent_max_tool_calls, s.agent_max_web_searches) == (3, 4, 2)
    assert s.agent_kb_top_k == 6
    assert s.agent_timeout_seconds == 20.0
    assert (s.agent_temperature, s.agent_max_tokens) == (0.1, 800)
    assert (s.agent_web_query_max_chars, s.agent_kb_query_max_chars) == (100, 200)


def test_retrieval_agent_switches_from_env(monkeypatch):
    monkeypatch.setenv("AGENT_RETRIEVAL_ENABLED", "false")
    monkeypatch.setenv("AGENT_WEB_IN_KB_QUIZ", "false")
    s = Settings(_env_file=None)
    assert (s.agent_retrieval_enabled, s.agent_web_in_kb_quiz) == (False, False)


def test_env_example_lists_agent_switches():
    lines = (BACKEND_DIR / ".env.example").read_text(encoding="utf-8").splitlines()
    assert "AGENT_RETRIEVAL_ENABLED=true" in lines
    assert "AGENT_WEB_IN_KB_QUIZ=true" in lines


def test_test_settings_turn_agent_off():
    from tests.llm_mock import test_settings

    assert test_settings().agent_retrieval_enabled is False
