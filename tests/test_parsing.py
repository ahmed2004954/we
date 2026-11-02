import pytest

from mywe.models import AccountData, Quota
from mywe.parsing import (
    parse_balance_text,
    parse_free_unit_response,
    parse_total_usage,
    parse_usage_text,
)

# Text copied from the My WE usage page (as provided by the user).
USAGE_TEXT = """Home Internet
Main Quota
232.84
GB
/
250
GB
Used17.16GB
GAME ON
35.78
GB
/
40
GB
Used4.22GB
"""

USAGE_TEXT_AR = """الانترنت المنزلي
228.18 جيجا / 250 جيجا
الباقة الأساسية
مستخدمة 21.82 جيجا
35.78 جيجا / 40 جيجا
GAME ON
مستخدمة 4.22 جيجا
"""

GAUGE_TEXT_AR = """الانترنت المنزلي
263.95
متبقية
26.05 مستخدمة
"""

GAUGE_TEXT_EN = """Home Internet
263.95
Remaining
26.05 Used
"""


def test_parse_usage_text_two_quotas():
    quotas = parse_usage_text(USAGE_TEXT)
    assert [x.name for x in quotas] == ["Main Quota", "GAME ON"]
    main, game = quotas
    assert main.remaining == pytest.approx(232.84)
    assert main.total == 250
    assert main.used == pytest.approx(17.16)
    assert main.used_pct == pytest.approx(6.864)
    assert game.total == 40 and game.used == pytest.approx(4.22)


def test_parse_usage_text_arabic():
    quotas = parse_usage_text(USAGE_TEXT_AR)
    assert [x.name for x in quotas] == ["الباقة الأساسية", "GAME ON"]
    main, game = quotas
    assert main.remaining == pytest.approx(228.18)
    assert main.total == 250
    assert main.used == pytest.approx(21.82)
    assert game.total == 40 and game.remaining == pytest.approx(35.78)


def test_parse_total_usage_arabic_and_english():
    total_ar = parse_total_usage(GAUGE_TEXT_AR)
    assert total_ar is not None
    assert total_ar.remaining == pytest.approx(263.95)
    assert total_ar.used == pytest.approx(26.05)
    assert total_ar.total == pytest.approx(290.0)

    total_en = parse_total_usage(GAUGE_TEXT_EN)
    assert total_en is not None
    assert total_en.remaining == pytest.approx(263.95)
    assert total_en.used == pytest.approx(26.05)


def test_account_data_total_property():
    q1 = Quota("Main", total=250, used=21.82, remaining=228.18)
    q2 = Quota("Game", total=40, used=4.22, remaining=35.78)
    data = AccountData(balance="67.82 EGP", quotas=[q1, q2])

    total = data.total
    assert total is not None
    assert total.remaining == pytest.approx(263.96)
    assert total.used == pytest.approx(26.04)
    assert total.total == pytest.approx(290.0)


def test_parse_usage_text_single_quota_inline_and_mb():
    quotas = parse_usage_text("Main Quota\n512 MB / 1 GB Used 512 MB")
    assert len(quotas) == 1
    assert quotas[0].total == 1
    assert quotas[0].used == pytest.approx(0.5)


def test_parse_usage_text_nothing():
    assert parse_usage_text("Loading...") == []


def test_parse_free_unit_response():
    payload = {
        "header": {"retCode": "0"},
        "body": [
            {"offerName": "Main Quota", "total": 250, "used": 17.16, "remain": 232.84},
            {"offerName": "GAME ON", "total": 40, "used": 4.22, "remain": 35.78},
        ],
    }
    quotas = parse_free_unit_response(payload)
    assert [x.name for x in quotas] == ["Main Quota", "GAME ON"]
    assert quotas[1].remaining == pytest.approx(35.78)


def test_parse_free_unit_response_error_or_garbage():
    assert parse_free_unit_response({"header": {"retCode": "1"}, "body": []}) == []
    assert parse_free_unit_response(None) == []
    assert parse_free_unit_response({"body": [{"offerName": "x"}]}) == []


def test_duplicate_names_get_suffix():
    payload = {"body": [{"offerName": "Add-on", "total": 10, "used": 1}, {"offerName": "Add-on", "total": 5, "used": 1}]}
    assert [x.name for x in parse_free_unit_response(payload)] == ["Add-on", "Add-on (2)"]


@pytest.mark.parametrize(
    "text,expected",
    [
        ("Current Balance\n120.50 EGP\nPay", "120.50 EGP"),
        ("Current Balance\nEGP 1,250.00", "1,250.00 EGP"),
        ("Current Balance: 0", "0"),
        ("Nothing here", None),
    ],
)
def test_parse_balance_text(text, expected):
    assert parse_balance_text(text) == expected
