"""Pure parsing helpers (no browser) so they can be unit-tested."""
from __future__ import annotations

import re
from typing import Any

from .models import Quota

_NUM = r"\d[\d,]*(?:\.\d+)?"
_UNIT = r"(?:TB|GB|MB|KB|جيجا|تيرا|ميجا|ميجابايت|ميجابايتس|ميجابيت)"

# Matches English or Arabic bundle cards
# English: Name\n232.84 GB / 250 GB\nUsed 17.16 GB
# Arabic: 228.18 جيجا / 250 جيجا\nالباقة الأساسية\nمستخدمة 21.82 جيجا
_CARD_EN_RE = re.compile(
    rf"(?P<name>[^\n\d][^\n]*?)[ \t]*\n\s*"
    rf"(?P<rem>{_NUM})\s*(?P<rem_u>{_UNIT})\s*/\s*"
    rf"(?P<tot>{_NUM})\s*(?P<tot_u>{_UNIT})\s*"
    rf"Used\s*(?P<used>{_NUM})\s*(?P<used_u>{_UNIT})",
    re.IGNORECASE,
)

_CARD_AR_RE = re.compile(
    rf"(?P<rem>{_NUM})\s*(?P<rem_u>{_UNIT})\s*/\s*(?P<tot>{_NUM})\s*(?P<tot_u>{_UNIT})\s*\n\s*"
    rf"(?P<name>[^\n\d][^\n]*?)\s*\n\s*"
    rf"(?:مستخدمة\s*(?P<used1>{_NUM})\s*(?P<used_u1>{_UNIT})|(?P<used2>{_NUM})\s*(?P<used_u2>{_UNIT})\s*مستخدمة)",
    re.IGNORECASE,
)

_BALANCE_RE = re.compile(r"(?:Current\s+Balance|الرصيد\s+الحالي)", re.IGNORECASE)
_BALANCE_VALUE_RE = re.compile(
    rf"(?P<cur1>EGP|LE|L\.E\.?|جنيه)?\s*(?P<num>-?{_NUM})\s*(?P<cur2>EGP|LE|L\.E\.?|جنيه)?",
    re.IGNORECASE,
)

_TO_GB = {
    "TB": 1024.0,
    "GB": 1.0,
    "MB": 1 / 1024,
    "KB": 1 / (1024 * 1024),
    "جيجا": 1.0,
    "تيرا": 1024.0,
    "ميجا": 1 / 1024,
    "ميجابايت": 1 / 1024,
    "ميجابايتس": 1 / 1024,
    "ميجابيت": 1 / 1024,
}


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _gb(value: str, unit: str) -> float:
    return _num(value) * _TO_GB.get(unit.upper() if unit.isascii() else unit, 1.0)


def _unique(name: str, seen: dict[str, int]) -> str:
    name = name.strip()
    seen[name] = seen.get(name, 0) + 1
    return name if seen[name] == 1 else f"{name} ({seen[name]})"


def parse_total_usage(text: str) -> Quota | None:
    """Extract total remaining and total used from the circular gauge on #/usage."""
    # Matches remaining: e.g. "263.95\nمتبقية" or "263.95 Remaining"
    m_rem = re.search(
        rf"(?P<rem>{_NUM})\s*(?:{_UNIT})?\s*(?:Remaining|متبقية|متبقي)",
        text,
        re.IGNORECASE,
    )
    # Matches used: e.g. "26.05 مستخدمة" or "26.05 Used" or "Used 26.05"
    m_used = re.search(
        rf"(?:(?P<used1>{_NUM})\s*(?:{_UNIT})?\s*(?:Used|مستخدمة|مستخدم)|(?:Used|مستخدمة|مستخدم)\s*(?P<used2>{_NUM}))",
        text,
        re.IGNORECASE,
    )
    if not m_rem or not m_used:
        return None

    try:
        rem_val = _num(m_rem.group("rem"))
        used_str = m_used.group("used1") or m_used.group("used2")
        used_val = _num(used_str)
        total_val = round(rem_val + used_val, 2)
        return Quota(
            name="الاستهلاك الكلي | Total Usage",
            total=total_val,
            used=used_val,
            remaining=rem_val,
        )
    except Exception:
        return None


def parse_usage_text(text: str) -> list[Quota]:
    """Extract quotas from the visible text of the usage page (English or Arabic)."""
    quotas: list[Quota] = []
    seen: dict[str, int] = {}

    # Try English card format first
    for m in _CARD_EN_RE.finditer(text):
        quotas.append(
            Quota(
                name=_unique(m["name"], seen),
                remaining=_gb(m["rem"], m["rem_u"]),
                total=_gb(m["tot"], m["tot_u"]),
                used=_gb(m["used"], m["used_u"]),
            )
        )
    if quotas:
        return quotas

    # Try Arabic card format
    for m in _CARD_AR_RE.finditer(text):
        used_val = m["used1"] or m["used2"]
        used_unit = m["used_u1"] or m["used_u2"]
        quotas.append(
            Quota(
                name=_unique(m["name"], seen),
                remaining=_gb(m["rem"], m["rem_u"]),
                total=_gb(m["tot"], m["tot_u"]),
                used=_gb(used_val, used_unit),
            )
        )
    return quotas


def parse_free_unit_response(payload: Any) -> list[Quota]:
    """Extract quotas from the site's internal `queryFreeUnit` JSON response.

    Expected shape: {"header": {"retCode": "0"}, "body": [{"offerName", "total", "used", "remain"}, ...]}
    """
    if not isinstance(payload, dict):
        return []
    header = payload.get("header") or {}
    if str(header.get("retCode", "0")) != "0":
        return []
    body = payload.get("body")
    if not isinstance(body, list):
        return []
    quotas: list[Quota] = []
    seen: dict[str, int] = {}
    for item in body:
        if not isinstance(item, dict):
            continue
        try:
            total = float(item["total"])
            used = float(item["used"])
            remain = float(item.get("remain", total - used))
        except (KeyError, TypeError, ValueError):
            continue
        name = str(item.get("offerName") or item.get("freeUnitName") or "Quota")
        quotas.append(Quota(name=_unique(name, seen), total=total, used=used, remaining=remain))
    return quotas


def parse_balance_text(text: str) -> str | None:
    """Return the value shown next to 'Current Balance' (e.g. '120.00 EGP')."""
    m = _BALANCE_RE.search(text)
    if not m:
        return None
    window = text[m.end(): m.end() + 80]
    v = _BALANCE_VALUE_RE.search(window)
    if not v:
        return None
    currency = v["cur1"] or v["cur2"] or ""
    return f"{v['num']} {currency}".strip()
