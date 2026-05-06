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
