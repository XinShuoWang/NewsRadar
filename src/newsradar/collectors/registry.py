from __future__ import annotations

from pathlib import Path

import yaml

from newsradar.models import SourceConfig


def load_sources(path: str | Path) -> list[SourceConfig]:
    """从 YAML 注册表加载启用中的来源配置。"""

    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    sources = payload.get("sources", [])
    return [SourceConfig(**item) for item in sources if item.get("enabled", True)]

