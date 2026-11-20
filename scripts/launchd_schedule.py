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
    launchd_schedule.py            # status of every declared scheduled job
    launchd_schedule.py --install  # generate launchd plists or systemd --user units & enable
    launchd_schedule.py --remove   # disable/unload and delete them
"""

from __future__ import annotations

import json
import os
import plistlib
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

ESTATE = Path(__file__).resolve().parents[1]
WEB_ROOT = ESTATE / "w0m-web"
SCHEDULES = WEB_ROOT / "project" / "launchd" / "schedules.jsonc"
AGENT_DIR = Path.home() / "Library" / "LaunchAgents"
SYSTEMD_USER_DIR = Path.home() / ".config" / "systemd" / "user"
LINUX_LOG_DIR = Path.home() / ".local" / "state" / "w0m" / "logs"

WEEKDAY_NAMES = {
    0: "Sun",
    1: "Mon",
    2: "Tue",
    3: "Wed",
    4: "Thu",
    5: "Fri",
    6: "Sat",
    7: "Sun",
}

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


def scheduler_backend() -> str:
    """Return active scheduler backend (`systemd` on Linux, `launchd` on macOS)."""
    override = os.environ.get("W0M_SCHEDULER_BACKEND", "").strip().lower()
    if override in ("launchd", "systemd"):
        return override
    return "systemd" if sys.platform.startswith("linux") else "launchd"


def canonical_estate_root() -> Path:
    """Resolve the persistent canonical estate root so timers never point at an ephemeral worktree."""
    override = os.environ.get("W0M_CANONICAL_ROOT", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    if "/.w0m/work/" in ESTATE.as_posix():
        r = subprocess.run(
            ["git", "-C", str(ESTATE), "rev-parse", "--path-format=absolute", "--git-common-dir"],
            capture_output=True,
            text=True,
        )
        if r.returncode == 0 and r.stdout.strip():
            common_dir = Path(r.stdout.strip())
            if common_dir.name == ".git":
                return common_dir.parent.resolve()
    return ESTATE.resolve()


def linux_log_path(agent: dict[str, Any]) -> Path:
    return LINUX_LOG_DIR / Path(agent["log"]).name


def systemd_calendar_for(sched: dict[str, Any]) -> str:
    hour = int(sched["hour"])
    minute = int(sched["minute"])
    if "weekday" in sched:
        day = WEEKDAY_NAMES[int(sched["weekday"]) % 7]
        return f"{day} *-*-* {hour:02d}:{minute:02d}:00"
    return f"*-*-* {hour:02d}:{minute:02d}:00"


def systemd_path_env() -> str:
    home = Path.home()
    candidates = [
        str(home / ".local/bin"),
        "/home/linuxbrew/.linuxbrew/bin",
        "/home/linuxbrew/.linuxbrew/sbin",
        str(home / ".local/share/fnm/aliases/default/bin"),
        str(home / ".cargo/bin"),
        "/usr/local/bin",
        "/usr/bin",
        "/bin",
    ]
    deduped: list[str] = []
    for entry in candidates:
        if entry not in deduped:
            deduped.append(entry)
    return ":".join(deduped)


def systemd_service_for(agent: dict[str, Any]) -> str:
    """Generate a systemd user oneshot service targeting the canonical estate checkout."""
    home = Path.home()
    cwd = (canonical_estate_root() / agent["cwd"]).resolve()
    log_path = linux_log_path(agent)
    return "\n".join([
        "[Unit]",
        f"Description={agent['description']} ({agent['label']})",
        "",
        "[Service]",
        "Type=oneshot",
        f"WorkingDirectory={cwd}",
        f'Environment="HOME={home}"',
        f'Environment="PATH={systemd_path_env()}"',
        f"StandardOutput=append:{log_path}",
        f"StandardError=append:{log_path}",
        f"ExecStart={just_bin()} {agent['command']}",
        "",
    ])


def systemd_timer_for(agent: dict[str, Any]) -> str:
    """Generate a persistent systemd user calendar timer for a scheduled estate job."""
    cal = systemd_calendar_for(agent["schedule"])
    return "\n".join([
        "[Unit]",
        f"Description=Timer for {agent['label']} — {agent['description']}",
        "",
        "[Timer]",
        f"OnCalendar={cal}",
        "Persistent=true",
        "RandomizedDelaySec=60",
        f"Unit={agent['label']}.service",
        "",
        "[Install]",
        "WantedBy=timers.target",
        "",
    ])


def _systemd_timer_state(label: str) -> tuple[bool, bool, str]:
    timer_unit = f"{label}.timer"
    r_act = subprocess.run(
        ["systemctl", "--user", "is-active", timer_unit],
        capture_output=True,
        text=True,
    )
    r_en = subprocess.run(
        ["systemctl", "--user", "is-enabled", timer_unit],
        capture_output=True,
        text=True,
    )
    r_next = subprocess.run(
        ["systemctl", "--user", "show", "-p", "NextElapseUSecRealtime", "--value", timer_unit],
        capture_output=True,
        text=True,
    )
    active = r_act.returncode == 0 and r_act.stdout.strip() == "active"
    enabled = r_en.returncode == 0 and r_en.stdout.strip() == "enabled"
    next_elapse = r_next.stdout.strip() if r_next.returncode == 0 else ""
    return active, enabled, next_elapse


def systemd_cmd_status(agents: list[dict[str, Any]]) -> int:
    print("▶ w0m scheduled maintenance (systemd --user)\n")
    any_missing = False
    days = ["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"]
    for a in agents:
        label = a["label"]
        svc_path = SYSTEMD_USER_DIR / f"{label}.service"
        tmr_path = SYSTEMD_USER_DIR / f"{label}.timer"
        exists = svc_path.exists() and tmr_path.exists()
        active, enabled, next_elapse = _systemd_timer_state(label)
        ready = exists and active and enabled
        if ready:
            mark = f"{GREEN}active & enabled{OFF}"
        elif exists:
            mark = f"{YELLOW}installed, inactive ({'enabled' if enabled else 'disabled'}){OFF}"
        else:
            mark = f"{RED}NOT INSTALLED{OFF}"
        s = a["schedule"]
        when = days[int(s["weekday"]) % 7] if "weekday" in s else "daily"
        print(f"  {label}  {mark}")
        print(f"    {DIM}{a['description']}{OFF}")
        print(
            f"    {DIM}{when} {int(s['hour']):02d}:{int(s['minute']):02d}"
            f" · just {a['command']} (in {a['cwd']}){OFF}"
        )
        if next_elapse:
            print(f"    {DIM}next run: {next_elapse}{OFF}")
        log = linux_log_path(a)
        if log.exists():
            age = (time.time() - log.stat().st_mtime) / 86400
            print(f"    {DIM}last run: {age:.1f} days ago ({log}){OFF}")
        else:
            print(f"    {DIM}last run: never — no log at {log}{OFF}")
        any_missing = any_missing or not ready
    if any_missing:
        print(
            f"\n{YELLOW}[WARN] Not every declared systemd timer is active — the schedule is a"
            f" claim, not a behaviour, until it is.{OFF}\n   Install: {BOLD}just tools-schedule{OFF}"
        )
        return 1
    print(f"\n{GREEN}✅ every declared systemd timer is active & enabled{OFF}")
    return 0


def systemd_cmd_install(agents: list[dict[str, Any]]) -> int:
    SYSTEMD_USER_DIR.mkdir(parents=True, exist_ok=True)
    LINUX_LOG_DIR.mkdir(parents=True, exist_ok=True)
    for a in agents:
        svc_path = SYSTEMD_USER_DIR / f"{a['label']}.service"
        tmr_path = SYSTEMD_USER_DIR / f"{a['label']}.timer"
        svc_path.write_text(systemd_service_for(a), encoding="utf-8")
        tmr_path.write_text(systemd_timer_for(a), encoding="utf-8")
    reload_res = subprocess.run(
        ["systemctl", "--user", "daemon-reload"],
        capture_output=True,
        text=True,
    )
    if reload_res.returncode != 0:
        print(f"{RED}❌ systemctl --user daemon-reload failed: {reload_res.stderr.strip()}{OFF}", file=sys.stderr)
        return 1
    for a in agents:
        timer_unit = f"{a['label']}.timer"
        r = subprocess.run(
            ["systemctl", "--user", "enable", "--now", timer_unit],
            capture_output=True,
            text=True,
        )
        if r.returncode != 0:
            print(
                f"{RED}❌ systemctl --user enable --now failed for {timer_unit}: {r.stderr.strip()}{OFF}",
                file=sys.stderr,
            )
            return 1
        print(f"{GREEN}✅ installed + enabled{OFF} {timer_unit}  {DIM}{SYSTEMD_USER_DIR / timer_unit}{OFF}")
    return systemd_cmd_status(agents)


def systemd_cmd_remove(agents: list[dict[str, Any]]) -> int:
    removed_any = False
    for a in agents:
        svc_path = SYSTEMD_USER_DIR / f"{a['label']}.service"
        tmr_path = SYSTEMD_USER_DIR / f"{a['label']}.timer"
        timer_unit = f"{a['label']}.timer"
        if tmr_path.exists() or svc_path.exists():
            subprocess.run(["systemctl", "--user", "disable", "--now", timer_unit], capture_output=True)
            if tmr_path.exists():
                tmr_path.unlink()
            if svc_path.exists():
                svc_path.unlink()
            removed_any = True
            print(f"{GREEN}✅ disabled + removed{OFF} {timer_unit}")
        else:
            print(f"{DIM}·  {timer_unit} was not installed{OFF}")
    if removed_any:
        subprocess.run(["systemctl", "--user", "daemon-reload"], capture_output=True)
    return 0


def is_loaded(label: str) -> bool:
    r = subprocess.run(["launchctl", "list"], capture_output=True, text=True)
    return any(line.split("\t")[-1] == label for line in r.stdout.splitlines())


def cmd_status(agents: list[dict[str, Any]]) -> int:
    if scheduler_backend() == "systemd":
        return systemd_cmd_status(agents)
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
    if scheduler_backend() == "systemd":
        return systemd_cmd_install(agents)
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
    if scheduler_backend() == "systemd":
        return systemd_cmd_remove(agents)
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
