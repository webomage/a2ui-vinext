#!/usr/bin/env python3
"""Install / inspect / remove the w0m LaunchAgents declared in project/launchd/schedules.jsonc.

FORMAT, AND WHY THERE ARE TWO
-----------------------------
Owner preference 2026-08-10: *"since xml is fragile let's better use jsonc and jsonl where
matching"*. launchd cannot read JSON — it takes an XML (or binary) plist and nothing else. So the
XML does not go away; it gets **demoted from source to artifact**. `schedules.jsonc` is what a
human edits; the `.plist` is generated here and never hand-written. Same rule the vault applies to
diagrams: one source, generate the tool-specific form, never maintain both by hand.

That demotion earned itself immediately — the first hand-written plist template was **invalid
XML**, because `--` is illegal inside an XML comment. Nobody would guess that, and it only
surfaced because the file was parsed before shipping.

WHY THE AGENTS EXIST AT ALL
---------------------------
`tools-policy.json` has declared `"auto": "patch"` per tool for months and
`tools_upgrade.py --apply` implements it, but **nothing ever ran it**: measured 2026-08-10, the
outdated cache was 20 days stale with no crontab entry and no LaunchAgent on the machine. A
declared automation with no mechanism is this estate's recurring defect, and this is the mechanism.

Usage:
    launchd_schedule.py            # status of every declared agent
    launchd_schedule.py --install  # generate plists, load them
    launchd_schedule.py --remove   # unload and delete them
"""

from __future__ import annotations

import json
import plistlib
import subprocess
import sys
from pathlib import Path
from typing import Any

ESTATE = Path(__file__).resolve().parents[1]
WEB_ROOT = ESTATE / "w0m-web"
SCHEDULES = WEB_ROOT / "project" / "launchd" / "schedules.jsonc"
AGENT_DIR = Path.home() / "Library" / "LaunchAgents"

GREEN, RED, YELLOW, DIM, BOLD, OFF = (
    "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[1m", "\033[0m",
)


def strip_jsonc(text: str) -> str:
    """Strip // and /* */ comments — WITHOUT touching them inside string literals.

    ⚠️ The naive version of this (a regex for `//.*$`) corrupts every URL in the file: the `//`
    in `https://…` is not a comment. It also mangles a Windows path or any string containing `/*`.
    So this walks the text tracking whether it is inside a string and honouring backslash escapes.
    Cheap to get right once, silently destructive to get wrong.
    """
    out: list[str] = []
    i, n = 0, len(text)
    in_str = in_line = in_block = False
    while i < n:
        c = text[i]
        nxt = text[i + 1] if i + 1 < n else ""
        if in_line:
            if c == "\n":
                in_line = False
                out.append(c)
        elif in_block:
            if c == "*" and nxt == "/":
                in_block = False
                i += 1
        elif in_str:
            out.append(c)
            if c == "\\":                      # escape: copy the next char verbatim
                if nxt:
                    out.append(nxt)
                    i += 1
            elif c == '"':
                in_str = False
        else:
            if c == '"':
                in_str = True
                out.append(c)
            elif c == "/" and nxt == "/":
                in_line = True
                i += 1
            elif c == "/" and nxt == "*":
                in_block = True
                i += 1
            else:
                out.append(c)
        i += 1
    return "".join(out)


