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
