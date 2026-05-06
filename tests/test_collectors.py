from pathlib import Path
from textwrap import dedent
from datetime import datetime, timezone

from newsradar.collectors.feed import parse_feed_text
from newsradar.collectors.html import parse_html_listing
from newsradar.collectors.openalex import parse_openalex_text
from newsradar.collectors.registry import load_sources
from newsradar.collectors.semanticscholar import parse_semantic_scholar_text


def test_parse_feed_text_returns_raw_items():
    xml_text = Path("tests/fixtures/collector/feed_entry.xml").read_text(encoding="utf-8")
    items = parse_feed_text("arxiv-db", xml_text)
    assert len(items) == 1
    assert items[0].title == "Memory governance for query engines"
    assert items[0].source_kind == "paper"
    assert items[0].url == "https://example.com/papers/memory-governance"
    assert items[0].authors == ["Alice Example"]
    assert items[0].published_at == datetime(2024, 4, 1, 10, 0, tzinfo=timezone.utc)


def test_parse_feed_text_accepts_source_kind_override():
    xml_text = Path("tests/fixtures/collector/feed_entry.xml").read_text(encoding="utf-8")
    items = parse_feed_text("arxiv-db", xml_text, source_kind="blog")

    assert len(items) == 1
    assert items[0].source_kind == "blog"


def test_parse_feed_text_uses_updated_when_published_is_invalid():
    xml_text = dedent(
        """
        <?xml version="1.0" encoding="utf-8"?>
        <rss version="2.0">
          <channel>
            <title>Bad Dates</title>
            <item>
              <title>Broken timestamp</title>
              <link>https://example.com/bad</link>
              <description>Entry with a broken published date.</description>
              <author>Broken Example</author>
              <published>not-a-real-date</published>
              <updated>Tue, 02 Apr 2024 11:00:00 GMT</updated>
            </item>
            <item>
              <title>Healthy timestamp</title>
              <link>https://example.com/good</link>
              <description>Entry that should still be collected.</description>
              <author>Good Example</author>
              <updated>Wed, 03 Apr 2024 12:30:00 GMT</updated>
            </item>
          </channel>
        </rss>
        """
    ).strip()

    items = parse_feed_text("arxiv-db", xml_text)

    assert len(items) == 2
    assert items[0].title == "Broken timestamp"
    assert items[0].published_at == datetime(2024, 4, 2, 11, 0, tzinfo=timezone.utc)
    assert items[1].title == "Healthy timestamp"
    assert items[1].published_at == datetime(2024, 4, 3, 12, 30, tzinfo=timezone.utc)


def test_parse_feed_text_accepts_iso_8601_atom_timestamps():
    xml_text = dedent(
        """
        <?xml version="1.0" encoding="utf-8"?>
        <feed xmlns="http://www.w3.org/2005/Atom">
          <title>Atom Feed</title>
          <entry>
            <title>ISO timestamp entry</title>
            <link href="https://example.com/iso-entry" rel="alternate" type="text/html" />
            <summary>Entry with ISO 8601 published timestamp.</summary>
            <published>2026-05-05T16:38:31Z</published>
            <updated>2026-05-05T16:38:31Z</updated>
          </entry>
        </feed>
        """
    ).strip()

    items = parse_feed_text("atom-source", xml_text)

    assert len(items) == 1
    assert items[0].published_at == datetime(2026, 5, 5, 16, 38, 31, tzinfo=timezone.utc)


def test_parse_html_listing_returns_raw_items():
    html_text = Path("tests/fixtures/collector/blog_index.html").read_text(encoding="utf-8")
    items = parse_html_listing("engine-blog", "blog", html_text)
    assert len(items) == 1
    assert items[0].title == "Spill tuning in a vectorized engine"
    assert items[0].source_kind == "blog"


def test_parse_openalex_text_returns_paper_level_items():
    json_text = dedent(
        """
        {
          "results": [
            {
              "display_name": "Memory governance for query engines",
              "doi": "https://doi.org/10.1000/memory-governance",
              "publication_date": "2026-04-17",
              "abstract_inverted_index": {
                "Memory": [0],
                "governance": [1],
                "for": [2],
                "query": [3],
                "engines": [4]
              },
              "authorships": [
                {"author": {"display_name": "Ada Lovelace"}},
                {"author": {"display_name": "Grace Hopper"}}
              ]
            }
          ]
        }
        """
    ).strip()

    items = parse_openalex_text("openalex-memory", json_text)

    assert len(items) == 1
    assert items[0].title == "Memory governance for query engines"
    assert items[0].url == "https://doi.org/10.1000/memory-governance"
    assert items[0].summary == "Memory governance for query engines"
    assert items[0].authors == ["Ada Lovelace", "Grace Hopper"]
    assert items[0].published_at == datetime(2026, 4, 17, 0, 0)


def test_parse_semantic_scholar_text_prefers_doi_or_pdf_link():
    json_text = dedent(
        """
        {
          "data": [
            {
              "title": "Spill-aware vectorized execution",
              "url": "https://www.semanticscholar.org/paper/abc",
              "abstract": "Discusses memory pressure and spill.",
              "publicationDate": "2026-04-16",
              "externalIds": {"DOI": "10.1000/spill-aware"},
              "authors": [
                {"name": "Leslie Lamport"}
              ]
            },
            {
              "title": "Runtime backpressure in distributed query engines",
              "url": "https://www.semanticscholar.org/paper/def",
              "abstract": "Uses a PDF fallback.",
              "publicationDate": "2026-04-15",
              "openAccessPdf": {"url": "https://example.com/runtime-backpressure.pdf"},
              "authors": [
                {"name": "Barbara Liskov"}
              ]
            }
          ]
        }
        """
    ).strip()

    items = parse_semantic_scholar_text("semantic-scholar-runtime", json_text)

    assert len(items) == 2
    assert items[0].url == "https://doi.org/10.1000/spill-aware"
    assert items[1].url == "https://example.com/runtime-backpressure.pdf"
    assert items[1].authors == ["Barbara Liskov"]


def test_load_sources_skips_disabled_entries(tmp_path: Path):
    config_path = tmp_path / "sources.yaml"
    config_path.write_text(
        """
sources:
  - name: arxiv-db
    kind: paper
    url: https://example.com/feed.xml
    parser: feed
    enabled: true
  - name: old-blog
    kind: blog
    url: https://example.com/blog
    parser: html
    enabled: false
""".strip()
        + "\n",
        encoding="utf-8",
    )

    sources = load_sources(config_path)

    assert len(sources) == 1
    assert sources[0].name == "arxiv-db"
    assert sources[0].parser == "feed"


def test_official_sources_use_arxiv_openalex_and_semantic_scholar_for_papers():
    sources = load_sources(Path("config/source.yaml"))
    source_names = {source.name for source in sources}

    assert "arxiv-db-systems-memory" in source_names
    assert "arxiv-db-recent" in source_names
    assert "arxiv-dc-execution-memory" in source_names
    assert "openalex-systems-memory" in source_names
    assert "openalex-db-execution" in source_names
    assert "semantic-scholar-systems-memory" in source_names
    assert "semantic-scholar-db-engine" in source_names
    assert not any(name.startswith("dblp-") for name in source_names)
