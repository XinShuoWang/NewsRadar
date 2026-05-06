import logging
from datetime import date, datetime
from pathlib import Path
from textwrap import dedent

from newsradar.app import build_daily_digest
from newsradar.collectors.service import collect_raw_items
from newsradar.llm.service import build_llm_runner
from newsradar.main import main
from newsradar.models import LlmPipelineResult, RawItem, RankedItem, SourceConfig


def test_build_daily_digest_success_path(tmp_path):
    items = [
        RawItem(
            source_name="arxiv-db",
            source_kind="paper",
            title="Memory governance for query engines",
            url="https://example.com/paper",
            published_at=datetime(2026, 4, 17, 9, 0, 0),
            summary="paper summary",
            authors=["Ada Lovelace", "Grace Hopper"],
        )
    ]
    llm_result = LlmPipelineResult(
        status="ok",
        items=[
            RankedItem(
                url="https://example.com/paper",
                score=0.95,
                tags=["memory", "execution"],
                summary_zh="讨论查询引擎内存治理。",
                why_it_matters_zh="帮助理解内存准入与 spill 控制。",
                is_relevant=True,
                is_duplicate=False,
            )
        ],
    )

    result = build_daily_digest(
        run_date=date(2026, 4, 17),
        collected_items=items,
        llm_runner=lambda value: llm_result,
    )

    assert result.llm_available is True

    assert result.email_subject == "[NewsRadar] 2026-04-17 每日技术情报"
    assert result.email_body == (
        "今天的 NewsRadar 已生成。\n"
        "\n"
        "今日抓取 1 条候选，LLM 精选 1 条。\n"
        "\n"
        "精选内容：\n"
        "- 讨论查询引擎内存治理。（https://example.com/paper）"
    )


def test_full_daily_run_fixture(tmp_path):
    from datetime import date, datetime

    from newsradar.app import build_daily_digest
    from newsradar.models import RawItem

    items = [
        RawItem(
            source_name="engine-blog",
            source_kind="blog",
            title="Spill tuning in a vectorized engine",
            url="https://example.com/blog",
            published_at=datetime(2026, 4, 17, 8, 30, 0),
            summary="blog summary",
        )
    ]

    result = build_daily_digest(
        run_date=date(2026, 4, 17),
        collected_items=items,
        llm_runner=lambda value: type("Result", (), {
            "status": "ok",
            "items": [type("Ranked", (), {
                "score": 0.92,
                "tags": ["spill", "engine"],
                "summary_zh": "介绍向量化执行引擎中的 spill 调优经验。",
                "why_it_matters_zh": "有助于优化内存与吞吐。",
                "is_relevant": True,
                "is_duplicate": False,
                "url": "https://example.com/blog",
            })()],
        })(),
    )

    assert "[LLM 不可用]" not in result.email_subject


def test_build_daily_digest_llm_unavailable_path(tmp_path):
    llm_result = LlmPipelineResult(status="unavailable", error_reason="timeout")
    result = build_daily_digest(
        run_date=date(2026, 4, 17),
        collected_items=[],
        llm_runner=lambda value: llm_result,
    )
    assert result.llm_available is False
    assert "LLM 不可用" in result.email_subject

    assert result.email_body == (
        "今天的 NewsRadar 已生成。\n"
        "\n"
        "今日抓取 0 条候选，使用降级路径输出。\n"
        "\n"
        "异常：LLM 降级原因：timeout。"
    )


