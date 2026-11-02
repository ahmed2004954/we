# My WE usage alerts

The scheduled GitHub Actions workflow checks a My WE Internet account every three hours. It sends a Telegram message with the current balance and every active quota when a quota crosses 25%, 50%, 75%, or 90% used. For the Main Quota, it also alerts for each additional 2 GB used after 90%.

## Configure GitHub Actions

Add these repository secrets under **Settings → Secrets and variables → Actions**:

- `MYWE_SERVICE_NUMBER`
- `MYWE_PASSWORD`
- `TELEGRAM_BOT_TOKEN`
- `TELEGRAM_CHAT_ID`

Enable Actions for the repository, then run **My WE usage alerts → Run workflow** once to establish the initial usage baseline. It sends a Telegram message only if an alert threshold is met. The scheduled run starts at 00:00 UTC and repeats every three hours. GitHub may delay scheduled workflows during busy periods.

The workflow writes `state/usage_state.json` to the repository after each successful check so threshold alerts are not repeated between runs. The workflow needs repository **contents: write** permission for this state update. It only runs on its schedule or manual dispatch, so the state commit does not start another check.

## Local checks

Run the automated logic tests with:

```powershell
python -m unittest discover -s tests -v
```

For a local account check, install dependencies and Chromium, set the same four environment variables, and run `python usage_monitor.py`. Keep credentials in environment variables or GitHub Secrets; do not commit them.
