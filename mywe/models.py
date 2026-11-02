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
    total_quota: Quota | None = None

    @property
    def total(self) -> Quota | None:
        """Return the overall/total usage across all bundles."""
        if self.total_quota is not None:
            return self.total_quota
        if not self.quotas:
            return None
        tot_rem = sum(q.remaining for q in self.quotas)
        tot_cap = sum(q.total for q in self.quotas)
        tot_used = sum(q.used for q in self.quotas)
        return Quota(
            name="الاستهلاك الكلي | Total Usage",
            total=round(tot_cap, 2),
            used=round(tot_used, 2),
            remaining=round(tot_rem, 2),
        )
