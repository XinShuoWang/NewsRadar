from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path


@dataclass(slots=True)
class SourceConfig:
    """来源注册表中的一条配置。"""

    name: str
    kind: str
    url: str
    parser: str
    enabled: bool = True


@dataclass(slots=True)
class RawItem:
    """采集器标准化后的原始条目。"""

    source_name: str
    source_kind: str
    title: str
    url: str
    published_at: datetime | None
    summary: str
    authors: list[str] = field(default_factory=list)


@dataclass(slots=True)
class Settings:
    """运行时配置。"""

    llm_enabled: bool
    llm_base_url: str
    llm_api_key: str
    llm_model: str
    smtp_host: str
    smtp_port: int
    smtp_username: str
    smtp_password: str
    email_to: str
    state_root: Path
    official_sources_path: Path
    llm_prompt_path: Path


@dataclass(slots=True)
class RankedItem:
    """LLM 判定后保留下来的候选条目。"""

    url: str
    score: float
    tags: list[str]
    summary_zh: str
    why_it_matters_zh: str
    is_relevant: bool
    is_duplicate: bool


@dataclass(slots=True)
class LlmPipelineResult:
    """LLM 判定流水线的执行结果。"""

    status: str
    items: list[RankedItem] = field(default_factory=list)
    error_reason: str = ""
