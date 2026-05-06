from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from newsradar.models import RawItem


def parse_semantic_scholar_text(source_name: str, json_text: str, source_kind: str = "paper") -> list[RawItem]:
    """解析 Semantic Scholar paper search 响应，并返回统一的原始条目。"""

    payload = json.loads(json_text or "{}")
    papers = payload.get("data", [])
    if not isinstance(papers, list):
        return []

    items: list[RawItem] = []
    for paper in papers:
        if not isinstance(paper, dict):
            continue

        title = _as_str(paper.get("title"))
        url = _pick_semantic_scholar_url(paper)
        if not title or not url:
            continue

        items.append(
            RawItem(
                source_name=source_name,
                source_kind=source_kind,
                title=title,
                url=url,
                published_at=_parse_date_text(paper.get("publicationDate")),
                summary=_as_str(paper.get("abstract")) or title,
                authors=_extract_semantic_scholar_authors(paper),
            )
        )
    return items


def _pick_semantic_scholar_url(paper: dict[str, Any]) -> str:
    external_ids = paper.get("externalIds")
    if isinstance(external_ids, dict):
        doi = _as_str(external_ids.get("DOI"))
        if doi:
            return f"https://doi.org/{doi}"

        arxiv = _as_str(external_ids.get("ArXiv"))
        if arxiv:
            return f"https://arxiv.org/abs/{arxiv}"

    open_access_pdf = paper.get("openAccessPdf")
    if isinstance(open_access_pdf, dict):
        pdf_url = _as_str(open_access_pdf.get("url"))
        if pdf_url:
            return pdf_url

    return _as_str(paper.get("url"))


def _extract_semantic_scholar_authors(paper: dict[str, Any]) -> list[str]:
    authors = paper.get("authors", [])
    if not isinstance(authors, list):
        return []

    names: list[str] = []
    for author in authors:
        if not isinstance(author, dict):
            continue
        name = _as_str(author.get("name"))
        if name:
            names.append(name)
    return names


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
