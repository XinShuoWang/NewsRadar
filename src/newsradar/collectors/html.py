from __future__ import annotations

from bs4 import BeautifulSoup

from newsradar.models import RawItem


def parse_html_listing(source_name: str, source_kind: str, html_text: str) -> list[RawItem]:
    """解析博客或列表页，把文章条目标准化为原始数据。"""

    soup = BeautifulSoup(html_text, "html.parser")
    items: list[RawItem] = []
    seen_urls: set[str] = set()
    article_nodes = soup.select("article.post") or soup.select("article")
    for node in article_nodes:
        link = _find_article_link(node)
        if link is None:
            continue
        url = link.get("href", "").strip()
        title = link.get_text(strip=True)
        if not url or not title or url in seen_urls:
            continue
        seen_urls.add(url)

        summary_node = node.select_one("p.summary")
        if summary_node is None:
            summary_node = node.select_one("div.summary")
        if summary_node is None:
            summary_node = _find_summary_paragraph(node, link)

        items.append(
            RawItem(
                source_name=source_name,
                source_kind=source_kind,
                title=title,
                url=url,
                published_at=None,
                summary=summary_node.get_text(" ", strip=True) if summary_node else "",
            )
        )
    return items


def _find_article_link(node):
    """尽量从真实博客卡片结构中提取文章链接。"""

    selectors = (
        "a.title",
        "h1 a",
        "h2 a",
        "h3 a",
        "h4 a",
        "header a",
    )
    for selector in selectors:
        link = node.select_one(selector)
        if link is not None and link.get("href"):
            return link
    return None


def _find_summary_paragraph(node, link):
    """回退提取文章摘要段落，避免真实页面完全取不到摘要。"""

    for paragraph in node.select("p"):
        if paragraph.find_parent("a") is not None and paragraph.find_parent("a") == link:
            continue
        text = paragraph.get_text(" ", strip=True)
        if text:
            return paragraph
    return None
