import os
from pathlib import Path

from newsradar.models import Settings


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_settings(
    official_sources_path: Path,
    state_root: Path | None = None,
) -> Settings:
    repo_root = _repo_root()
    return Settings(
        llm_enabled=os.getenv("LLM_ENABLED", "false").lower() == "true",
        llm_base_url=os.getenv("LLM_BASE_URL", ""),
        llm_api_key=os.getenv("LLM_API_KEY", ""),
        llm_model=os.getenv("LLM_MODEL", ""),
        smtp_host=os.getenv("SMTP_HOST", "smtp.gmail.com"),
        smtp_port=_load_int_env("SMTP_PORT", 587),
        smtp_username=os.getenv("SMTP_USERNAME", ""),
        smtp_password=os.getenv("SMTP_PASSWORD", ""),
        email_to=os.getenv("EMAIL_TO", ""),
        state_root=state_root or repo_root / "state",
        official_sources_path=official_sources_path,
        llm_prompt_path=repo_root / "config" / "llm_prompt.yaml",
    )


def _load_int_env(name: str, default: int) -> int:
    value = os.getenv(name, "")
    if not value:
        return default
    try:
        return int(value)
    except ValueError:
        return default
