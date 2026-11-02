import json
import os
import re
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import quote

import requests
from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright


LOGIN_URL = "https://my.te.eg/echannel/#/login"
OVERVIEW_URL = "https://my.te.eg/echannel/#/accountoverview"
USAGE_URL = "https://my.te.eg/echannel/#/usage"
STATE_PATH = Path("state/usage_state.json")
THRESHOLDS = (25, 50, 75, 90)


@dataclass(frozen=True)
class PackageUsage:
    name: str
    remaining_gb: float
    total_gb: float
    used_gb: float

    @property
    def used_percent(self):
        return self.used_gb / self.total_gb * 100


def parse_usage_text(page_text):
    row_pattern = re.compile(
        r"(?m)^\s*(?P<name>[^\n\d]+?)\s*\n\s*"
        r"(?P<remaining>\d+(?:\.\d+)?)\s*GB\s*/\s*"
        r"(?P<total>\d+(?:\.\d+)?)\s*GB\s*\n\s*"
        r"Used\s*(?P<used>\d+(?:\.\d+)?)\s*GB\s*$",
        re.IGNORECASE,
    )
    packages = [
        PackageUsage(
            name=match.group("name").strip(),
            remaining_gb=float(match.group("remaining")),
            total_gb=float(match.group("total")),
            used_gb=float(match.group("used")),
        )
        for match in row_pattern.finditer(page_text)
    ]
    if not packages:
        raise ValueError("Could not find any quota rows on the My WE usage page")
    return packages


