from mywe.alerts import compute_alerts, level_for
from mywe.models import Quota


def q(name: str, used: float, total: float = 100.0) -> Quota:
    return Quota(name=name, total=total, used=used, remaining=total - used)


def test_level_for():
    assert level_for(0) == 0
    assert level_for(24.99) == 0
    assert level_for(25) == 25
    assert level_for(60) == 50
    assert level_for(89.9) == 75
    assert level_for(90) == 90
    assert level_for(100) == 90


def test_each_threshold_fires_once():
    state = {"quotas": {}, "last_error": None}
    sent = []
    for used in (10, 26, 30, 51, 55, 76, 80, 91, 99):
        alerts, state = compute_alerts([q("Main", used)], state)
        sent += [a.level for a in alerts]
    assert sent == [25, 50, 75, 90]


def test_jump_sends_single_alert_at_current_level():
    alerts, state = compute_alerts([q("Main", 80)], {"quotas": {"Main": {"level": 0}}})
    assert [a.level for a in alerts] == [75]
    assert state["quotas"]["Main"]["level"] == 75


def test_renewal_resets_silently_then_alerts_again():
    state = {"quotas": {"Main": {"level": 90}}}
    alerts, state = compute_alerts([q("Main", 2)], state)
    assert alerts == []
    assert state["quotas"]["Main"]["level"] == 0
    alerts, state = compute_alerts([q("Main", 30)], state)
    assert [a.level for a in alerts] == [25]


def test_multiple_quotas_independent_and_removed_dropped():
    state = {"quotas": {"Main": {"level": 25}, "Old": {"level": 50}}}
    alerts, state = compute_alerts([q("Main", 30), q("GAME ON", 4.22, 40), q("Extra", 60)], state)
    assert [(a.quota.name, a.level) for a in alerts] == [("Extra", 50)]
    assert set(state["quotas"]) == {"Main", "GAME ON", "Extra"}


def test_other_state_keys_preserved():
    _, state = compute_alerts([q("Main", 0)], {"quotas": {}, "last_error": "x"})
    assert state["last_error"] == "x"


def test_total_quota_alerting():
    state = {"quotas": {}}
    main = q("Main", 20, 100)
    game = q("GAME ON", 35, 40)  # 35/40 = 87.5% -> level 75
    total = q("Total", 55, 140)  # 55/140 = 39.2% -> level 25

    alerts, state = compute_alerts([main, game], state, total_quota=total)
    names_and_levels = {(a.quota.name, a.level) for a in alerts}
    assert ("GAME ON", 75) in names_and_levels
    assert ("Total", 25) in names_and_levels
    assert state["quotas"]["Total"]["level"] == 25
    assert state["quotas"]["GAME ON"]["level"] == 75
