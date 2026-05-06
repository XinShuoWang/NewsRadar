import json
from datetime import date, datetime, timezone
from pathlib import Path

from newsradar.collectors import service as collector_service
from newsradar.main import main
from newsradar.storage import (
    IncrementalState,
    apply_incremental_filter,
    build_next_incremental_state,
    persist_incremental_state,
)
from newsradar.models import RawItem


def _item(
    *,
    source_name: str,
    title: str,
    url: str,
    published_at: datetime | None,
) -> RawItem:
    return RawItem(
        source_name=source_name,
        source_kind="paper",
        title=title,
        url=url,
        published_at=published_at,
        summary="summary",
    )


def test_apply_incremental_filter_keeps_only_unseen_items():
    state = IncrementalState(
        seen_items={
            "engine-blog": {
                "2026-04-17": ["url:https://example.com/already-seen"]
            }
        },
    )
    items = [
        _item(
            source_name="arxiv-db",
            title="old item",
            url="https://example.com/old",
            published_at=datetime(2026, 4, 17, 8, 0, tzinfo=timezone.utc),
        ),
        _item(
            source_name="arxiv-db",
            title="new item",
            url="https://example.com/new",
            published_at=datetime(2026, 4, 17, 10, 0, tzinfo=timezone.utc),
        ),
        _item(
            source_name="engine-blog",
            title="already seen",
            url="https://example.com/already-seen",
            published_at=None,
        ),
        _item(
            source_name="engine-blog",
            title="same day duplicate",
            url="https://example.com/duplicate",
            published_at=None,
        ),
        _item(
            source_name="engine-blog",
            title="same day duplicate again",
            url="https://example.com/duplicate",
            published_at=None,
        ),
    ]

    filtered_items, stats = apply_incremental_filter(items, state)

    assert [item.url for item in filtered_items] == [
        "https://example.com/old",
        "https://example.com/new",
        "https://example.com/duplicate",
    ]
    assert stats["dropped_by_history"] == 2


def test_persist_incremental_state_writes_seen_items_only(tmp_path: Path):
    state = IncrementalState(
        seen_items={
            "arxiv-db": {
                "2026-04-17": ["url:https://example.com/a"]
            }
        },
    )

    persist_incremental_state(tmp_path / "state", state)
    seen_path = tmp_path / "state" / "seen_items.json"
    seen_payload = json.loads(seen_path.read_text(encoding="utf-8"))

    assert seen_payload["seen_items"]["arxiv-db"]["2026-04-17"] == ["url:https://example.com/a"]
    assert not (tmp_path / "state" / "source_cursors.json").exists()


def test_build_next_incremental_state_prunes_days_older_than_retention_window():
    previous_state = IncrementalState(
        seen_items={
            "arxiv-db": {
                "2026-03-10": ["url:https://example.com/old"],
                "2026-04-10": ["url:https://example.com/recent"],
            }
        },
    )
    collected_items = [
        _item(
            source_name="arxiv-db",
            title="new item",
            url="https://example.com/new",
            published_at=datetime(2026, 4, 20, 0, 0, tzinfo=timezone.utc),
        )
    ]

    next_state = build_next_incremental_state(
        previous_state,
        collected_items=collected_items,
        filtered_items=collected_items,
        run_date=date(2026, 4, 20),
        seen_retention_days=30,
    )

    assert "2026-03-10" not in next_state.seen_items["arxiv-db"]
    assert next_state.seen_items["arxiv-db"]["2026-04-10"] == ["url:https://example.com/recent"]
    assert next_state.seen_items["arxiv-db"]["2026-04-20"] == ["url:https://example.com/new"]


def test_apply_incremental_filter_only_dedupes_within_same_source():
    state = IncrementalState(
        seen_items={
            "source-a": {
                "2026-04-17": ["url:https://example.com/shared"]
            }
        }
    )
    items = [
        _item(
            source_name="source-b",
            title="shared elsewhere",
            url="https://example.com/shared",
            published_at=None,
        ),
    ]

    filtered_items, stats = apply_incremental_filter(items, state)

    assert [item.url for item in filtered_items] == ["https://example.com/shared"]
    assert stats["dropped_by_history"] == 0


