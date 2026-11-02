"""Minimal Telegram Bot API client and message formatting (Arabic + English)."""
from __future__ import annotations

import html

import requests

from .alerts import Alert
from .models import AccountData, Quota


class TelegramError(RuntimeError):
    pass


def send_message(token: str, chat_id: str, text: str) -> None:
    resp = requests.post(
        f"https://api.telegram.org/bot{token}/sendMessage",
        json={"chat_id": chat_id, "text": text, "parse_mode": "HTML", "disable_web_page_preview": True},
        timeout=30,
    )
    data = resp.json() if resp.headers.get("content-type", "").startswith("application/json") else {}
    if resp.status_code != 200 or not data.get("ok"):
        raise TelegramError(f"Telegram sendMessage failed ({resp.status_code}): {data.get('description', resp.text[:200])}")


def _fmt(n: float) -> str:
    return f"{n:,.2f}".rstrip("0").rstrip(".")


def _quota_lines(q: Quota) -> list[str]:
    return [
        f"📦 <b>{html.escape(q.name)}</b>",
        f"المتبقي | Remaining: {_fmt(q.remaining)} / {_fmt(q.total)} GB",
        f"المستخدم | Used: {_fmt(q.used)} GB ({q.used_pct:.1f}%)",
    ]


def _balance_line(balance: str | None) -> str:
    return f"💰 الرصيد | Balance: {html.escape(balance) if balance else 'غير متاح | N/A'}"


def format_alerts(alerts: list[Alert], balance: str | None) -> str:
    lines = ["⚠️ <b>تنبيه استهلاك WE | WE usage alert</b>", ""]
    for a in alerts:
        if a.level >= 90:
            lines.append("🔴 باقي 10% أو أقل | 10% or less left")
        else:
            lines.append(f"🟠 وصلت {a.level}% | Reached {a.level}%")
        lines.extend(_quota_lines(a.quota))
        lines.append("")
    lines.append(_balance_line(balance))
    return "\n".join(lines)


def format_report(data: AccountData) -> str:
    lines = ["📊 <b>تقرير استهلاك WE | WE usage report</b>", ""]
    if not data.quotas:
        lines.append("لا توجد باقات | No quotas found")
        lines.append("")
    for q in data.quotas:
        lines.extend(_quota_lines(q))
        lines.append("")
    lines.append(_balance_line(data.balance))
    return "\n".join(lines)


def format_error(error: str) -> str:
    return (
        "❌ <b>فشل فحص استهلاك WE | WE usage check failed</b>\n\n"
        f"<code>{html.escape(error)}</code>\n\n"
        "لن تصلك هذه الرسالة مرة أخرى حتى ينجح الفحص أو يتغير الخطأ.\n"
        "You won't get this again until a check succeeds or the error changes."
    )
