from datetime import datetime

from pathlib import Path

from newsradar.llm.pipeline import load_prompt_config, run_llm_pipeline
from newsradar.models import RawItem


def test_run_llm_pipeline_returns_ranked_items():
    items = [
        RawItem(
            source_name="arxiv-db",
            source_kind="paper",
            title="Memory governance for query engines",
            url="https://example.com/paper",
            published_at=datetime(2026, 4, 17, 9, 0, 0),
            summary="A paper about memory admission and spill control.",
        )
    ]

    result = run_llm_pipeline(
        items=items,
        llm_client=lambda payload: {
            "status": "ok",
            "items": [
                {
                    "url": "https://example.com/paper",
                    "is_relevant": True,
                    "is_duplicate": False,
                    "score": 0.95,
                    "tags": ["memory", "execution"],
                    "summary_zh": "讨论查询引擎中的内存准入与 spill 控制。",
                    "why_it_matters_zh": "适合关注内存治理与执行器资源控制的工程师。",
                }
            ],
        },
    )

    assert result.status == "ok"
    assert result.items[0].score == 0.95
    assert result.items[0].summary_zh.startswith("讨论查询引擎")


def test_run_llm_pipeline_batches_items_and_merges_ranked_results():
    items = [
        RawItem(
            source_name="arxiv-db",
            source_kind="paper",
            title=f"Memory governance paper {index}",
            url=f"https://example.com/paper-{index}",
            published_at=datetime(2026, 4, 17, 9, index, 0),
            summary="A paper about memory admission and spill control.",
        )
        for index in range(5)
    ]
    batch_titles = []

    def fake_client(payload):
        titles = [
            item.title
            for item in items
            if item.title in payload["user_prompt"]
        ]
        batch_titles.append(titles)
        return {
            "status": "ok",
            "items": [
                {
                    "url": f"https://example.com/selected-{len(batch_titles)}",
                    "is_relevant": True,
                    "is_duplicate": False,
                    "score": 1.0 - len(batch_titles) / 10,
                    "tags": ["memory"],
                    "summary_zh": f"第 {len(batch_titles)} 批摘要。",
                    "why_it_matters_zh": "原因。",
                }
            ],
        }

    result = run_llm_pipeline(items=items, llm_client=fake_client, batch_size=2)

    assert result.status == "ok"
    assert batch_titles == [
        ["Memory governance paper 0", "Memory governance paper 1"],
        ["Memory governance paper 2", "Memory governance paper 3"],
        ["Memory governance paper 4"],
    ]
    assert [item.url for item in result.items] == [
        "https://example.com/selected-1",
        "https://example.com/selected-2",
        "https://example.com/selected-3",
    ]


def test_run_llm_pipeline_logs_batch_failure_reason(caplog):
    items = [
        RawItem(
            source_name="arxiv-db",
            source_kind="paper",
            title=f"Memory governance paper {index}",
            url=f"https://example.com/paper-{index}",
            published_at=datetime(2026, 4, 17, 9, index, 0),
            summary="A paper about memory admission and spill control.",
        )
        for index in range(3)
    ]
    calls = 0

    def fake_client(payload):
        nonlocal calls
        calls += 1
        if calls == 2:
            return {"status": "error", "reason": "timeout"}
        return {"status": "ok", "items": []}

    result = run_llm_pipeline(items=items, llm_client=fake_client, batch_size=2)

    assert result.status == "unavailable"
    assert result.error_reason == "timeout"
    assert "LLM 批次失败: batch=2/2, reason=timeout" in caplog.text


def test_run_llm_pipeline_marks_unavailable_on_failure():
    result = run_llm_pipeline(items=[], llm_client=lambda payload: {"status": "error", "reason": "timeout"})
    assert result.status == "unavailable"
    assert result.error_reason == "timeout"


def test_run_llm_pipeline_marks_unavailable_on_malformed_success_payload():
    result = run_llm_pipeline(
        items=[],
        llm_client=lambda payload: {
            "status": "ok",
            "items": [
                {
                    "url": "https://example.com/paper",
                    "score": 0.95,
                    "tags": ["memory", "execution"],
                    "summary_zh": "讨论查询引擎中的内存准入与 spill 控制。",
                    "why_it_matters_zh": "适合关注内存治理与执行器资源控制的工程师。",
                    "is_relevant": "yes",
                    "is_duplicate": False,
                }
            ],
        },
    )

    assert result.status == "unavailable"


def test_run_llm_pipeline_supports_rank_method_client():
    class RankClient:
        def __init__(self):
            self.prompts = []

        def rank(self, prompt):
            self.prompts.append(prompt)
            return {
                "status": "ok",
                "items": [
                    {
                        "url": "https://example.com/paper",
                        "is_relevant": True,
                        "is_duplicate": False,
                        "score": 0.9,
                        "tags": ["memory"],
                        "summary_zh": "摘要。",
                        "why_it_matters_zh": "原因。",
                    }
                ],
            }

    client = RankClient()
    items = [
        RawItem(
            source_name="arxiv-db",
            source_kind="paper",
            title="Memory governance for query engines",
            url="https://example.com/paper",
            published_at=datetime(2026, 4, 17, 9, 0, 0),
            summary="A paper about memory admission and spill control.",
        )
    ]

    result = run_llm_pipeline(items=items, llm_client=client)

    assert result.status == "ok"
    assert client.prompts
    assert "数据库内核" in client.prompts[0]["system_prompt"]
    assert "Memory governance for query engines" in client.prompts[0]["user_prompt"]
    assert "A paper about memory admission and spill control." in client.prompts[0]["user_prompt"]
    assert "arxiv-db" in client.prompts[0]["user_prompt"]
    assert "paper" in client.prompts[0]["user_prompt"]
    assert "summary_zh" in client.prompts[0]["user_prompt"]
    assert "is_duplicate" in client.prompts[0]["user_prompt"]


def test_run_llm_pipeline_reads_prompt_from_yaml(tmp_path: Path):
    prompt_path = tmp_path / "llm_prompt.yaml"
    prompt_path.write_text(
        (
            "system_prompt: 你是测试系统提示词。\n"
            "user_prompt_template: |\n"
            "  请处理下面的候选条目。\n"
            "  输出字段必须包含 summary_zh。\n"
            "  候选数据：\n"
            "  {items_json}\n"
        ),
        encoding="utf-8",
    )

    class RankClient:
        def __init__(self):
            self.prompts = []

        def rank(self, prompt):
            self.prompts.append(prompt)
            return {"status": "ok", "items": []}

    client = RankClient()
    items = [
        RawItem(
            source_name="openalex-memory",
            source_kind="paper",
            title="Allocator design for OLAP engines",
            url="https://example.com/allocator",
            published_at=datetime(2026, 4, 20, 9, 0, 0),
            summary="Allocator design and runtime memory accounting.",
            authors=["Ada"],
        )
    ]

    result = run_llm_pipeline(items=items, llm_client=client, prompt_config=load_prompt_config(prompt_path))

    assert result.status == "ok"
    assert client.prompts[0]["system_prompt"] == "你是测试系统提示词。"
    assert "请处理下面的候选条目。" in client.prompts[0]["user_prompt"]
    assert "Allocator design for OLAP engines" in client.prompts[0]["user_prompt"]
    assert "summary_zh" in client.prompts[0]["user_prompt"]
