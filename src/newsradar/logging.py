"""统一日志等级与格式配置。"""

from __future__ import annotations

import logging
from typing import Any


TRACE_LEVEL = 5
_LEVELS = {
    "TRACE": TRACE_LEVEL,
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
}


def parse_log_level(level_name: str) -> int:
    """把外部日志等级名称解析为 logging 等级值。"""

    normalized = str(level_name or "").strip().upper()
    try:
        return _LEVELS[normalized]
    except KeyError as exc:
        raise ValueError(f"unsupported_log_level:{level_name}") from exc


def configure_logging(level_name: str = "INFO", force: bool = False) -> None:
    """配置 CLI 默认日志格式，并注册 TRACE 等级。"""

    _install_trace_level()
    root_logger = logging.getLogger()
    if root_logger.handlers and not force:
        root_logger.setLevel(parse_log_level(level_name))
        return
    logging.basicConfig(
        level=parse_log_level(level_name),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
        force=force,
    )


def _install_trace_level() -> None:
    logging.addLevelName(TRACE_LEVEL, "TRACE")
    if hasattr(logging.Logger, "trace"):
        return

    def trace(self: logging.Logger, message: str, *args: Any, **kwargs: Any) -> None:
        if self.isEnabledFor(TRACE_LEVEL):
            self._log(TRACE_LEVEL, message, args, **kwargs)

    logging.Logger.trace = trace  # type: ignore[attr-defined]