def load_agents() -> list[dict[str, Any]]:
    if not SCHEDULES.exists():
        print(f"{RED}❌ {SCHEDULES} missing{OFF}", file=sys.stderr)
        raise SystemExit(1)
    try:
        data = json.loads(strip_jsonc(SCHEDULES.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        print(f"{RED}❌ schedules.jsonc is not valid JSONC: {exc}{OFF}", file=sys.stderr)
        raise SystemExit(1) from exc
    agents: list[dict[str, Any]] = data.get("agents", [])
    if not agents:
        print(f"{RED}❌ schedules.jsonc declares no agents — that is not a schedule.{OFF}",
              file=sys.stderr)
        raise SystemExit(1)
    return agents


def just_bin() -> str:
    which = subprocess.run(["which", "just"], capture_output=True, text=True)
    return which.stdout.strip() or "just"


def plist_for(agent: dict[str, Any]) -> dict[str, Any]:
    """Build the plist as a dict and let plistlib emit the XML.

    Deliberately NOT a string template: plistlib cannot emit malformed XML, and the escaping of
    `&`/`<` in a path stops being something anyone has to remember.
    """
    log = str(Path(agent["log"]).expanduser())
    cwd = str((ESTATE / agent["cwd"]).resolve())
    sched = agent["schedule"]
    return {
        "Label": agent["label"],
        "ProgramArguments": ["/bin/zsh", "-lc", f"cd {cwd} && {just_bin()} {agent['command']}"],
        # `weekday` OPTIONAL — omit it for a DAILY agent. launchd treats an absent key as "every",
        # so {Hour, Minute} fires every day while {Weekday, Hour, Minute} fires weekly. Added
        # 2026-08-18 for backups: `backups.max_age_days.postgres` is 7, so a WEEKLY dump sits
        # exactly on its own limit and a single missed run is instantly stale. Daily gives the
        # freshness gate six days of headroom to be useful in.
        "StartCalendarInterval": ({
            "Hour": int(sched["hour"]),
            "Minute": int(sched["minute"]),
        } | ({"Weekday": int(sched["weekday"])} if "weekday" in sched else {})),
        "RunAtLoad": False,
        "StandardOutPath": log,
        "StandardErrorPath": log,
        "ProcessType": "Background",
    }


def is_loaded(label: str) -> bool:
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    return any(line.split("\t")[-1] == label for line in r.stdout.splitlines())


def cmd_status(agents: list[dict[str, Any]]) -> int:
    print("▶ w0m scheduled maintenance\n")
    any_missing = False
    for a in agents:
        label = a["label"]
        path = AGENT_DIR / f"{label}.plist"
        loaded, exists = is_loaded(label), path.exists()
        mark = f"{GREEN}loaded{OFF}" if loaded else (
            f"{YELLOW}installed, not loaded{OFF}" if exists else f"{RED}NOT INSTALLED{OFF}")
        s = a["schedule"]
        days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
        print(f"  {label}  {mark}")
        print(f"    {DIM}{a['description']}{OFF}")
        when = days[int(s["weekday"]) % 7] if "weekday" in s else "daily"
        print(f"    {DIM}{when} {int(s['hour']):02d}:{int(s['minute']):02d}"
              f" · just {a['command']} (in {a['cwd']}){OFF}")
        log = Path(a["log"]).expanduser()
        if log.exists():
            import time
            age = (time.time() - log.stat().st_mtime) / 86400
            print(f"    {DIM}last run: {age:.1f} days ago ({log}){OFF}")
        else:
            print(f"    {DIM}last run: never — no log at {log}{OFF}")
        any_missing = any_missing or not loaded
    if any_missing:
        print(f"\n{YELLOW}[WARN] Not every declared agent is loaded — the schedule is a claim, not a"
              f" behaviour, until it is.{OFF}\n   Install: {BOLD}just tools-schedule{OFF}")
        return 1
    print(f"\n{GREEN}✅ every declared agent is loaded{OFF}")
    return 0


def cmd_install(agents: list[dict[str, Any]]) -> int:
    AGENT_DIR.mkdir(parents=True, exist_ok=True)
    for a in agents:
        path = AGENT_DIR / f"{a['label']}.plist"
        with path.open("wb") as fh:
            plistlib.dump(plist_for(a), fh)
        subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
        r = subprocess.run(["launchctl", "load", str(path)], capture_output=True, text=True)
        if r.returncode != 0:
            print(f"{RED}❌ launchctl load failed for {a['label']}: {r.stderr.strip()}{OFF}",
                  file=sys.stderr)
            return 1
        print(f"{GREEN}✅ installed + loaded{OFF} {a['label']}  {DIM}{path}{OFF}")
    return cmd_status(agents)


def cmd_remove(agents: list[dict[str, Any]]) -> int:
    for a in agents:
        path = AGENT_DIR / f"{a['label']}.plist"
        if path.exists():
            subprocess.run(["launchctl", "unload", str(path)], capture_output=True)
            path.unlink()
            print(f"{GREEN}✅ unloaded + removed{OFF} {a['label']}")
        else:
            print(f"{DIM}·  {a['label']} was not installed{OFF}")
    return 0


def main() -> int:
    agents = load_agents()
    if "--install" in sys.argv:
        return cmd_install(agents)
    if "--remove" in sys.argv:
        return cmd_remove(agents)
    return cmd_status(agents)


if __name__ == "__main__":
    raise SystemExit(main())
