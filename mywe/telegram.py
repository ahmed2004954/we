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


def _progress_bar(pct: float, length: int = 10) -> str:
    filled = int(round((pct / 100.0) * length))
    filled = max(0, min(length, filled))
    return "█" * filled + "░" * (length - filled)


def _quota_lines(q: Quota, prefix: str = "📦") -> list[str]:
    return [
        f"{prefix} <b>{html.escape(q.name)}</b>",
        f"• المتبقي | Remaining: <b>{_fmt(q.remaining)}</b> / {_fmt(q.total)} GB",
        f"• المستخدم | Used: <b>{_fmt(q.used)} GB</b> ({q.used_pct:.1f}%)",
        f"<code>[{_progress_bar(q.used_pct)}] {q.used_pct:.1f}%</code>",
    ]


def _balance_line(balance: str | None) -> str:
    return f"💰 <b>الرصيد | Balance:</b> {html.escape(balance) if balance else 'غير متاح | N/A'}"


def format_alerts(alerts: list[Alert], data: AccountData) -> str:
    lines = ["⚠️ <b>تنبيه استهلاك WE | WE Usage Alert</b>", ""]

    # 1. Triggered alert(s)
    for a in alerts:
        if a.level >= 90:
            badge = "🔴 <b>باقي 10% أو أقل | 10% or less left</b>"
        elif a.level >= 75:
            badge = f"🟠 <b>تجاوزت {a.level}% | Crossed {a.level}%</b>"
        else:
            badge = f"🟡 <b>وصلت {a.level}% | Reached {a.level}%</b>"

        lines.extend([badge, *_quota_lines(a.quota), ""])

    # 2. Total consumption overview
    total = data.total
    if total and len(data.quotas) > 1:
        lines.extend([
            "━━━━━━━━━━━━━━━━━━━",
            "🌐 <b>الاستهلاك الكلي | Total Usage</b>",
            f"• المتبقي | Remaining: <b>{_fmt(total.remaining)}</b> / {_fmt(total.total)} GB",
            f"• المستخدم | Used: <b>{_fmt(total.used)} GB</b> ({total.used_pct:.1f}%)",
            f"<code>[{_progress_bar(total.used_pct)}] {total.used_pct:.1f}%</code>",
            "",
        ])

    # 3. All individual bundles breakdown if more than 1
    if len(data.quotas) > 1:
        lines.extend(["━━━━━━━━━━━━━━━━━━━", "📦 <b>حالة الباقات | All Bundles</b>", ""])
        for q in data.quotas:
            lines.append(
                f"• <b>{html.escape(q.name)}:</b> {_fmt(q.remaining)}/{_fmt(q.total)} GB (مستخدم {q.used_pct:.1f}%)"
            )
        lines.append("")

    lines.extend(["━━━━━━━━━━━━━━━━━━━", _balance_line(data.balance)])
    return "\n".join(lines)


def format_report(data: AccountData) -> str:
    lines = ["📊 <b>تقرير استهلاك WE | WE Usage Report</b>", ""]

    # 1. Total consumption (الاستهلاك كامل)
    total = data.total
    if total:
        lines.extend([
            "🌐 <b>الاستهلاك الكلي | Total Usage</b>",
            f"• المتبقي | Remaining: <b>{_fmt(total.remaining)}</b> / {_fmt(total.total)} GB",
            f"• المستخدم | Used: <b>{_fmt(total.used)} GB</b> ({total.used_pct:.1f}%)",
            f"<code>[{_progress_bar(total.used_pct)}] {total.used_pct:.1f}%</code>",
            "",
        ])

    # 2. Breakdown of each bundle
    if data.quotas:
        if len(data.quotas) > 1:
            lines.extend(["━━━━━━━━━━━━━━━━━━━", "📦 <b>تفاصيل الباقات | Bundles Breakdown</b>", ""])
            for q in data.quotas:
                lines.extend([*_quota_lines(q, prefix="🔹"), ""])
        elif not total:
            # Single quota when total is not present
            lines.extend([*_quota_lines(data.quotas[0]), ""])
    else:
        lines.append("لا توجد باقات | No quotas found\n")

    lines.extend(["━━━━━━━━━━━━━━━━━━━", _balance_line(data.balance)])
    return "\n".join(lines)


def format_error(error: str) -> str:
    return (
        "❌ <b>فشل فحص استهلاك WE | WE usage check failed</b>\n\n"
        f"<code>{html.escape(error)}</code>\n\n"
        "لن تصلك هذه الرسالة مرة أخرى حتى ينجح الفحص أو يتغير الخطأ.\n"
        "You won't get this again until a check succeeds or the error changes."
    )
