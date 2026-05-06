"""来源抓取与解析服务。"""

from __future__ import annotations

import logging
from collections.abc import Callable

import requests

from newsradar.collectors.feed import parse_feed_text
from newsradar.collectors.html import parse_html_listing
from newsradar.collectors.openalex import parse_openalex_text
from newsradar.collectors.semanticscholar import parse_semantic_scholar_text
from newsradar.models import RawItem, SourceConfig


logger = logging.getLogger(__name__)

Parser = Callable[[SourceConfig, str], list[RawItem]]


def collect_raw_items(
    sources: list[SourceConfig],
    fetcher: Callable[[str], str] | None = None,
) -> tuple[list[RawItem], list[dict[str, str]]]:
    """根据来源配置抓取并解析原始条目。"""

    fetch = fetcher or fetch_url_text
    items: list[RawItem] = []
    errors: list[dict[str, str]] = []

    for source in sources:
        try:
            logger.info("开始抓取来源: %s", source.name)
            text = fetch(source.url)
            parsed_items = parse_source_items(source, text)
            items.extend(parsed_items)
            logger.info("来源抓取成功: %s, 新增 %s 条", source.name, len(parsed_items))
        except Exception as exc:
            error = str(exc) or exc.__class__.__name__
            logger.exception(
                "来源抓取失败: %s, parser=%s, error=%s",
                source.name,
                source.parser,
                error,
            )
            errors.append(
                {
                    "source_name": source.name,
                    "url": source.url,
                    "parser": source.parser,
                    "error": error,
                }
            )

    return items, errors


def parse_source_items(source: SourceConfig, text: str) -> list[RawItem]:
    """按来源声明的 parser 分发到对应解析器。"""

    parser = _parser_registry().get(source.parser)
    if parser is None:
        raise ValueError(f"unsupported_parser:{source.parser}")
    return parser(source, text)


def fetch_url_text(url: str) -> str:
    """抓取 URL 文本内容。"""

    response = requests.get(url, timeout=30)
    response.raise_for_status()
    return response.text


def _parser_registry() -> dict[str, Parser]:
    return {
        "feed": lambda source, text: parse_feed_text(source.name, text, source_kind=source.kind),
        "html": lambda source, text: parse_html_listing(source.name, source.kind, text),
        "openalex": lambda source, text: parse_openalex_text(source.name, text, source_kind=source.kind),
        "semanticscholar": lambda source, text: parse_semantic_scholar_text(
            source.name,
            text,
            source_kind=source.kind,
        ),
    }
