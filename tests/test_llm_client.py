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
    assert captured["timeout"] == 60
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
    assert captured["timeout"] == 60
    assert captured["json"]["model"] == "gemini-3-flash-preview"
