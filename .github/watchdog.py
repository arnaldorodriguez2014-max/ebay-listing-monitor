#!/usr/bin/env python3
"""Independent watchdog for the eBay monitor.

The monitor's in-scan health check alerts when a *running* scan goes bad. It cannot
catch the cases where the monitor stops running entirely (GitHub throttles/disables
the cron, or every run crashes) — those fail silently. This runs as a SEPARATE
scheduled workflow and pings Discord if:

  1. no monitor run has STARTED in STALE_HOURS (cron throttled/disabled/broken), or
  2. the most recent completed monitor run FAILED (the job is crashing), or
  3. the committed health state is "down" (scraper/matching broken and unresolved).

Because it's a distinct workflow, a break in the monitor workflow itself doesn't stop
this. It never fails the job — the Discord alert (and log) is the signal.
"""
import json
import os
import sqlite3
import subprocess
import sys
import urllib.request
from datetime import datetime, timezone

STALE_HOURS = 5.0     # GitHub cron gaps of ~3.8h were observed; alert only past that
REPO = os.environ.get("GITHUB_REPOSITORY", "")
HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))   # repo root
DB = os.path.join(HERE, "seen.db")


def discord(msg):
    url = os.environ.get("DISCORD_WEBHOOK_URL", "")
    if not url or url.startswith("PASTE_"):
        print("watchdog: no webhook configured; not sending.")
        return
    payload = {"embeds": [{
        "title": "\U0001F415 eBay monitor watchdog",
        "description": msg,
        "color": 0xB71C1C,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }]}
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"})
    try:
        urllib.request.urlopen(req, timeout=20)
        print("watchdog: Discord alert sent.")
    except Exception as e:
        print(f"watchdog: Discord send failed: {e}", file=sys.stderr)


def recent_runs():
    """Recent monitor.yml runs via the GitHub CLI, newest first (or [] on error)."""
    try:
        out = subprocess.check_output(
            ["gh", "run", "list", "--workflow", "monitor.yml", "-L", "5",
             "--json", "createdAt,status,conclusion", "-R", REPO],
            text=True, timeout=60)
        return json.loads(out)
    except Exception as e:
        print(f"watchdog: could not list runs: {e}", file=sys.stderr)
        return []


def main():
    now = datetime.now(timezone.utc)
    problems = []

    runs = recent_runs()
    if runs:
        newest = datetime.fromisoformat(runs[0]["createdAt"].replace("Z", "+00:00"))
        age_h = (now - newest).total_seconds() / 3600
        if age_h > STALE_HOURS:
            problems.append(
                f"No monitor run has started in {age_h:.1f}h (last: {newest:%Y-%m-%d %H:%M} UTC). "
                "GitHub cron may be throttled/disabled, or the workflow is failing to trigger.")
        completed = [r for r in runs if r.get("status") == "completed"]
        if completed and completed[0].get("conclusion") == "failure":
            problems.append("The most recent completed monitor run FAILED — the job is crashing.")
    else:
        # gh returned nothing; note it but don't hard-alert (could be a transient API/auth issue)
        print("watchdog: no run data available (skipping recency/failure checks).")

    try:
        if os.path.exists(DB):
            c = sqlite3.connect(DB)
            row = c.execute("SELECT value FROM meta WHERE key='health'").fetchone()
            if row and row[0] == "down":
                problems.append("Committed health state is DOWN (0 scraped, or 0 matched across scans) "
                                "and hasn't recovered — the scraper or matching is broken.")
    except Exception as e:
        print(f"watchdog: health read error: {e}", file=sys.stderr)

    if problems:
        msg = "\n".join(f"• {p}" for p in problems)
        if REPO:
            msg += f"\n\nActions: https://github.com/{REPO}/actions"
        print("WATCHDOG ALERT:\n" + msg)
        discord(msg)
    else:
        print("watchdog: monitor is running and healthy.")


if __name__ == "__main__":
    main()
