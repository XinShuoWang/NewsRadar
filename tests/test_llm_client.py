import requests

from newsradar.llm.client import OpenAiCompatibleClient


def test_openai_compatible_client_sends_system_and_user_messages(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": {
                                "status": "ok",
                                "items": [],
                            }
                        }
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("newsradar.llm.client.requests.post", fake_post)

    client = OpenAiCompatibleClient(
        base_url="https://llm.example.com/v1",
        api_key="secret",
        model="gpt-test",
        max_attempts=1,
    )

    result = client.rank(
        {
            "system_prompt": "你是数据库和 OLAP 方向的技术雷达助手。",
            "user_prompt": "请基于候选条目输出 JSON。",
        }
    )

    assert result == {"status": "ok", "items": []}
    assert captured["url"] == "https://llm.example.com/v1/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer secret"}
    assert captured["timeout"] == 600
    assert captured["json"]["model"] == "gpt-test"
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["json"]["messages"] == [
        {"role": "system", "content": "你是数据库和 OLAP 方向的技术雷达助手。"},
        {"role": "user", "content": "请基于候选条目输出 JSON。"},
    ]


def test_openai_compatible_client_supports_gemini_openai_compatible_endpoint(monkeypatch):
    captured = {}

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [
                    {
                        "message": {
                            "content": {
                                "status": "ok",
                                "items": [],
                            }
                        }
                    }
                ]
            }

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return FakeResponse()

    monkeypatch.setattr("newsradar.llm.client.requests.post", fake_post)

    client = OpenAiCompatibleClient(
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/",
        api_key="gemini-secret",
        model="gemini-3-flash-preview",
    )

    result = client.rank(
        {
            "system_prompt": "你是数据库和 OLAP 方向的技术雷达助手。",
            "user_prompt": "请基于候选条目输出 JSON。",
        }
    )

    assert result == {"status": "ok", "items": []}
    assert captured["url"] == "https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"
    assert captured["headers"] == {"Authorization": "Bearer gemini-secret"}
    assert captured["timeout"] == 600
    assert captured["json"]["model"] == "gemini-3-flash-preview"


def test_openai_compatible_client_reports_timeout(monkeypatch):
    def fake_post(url, headers, json, timeout):
        raise requests.Timeout("request timed out")

    monkeypatch.setattr("newsradar.llm.client.requests.post", fake_post)

    client = OpenAiCompatibleClient(
        base_url="https://llm.example.com/v1",
        api_key="secret",
        model="gpt-test",
        max_attempts=1,
    )

    assert client.rank({"user_prompt": "请输出 JSON"}) == {"status": "error", "reason": "timeout"}


def test_openai_compatible_client_reports_http_error(monkeypatch):
    class FakeResponse:
        status_code = 429
        text = "quota exceeded"

        def raise_for_status(self):
            raise requests.HTTPError("429 Client Error", response=self)

    def fake_post(url, headers, json, timeout):
        return FakeResponse()

    monkeypatch.setattr("newsradar.llm.client.requests.post", fake_post)

    client = OpenAiCompatibleClient(
        base_url="https://llm.example.com/v1",
        api_key="secret",
        model="gpt-test",
        max_attempts=1,
    )

    assert client.rank({"user_prompt": "请输出 JSON"}) == {"status": "error", "reason": "http_429"}


def test_openai_compatible_client_retries_http_errors(monkeypatch):
    attempts = []

    class ErrorResponse:
        status_code = 503

        def raise_for_status(self):
            raise requests.HTTPError("503 Server Error", response=self)

    class SuccessResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": {"status": "ok", "items": []}}}]}

    def fake_post(url, headers, json, timeout):
        attempts.append(url)
        if len(attempts) < 3:
            return ErrorResponse()
        return SuccessResponse()

    sleep_calls = []

    monkeypatch.setattr("newsradar.llm.client.requests.post", fake_post)
    monkeypatch.setattr("newsradar.llm.client.time.sleep", sleep_calls.append)

    client = OpenAiCompatibleClient(
        base_url="https://llm.example.com/v1",
        api_key="secret",
        model="gpt-test",
    )

    assert client.rank({"user_prompt": "请输出 JSON"}) == {"status": "ok", "items": []}
    assert len(attempts) == 3
    assert sleep_calls == [300.0, 300.0]


def test_openai_compatible_client_uses_five_attempts_by_default(monkeypatch):
    attempts = []

    class ErrorResponse:
        status_code = 503

        def raise_for_status(self):
            raise requests.HTTPError("503 Server Error", response=self)

    def fake_post(url, headers, json, timeout):
        attempts.append(url)
        return ErrorResponse()

    sleep_calls = []

    monkeypatch.setattr("newsradar.llm.client.requests.post", fake_post)
    monkeypatch.setattr("newsradar.llm.client.time.sleep", sleep_calls.append)

    client = OpenAiCompatibleClient(
        base_url="https://llm.example.com/v1",
        api_key="secret",
        model="gpt-test",
    )

    assert client.rank({"user_prompt": "请输出 JSON"}) == {"status": "error", "reason": "http_503"}
    assert len(attempts) == 5
    assert sleep_calls == [300.0, 300.0, 300.0, 300.0]


def test_openai_compatible_client_reports_invalid_content_json(monkeypatch):
    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {"choices": [{"message": {"content": "not json"}}]}

    def fake_post(url, headers, json, timeout):
        return FakeResponse()

    monkeypatch.setattr("newsradar.llm.client.requests.post", fake_post)

    client = OpenAiCompatibleClient(
        base_url="https://llm.example.com/v1",
        api_key="secret",
        model="gpt-test",
        max_attempts=1,
    )

    assert client.rank({"user_prompt": "请输出 JSON"}) == {"status": "error", "reason": "invalid_content_json"}


def test_openai_compatible_client_retries_invalid_content_json(monkeypatch):
    attempts = []

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            attempts.append("json")
            if len(attempts) < 3:
                return {"choices": [{"message": {"content": "not json"}}]}
            return {"choices": [{"message": {"content": {"status": "ok", "items": []}}}]}

    def fake_post(url, headers, json, timeout):
        return FakeResponse()

    sleep_calls = []

    monkeypatch.setattr("newsradar.llm.client.requests.post", fake_post)
    monkeypatch.setattr("newsradar.llm.client.time.sleep", sleep_calls.append)

    client = OpenAiCompatibleClient(
        base_url="https://llm.example.com/v1",
        api_key="secret",
        model="gpt-test",
    )

    assert client.rank({"user_prompt": "请输出 JSON"}) == {"status": "ok", "items": []}
    assert len(attempts) == 3
    assert sleep_calls == [300.0, 300.0]
