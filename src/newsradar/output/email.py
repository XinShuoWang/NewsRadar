"""邮件标题与正文生成。"""

import smtplib
from dataclasses import dataclass
from datetime import date
from email.message import EmailMessage
from typing import Any


def build_email_subject(run_date: date, llm_available: bool) -> str:
    """生成日报邮件标题。"""

    return _build_email_subject(run_date, llm_available)


def build_email_body(
    summary_line: str,
    alert_line: str = "",
    items: list[dict[str, str]] | None = None,
) -> str:
    """生成日报邮件正文。"""

    return _build_email_body(summary_line, alert_line=alert_line, items=items)


@dataclass(slots=True)
class EmailContent:
    """邮件标题与正文的结构化结果，便于后续任务复用。"""

    subject: str
    body: str


def build_email_content(
    run_date: date | None,
    llm_available: bool,
    summary_line: str,
    alert_line: str = "",
    items: list[dict[str, str]] | None = None,
) -> EmailContent:
    """统一组装邮件文案，避免标题与正文逻辑分散。"""

    return EmailContent(
        subject=_build_email_subject(run_date, llm_available),
        body=_build_email_body(summary_line, alert_line=alert_line, items=items),
    )


def _build_email_subject(run_date: date | None, llm_available: bool) -> str:
    """生成邮件标题。"""

    if run_date is None:
        return ""

    subject = f"[NewsRadar] {run_date.isoformat()} 每日技术情报"
    if not llm_available:
        return f"{subject} [LLM 不可用]"
    return subject


def _build_email_body(
    summary_line: str,
    alert_line: str = "",
    items: list[dict[str, str]] | None = None,
) -> str:
    """生成邮件正文。"""

    lines = build_email_body_lines(
        summary_line=summary_line,
        alert_line=alert_line,
        items=items,
    )
    while lines and lines[-1] == "":
        lines.pop()
    return "\n".join(lines)


def build_email_body_lines(
    summary_line: str,
    alert_line: str = "",
    items: list[dict[str, str]] | None = None,
) -> list[str]:
    """生成邮件正文行列表。"""

    lines = [
        "今天的 NewsRadar 已生成。",
        "",
        summary_line,
        "",
    ]
    if alert_line:
        lines.extend([alert_line, ""])
    lines.extend(render_digest_items(items, section_title="精选内容："))
    return lines


def render_digest_items(items: list[dict[str, Any]] | None, section_title: str = "精选内容：") -> list[str]:
    """渲染精选内容段落，保证不同输出通道格式一致。"""

    rendered_items = _normalize_items(items)
    if not rendered_items:
        return []

    lines = [section_title]
    for item in rendered_items:
        lines.append(f"- {item['text']}（{item['url']}）")
    lines.append("")
    return lines


def _normalize_items(items: list[dict[str, Any]] | None) -> list[dict[str, str]]:
    """过滤掉缺少正文或链接的条目，避免邮件里出现空白项。"""

    normalized: list[dict[str, str]] = []
    for item in items or []:
        text = str(item.get("summary", "") or item.get("title", "") or item.get("text", "")).strip()
        url = str(item.get("url", "")).strip()
        if not text or not url:
            continue
        normalized.append({"text": text, "url": url})
    return normalized


def send_email(
    *,
    subject: str,
    body: str,
    email_to: str,
    smtp_host: str,
    smtp_port: int,
    smtp_username: str,
    smtp_password: str,
    timeout_seconds: int = 30,
) -> None:
    """通过 SMTP 发送日报邮件。"""

    recipients = _split_recipients(email_to)
    if not recipients:
        raise ValueError("EMAIL_TO 不能为空")

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = smtp_username
    message["To"] = ", ".join(recipients)
    message.set_content(body)

    with smtplib.SMTP(smtp_host, smtp_port, timeout=timeout_seconds) as smtp:
        smtp.starttls()
        smtp.login(smtp_username, smtp_password)
        smtp.send_message(message)


def _split_recipients(email_to: str) -> list[str]:
    return [item.strip() for item in email_to.replace(";", ",").split(",") if item.strip()]
