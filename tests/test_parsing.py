import pytest

from mywe.parsing import parse_balance_text, parse_free_unit_response, parse_usage_text

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


def test_parse_usage_text_two_quotas():
    quotas = parse_usage_text(USAGE_TEXT)
    assert [x.name for x in quotas] == ["Main Quota", "GAME ON"]
    main, game = quotas
    assert main.remaining == pytest.approx(232.84)
    assert main.total == 250
    assert main.used == pytest.approx(17.16)
    assert main.used_pct == pytest.approx(6.864)
    assert game.total == 40 and game.used == pytest.approx(4.22)


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
