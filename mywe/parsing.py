"""Pure parsing helpers (no browser) so they can be unit-tested."""
from __future__ import annotations

import re
from typing import Any

from .models import Quota

_NUM = r"\d[\d,]*(?:\.\d+)?"
_UNIT = r"(?:TB|GB|MB|KB)"

# Matches a usage card as rendered on #/usage, e.g.
#   Main Quota\n232.84\nGB\n/\n250\nGB\nUsed17.16GB
_CARD_RE = re.compile(
    rf"(?P<name>[^\n\d][^\n]*?)[ \t]*\n\s*"
    rf"(?P<rem>{_NUM})\s*(?P<rem_u>{_UNIT})\s*/\s*"
    rf"(?P<tot>{_NUM})\s*(?P<tot_u>{_UNIT})\s*"
    rf"Used\s*(?P<used>{_NUM})\s*(?P<used_u>{_UNIT})",
    re.IGNORECASE,
)

_BALANCE_RE = re.compile(r"Current\s+Balance", re.IGNORECASE)
_BALANCE_VALUE_RE = re.compile(
    rf"(?P<cur1>EGP|LE|L\.E\.?|جنيه)?\s*(?P<num>-?{_NUM})\s*(?P<cur2>EGP|LE|L\.E\.?|جنيه)?",
    re.IGNORECASE,
)

_TO_GB = {"TB": 1024.0, "GB": 1.0, "MB": 1 / 1024, "KB": 1 / (1024 * 1024)}


def _num(text: str) -> float:
    return float(text.replace(",", ""))


def _gb(value: str, unit: str) -> float:
    return _num(value) * _TO_GB[unit.upper()]


def _unique(name: str, seen: dict[str, int]) -> str:
    name = name.strip()
    seen[name] = seen.get(name, 0) + 1
    return name if seen[name] == 1 else f"{name} ({seen[name]})"


def parse_usage_text(text: str) -> list[Quota]:
    """Extract quotas from the visible text of the usage page."""
    quotas: list[Quota] = []
    seen: dict[str, int] = {}
    for m in _CARD_RE.finditer(text):
        quotas.append(
            Quota(
                name=_unique(m["name"], seen),
                remaining=_gb(m["rem"], m["rem_u"]),
                total=_gb(m["tot"], m["tot_u"]),
                used=_gb(m["used"], m["used_u"]),
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
