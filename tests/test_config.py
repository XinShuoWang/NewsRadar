from pathlib import Path

from newsradar.config import load_settings
from newsradar.paths import repo_root


def test_load_settings_reads_paths_and_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_API_KEY", "secret")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setenv("EMAIL_TO", "reader@example.com")

    settings = load_settings(
        official_sources_path=tmp_path / "official.yaml",
    )

    assert settings.llm_enabled is True
    assert settings.llm_model == "gpt-test"
    assert settings.email_to == "reader@example.com"
    assert settings.state_root.as_posix().endswith("state")
    assert settings.llm_prompt_path.as_posix().endswith("config/llm_prompt.yaml")


def test_load_settings_reads_gemini_openai_compatible_env(monkeypatch, tmp_path: Path):
    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/openai/")
    monkeypatch.setenv("LLM_API_KEY", "gemini-secret")
    monkeypatch.setenv("LLM_MODEL", "gemini-3-flash-preview")

    settings = load_settings(
        official_sources_path=tmp_path / "official.yaml",
    )

    assert settings.llm_enabled is True
    assert settings.llm_base_url == "https://generativelanguage.googleapis.com/v1beta/openai/"
    assert settings.llm_api_key == "gemini-secret"
    assert settings.llm_model == "gemini-3-flash-preview"


def test_repo_default_official_sources_path_moves_to_config_directory():
    default_path = repo_root() / "config" / "source.yaml"

    assert default_path.exists()