def test_collect_raw_items_logs_source_progress_and_failures(caplog):
    sources = [
        SourceConfig(
            name="arxiv-db",
            kind="paper",
            url="https://example.com/feed.xml",
            parser="feed",
        ),
        SourceConfig(
            name="broken-blog",
            kind="blog",
            url="https://example.com/broken",
            parser="html",
        ),
    ]
    fixtures = {
        "https://example.com/feed.xml": Path("tests/fixtures/collector/feed_entry.xml").read_text(encoding="utf-8"),
    }

    def fake_fetcher(url: str) -> str:
        if url == "https://example.com/broken":
            raise RuntimeError("network timeout")
        return fixtures[url]

    with caplog.at_level(logging.INFO, logger="newsradar.collectors.service"):
        items, errors = collect_raw_items(sources, fetcher=fake_fetcher)

    assert len(items) == 1
    assert errors == [
        {
            "source_name": "broken-blog",
            "url": "https://example.com/broken",
            "parser": "html",
            "error": "network timeout",
        }
    ]
    assert "开始抓取来源: arxiv-db" in caplog.text
    assert "来源抓取成功: arxiv-db, 新增 1 条" in caplog.text
    assert "开始抓取来源: broken-blog" in caplog.text
    assert "来源抓取失败: broken-blog, parser=html, error=network timeout" in caplog.text


def test_main_logs_key_stages_for_degraded_run(tmp_path, monkeypatch, caplog):
    official_sources = tmp_path / "official.yaml"
    official_sources.write_text("sources: []\n", encoding="utf-8")

    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("EMAIL_TO", "reader@example.com")
    monkeypatch.setattr("newsradar.app.send_email", lambda **kwargs: None)

    with caplog.at_level(logging.INFO, logger="newsradar.main"):
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

    assert exit_code == 0
    assert "开始执行每日日报: run_date=2026-04-17" in caplog.text
    assert "来源加载完成: 0 个" in caplog.text
    assert "开始执行 LLM 流水线: collected_count=0" in caplog.text
    assert "LLM 流水线降级: reason=disabled" in caplog.text
    assert "邮件内容生成完成:" in caplog.text
    assert "准备发送日报邮件:" in caplog.text
    assert "日报邮件发送完成" in caplog.text