def evaluate_alerts(current, previous, saved_state, is_main_quota=False):
    if previous and current.used_gb < previous.used_gb:
        saved_state = {}

    sent_thresholds = set(saved_state.get("thresholds", []))
    current_percent = current.used_percent
    previous_percent = previous.used_percent if previous else 0
    alerts = []
    for threshold in THRESHOLDS:
        if threshold in sent_thresholds:
            continue
        if previous_percent < threshold <= current_percent or (not previous and current_percent >= threshold):
            alerts.append(f"{threshold}%")
            sent_thresholds.add(threshold)

    next_state = {"thresholds": sorted(sent_thresholds)}
    if is_main_quota:
        next_state["two_gb_steps"] = saved_state.get("two_gb_steps", 0)
    if is_main_quota and current_percent >= 90:
        ninety_used = saved_state.get("ninety_used")
        if ninety_used is None:
            ninety_used = current.total_gb * 0.9
        completed_steps = int((current.used_gb - ninety_used + 1e-9) // 2)
        previous_steps = saved_state.get("two_gb_steps", 0)
        for step in range(previous_steps + 1, completed_steps + 1):
            alerts.append(f"{step * 2} GB after 90%")
        next_state.update({"ninety_used": ninety_used, "two_gb_steps": completed_steps})
    elif is_main_quota and "ninety_used" in saved_state:
        next_state["ninety_used"] = saved_state["ninety_used"]
    return alerts, next_state


def read_state():
    if not STATE_PATH.exists():
        return {}
    return json.loads(STATE_PATH.read_text(encoding="utf-8"))


def save_state(state):
    STATE_PATH.parent.mkdir(parents=True, exist_ok=True)
    STATE_PATH.write_text(json.dumps(state, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def required_secret(name):
    secret = os.environ.get(name, "").strip()
    if not secret:
        raise RuntimeError(f"Required GitHub Actions secret is missing: {name}")
    return secret


def extract_balance(page_text):
    match = re.search(r"Current Balance\s*([\d,]+(?:\.\d+)?)\s*EGP", page_text, re.IGNORECASE)
    if not match:
        raise ValueError("Could not find Current Balance on the My WE account page")
    return f"{match.group(1)} EGP"


def wait_for_page_content(page, marker):
    try:
        page.get_by_text(marker, exact=False).first.wait_for(timeout=30000)
    except PlaywrightTimeoutError as error:
        raise RuntimeError(f"My WE page did not show expected content: {marker}") from error


def fetch_my_we_data(service_number, password):
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        page = browser.new_page()
        page.goto(LOGIN_URL, wait_until="domcontentloaded", timeout=60000)
        page.get_by_label(re.compile("Service number", re.IGNORECASE)).fill(service_number)
        page.get_by_label(re.compile("Service Type", re.IGNORECASE)).select_option(label="Internet")
        page.get_by_label(re.compile("Password", re.IGNORECASE)).fill(password)
        page.get_by_role("button", name=re.compile("Login", re.IGNORECASE)).click()
        wait_for_page_content(page, "Your Current Plan")

        page.goto(OVERVIEW_URL, wait_until="domcontentloaded", timeout=60000)
        wait_for_page_content(page, "Current Balance")
        balance = extract_balance(page.locator("body").inner_text())

        page.goto(USAGE_URL, wait_until="domcontentloaded", timeout=60000)
        wait_for_page_content(page, "Home Internet")
        packages = parse_usage_text(page.locator("body").inner_text())
        browser.close()
    return balance, packages


def format_telegram_message(balance, packages, package_alerts):
    lines = ["📊 My WE usage update", f"Current Balance: {balance}", ""]
    for package in packages:
        lines.extend(
            [
                f"{package.name}: {package.remaining_gb:g} / {package.total_gb:g} GB remaining",
                f"Used: {package.used_gb:g} GB ({package.used_percent:.1f}%)",
            ]
        )
        alerts = package_alerts.get(package.name, [])
        if alerts:
            lines.append("Alerts: " + ", ".join(alerts))
        lines.append("")
    return "\n".join(lines).strip()


def send_telegram_message(bot_token, chat_id, message):
    telegram_url = f"https://api.telegram.org/bot{quote(bot_token, safe=':')}/sendMessage"
    response = requests.post(
        telegram_url,
        json={"chat_id": chat_id, "text": message},
        timeout=30,
    )
    response.raise_for_status()
    if not response.json().get("ok"):
        raise RuntimeError("Telegram rejected the usage notification")


def make_package_key(package):
    return f"{package.name}|{package.total_gb:g}"


def evaluate_all_packages(packages, previous_state):
    updated_state = {}
    all_alerts = {}
    main_quota = next((package for package in packages if package.name.casefold() == "main quota"), None)
    for package in packages:
        package_key = make_package_key(package)
        saved_package = previous_state.get("packages", {}).get(package_key, {})
        previous_package = saved_package.get("last_usage")
        previous = PackageUsage(**previous_package) if previous_package else None
        package_alerts, next_package_state = evaluate_alerts(
            package,
            previous,
            saved_package,
            is_main_quota=package is main_quota,
        )
        all_alerts[package.name] = package_alerts
        next_package_state["last_usage"] = asdict(package)
        updated_state[package_key] = next_package_state
    return all_alerts, {"packages": updated_state}


def persist_github_state():
    subprocess.run(["git", "config", "user.name", "github-actions[bot]"], check=True)
    subprocess.run(
        ["git", "config", "user.email", "41898282+github-actions[bot]@users.noreply.github.com"],
        check=True,
    )
    subprocess.run(["git", "add", str(STATE_PATH)], check=True)
    changed = subprocess.run(["git", "diff", "--cached", "--quiet"], check=False)
    if changed.returncode == 1:
        subprocess.run(["git", "commit", "-m", "Update My WE usage state"], check=True)
        subprocess.run(["git", "push"], check=True)
    elif changed.returncode != 0:
        raise RuntimeError("Could not check whether the usage state changed")


def main():
    balance, packages = fetch_my_we_data(
        required_secret("MYWE_SERVICE_NUMBER"),
        required_secret("MYWE_PASSWORD"),
    )
    previous_state = read_state()
    package_alerts, next_state = evaluate_all_packages(packages, previous_state)
    if any(package_alerts.values()):
        send_telegram_message(
            required_secret("TELEGRAM_BOT_TOKEN"),
            required_secret("TELEGRAM_CHAT_ID"),
            format_telegram_message(balance, packages, package_alerts),
        )
    save_state(next_state)
    if os.environ.get("GITHUB_ACTIONS") == "true":
        persist_github_state()


if __name__ == "__main__":
    main()
