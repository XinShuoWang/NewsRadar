"""LLM 客户端封装。"""

from __future__ import annotations

import json

import requests


class OpenAiCompatibleClient:
    """调用 OpenAI 兼容接口的最小客户端。"""

    def __init__(self, base_url: str, api_key: str, model: str, timeout_seconds: int = 60) -> None:
        self.base_url = base_url.rstrip("/")
        self.api_key = api_key
        self.model = model
        self.timeout_seconds = timeout_seconds

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

        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers={"Authorization": f"Bearer {self.api_key}"},
                json={
                    "model": self.model,
                    "messages": messages,
                    "response_format": {"type": "json_object"},
                },
                timeout=self.timeout_seconds,
            )
            response.raise_for_status()
            payload = response.json()
            content = payload["choices"][0]["message"]["content"]
            if isinstance(content, dict):
                parsed_content = content
            else:
                parsed_content = json.loads(content)
        except (requests.RequestException, KeyError, IndexError, TypeError, ValueError, json.JSONDecodeError):
            return {"status": "error", "reason": "invalid_response"}

        if not isinstance(parsed_content, dict):
            return {"status": "error", "reason": "invalid_response"}

        status = parsed_content.get("status", "ok")
        if status == "ok":
            return {
                "status": "ok",
                "items": parsed_content.get("items", []),
            }

        reason = parsed_content.get("reason", "unknown")
        return {"status": "error", "reason": reason}
