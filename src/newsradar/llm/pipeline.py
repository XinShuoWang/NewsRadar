"""LLM 判定流水线。"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any

import yaml

from newsradar.models import LlmPipelineResult, RankedItem

logger = logging.getLogger(__name__)
DEFAULT_BATCH_SIZE = 50


def is_llm_pipeline_success(llm_result: Any) -> bool:
    """统一判断 LLM 结果是否成功，仅 `ok` 视为成功。"""

    return getattr(llm_result, "status", "") == "ok"


def load_prompt_config(path: str | Path) -> dict[str, str]:
    """从 YAML 文件读取 LLM 提示词配置。"""

    payload = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
    system_prompt = str(payload.get("system_prompt", "")).strip()
    user_prompt_template = str(payload.get("user_prompt_template", "")).strip()
    if not system_prompt or not user_prompt_template:
        raise ValueError("invalid_prompt_config")
    return {
        "system_prompt": system_prompt,
        "user_prompt_template": user_prompt_template,
    }


def run_llm_pipeline(
    items,
    llm_client,
    prompt_config: dict[str, str] | None = None,
    batch_size: int = DEFAULT_BATCH_SIZE,
):
    """把原始条目送入 LLM，并整理成排序后的结果。"""

    item_list = list(items or [])
    effective_batch_size = max(1, int(batch_size or DEFAULT_BATCH_SIZE))
    batches = list(_iter_batches(item_list, effective_batch_size)) or [[]]
    logger.info(
        "LLM 流水线批处理开始: total_items=%s, batch_size=%s, batches=%s",
        len(item_list),
        effective_batch_size,
        len(batches),
    )

    ranked_items = []
    for batch_index, batch_items in enumerate(batches, start=1):
        payload = _build_prompt_payload(batch_items, prompt_config=prompt_config)
        logger.info(
            "LLM 批次开始: batch=%s/%s, items=%s",
            batch_index,
            len(batches),
            len(batch_items),
        )
        response = _invoke_llm_client(llm_client, payload)
        normalized_response = _normalize_response(response)
        if normalized_response["status"] != "ok":
            reason = normalized_response["reason"]
            logger.warning("LLM 批次失败: batch=%s/%s, reason=%s", batch_index, len(batches), reason)
            return LlmPipelineResult(status="unavailable", error_reason=reason)

        selected_count = 0
        for item in normalized_response["items"]:
            validation_error = _validate_ranked_item_structure(item)
            if validation_error is not None:
                logger.warning(
                    "LLM 批次结果校验失败: batch=%s/%s, reason=%s",
                    batch_index,
                    len(batches),
                    validation_error,
                )
                return LlmPipelineResult(status="unavailable", error_reason=validation_error)

            if item["is_relevant"] and not item["is_duplicate"]:
                selected_validation_error = _validate_selected_ranked_item(item)
                if selected_validation_error is not None:
                    logger.warning(
                        "LLM 已选条目跳过: batch=%s/%s, reason=%s",
                        batch_index,
                        len(batches),
                        selected_validation_error,
                    )
                    continue
                selected_count += 1
                ranked_items.append(
                    RankedItem(
                        url=item["url"],
                        score=float(item["score"]),
                        tags=list(item["tags"]),
                        summary_zh=item["summary_zh"],
                        why_it_matters_zh=item["why_it_matters_zh"],
                        is_relevant=item["is_relevant"],
                        is_duplicate=item["is_duplicate"],
                    )
                )
        logger.info(
            "LLM 批次完成: batch=%s/%s, returned_items=%s, selected_items=%s",
            batch_index,
            len(batches),
            len(normalized_response["items"]),
            selected_count,
        )

    ranked_items.sort(key=lambda current: current.score, reverse=True)
    logger.info("LLM 流水线批处理完成: selected_count=%s", len(ranked_items))
    return LlmPipelineResult(status="ok", items=ranked_items)


def _iter_batches(items: list[Any], batch_size: int):
    for start in range(0, len(items), batch_size):
        yield items[start : start + batch_size]


def _build_prompt_payload(items: Any, prompt_config: dict[str, str] | None = None) -> dict[str, str]:
    """构造发送给 LLM 的系统提示词与用户提示词。"""

    serialized_items = []
    for item in items or []:
        serialized_items.append(
            {
                "source_name": getattr(item, "source_name", ""),
                "source_kind": getattr(item, "source_kind", ""),
                "title": getattr(item, "title", ""),
                "url": getattr(item, "url", ""),
                "published_at": _serialize_datetime(getattr(item, "published_at", None)),
                "summary": getattr(item, "summary", ""),
                "authors": list(getattr(item, "authors", []) or []),
            }
        )

    config = prompt_config or _default_prompt_config()
    system_prompt = config["system_prompt"]
    user_prompt = config["user_prompt_template"].replace(
        "{items_json}",
        json.dumps({"items": serialized_items}, ensure_ascii=False, indent=2),
    )
    return {
        "system_prompt": system_prompt,
        "user_prompt": user_prompt,
    }


def _invoke_llm_client(llm_client: Any, payload: dict[str, str]) -> Any:
    """兼容可调用对象与带 rank 方法的客户端对象。"""

    if hasattr(llm_client, "rank") and callable(getattr(llm_client, "rank")):
        return llm_client.rank(payload)
    if callable(llm_client):
        return llm_client(payload)
    return {"status": "error", "reason": "invalid_client"}


def _normalize_response(response: Any) -> dict[str, Any]:
    """把各种 LLM 返回值收敛成统一结构。"""

    if not isinstance(response, dict):
        return {"status": "error", "reason": "invalid_response_type"}

    status = response.get("status")
    if status != "ok":
        reason = response.get("reason", "unknown")
        if not isinstance(reason, str) or not reason:
            reason = "unknown"
        return {"status": "error", "reason": reason}

    items = response.get("items")
    if not isinstance(items, list):
        return {"status": "error", "reason": "invalid_items"}

    return {"status": "ok", "items": items}


def _validate_ranked_item_structure(item: Any) -> str | None:
    """校验单个条目的通用结构，返回错误原因或 None。"""

    if not isinstance(item, dict):
        return "invalid_item_type"

    if not isinstance(item.get("score"), (int, float)):
        return "invalid_item_score"

    tags = item.get("tags")
    if not isinstance(tags, list) or any(not isinstance(tag, str) for tag in tags):
        return "invalid_item_tags"

    if not isinstance(item.get("is_relevant"), bool):
        return "invalid_item_is_relevant"

    if not isinstance(item.get("is_duplicate"), bool):
        return "invalid_item_is_duplicate"

    return None


def _validate_selected_ranked_item(item: dict[str, Any]) -> str | None:
    """校验进入日报展示的条目字段，返回错误原因或 None。"""

    required_str_fields = ("url", "summary_zh", "why_it_matters_zh")
    for field_name in required_str_fields:
        if not isinstance(item.get(field_name), str) or not item[field_name].strip():
            return f"invalid_item_{field_name}"

    return None


def _serialize_datetime(value: Any) -> str | None:
    """把时间戳统一序列化为 ISO 文本。"""

    if value is None:
        return None
    if hasattr(value, "isoformat"):
        return value.isoformat()
    return str(value)


def _default_prompt_config() -> dict[str, str]:
    """返回内置默认提示词配置。"""

    return {
        "system_prompt": (
            "你是一个数据库内核、OLAP 引擎、大数据执行引擎技术雷达助手。"
            "你的任务是从论文和工程博客中识别与数据库内核 / OLAP / 大数据引擎 / 计算引擎相关的内容，"
            "尤其关注 memory management、spill、allocator、query execution、vectorized execution、runtime、"
            "scheduler、shuffle、sort、aggregation、resource management 等主题。"
            "请只输出 JSON，不要输出任何额外说明。"
        ),
        "user_prompt_template": (
            "下面是候选条目列表，请你完成相关性判断、跨条目重复判断、打标签、打分，并输出固定 JSON。\n"
            "要求：\n"
            "1. score 使用 0 到 1 的浮点数，越高表示越值得进入日报。\n"
            "2. is_relevant 表示是否与数据库内核 / OLAP / 大数据执行引擎相关。\n"
            "3. is_duplicate 表示它是否与本批次其他条目重复。\n"
            "4. summary_zh 和 why_it_matters_zh 必须使用简洁中文。\n"
            "5. tags 应该是简短英文标签，例如 memory、execution、runtime、spill。\n"
            "6. 请返回格式："
            '{"status":"ok","items":[{"url":"","score":0.0,"tags":[],"summary_zh":"","why_it_matters_zh":"","is_relevant":true,"is_duplicate":false}]}\n'
            "候选条目如下：\n"
            "{items_json}"
        ),
    }
