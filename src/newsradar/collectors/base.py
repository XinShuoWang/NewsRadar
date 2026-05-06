from __future__ import annotations

from abc import ABC, abstractmethod

from newsradar.models import RawItem, SourceConfig


class BaseCollector(ABC):
    """采集器基类，统一不同来源的解析入口。"""

    def __init__(self, source: SourceConfig) -> None:
        self.source = source

    @abstractmethod
    def collect(self) -> list[RawItem]:
        """抓取并返回标准化条目。"""

