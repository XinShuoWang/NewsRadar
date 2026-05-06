from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from newsradar.models import RawItem


def parse_openalex_text(source_name: str, json_text: str, source_kind: str = "paper") -> list[RawItem]:
    """解析 OpenAlex works 响应，并返回统一的原始条目。"""

    payload = json.loads(json_text or "{}")
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []

    items: list[RawItem] = []
    for work in results:
        if not isinstance(work, dict):
            continue

        title = _as_str(work.get("display_name"))
        url = _pick_openalex_url(work)
        if not title or not url:
            continue

        items.append(
            RawItem(
                source_name=source_name,
                source_kind=source_kind,
                title=title,
                url=url,
                published_at=_parse_date_text(work.get("publication_date")),
                summary=_build_openalex_summary(work, title),
                authors=_extract_openalex_authors(work),
            )
        )
    return items


def _pick_openalex_url(work: dict[str, Any]) -> str:
    doi = _as_str(work.get("doi"))
    if doi:
        return doi

    primary_location = work.get("primary_location")
    if isinstance(primary_location, dict):
        for field_name in ("landing_page_url", "pdf_url"):
            value = _as_str(primary_location.get(field_name))
            if value:
                return value

    best_location = work.get("best_oa_location")
    if isinstance(best_location, dict):
        for field_name in ("landing_page_url", "pdf_url"):
            value = _as_str(best_location.get(field_name))
            if value:
                return value

    return _as_str(work.get("id"))


def _extract_openalex_authors(work: dict[str, Any]) -> list[str]:
    authorships = work.get("authorships", [])
    if not isinstance(authorships, list):
        return []

    authors: list[str] = []
    for authorship in authorships:
        if not isinstance(authorship, dict):
            continue
        author = authorship.get("author")
        if not isinstance(author, dict):
            continue
        display_name = _as_str(author.get("display_name"))
        if display_name:
            authors.append(display_name)
    return authors


def _build_openalex_summary(work: dict[str, Any], title: str) -> str:
    abstract_index = work.get("abstract_inverted_index")
    if isinstance(abstract_index, dict):
        reconstructed = _reconstruct_abstract(abstract_index)
        if reconstructed:
            return reconstructed
    return title


def _reconstruct_abstract(abstract_index: dict[str, Any]) -> str:
    positions: list[tuple[int, str]] = []
    for word, indexes in abstract_index.items():
        if not isinstance(word, str) or not isinstance(indexes, list):
            continue
        for index in indexes:
            if isinstance(index, int):
                positions.append((index, word))
    if not positions:
        return ""
    positions.sort(key=lambda value: value[0])
    return " ".join(word for _, word in positions)


def _parse_date_text(value: Any) -> datetime | None:
    date_text = _as_str(value)
    if not date_text:
        return None
    try:
        return datetime.fromisoformat(date_text.replace("Z", "+00:00"))
    except ValueError:
        return None


def _as_str(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    return ""
