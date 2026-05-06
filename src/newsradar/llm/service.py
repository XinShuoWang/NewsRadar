"""LLM runner 装配服务。"""

from __future__ import annotations

import logging
from collections.abc import Callable

from newsradar.llm.client import OpenAiCompatibleClient
from newsradar.llm.pipeline import load_prompt_config, run_llm_pipeline
from newsradar.models import LlmPipelineResult, RawItem, Settings


logger = logging.getLogger(__name__)


def build_llm_runner(settings: Settings) -> Callable[[list[RawItem]], LlmPipelineResult]:
    """根据配置构建每日流程使用的 LLM runner。"""

    if not settings.llm_enabled:
        return lambda collected_items: LlmPipelineResult(status="unavailable", error_reason="disabled")

    missing = [
        name
        for name, value in {
            "LLM_BASE_URL": settings.llm_base_url,
            "LLM_API_KEY": settings.llm_api_key,
            "LLM_MODEL": settings.llm_model,
        }.items()
        if not value
    ]
    if missing:
        reason = "missing_config:" + ",".join(missing)
        return lambda collected_items: LlmPipelineResult(status="unavailable", error_reason=reason)

    try:
        prompt_config = load_prompt_config(settings.llm_prompt_path)
    except Exception:
        logger.exception("LLM 提示词配置加载失败: %s", settings.llm_prompt_path)
        return lambda collected_items: LlmPipelineResult(status="unavailable", error_reason="invalid_prompt_config")

    client = OpenAiCompatibleClient(
        base_url=settings.llm_base_url,
        api_key=settings.llm_api_key,
        model=settings.llm_model,
    )
    return lambda collected_items: run_llm_pipeline(
        items=collected_items,
        llm_client=client,
        prompt_config=prompt_config,
    )
