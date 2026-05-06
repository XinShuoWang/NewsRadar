from datetime import date
from email.message import EmailMessage

from newsradar.output.email import build_email_body, build_email_subject, send_email


def test_build_email_subject_for_success():
    subject = build_email_subject(date(2026, 4, 17), llm_available=True)
    assert subject == "[NewsRadar] 2026-04-17 每日技术情报"


def test_build_email_subject_for_llm_failure():
    subject = build_email_subject(date(2026, 4, 17), llm_available=False)
    assert subject == "[NewsRadar] 2026-04-17 每日技术情报 [LLM 不可用]"


def test_build_email_body_matches_full_output():
    body = build_email_body(
        summary_line="今日候选 12 条，精选 8 条。",
    )
    assert body == (
        "今天的 NewsRadar 已生成。\n"
        "\n"
        "今日候选 12 条，精选 8 条。"
    )


def test_build_email_body_includes_alert_line():
    body = build_email_body(
        summary_line="今日候选 3 条，使用降级路径输出。",
        alert_line="异常：LLM 未启用，邮件内容来自降级流程。",
    )

    assert body == (
        "今天的 NewsRadar 已生成。\n"
        "\n"
        "今日候选 3 条，使用降级路径输出。\n"
        "\n"
        "异常：LLM 未启用，邮件内容来自降级流程。"
    )


def test_build_email_body_includes_item_titles_and_links():
    body = build_email_body(
        summary_line="今日候选 12 条，精选 2 条。",
        items=[
            {
                "summary": "这篇文章讨论查询引擎里的内存治理与 spill 控制。",
                "url": "https://example.com/paper-a",
            },
            {
                "summary": "这篇文章总结向量化执行中的 spill 感知优化方法。",
                "url": "https://example.com/paper-b",
            },
        ],
    )

    assert body == (
        "今天的 NewsRadar 已生成。\n"
        "\n"
        "今日候选 12 条，精选 2 条。\n"
        "\n"
        "精选内容：\n"
        "- 这篇文章讨论查询引擎里的内存治理与 spill 控制。（https://example.com/paper-a）\n"
        "- 这篇文章总结向量化执行中的 spill 感知优化方法。（https://example.com/paper-b）"
    )


def test_send_email_uses_tls_login_and_send(monkeypatch):
    events: list[tuple[str, object]] = []

    class FakeSmtp:
        def __init__(self, host: str, port: int, timeout: int):
            events.append(("connect", (host, port, timeout)))

        def __enter__(self):
            events.append(("enter", None))
            return self

        def __exit__(self, exc_type, exc, tb):
            events.append(("exit", exc_type))
            return False

        def starttls(self):
            events.append(("starttls", None))

        def login(self, username: str, password: str):
            events.append(("login", (username, password)))

        def send_message(self, message: EmailMessage):
            events.append(("send_message", message))

    monkeypatch.setattr("newsradar.output.email.smtplib.SMTP", FakeSmtp)

    send_email(
        subject="[NewsRadar] 2026-04-17 每日技术情报",
        body="今天的日报已生成。",
        email_to="a@example.com, b@example.com",
        smtp_host="smtp.gmail.com",
        smtp_port=587,
        smtp_username="sender@example.com",
        smtp_password="app-password",
    )

    assert events[0] == ("connect", ("smtp.gmail.com", 587, 30))
    assert ("starttls", None) in events
    assert ("login", ("sender@example.com", "app-password")) in events

    message = next(event[1] for event in events if event[0] == "send_message")
    assert message["From"] == "sender@example.com"
    assert message["To"] == "a@example.com, b@example.com"
    assert message["Subject"] == "[NewsRadar] 2026-04-17 每日技术情报"
    assert "今天的日报已生成。" in message.get_content()
