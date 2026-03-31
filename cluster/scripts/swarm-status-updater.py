#!/usr/bin/env python3
"""Hourly swarm status updater — sends Telegram summary of active/recent runs.

Deployed to Leader Mac mini as a cron job or LaunchAgent.
Runs every hour and sends a status update to the boss Telegram chat.

Also monitors any 'running' swarm and sends progress updates.
"""
import json
import glob
import os
import sys
import time
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# --- Configuration ---
DARKLAB_HOME = os.environ.get("DARKLAB_HOME", os.path.expanduser("~/.darklab"))
FULLSWARM_DIR = os.path.join(DARKLAB_HOME, "fullswarm")
LEADER_URL = os.environ.get("LEADER_URL", "http://localhost:8100")

# Load from env or .env file
def _load_env():
    env_file = os.path.join(DARKLAB_HOME, ".env")
    if not os.path.exists(env_file):
        # Try parent
        env_file = os.path.join(os.path.expanduser("~/darklab"), ".env")
    if os.path.exists(env_file):
        with open(env_file) as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    key, _, val = line.partition("=")
                    os.environ.setdefault(key.strip(), val.strip())

_load_env()

BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "1269510690")


def send_telegram(text: str) -> bool:
    """Send a message via Telegram Bot API."""
    if not BOT_TOKEN:
        print("No TELEGRAM_BOT_TOKEN set", file=sys.stderr)
        return False

    url = f"https://api.telegram.org/bot{BOT_TOKEN}/sendMessage"
    # Truncate to Telegram's 4096 char limit
    if len(text) > 4000:
        text = text[:4000] + "\n\n[truncated]"

    payload = json.dumps({
        "chat_id": CHAT_ID,
        "text": text,
        "parse_mode": "HTML",
        "disable_notification": True,  # Silent — don't wake the boss at 3am
    }).encode()

    req = urllib.request.Request(url, data=payload, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.status == 200
    except Exception as e:
        print(f"Telegram send failed: {e}", file=sys.stderr)
        return False


def load_runs() -> list[dict]:
    """Load all swarm run states."""
    runs = []
    for f in glob.glob(os.path.join(FULLSWARM_DIR, "*.json")):
        try:
            with open(f) as fh:
                runs.append(json.load(fh))
        except Exception:
            pass
    # Sort by newest first
    runs.sort(key=lambda r: r.get("started_at", r.get("created_at", "")), reverse=True)
    return runs


def check_leader_health() -> dict | None:
    """Quick health check on the Leader API."""
    try:
        req = urllib.request.Request(f"{LEADER_URL}/health", method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return json.loads(resp.read())
    except Exception:
        return None


def format_status_update(runs: list[dict], health: dict | None) -> str:
    """Format the hourly Telegram status update."""
    now = datetime.now(timezone.utc)
    lines = [
        f"<b>DarkLab Hourly Status</b>",
        f"{now.strftime('%Y-%m-%d %H:%M UTC')}",
        "",
    ]

    # Cluster health
    if health and health.get("status") == "ok":
        n_cmds = len(health.get("commands", []))
        lines.append(f"Cluster: OK ({n_cmds} commands)")
    else:
        lines.append("Cluster: UNREACHABLE")

    lines.append("")

    # Active/running swarms
    running = [r for r in runs if r.get("status") == "running"]
    paused = [r for r in runs if r.get("status") == "paused"]
    completed_recent = [
        r for r in runs
        if r.get("status") in ("completed", "partial")
        and _age_hours(r) < 24
    ]
    failed_recent = [
        r for r in runs
        if r.get("status") == "failed"
        and _age_hours(r) < 24
    ]

    if running:
        lines.append(f"<b>Running ({len(running)}):</b>")
        for r in running:
            c = len(r.get("completed_steps", []))
            t = r.get("total_steps", 18)
            phase = r.get("current_phase", "?")
            topic = r.get("topic", "?")[:50]
            lines.append(f"  {r['run_id']}: {c}/{t} steps — {topic}")
            lines.append(f"    Phase: {phase}")
        lines.append("")

    if paused:
        lines.append(f"<b>Paused ({len(paused)}):</b>")
        for r in paused:
            c = len(r.get("completed_steps", []))
            t = r.get("total_steps", 18)
            lines.append(f"  {r['run_id']}: {c}/{t} — /fullswarm resume {r['run_id']}")
        lines.append("")

    if completed_recent:
        lines.append(f"<b>Completed (last 24h): {len(completed_recent)}</b>")
        for r in completed_recent:
            c = len(r.get("completed_steps", []))
            t = r.get("total_steps", 18)
            dur = r.get("duration_seconds", 0)
            mins = int(dur // 60) if dur else 0
            topic = r.get("topic", "?")[:50]
            lines.append(f"  {r['run_id']}: {c}/{t} in {mins}m — {topic}")
        lines.append("")

    if failed_recent:
        lines.append(f"<b>Failed (last 24h): {len(failed_recent)}</b>")
        for r in failed_recent[:3]:
            err = r.get("error", "")[:60]
            lines.append(f"  {r['run_id']}: {err}")
        lines.append("")

    total = len(runs)
    total_completed = len([r for r in runs if r.get("status") in ("completed", "partial")])
    if not running and not paused and not completed_recent and not failed_recent:
        lines.append("No active or recent swarm runs.")
        lines.append("Start one: /fullswarm auto <topic>")
    else:
        lines.append(f"Total runs: {total} ({total_completed} completed)")

    return "\n".join(lines)


def _age_hours(run: dict) -> float:
    """How many hours ago the run finished/started."""
    ts = run.get("finished_at") or run.get("started_at") or run.get("created_at", "")
    if not ts:
        return 999
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - dt).total_seconds() / 3600
    except Exception:
        return 999


def main():
    runs = load_runs()
    health = check_leader_health()
    msg = format_status_update(runs, health)
    print(msg)
    print("---")
    ok = send_telegram(msg)
    print(f"Telegram: {'sent' if ok else 'FAILED'}")


if __name__ == "__main__":
    main()
