"""NewsRadar 每日流程应用服务。"""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from typing import Any

from newsradar.collectors.registry import load_sources
from newsradar.collectors.service import collect_raw_items
from newsradar.llm.pipeline import is_llm_pipeline_success
from newsradar.llm.service import build_llm_runner
from newsradar.models import LlmPipelineResult, RawItem, Settings
from newsradar.output.email import build_email_content, send_email
from newsradar.storage import (
    apply_incremental_filter,
    build_next_incremental_state,
    load_incremental_state,
    persist_incremental_state,
)


logger = logging.getLogger(__name__)


@dataclass(slots=True)
class DailyRunResult:
    """每日运行结果，便于测试和后续输出复用。"""

    llm_available: bool
    email_subject: str
    email_body: str


def run_daily_digest(run_date: date, settings: Settings) -> int:
    """执行一次完整日报流程。"""

    logger.info(
        "开始执行每日日报: run_date=%s, official_sources=%s, state_root=%s",
        run_date.isoformat(),
        settings.official_sources_path,
        settings.state_root,
    )
    sources = load_sources(settings.official_sources_path)
    logger.info("来源加载完成: %s 个", len(sources))
    incremental_state = load_incremental_state(settings.state_root)
    logger.info("增量状态加载完成: seen_items=%s", len(incremental_state.seen_items))
    collected_items, collection_errors = collect_raw_items(sources)
    logger.info("来源抓取完成: items=%s, errors=%s", len(collected_items), len(collection_errors))
    filtered_items, filter_stats = apply_incremental_filter(collected_items, incremental_state)
    logger.info(
        "增量过滤完成: kept=%s, dropped_by_history=%s",
        len(filtered_items),
        filter_stats["dropped_by_history"],
    )

    result = build_daily_digest(
        run_date=run_date,
        collected_items=filtered_items,
        llm_runner=build_llm_runner(settings),
        source_count=len(sources),
        collection_errors=collection_errors,
    )

    if _smtp_ready(settings):
        try:
            logger.info("准备发送日报邮件: to=%s, subject=%s", settings.email_to, result.email_subject)
            send_email(
                subject=result.email_subject,
                body=result.email_body,
                email_to=settings.email_to,
                smtp_host=settings.smtp_host,
                smtp_port=settings.smtp_port,
                smtp_username=settings.smtp_username,
                smtp_password=settings.smtp_password,
            )
        except Exception as exc:
            logger.exception("日报邮件发送失败: %s", exc)
            return 1
        logger.info("日报邮件发送完成")
    else:
        logger.warning("SMTP 配置不完整，跳过邮件发送")

    next_incremental_state = build_next_incremental_state(
        incremental_state,
        collected_items=collected_items,
        filtered_items=filtered_items,
        run_date=run_date,
    )
    persist_incremental_state(settings.state_root, next_incremental_state)
    logger.info("增量状态写入完成")
    return 0


def build_daily_digest(
    run_date: date,
    collected_items: list[RawItem],
    llm_runner: Callable[[list[RawItem]], LlmPipelineResult],
    source_count: int = 0,
    collection_errors: list[dict[str, str]] | None = None,
) -> DailyRunResult:
    """串起日报的 LLM 处理和邮件文案生成。"""

    logger.info("开始执行 LLM 流水线: collected_count=%s", len(collected_items))
    llm_result = llm_runner(collected_items)
    collection_errors = list(collection_errors or [])

    llm_available = is_llm_pipeline_success(llm_result)
    summary_line = _build_summary_line(collected_items, llm_result)
    alert_line = _build_alert_line(llm_result, collection_errors)
    email_items = _build_email_items(collected_items, llm_result)
    email_content = build_email_content(
        run_date=run_date,
        llm_available=llm_available,
        summary_line=summary_line,
        alert_line=alert_line,
        items=email_items,
    )
    if llm_available:
        logger.info("LLM 流水线完成: selected_count=%s", len(getattr(llm_result, "items", [])))
    else:
        logger.warning("LLM 流水线降级: reason=%s", getattr(llm_result, "error_reason", "unknown"))
    logger.info(
        "邮件内容生成完成: subject=%s, source_count=%s, error_count=%s, body_chars=%s",
        email_content.subject,
        source_count,
        len(collection_errors),
        len(email_content.body),
    )

    return DailyRunResult(
        llm_available=llm_available,
        email_subject=email_content.subject,
        email_body=email_content.body,
    )


def _build_email_items(collected_items: list[RawItem], llm_result: Any) -> list[dict[str, str]]:
    if is_llm_pipeline_success(llm_result):
        email_items: list[dict[str, str]] = []
        for ranked_item in getattr(llm_result, "items", []):
            summary = str(getattr(ranked_item, "summary_zh", "")).strip()
            if not summary or not ranked_item.url:
                continue
            email_items.append({"summary": summary, "url": ranked_item.url})
        return email_items

    return [{"title": item.title, "url": item.url} for item in collected_items if item.title and item.url]


def _build_summary_line(collected_items: list[RawItem], llm_result: Any) -> str:
    if is_llm_pipeline_success(llm_result):
        return f"今日抓取 {len(collected_items)} 条候选，LLM 精选 {len(getattr(llm_result, 'items', []))} 条。"
    return f"今日抓取 {len(collected_items)} 条候选，使用降级路径输出。"


def _build_alert_line(llm_result: Any, collection_errors: list[dict[str, str]]) -> str:
    alert_parts: list[str] = []
    if not is_llm_pipeline_success(llm_result):
        reason = getattr(llm_result, "error_reason", "") or "unknown"
        alert_parts.append(f"异常：LLM 降级原因：{reason}。")
    if collection_errors:
        alert_parts.append(f"抓取阶段有 {len(collection_errors)} 个来源异常。")
    return " ".join(alert_parts)


def _smtp_ready(settings: Settings) -> bool:
    return all(
        [
            settings.smtp_host,
            settings.smtp_port,
            settings.smtp_username,
            settings.smtp_password,
            settings.email_to,
        ]
    )
