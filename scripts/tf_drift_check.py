#!/usr/bin/env python3
"""Terraform Drift Detector & Telegram Alerting (T787).

Runs `terraform plan -detailed-exitcode` on w0m-api/cloudflare and parses drift.
On detected drift (exit code 2), dispatches an actionable Telegram alert to
Aleksei (TELEGRAM_ADMIN_ID) via @webomage_bot (TELEGRAM_BOT_TOKEN).
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import urllib.parse
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

DEFAULT_ADMIN_ID = "275104413"
TELEGRAM_API_URL = "https://api.telegram.org/bot{token}/sendMessage"


def parse_plan_output(stdout: str) -> Dict[str, Any]:
    """Parse terraform plan output into structured drift details."""
    changes: List[Dict[str, str]] = []
    plan_summary = ""

    # Match resources introduced by `# <type>.<name> will be <action>`
    # e.g.: # cloudflare_record.xyz will be created
    # e.g.: # cloudflare_record.w0m_xyz_mx_route1 will be updated in-place
    resource_header_pattern = re.compile(
        r'^\s*#\s+([a-zA-Z0-9_]+)\.([a-zA-Z0-9_.-]+)\s+(will be [a-zA-Z -]+|must be replaced)',
    )

    for line in stdout.splitlines():
        line_clean = line.strip()
        if line_clean.startswith("Plan:"):
            plan_summary = line_clean
        elif line_clean.startswith("No changes."):
            plan_summary = line_clean

        m = resource_header_pattern.match(line)
        if m:
            rtype = m.group(1)
            rname = m.group(2)
            verb = m.group(3).lower()

            if "read" in verb:
                continue

            if "created" in verb:
                action = "create"
                symbol = "+"
            elif "destroyed" in verb or "must be replaced" in verb:
                action = "destroy"
                symbol = "-"
            elif "updated" in verb:
                action = "update"
                symbol = "~"
            else:
                action = "change"
                symbol = "~"

            changes.append({
                "symbol": symbol,
                "type": rtype,
                "name": rname,
                "action": action,
            })

    return {
        "summary": plan_summary or "Drift detected (resource state differences)",
        "changes": changes,
        "has_drift": bool(changes) or ("to add" in plan_summary or "to change" in plan_summary or "to destroy" in plan_summary),
    }


def format_telegram_alert(
    drift_info: Dict[str, Any],
    environment: str = "beta",
    zone_label: str = "webomage.com & w0m.xyz",
) -> str:
    """Format markdown message for Telegram delivery."""
    summary = drift_info.get("summary", "Drift detected")
    changes = drift_info.get("changes", [])

    lines = [
        "🚨 *Cloudflare Terraform Drift Detected*",
        f"*Env:* `{environment}` · *Zones:* `{zone_label}`",
        f"*Summary:* `{summary}`",
        "",
        "*Drifted Resources:*",
    ]

    if changes:
        for c in changes[:10]:
            sym = "+" if c["action"] == "create" else ("-" if c["action"] == "destroy" else "~")
            lines.append(f"• `{sym}` `{c['type']}.{c['name']}` ({c['action']})")
        if len(changes) > 10:
            lines.append(f"• _...and {len(changes) - 10} more resource(s)_")
    else:
        lines.append("• _State refresh indicated unmanaged drift._")

    lines.extend([
        "",
        "🛠 *Reconciliation Recipe:*",
        "`just tf-plan` · `just cf-apply`",
    ])

    return "\n".join(lines)


def send_telegram_alert(
    message: str,
    token: Optional[str] = None,
    chat_id: Optional[str] = None,
    dry_run: bool = False,
) -> bool:
    """Send alert to Telegram chat via Bot API."""
    bot_token = token or os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
    target_chat = chat_id or os.environ.get("TELEGRAM_ADMIN_ID", DEFAULT_ADMIN_ID).strip()

    if not bot_token:
        print("[WARN] TELEGRAM_BOT_TOKEN not configured; cannot send alert.")
        return False

    if not target_chat:
        print("[WARN] TELEGRAM_ADMIN_ID not configured; cannot send alert.")
        return False

    if dry_run:
        print(f"[DRY-RUN] Would send Telegram alert to chat {target_chat}:\n{message}")
        return True

    url = TELEGRAM_API_URL.format(token=bot_token)
    payload = json.dumps({
        "chat_id": target_chat,
        "text": message,
        "parse_mode": "Markdown",
        "disable_web_page_preview": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "User-Agent": "w0m-tf-drift/1.0"},
    )

    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
            if data.get("ok"):
                print(f"✅ Telegram drift alert dispatched to chat {target_chat} (message_id: {data['result']['message_id']}).")
                return True
            print(f"[ERROR] Telegram API error: {data}")
            return False
    except Exception as e:
        print(f"[ERROR] Failed to send Telegram alert: {e}")
        return False


def run_terraform_plan(
    chdir: str = "w0m-api/cloudflare",
    refresh_only: bool = False,
) -> Tuple[int, str, str]:
    """Execute terraform plan and return exit code, stdout, stderr."""
    cmd = ["terraform", f"-chdir={chdir}", "plan", "-detailed-exitcode", "-lock=false", "-no-color"]
    if refresh_only:
        cmd.append("-refresh-only")

    # Ensure AWS_* credentials are mapped from R2_* if present
    env = os.environ.copy()
    if "R2_ACCESS_KEY_ID" in env and "AWS_ACCESS_KEY_ID" not in env:
        env["AWS_ACCESS_KEY_ID"] = env["R2_ACCESS_KEY_ID"]
    if "R2_SECRET_ACCESS_KEY" in env and "AWS_SECRET_ACCESS_KEY" not in env:
        env["AWS_SECRET_ACCESS_KEY"] = env["R2_SECRET_ACCESS_KEY"]

    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout, proc.stderr


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description="Check Terraform drift and alert Telegram on changes.")
    parser.add_argument("--check", action="store_true", help="Check for drift without sending alerts (dry-run check).")
    parser.add_argument("--alert", action="store_true", help="Send Telegram alert if drift is detected.")
    parser.add_argument("--dry-run-alert", action="store_true", help="Format alert and print without sending to Telegram.")
    parser.add_argument("--refresh-only", action="store_true", help="Run terraform plan with -refresh-only.")
    parser.add_argument("--chdir", default="w0m-api/cloudflare", help="Path to terraform configuration directory.")
    parser.add_argument("--mock-file", help="Read plan output from mock file instead of executing terraform.")

    args = parser.parse_args(argv)

    if args.mock_file:
        with open(args.mock_file, "r", encoding="utf-8") as f:
            stdout = f.read()
        returncode = 2 if "Plan:" in stdout and not "No changes" in stdout else 0
        stderr = ""
    else:
        returncode, stdout, stderr = run_terraform_plan(chdir=args.chdir, refresh_only=args.refresh_only)

    if returncode == 0:
        print("✅ Cloudflare Terraform is in sync — zero drift detected.")
        return 0

    if returncode == 1:
        print(f"❌ Terraform execution error:\n{stderr or stdout}")
        return 1

    if returncode == 2:
        drift_info = parse_plan_output(stdout)
        print(f"⚠️ Terraform drift detected: {drift_info['summary']}")
        for c in drift_info["changes"]:
            print(f"  • {c['symbol']} {c['type']}.{c['name']} ({c['action']})")

        if args.alert or args.dry_run_alert:
            msg = format_telegram_alert(drift_info)
            send_telegram_alert(msg, dry_run=args.dry_run_alert)

        return 2

    print(f"Unexpected exit code from terraform: {returncode}\n{stderr or stdout}")
    return returncode


if __name__ == "__main__":
    sys.exit(main())
