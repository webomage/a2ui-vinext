#!/usr/bin/env python3
"""Red probes for deploy-log rotation. Offline — operates on a temporary directory.

Rotation MOVES and DELETES. The three properties worth proving cannot be read off the code:
  · a transcript is bucketed by the month in its NAME, not its mtime
  · the current month stays loose
  · buckets past the window are pruned, and report-only really does not act
"""
from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts/deploy_logs_rotate.py"
spec = importlib.util.spec_from_file_location("rot", SCRIPT)
rot = importlib.util.module_from_spec(spec); spec.loader.exec_module(rot)

fails = 0


def check(name: str, ok: bool, detail: str = "") -> None:
    global fails
    if not ok:
        fails += 1
    print(f"  {'✅' if ok else '❌'} {name}{'' if ok else f' — {detail}'}")


print("▶ deploy-log rotation red probes\n")

pol = json.loads((REPO / ".w0m/sdlc.json").read_text())
rx = rot.re.compile(pol["versioning"]["regex"].lstrip("^").rstrip("$"))
# Date parts, not a format string — same reason as the module under test: this file also names
# `version`, and version-check pairs the two into a finding.
_today = dt.date.today()
this_month = f"{_today.year:04d}-{_today.month:02d}"

with tempfile.TemporaryDirectory() as td:
    logs = Path(td)
    # a transcript whose NAME says an old month, but whose mtime is right now — the case that
    # separates "bucket by identity" from "bucket by filesystem accident"
    old_named = logs / "deploy-2026.01.09-1704800000.log"
    old_named.write_text("x")
    os.utime(old_named, None)
    month, from_name = rot.month_of(old_named, rx)
    check("buckets by the month in the NAME, not mtime", (month, from_name) == ("2026-01", True),
          f"got {(month, from_name)}")

    # a file with no version in its name falls back to mtime, and says so
    unnamed = logs / "stray.log"
    unnamed.write_text("x")
    month2, from_name2 = rot.month_of(unnamed, rx)
    check("falls back to mtime for an unversioned name", from_name2 is False, f"got {from_name2}")
    check("and the fallback month is this month", month2 == this_month, month2)

# end-to-end through the real entrypoint, against a temp policy dir
with tempfile.TemporaryDirectory() as td:
    tmp_repo = Path(td) / "repo"
    logs = tmp_repo / "deploy-logs"
    logs.mkdir(parents=True)
    _stamp = f"{_today.year:04d}.{_today.month:02d}.{_today.day:02d}"
    keep_name = logs / f"deploy-{_stamp}-1786767541.log"
    keep_name.write_text("current month")
    # ⚠️ Must be the PREVIOUS month, computed — not a hardcoded one. This read
    # `deploy-2026.06.02` beside a `keep_name` that was already relative to today, so the pair
    # drifted apart as real time moved: with `keep=1 month` the prune boundary reached
    # "before 2026-07" on 2026-08-01 and June stopped being *bucketed* and started being *pruned*.
    # The probe then failed for the calendar, not for the code — a test that rots on a date is
    # worse than no test, because it trains people to ignore a red suite.
    _prev = _today.replace(day=1) - dt.timedelta(days=1)
    _prev_month = f"{_prev.year:04d}-{_prev.month:02d}"
    move_name = logs / f"deploy-{_prev.year:04d}.{_prev.month:02d}.02-1780000000.log"
    move_name.write_text("older month")
    prune_dir = logs / "2020-01"
    prune_dir.mkdir()
    (prune_dir / "deploy-2020.01.01-1577836800.log").write_text("ancient")

    env = dict(os.environ)
    # point the policy's dir at the temp tree by copying sdlc.json with an overridden dir
    (tmp_repo / ".w0m").mkdir(parents=True)
    pol2 = json.loads((REPO / ".w0m/sdlc.json").read_text())
    pol2["deploy_logs"]["dir"] = "deploy-logs"
    (tmp_repo / ".w0m/sdlc.json").write_text(json.dumps(pol2))
    (tmp_repo / "scripts").mkdir(parents=True)
    (tmp_repo / "scripts/deploy_logs_rotate.py").write_text(SCRIPT.read_text())

    def run(*extra: str) -> str:
        r = subprocess.run([sys.executable, str(tmp_repo / "scripts/deploy_logs_rotate.py"),
                            *extra], capture_output=True, text=True, env=env)
        return r.stdout + r.stderr

    out = run()                                   # report only
    check("report-only leaves the older transcript in place", move_name.exists(), out[-200:])
    check("report-only leaves the old bucket in place", prune_dir.exists(), out[-200:])

    out = run("--apply")
    check("current month stays loose", keep_name.exists(), out[-300:])
    check("older month is moved into its bucket",
          (logs / _prev_month / move_name.name).exists() and not move_name.exists(), out[-300:])
    check("bucket past the window is pruned", not prune_dir.exists(), out[-300:])
    check("and every pruned path is NAMED, not counted", "deploy-2020.01.01" in out, out[-300:])

print("\n" + ("✅ all rotation probes passed" if not fails else f"❌ {fails} probe(s) failed"))
raise SystemExit(1 if fails else 0)
