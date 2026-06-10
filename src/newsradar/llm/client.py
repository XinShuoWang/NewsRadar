"""LLM 客户端封装。"""

from __future__ import annotations

import json
import logging
import time

import requests

logger = logging.getLogger(__name__)


class OpenAiCompatibleClient:
    """调用 OpenAI 兼容接口的最小客户端。"""

    def __init__(
        self,
        base_url: str,
        api_key: str,
        model: str,
        timeout_seconds: int = 600,
        max_attempts: int = 5,
        retry_base_delay_seconds: float = 300.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.max_attempts = max(1, int(max_attempts or 1))
        self.retry_base_delay_seconds = max(0.0, float(retry_base_delay_seconds))

    def rank(self, prompt_payload: dict[str, str] | str) -> dict:
        """提交提示词并返回标准化结果。"""

        if isinstance(prompt_payload, str):
            system_prompt = ""
            user_prompt = prompt_payload
        elif isinstance(prompt_payload, dict):
            system_prompt = str(prompt_payload.get("system_prompt", "")).strip()
            user_prompt = str(prompt_payload.get("user_prompt", "")).strip()
        else:
            return {"status": "error", "reason": "invalid_prompt"}

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        if user_prompt:
            messages.append({"role": "user", "content": user_prompt})
        if not messages:
            return {"status": "error", "reason": "invalid_prompt"}

        url = f"{self.base_url}/chat/completions"
        logger.info(
            "LLM 请求开始: model=%s, base_url=%s, timeout=%ss",
            self.model,
            self.base_url,
            self.timeout_seconds,
        )

        result = {"status": "error", "reason": "unknown"}
        for attempt in range(1, self.max_attempts + 1):
            result = self._rank_once(url, messages)
            if result.get("status") == "ok":
                return result
            if attempt >= self.max_attempts or not _is_retryable_reason(result.get("reason")):
                return result

            delay_seconds = self.retry_base_delay_seconds
            logger.warning(
                "LLM 请求失败，准备重试: model=%s, attempt=%s/%s, reason=%s, delay=%ss",
                self.model,
                attempt,
                self.max_attempts,
                result.get("reason", "unknown"),
                delay_seconds,
            )
            time.sleep(delay_seconds)

        return result

    def _rank_once(self, url: str, messages: list[dict[str, str]]) -> dict:
        try:
            response = requests.post(
                url,
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
        except requests.Timeout:
            logger.warning("LLM 请求超时: model=%s, timeout=%ss", self.model, self.timeout_seconds)
            return {"status": "error", "reason": "timeout"}
        except requests.HTTPError as exc:
            status_code = getattr(getattr(exc, "response", None), "status_code", None)
            reason = f"http_{status_code}" if status_code else "http_error"
            logger.warning("LLM HTTP 错误: model=%s, reason=%s", self.model, reason)
            return {"status": "error", "reason": reason}
        except requests.RequestException as exc:
            logger.warning("LLM 请求异常: model=%s, error=%s", self.model, exc.__class__.__name__)
            return {"status": "error", "reason": "request_error"}

        try:
            payload = response.json()
        except ValueError:
            logger.warning("LLM 响应体不是合法 JSON: model=%s", self.model)
            return {"status": "error", "reason": "invalid_response_json"}

        try:
            content = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError):
            logger.warning("LLM 响应缺少 content 字段: model=%s", self.model)
            return {"status": "error", "reason": "missing_content"}

        if isinstance(content, dict):
            parsed_content = content
        else:
            try:
                parsed_content = json.loads(content)
            except (TypeError, json.JSONDecodeError):
                logger.warning("LLM content 不是合法 JSON: model=%s", self.model)
                return {"status": "error", "reason": "invalid_content_json"}

        if not isinstance(parsed_content, dict):
            logger.warning("LLM content JSON 顶层不是对象: model=%s", self.model)
            return {"status": "error", "reason": "invalid_content_schema"}

        status = parsed_content.get("status", "ok")
        if status == "ok":
            items = parsed_content.get("items", [])
            logger.info(
                "LLM 请求完成: model=%s, returned_items=%s",
                self.model,
                len(items) if isinstance(items, list) else "invalid",
            )
            return {
                "status": "ok",
                "items": items,
            }

        reason = parsed_content.get("reason", "unknown")
        logger.warning("LLM 返回错误状态: model=%s, reason=%s", self.model, reason)
        return {"status": "error", "reason": reason}


def _is_retryable_reason(reason: object) -> bool:
    if not isinstance(reason, str):
        return False
    if reason.startswith("http_"):
        return True
    return reason in {
        "timeout",
        "request_error",
        "invalid_response_json",
        "missing_content",
        "invalid_content_json",
    }