def test_load_incremental_state_drops_legacy_flat_seen_items(tmp_path: Path):
    seen_path = tmp_path / "state" / "seen_items.json"
    seen_path.parent.mkdir(parents=True, exist_ok=True)
    seen_path.write_text(
        json.dumps(
            {
                "seen_items": {
                    "url:https://example.com/legacy": "2026-04-17T10:00:00+00:00",
                }
            }
        ),
        encoding="utf-8",
    )

    from newsradar.storage import load_incremental_state

    state = load_incremental_state(tmp_path / "state")

    assert state.seen_items == {}


def test_main_does_not_advance_incremental_state_when_email_send_fails(tmp_path, monkeypatch):
    official_sources = tmp_path / "official.yaml"
    official_sources.write_text(
        "sources:\n"
        "  - name: arxiv-db\n"
        "    kind: paper\n"
        "    url: https://example.com/feed.xml\n"
        "    parser: feed\n",
        encoding="utf-8",
    )
    feed_text = Path("tests/fixtures/collector/feed_entry.xml").read_text(encoding="utf-8")

    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("EMAIL_TO", "reader@example.com")
    monkeypatch.setattr(collector_service, "fetch_url_text", lambda url: feed_text)

    def failing_send_email(**kwargs):
        raise RuntimeError("smtp down")

    monkeypatch.setattr("newsradar.app.send_email", failing_send_email)

    exit_code = main(
        [
            "--run-date",
            "2026-04-17",
            "--official-sources-path",
            str(official_sources),
            "--state-root",
            str(tmp_path / "state"),
        ]
    )

    assert exit_code == 1
    seen_path = tmp_path / "state" / "seen_items.json"
    assert not seen_path.exists()


def test_main_second_run_only_keeps_incremental_items(tmp_path, monkeypatch):
    official_sources = tmp_path / "official.yaml"
    official_sources.write_text(
        "sources:\n"
        "  - name: arxiv-db\n"
        "    kind: paper\n"
        "    url: https://example.com/feed.xml\n"
        "    parser: feed\n",
        encoding="utf-8",
    )

    first_feed = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Example</title>
    <item>
      <title>First paper</title>
      <link>https://example.com/papers/first</link>
      <description>first summary</description>
      <author>Example Author</author>
      <published>Thu, 17 Apr 2026 09:00:00 GMT</published>
    </item>
  </channel>
</rss>
"""
    second_feed = """<?xml version="1.0" encoding="utf-8"?>
<rss version="2.0">
  <channel>
    <title>Example</title>
    <item>
      <title>First paper</title>
      <link>https://example.com/papers/first</link>
      <description>first summary</description>
      <author>Example Author</author>
      <published>Thu, 17 Apr 2026 09:00:00 GMT</published>
    </item>
    <item>
      <title>Second paper</title>
      <link>https://example.com/papers/second</link>
      <description>second summary</description>
      <author>Example Author</author>
      <published>Fri, 18 Apr 2026 09:00:00 GMT</published>
    </item>
  </channel>
</rss>
"""
    fetch_payloads = [first_feed, second_feed]

    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.delenv("SMTP_HOST", raising=False)
    monkeypatch.delenv("SMTP_PORT", raising=False)
    monkeypatch.delenv("SMTP_USERNAME", raising=False)
    monkeypatch.delenv("SMTP_PASSWORD", raising=False)
    monkeypatch.delenv("EMAIL_TO", raising=False)
    monkeypatch.setattr(collector_service, "fetch_url_text", lambda url: fetch_payloads.pop(0))

    first_exit_code = main(
        [
            "--run-date",
            "2026-04-17",
            "--official-sources-path",
            str(official_sources),
            "--state-root",
            str(tmp_path / "state"),
        ]
    )
    second_exit_code = main(
        [
            "--run-date",
            "2026-04-18",
            "--official-sources-path",
            str(official_sources),
            "--state-root",
            str(tmp_path / "state"),
        ]
    )

    assert first_exit_code == 0
    assert second_exit_code == 0

    seen_state = json.loads((tmp_path / "state" / "seen_items.json").read_text(encoding="utf-8"))

    assert "2026-04-17" not in seen_state["seen_items"]["arxiv-db"]
    assert "url:https://example.com/papers/first" in seen_state["seen_items"]["arxiv-db"]["2026-04-18"]
    assert "url:https://example.com/papers/second" in seen_state["seen_items"]["arxiv-db"]["2026-04-18"]
    assert not (tmp_path / "state" / "source_cursors.json").exists()
    assert not (tmp_path / "archive").exists()
