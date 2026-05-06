from __future__ import annotations

from email.utils import parsedate_to_datetime
from datetime import datetime, timezone
from typing import Any

import feedparser

from newsradar.models import RawItem


def _extract_author_names(entry: Any) -> list[str]:
    authors: list[str] = []
    for author in getattr(entry, "authors", []) or []:
        if isinstance(author, dict):
            name = author.get("name") or author.get("href") or author.get("email")
        else:
            name = getattr(author, "name", None) or getattr(author, "href", None)
        if name:
            authors.append(name)
    return authors


def _parse_entry_datetime(entry: Any) -> datetime | None:
    for field_name in ("published", "updated"):
        date_text = getattr(entry, field_name, None)
        if not date_text:
            continue
        try:
            return parsedate_to_datetime(date_text)
        except (TypeError, ValueError, IndexError, OverflowError):
            try:
                return datetime.fromisoformat(date_text.replace("Z", "+00:00"))
            except ValueError:
                continue

    for field_name in ("published_parsed", "updated_parsed"):
        parsed_value = getattr(entry, field_name, None)
        if parsed_value is None:
            continue
        try:
            return datetime(*parsed_value[:6], tzinfo=timezone.utc)
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def parse_feed_text(source_name: str, xml_text: str, source_kind: str = "paper") -> list[RawItem]:
    """解析 RSS / Atom 文本，并返回统一的原始条目。"""

    parsed = feedparser.parse(xml_text)
    items: list[RawItem] = []
    for entry in parsed.entries:
        title = getattr(entry, "title", "")
        link = getattr(entry, "link", "")
        summary = getattr(entry, "summary", "") or ""
        items.append(
            RawItem(
                source_name=source_name,
                source_kind=source_kind,
                title=title,
                url=link,
                published_at=_parse_entry_datetime(entry),
                summary=summary,
                authors=_extract_author_names(entry),
            )
        )
    return items
