"""Plain data models shared by the scraper, alert logic and message formatting."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Quota:
    """One bundle/quota shown on the My WE usage page (values in GB)."""

    name: str
    total: float
    used: float
    remaining: float

    @property
    def used_pct(self) -> float:
        if self.total <= 0:
            return 0.0
        return max(0.0, min(100.0, self.used / self.total * 100))


@dataclass
class AccountData:
    balance: str | None
    quotas: list[Quota] = field(default_factory=list)
