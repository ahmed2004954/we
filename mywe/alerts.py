"""Threshold alert logic (pure, no I/O)."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .models import Quota

# Usage percentages that trigger an alert. 90 == "only 10% left".
THRESHOLDS: tuple[int, ...] = (25, 50, 75, 90)


@dataclass(frozen=True)
class Alert:
    quota: Quota
    level: int


def level_for(used_pct: float) -> int:
    """Highest threshold reached for the given usage percentage (0 if none)."""
    return max((t for t in THRESHOLDS if used_pct >= t), default=0)


def compute_alerts(
    quotas: list[Quota],
    state: dict[str, Any],
    total_quota: Quota | None = None,
) -> tuple[list[Alert], dict[str, Any]]:
    """Compare current quotas with the stored state.

    - Tracks both individual quotas and (if multiple bundles) the total usage.
    - An alert fires when a quota reaches a higher threshold than last stored.
      Skipping several thresholds at once yields a single alert (current level).
    - If the level drops (bundle renewed), the stored level is reset silently.
    - Quotas that disappear are dropped from the state; new ones are tracked.
    """
    previous: dict[str, Any] = state.get("quotas") or {}
    new_quotas: dict[str, Any] = {}
    alerts: list[Alert] = []

    items = list(quotas)
    if total_quota is not None and len(quotas) > 1:
        items.append(total_quota)

    for q in items:
        level = level_for(q.used_pct)
        prev_level = int((previous.get(q.name) or {}).get("level", 0))
        if level > prev_level:
            alerts.append(Alert(quota=q, level=level))
        new_quotas[q.name] = {"level": level}

    new_state = dict(state)
    new_state["quotas"] = new_quotas
    return alerts, new_state