def test_main_runs_real_collection_and_llm_path(tmp_path, monkeypatch):
    official_sources = tmp_path / "official.yaml"
    official_sources.write_text(
        dedent(
            """
            sources:
              - name: arxiv-db
                kind: paper
                url: https://example.com/feed.xml
                parser: feed
                enabled: true
              - name: engine-blog
                kind: blog
                url: https://example.com/blog
                parser: html
                enabled: true
              - name: disabled-source
                kind: blog
                url: https://example.com/ignored
                parser: html
                enabled: false
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    sent_payloads: list[dict[str, str]] = []
    llm_inputs: list[list[RawItem]] = []
    fixtures = {
        "https://example.com/feed.xml": Path("tests/fixtures/collector/feed_entry.xml").read_text(encoding="utf-8"),
        "https://example.com/blog": Path("tests/fixtures/collector/blog_index.html").read_text(encoding="utf-8"),
    }

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("EMAIL_TO", "reader@example.com")

    monkeypatch.setattr("newsradar.collectors.service.fetch_url_text", lambda url: fixtures[url])

    def fake_run_llm_pipeline(items, llm_client, prompt_config):
        llm_inputs.append(list(items))
        assert llm_client.model == "gpt-test"
        assert "system_prompt" in prompt_config
        assert "user_prompt_template" in prompt_config
        return LlmPipelineResult(
            status="ok",
            items=[
                RankedItem(
                    url="https://example.com/papers/memory-governance",
                    score=0.95,
                    tags=["memory", "execution"],
                    summary_zh="讨论查询引擎中的内存准入与 spill 控制。",
                    why_it_matters_zh="帮助理解执行器资源治理。",
                    is_relevant=True,
                    is_duplicate=False,
                )
            ],
        )

    monkeypatch.setattr("newsradar.llm.service.run_llm_pipeline", fake_run_llm_pipeline)
    monkeypatch.setattr(
        "newsradar.app.send_email",
        lambda **kwargs: sent_payloads.append(kwargs),
    )

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

    assert exit_code == 0
    assert len(llm_inputs) == 1
    assert len(llm_inputs[0]) == 2
    assert {item.source_name for item in llm_inputs[0]} == {"arxiv-db", "engine-blog"}
    assert sent_payloads[0]["subject"] == "[NewsRadar] 2026-04-17 每日技术情报"
    assert sent_payloads[0]["email_to"] == "reader@example.com"
    assert "讨论查询引擎中的内存准入与 spill 控制。" in sent_payloads[0]["body"]
    assert not (tmp_path / "archive").exists()


def test_build_llm_runner_uses_gemini_openai_compatible_settings(tmp_path, monkeypatch):
    prompt_path = tmp_path / "llm_prompt.yaml"
    prompt_path.write_text(
        dedent(
            """
            system_prompt: |
              你是数据库和 OLAP 方向的技术雷达助手。
            user_prompt_template: |
              请基于候选条目输出 JSON。
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    class Settings:
        llm_enabled = True
        llm_base_url = "https://generativelanguage.googleapis.com/v1beta/openai/"
        llm_api_key = "gemini-secret"
        llm_model = "gemini-3-flash-preview"
        llm_prompt_path = prompt_path

    captured = {}

    def fake_run_llm_pipeline(items, llm_client, prompt_config):
        captured["items"] = list(items)
        captured["base_url"] = llm_client.base_url
        captured["api_key"] = llm_client.api_key
        captured["model"] = llm_client.model
        captured["prompt_config"] = prompt_config
        return LlmPipelineResult(status="ok", items=[])

    monkeypatch.setattr("newsradar.llm.service.run_llm_pipeline", fake_run_llm_pipeline)

    runner = build_llm_runner(Settings())
    result = runner(
        [
            RawItem(
                source_name="engine-blog",
                source_kind="blog",
                title="Vectorized execution update",
                url="https://example.com/blog",
                published_at=datetime(2026, 4, 17, 8, 30, 0),
                summary="summary",
            )
        ]
    )

    assert result.status == "ok"
    assert len(captured["items"]) == 1
    assert captured["base_url"] == "https://generativelanguage.googleapis.com/v1beta/openai"
    assert captured["api_key"] == "gemini-secret"
    assert captured["model"] == "gemini-3-flash-preview"
    assert "system_prompt" in captured["prompt_config"]
    assert "user_prompt_template" in captured["prompt_config"]


def test_main_falls_back_when_llm_disabled_and_marks_email(tmp_path, monkeypatch):
    official_sources = tmp_path / "official.yaml"
    official_sources.write_text(
        dedent(
            """
            sources:
              - name: engine-blog
                kind: blog
                url: https://example.com/blog
                parser: html
                enabled: true
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    sent_payloads: list[dict[str, str]] = []

    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("EMAIL_TO", "reader@example.com")
    monkeypatch.setattr(
        "newsradar.collectors.service.fetch_url_text",
        lambda url: Path("tests/fixtures/collector/blog_index.html").read_text(encoding="utf-8"),
    )
    monkeypatch.setattr(
        "newsradar.app.send_email",
        lambda **kwargs: sent_payloads.append(kwargs),
    )

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

    assert exit_code == 0
    assert sent_payloads[0]["subject"].endswith("[LLM 不可用]")
    assert "异常：LLM 降级原因：disabled。" in sent_payloads[0]["body"]
    assert not (tmp_path / "archive").exists()


def test_main_returns_error_when_email_send_fails_after_persisting_files(tmp_path, monkeypatch):
    official_sources = tmp_path / "official.yaml"
    official_sources.write_text("sources: []\n", encoding="utf-8")

    monkeypatch.setenv("LLM_ENABLED", "false")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("EMAIL_TO", "reader@example.com")

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
    assert not (tmp_path / "archive").exists()
    assert not (tmp_path / "state" / "source_cursors.json").exists()


def test_main_end_to_end_full_cycle_persists_outputs_and_filters_repeated_items(tmp_path, monkeypatch):
    official_sources = tmp_path / "official.yaml"
    official_sources.write_text(
        dedent(
            """
            sources:
              - name: arxiv-db
                kind: paper
                url: https://example.com/feed.xml
                parser: feed
                enabled: true
              - name: engine-blog
                kind: blog
                url: https://example.com/blog
                parser: html
                enabled: true
            """
        ).strip()
        + "\n",
        encoding="utf-8",
    )

    fixtures = {
        "https://example.com/feed.xml": Path("tests/fixtures/collector/feed_entry.xml").read_text(encoding="utf-8"),
        "https://example.com/blog": Path("tests/fixtures/collector/blog_index.html").read_text(encoding="utf-8"),
    }
    sent_payloads: list[dict[str, str]] = []
    llm_inputs: list[list[RawItem]] = []

    monkeypatch.setenv("LLM_ENABLED", "true")
    monkeypatch.setenv("LLM_BASE_URL", "https://llm.example.com")
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL", "gpt-test")
    monkeypatch.setenv("SMTP_HOST", "smtp.gmail.com")
    monkeypatch.setenv("SMTP_PORT", "587")
    monkeypatch.setenv("SMTP_USERNAME", "sender@example.com")
    monkeypatch.setenv("SMTP_PASSWORD", "app-password")
    monkeypatch.setenv("EMAIL_TO", "reader@example.com")
    monkeypatch.setattr("newsradar.collectors.service.fetch_url_text", lambda url: fixtures[url])

    def fake_run_llm_pipeline(items, llm_client, prompt_config):
        llm_inputs.append(list(items))
        assert llm_client.model == "gpt-test"
        assert "system_prompt" in prompt_config
        assert "user_prompt_template" in prompt_config
        if items:
            return LlmPipelineResult(
                status="ok",
                items=[
                    RankedItem(
                        url="https://example.com/papers/memory-governance",
                        score=0.95,
                        tags=["memory", "execution"],
                        summary_zh="讨论查询引擎中的内存准入与 spill 控制。",
                        why_it_matters_zh="帮助理解执行器资源治理。",
                        is_relevant=True,
                        is_duplicate=False,
                    )
                ],
            )
        return LlmPipelineResult(status="ok", items=[])

    monkeypatch.setattr("newsradar.llm.service.run_llm_pipeline", fake_run_llm_pipeline)
    monkeypatch.setattr(
        "newsradar.app.send_email",
        lambda **kwargs: sent_payloads.append(kwargs),
    )

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
    third_exit_code = main(
        [
            "--run-date",
            "2026-04-19",
            "--official-sources-path",
            str(official_sources),
            "--state-root",
            str(tmp_path / "state"),
        ]
    )

    assert first_exit_code == 0
    assert second_exit_code == 0
    assert third_exit_code == 0
    assert [len(items) for items in llm_inputs] == [2, 0, 0]
    assert len(sent_payloads) == 3

    assert sent_payloads[0]["subject"] == "[NewsRadar] 2026-04-17 每日技术情报"
    assert sent_payloads[0]["email_to"] == "reader@example.com"
    assert "精选内容：" in sent_payloads[0]["body"]
    assert "讨论查询引擎中的内存准入与 spill 控制。" in sent_payloads[0]["body"]

    import json

    seen_state = json.loads((tmp_path / "state" / "seen_items.json").read_text(encoding="utf-8"))

    assert "url:https://example.com/papers/memory-governance" in seen_state["seen_items"]["arxiv-db"]["2026-04-19"]
    assert "url:https://example.com/blog/spill-tuning" in seen_state["seen_items"]["engine-blog"]["2026-04-19"]
    assert not (tmp_path / "state" / "source_cursors.json").exists()

    assert "今日抓取 0 条候选，LLM 精选 0 条。" in sent_payloads[1]["body"]
    assert "精选内容：" not in sent_payloads[1]["body"]
    assert not (tmp_path / "archive").exists()
