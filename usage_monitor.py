"""Check My WE usage and send Telegram alerts at 25/50/75/90% usage.

Usage:
    python usage_monitor.py              # normal run (alerts only)
    python usage_monitor.py --report     # also send a full report now
    python usage_monitor.py --headed --dump --dry-run   # local debugging
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path

from mywe.alerts import compute_alerts
from mywe.scraper import fetch_account_data
from mywe.telegram import format_alerts, format_error, format_report, send_message

STATE_FILE = Path("state.json")
REQUIRED_ENV = ("MYWE_SERVICE_NUMBER", "MYWE_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")


def load_dotenv(path: Path = Path(".env")) -> None:
    """Tiny .env loader for local runs (does not override real env vars)."""
    if not path.exists():
        return
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def load_state() -> dict:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {"quotas": {}, "last_error": None}


def save_state(state: dict) -> None:
    STATE_FILE.write_text(json.dumps(state, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def redact(text: str, *secrets: str) -> str:
    for s in secrets:
        if s:
            text = text.replace(s, "***")
    return text


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--report", action="store_true", help="send a full usage report now")
    parser.add_argument("--headed", action="store_true", help="show the browser window")
    parser.add_argument("--dump", action="store_true", help="save page text, screenshots and API responses to ./debug")
    parser.add_argument("--dry-run", action="store_true", help="print messages instead of sending; don't save state")
    args = parser.parse_args()

    load_dotenv()
    missing = [k for k in REQUIRED_ENV if not os.environ.get(k) and not (args.dry_run and k.startswith("TELEGRAM"))]
    if missing:
        print(f"Missing environment variables: {', '.join(missing)}", file=sys.stderr)
        return 2

    number = os.environ["MYWE_SERVICE_NUMBER"].strip()
    password = os.environ["MYWE_PASSWORD"]
    token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")

    def send(text: str) -> None:
        if args.dry_run:
            print("----- Telegram message -----\n" + text + "\n----------------------------")
        else:
            send_message(token, chat_id, text)

    state = load_state()

    try:
        data = fetch_account_data(number, password, headless=not args.headed, dump=args.dump)
    except Exception as exc:  # noqa: BLE001 - report any failure once
        error = redact(f"{type(exc).__name__}: {exc}", password, number).splitlines()[0][:300]
        print(f"Check failed: {error}", file=sys.stderr)
        if state.get("last_error") != error:
            send(format_error(error))
            state["last_error"] = error
            if not args.dry_run:
                save_state(state)
        return 1

    print(f"Balance: {data.balance}")
    for q in data.quotas:
        print(f"  {q.name}: {q.remaining:.2f}/{q.total:.2f} GB remaining, used {q.used:.2f} GB ({q.used_pct:.1f}%)")

    alerts, new_state = compute_alerts(data.quotas, state)
    new_state["last_error"] = None

    if args.report:
        send(format_report(data))
    if alerts:
        send(format_alerts(alerts, data.balance))
    else:
        print("No new threshold crossed.")

    # Only persist after messages were sent successfully, so failed sends are retried next run.
    if not args.dry_run:
        save_state(new_state)
    return 0


if __name__ == "__main__":
    sys.exit(main())
