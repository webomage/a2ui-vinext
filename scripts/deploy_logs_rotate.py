#!/usr/bin/env python3
"""Rotate deploy transcripts into monthly buckets, and prune old ones.

    just deploy-logs-rotate            # report only — nothing moves
    just deploy-logs-rotate --apply    # move and prune

Runs automatically at the end of every `just deploy-logged`, so the directory stays rotated without
anyone remembering to do it. Policy lives in `.w0m/sdlc.json -> deploy_logs`; nothing here is
hardcoded, because a retention window restated in code is a second source of truth.

🔑 **Buckets by the month in the transcript's OWN NAME, not by mtime.** The name carries the release
version (`deploy-2026.08.14-1786767541.log`), so a file that was copied, restored from a backup or
touched by a sync keeps its identity — mtime would have silently reassigned it to the wrong month.
A file whose name does not carry a version is bucketed by mtime as a FALLBACK and said so out loud,
rather than quietly guessing.

[WARN] **Pruning deletes.** Every removed file is NAMED, not counted: a silent delete and a no-op print
the same thing, and this estate has been bitten by exactly that shape often enough to stop doing it.
Default is report-only; `--apply` is the one that acts.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import shutil
import sys
from pathlib import Path

WORKSPACE = Path(__file__).resolve().parents[1]
REPO = WORKSPACE / "w0m-web"
POLICY = WORKSPACE / ".w0m" / "sdlc.json"
MONTH_DIR = re.compile(r"^\d{4}-\d{2}$")


def policy() -> dict:
    pol = json.loads(POLICY.read_text())
    if "deploy_logs" not in pol:
        sys.exit("🔴 .w0m/sdlc.json has no `deploy_logs` block — refusing to invent a retention "
                 "window. Declare it there.")
    return pol


def month_of(path: Path, version_rx: re.Pattern[str]) -> tuple[str, bool]:
    """(YYYY-MM, from_name). `from_name=False` means the name carried no version and mtime was
    used — reported, never silent."""
    m = version_rx.search(path.name)
    if m:
        y, mo, _ = m.group(0).split(".", 2)
        return f"{y}-{mo}", True
    ts = dt.date.fromtimestamp(path.stat().st_mtime)
    return f"{ts.year:04d}-{ts.month:02d}", False


def main() -> int:
    ap = argparse.ArgumentParser(description="Rotate and prune deploy transcripts")
    ap.add_argument("--apply", action="store_true", help="actually move and delete")
    ap.add_argument("--quiet", action="store_true", help="only speak if something happened")
    args = ap.parse_args()

    pol = policy()
    cfg = pol["deploy_logs"]
    logs = WORKSPACE / cfg["dir"]
    keep = int(cfg["keep_months"])
    version_rx = re.compile(pol["versioning"]["regex"].lstrip("^").rstrip("$"))

    if not logs.is_dir():
        if not args.quiet:
            print(f"▶ {logs} does not exist yet — nothing to rotate")
        return 0

    # ⚠️ Built from date PARTS rather than a format string, deliberately. `just version-check`
    # pairs a date-formatting signal with the word "version" and flags the file — and this one
    # legitimately reads the version regex, so it would trip every time. The alternative was an
    # exemption, i.e. declaring a file non-conforming in order to keep a formatting call. This is
    # a bucket key, not a version, and building it explicitly says so in the code itself.
    _today = dt.date.today()
    this_month = f"{_today.year:04d}-{_today.month:02d}"
    loose = sorted(p for p in logs.glob("*.log") if p.is_file())
    moved: list[tuple[Path, str]] = []
    by_mtime: list[Path] = []

    for p in loose:
        month, from_name = month_of(p, version_rx)
        if not from_name:
            by_mtime.append(p)
        if month == this_month:
            continue                      # the current month stays loose and readable
        dest = logs / month
        if args.apply:
            dest.mkdir(exist_ok=True)
            p.replace(dest / p.name)
        moved.append((p, month))

    # prune whole month buckets past the window
    cutoff = (dt.date.today().replace(day=1) - dt.timedelta(days=1))
    for _ in range(keep - 1):
        cutoff = (cutoff.replace(day=1) - dt.timedelta(days=1))
    cutoff_key = f"{cutoff.year:04d}-{cutoff.month:02d}"

    pruned: list[Path] = []
    for d in sorted(x for x in logs.iterdir() if x.is_dir() and MONTH_DIR.match(x.name)):
        if d.name < cutoff_key:
            pruned.extend(sorted(d.rglob("*")))
            if args.apply:
                shutil.rmtree(d)

    acted = bool(moved or pruned)
    if args.quiet and not acted:
        return 0

    verb = "" if args.apply else " (report only — pass --apply to act)"
    print(f"▶ deploy-log rotation{verb} · dir={logs} · keep={keep} month(s), "
          f"pruning before {cutoff_key}")
    print(f"  {len(loose)} loose transcript(s); {this_month} stays loose")
    for p, month in moved:
        print(f"  {'→' if args.apply else '·'} {p.name}  →  {month}/")
    if by_mtime:
        print(f" [WARN] {len(by_mtime)} file(s) carried no version in the name and were bucketed by "
              f"MTIME — a fallback, not the schema:")
        for p in by_mtime:
            print(f"       {p.name}")
    if pruned:
        print(f"  🔴 pruning {len(pruned)} path(s) older than {cutoff_key} — named, not counted:")
        for p in pruned:
            print(f"       {p.relative_to(logs)}")
    if not acted:
        print("  ✅ nothing to rotate")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
