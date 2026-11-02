"""Playwright scraper for my.te.eg (My WE).

Flow: login (number -> optional Service Type -> password) -> #/accountoverview
(Current Balance) -> #/usage (all quotas).

Quotas are read from the site's own `queryFreeUnit` API response captured while
the usage page loads; if that isn't available, the visible page text is parsed.
"""
from __future__ import annotations

import json
import re
import time
from pathlib import Path
from typing import Any

from playwright.sync_api import Page, Response, TimeoutError as PWTimeout, sync_playwright

from .models import AccountData, Quota
from .parsing import parse_balance_text, parse_free_unit_response, parse_usage_text

LOGIN_URL = "https://my.te.eg/echannel/#/login"
OVERVIEW_URL = "https://my.te.eg/echannel/#/accountoverview"
USAGE_URL = "https://my.te.eg/echannel/#/usage"

SERVICE_TYPE = "Internet"

NUMBER_INPUT = "#login_loginid_input_01"
SERVICE_TYPE_SELECT = "#login_input_type_01"
PASSWORD_INPUT = "#login_password_input_01"

DEBUG_DIR = Path("debug")


class ScrapeError(RuntimeError):
    pass


class _Capture:
    """Collects JSON responses from the site's backend API."""

    def __init__(self) -> None:
        self.responses: list[tuple[str, Any]] = []

    def __call__(self, response: Response) -> None:
        url = response.url
        if "te.eg" not in url or "/rest/" not in url:
            return
        try:
            self.responses.append((url, response.json()))
        except Exception:  # non-JSON / body unavailable
            pass

    def latest(self, url_part: str) -> Any | None:
        for url, data in reversed(self.responses):
            if url_part.lower() in url.lower():
                return data
        return None


def _save_debug(page: Page, name: str) -> None:
    DEBUG_DIR.mkdir(exist_ok=True)
    try:
        page.screenshot(path=str(DEBUG_DIR / f"{name}.png"), full_page=True)
        (DEBUG_DIR / f"{name}.txt").write_text(page.inner_text("body"), encoding="utf-8")
    except Exception:
        pass


def _click_visible_text(page: Page, text: str, timeout_ms: int = 10_000) -> None:
    """Click the first *visible* element whose text is exactly `text`."""
    locator = page.get_by_text(text, exact=True)
    deadline = time.monotonic() + timeout_ms / 1000
    while time.monotonic() < deadline:
        for el in locator.all():
            if el.is_visible():
                el.click()
                return
        page.wait_for_timeout(250)
    raise ScrapeError(f"Option '{text}' not found in Service Type dropdown")


def _login(page: Page, number: str, password: str) -> None:
    page.goto(LOGIN_URL, wait_until="domcontentloaded")
    number_input = page.locator(NUMBER_INPUT)
    number_input.wait_for(state="visible", timeout=45_000)
    number_input.fill(number)
    number_input.press("Tab")

    # The Service Type dropdown only appears for some numbers (e.g. landlines).
    service_type = page.locator(SERVICE_TYPE_SELECT)
    try:
        service_type.wait_for(state="visible", timeout=5_000)
    except PWTimeout:
        pass
    else:
        service_type.click()
        _click_visible_text(page, SERVICE_TYPE)

    page.locator(PASSWORD_INPUT).fill(password)
    login_button = page.get_by_role("button", name=re.compile(r"^\s*(Login|تسجيل الدخول)\s*$", re.I)).first
    login_button.click(timeout=15_000)

    try:
        page.wait_for_url(lambda url: "#/login" not in url, timeout=45_000)
    except PWTimeout as exc:
        _save_debug(page, "login_failed")
        raise ScrapeError("Login failed: still on the login page (wrong number/password or site changed)") from exc


def _read_balance(page: Page) -> str | None:
    page.goto(OVERVIEW_URL, wait_until="domcontentloaded")
    try:
        page.get_by_text(re.compile(r"Current\s+Balance", re.I)).first.wait_for(timeout=30_000)
        page.wait_for_timeout(1_500)  # let the number render
    except PWTimeout:
        _save_debug(page, "overview")
        return None
    return parse_balance_text(page.inner_text("body"))


def _read_quotas(page: Page, capture: _Capture) -> list[Quota]:
    page.goto(USAGE_URL, wait_until="domcontentloaded")
    try:
        page.get_by_text(re.compile(r"Used\s*\d", re.I)).first.wait_for(timeout=45_000)
    except PWTimeout:
        _save_debug(page, "usage")
        raise ScrapeError("Usage page did not show any quota")
    try:
        page.wait_for_load_state("networkidle", timeout=10_000)
    except PWTimeout:
        pass

    quotas = parse_free_unit_response(capture.latest("queryFreeUnit"))
    if quotas:
        return quotas
    quotas = parse_usage_text(page.inner_text("body"))
    if not quotas:
        _save_debug(page, "usage")
        raise ScrapeError("Could not parse any quota from the usage page")
    return quotas


def fetch_account_data(number: str, password: str, *, headless: bool = True, dump: bool = False) -> AccountData:
    capture = _Capture()
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=headless)
        context = browser.new_context(
            locale="en-US",
            viewport={"width": 1366, "height": 900},
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36"
            ),
        )
        page = context.new_page()
        page.set_default_timeout(30_000)
        page.on("response", capture)
        try:
            _login(page, number, password)
            balance = _read_balance(page)
            quotas = _read_quotas(page, capture)
            if dump:
                _save_debug(page, "usage")
                DEBUG_DIR.mkdir(exist_ok=True)
                (DEBUG_DIR / "api_responses.json").write_text(
                    json.dumps(capture.responses, ensure_ascii=False, indent=2), encoding="utf-8"
                )
            return AccountData(balance=balance, quotas=quotas)
        except ScrapeError:
            raise
        except Exception:
            _save_debug(page, "error")
            raise
        finally:
            context.close()
            browser.close()
