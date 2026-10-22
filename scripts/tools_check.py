#!/usr/bin/env python3
"""Monitor the host CLI tool versions the w0m workflow depends on.

Reads `project/tools-policy.json`, runs each tool's version command, and reports:
  - MISSING     : not on PATH        (FAIL if required, else note)
  - below min   : older than policy min   (FAIL if required, else WARN)
  - drift       : present & >= min but != known_good (INFO — not a problem)
  - ok          : == known_good

ADVISORY by default (exit 0) — host tools legitimately vary per machine. `--strict` exits
non-zero on any required tool that is MISSING or below min (for `just audit --deep` / CI).
`--update-known-good` rewrites each present tool's known_good to the installed version.

Usage:
    python3 project/scripts/tools_check.py            # report, exit 0
    python3 project/scripts/tools_check.py --strict   # exit 1 if a required tool is missing/old
    python3 project/scripts/tools_check.py --update-known-good
"""
from __future__ import annotations

import json
import re
import os
import shlex
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
POLICY = ROOT / "project" / "policies" / "tools-policy.json"
SEMVER = re.compile(r"(\d+)\.(\d+)(?:\.(\d+))?")


def ver_tuple(s: str) -> tuple[int, int, int]:
    m = SEMVER.search(s or "")
    if not m:
        return (0, 0, 0)
    # Unpacked rather than `tuple(int(x) for x in m.groups())`: SEMVER has three groups (patch optional),
    # so that comprehension is correct at runtime but types as `tuple[int, ...]` — the declared
    # 3-tuple was a claim the code could not back. This makes the arity checkable (T188).
    major, minor, patch = m.groups()
    return (int(major), int(minor), int(patch or 0))


BREW_FORMULA = {"aws": "awscli", "az": "azure-cli"}  # tool name -> brew formula when they differ


def brew_latest() -> dict[str, str]:
    """{formula: latest_version} for outdated brew formulae. One `brew outdated` call, best-effort."""
    try:
        out = subprocess.run(["brew", "outdated", "--formula", "--verbose"],
                             capture_output=True, text=True, timeout=60)
    except (OSError, subprocess.SubprocessError):
        return {}
    latest: dict[str, str] = {}
    # lines: "just (1.46.0) < 1.57.0"  |  "deno (1.45.5_1, 2.8.0) < 2.9.3"
    for ln in out.stdout.splitlines():
        m = re.match(r"(\S+)\s+\(.*\)\s+<\s+(\S+)", ln)
        if m:
            latest[m.group(1)] = m.group(2)
    return latest


def gcloud_latest() -> tuple[str, str] | None:
    """(current, latest) for the Google Cloud CLI, or None if gcloud is absent / can't resolve.

    gcloud is NOT a brew formula for update purposes — it self-updates via
    `gcloud components update`. `gcloud components list` prints its own current and latest
    SDK version in the header, which is the one authoritative signal for "is there an update".
    """
    if shutil.which("gcloud") is None:
        return None
    try:
        out = subprocess.run(["gcloud", "components", "list", "--quiet"],
                             capture_output=True, text=True, timeout=90)
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or "") + "\n" + (out.stderr or "")
    cur = re.search(r"current Google Cloud CLI version is:\s*(\S+)", text)
    latest = re.search(r"latest available version is:\s*(\S+)", text)
    if cur and latest:
        return cur.group(1), latest.group(1)
    return None


def bump_level(cur: tuple, new: tuple) -> str:
    if new[0] != cur[0]:
        return "major"
    if new[1] != cur[1]:
        return "minor"
    return "patch"


def installed_version(tool: str, arg: str, spec: dict | None = None) -> str | None:
    """First semver anywhere in the tool's version output, or None if not found/installed.

    Normally probes `<tool> <arg>` after a PATH lookup. `source: uvx` tools have NO binary on
    PATH — uvx materialises them per-run from a pinned package — so a `which` check reports them
    missing forever and their `min`/`known_good` are never actually enforced. T166 AC1 requires
    serena's version be "checked like every other tool"; for that class the declared `smoke`
    command IS the probe. Run it as a real argv (never a shell string) so a policy file cannot
    become a command-injection surface.
    """
    if (spec or {}).get("source") == "uvx":
        cmd = (spec or {}).get("version_cmd") or (spec or {}).get("smoke")
        if not cmd:
            return None
        try:
            out = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        m = SEMVER.search((out.stdout or "") + "\n" + (out.stderr or ""))
        return m.group(0) if m else None

    if shutil.which(tool) is None:
        return None
    try:
        out = subprocess.run([tool, arg], capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.SubprocessError):
        return None
    m = SEMVER.search((out.stdout or "") + "\n" + (out.stderr or ""))
    return m.group(0) if m else None


CACHE = ROOT / "project" / ".tools-outdated.json"  # gitignored, per-machine; written by the weekly run
# T247 AC1 — the OUTCOME of the last scheduled run, which the cache cannot express.
# `tools-weekly` refreshes the cache FIRST and applies upgrades second, so a run that failed at the
# apply step leaves a perfectly fresh cache. That is exactly what happened on 2026-08-17: the run
# exited 1 holding osv-scanner and semgrep, the cache looked 0 days old, and the only record was a
# launchd log nobody reads. Cache age therefore cannot detect a failed run — only a separate
# outcome record can. Written by `tools_upgrade.py --apply`; gitignored, per-machine.
STATUS = ROOT / "project" / ".tools-weekly-status.json"


# T546 — PROPOSED `known_good` bumps. The scheduled run upgrades and smoke-tests, then RECORDS what it verified here instead of writing
# the policy: it ran in the live checkout and never committed, so that checkout sat dirty and `git merge --ff-only` aborted. The file is
# machine-level (outside every tree) on purpose: the weekly run happens in the live tree, the promotion in an agent tree, and both must see
# the same state. `W0M_STATE_DIR` redirects it for tests.
def state_dir() -> Path:
    env = os.environ.get("W0M_STATE_DIR")
    return Path(env) if env else Path.home() / ".w0m" / "state"


PROPOSED = state_dir() / "tools-proposed.json"


def load_proposals(path: Path) -> dict:
    """The proposals, or {} when there is no file. A file that exists but cannot be read raises: an unreadable state file must not read as 'nothing proposed'."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object of proposals")
    return data


def save_proposals(path: Path, proposals: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(proposals, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def pending_proposals_line(path: Path | None = None) -> str:
    """One line for the full check: what the weekly run verified and nobody has promoted yet. '' when there is nothing."""
    path = PROPOSED if path is None else path
    try:
        props = load_proposals(path)
    except (OSError, ValueError) as exc:
        return f"proposed bumps: state file unreadable ({exc}) — fix or delete {path}"
    if not props:
        return ""
    names = ", ".join(f"{p['tool']} {p['from']}→{p['to']}" for _k, p in sorted(props.items()))
    return f"{len(props)} proposed known_good bump(s) awaiting promotion: {names} — `just tools-promote` (dry run), then `--apply` in an agent tree"


def report_outdated(tools: dict, cache: bool = False) -> int:
    """Read-only: which policy tools have an upstream update, and would tools-upgrade take it?

    With cache=True, also writes CACHE (timestamp + rows) so pre-push can warn instantly without
    the slow `brew outdated` call.
    """
    import datetime
    brew = brew_latest()
    gcloud = gcloud_latest() if any(s.get("source") == "gcloud" for s in tools.values()) else None
    ranked = {"patch": 0, "minor": 1, "major": 2}
    rows = []
    for name, spec in tools.items():
        if name.startswith("_"):
            continue
        cur = installed_version(name, spec.get("version_arg", "--version"))
        src = spec.get("source", "manual")
        if src == "brew":
            latest = brew.get(BREW_FORMULA.get(name, name))
        elif src == "gcloud":
            # gcloud self-updates (`gcloud components update`); resolve via its own version header.
            cur = (gcloud[0] if gcloud else cur) or cur
            latest = gcloud[1] if gcloud else None
        else:
            latest = None  # nvs / pyenv / tfenv / uv / npm — not resolvable here (report via note only)
        if cur is None or latest is None or ver_tuple(latest) <= ver_tuple(cur):
            continue  # up to date, or not resolvable
        lvl = bump_level(ver_tuple(cur), ver_tuple(latest))
        allow = spec.get("auto", "none")
        auto_ok = allow != "none" and ranked[lvl] <= ranked[allow]
        rows.append((name, cur, latest, lvl, "AUTO" if auto_ok else "manual", src))
    if cache:
        CACHE.write_text(json.dumps({
            "generated": datetime.datetime.now().isoformat(timespec="seconds"),
            "updates": [{"tool": r[0], "cur": r[1], "latest": r[2], "level": r[3],
                         "mode": r[4], "source": r[5]} for r in rows],
        }, indent=2) + "\n", encoding="utf-8")
    if not rows:
        print("  ✓ all policy tools up to date (brew-resolvable)")
        return 0
    print("  updates available:")
    for name, cur, latest, lvl, mode, src in sorted(rows, key=lambda r: (r[4] != "AUTO", r[0])):
        print(f"    {name:12} {cur:>10} → {latest:<10} [{lvl}]  {mode} ({src})")
    n_auto = sum(1 for r in rows if r[4] == "AUTO")
    print(f"\n  {len(rows)} update(s): {n_auto} auto-eligible (`just tools-upgrade`), "
          f"{len(rows) - n_auto} manual (prod-gating / major / non-brew)")
    # Explicit: this reporter is READ-ONLY and never gates, so an available update is not a
    # failure. It previously fell off the end, returning None through `main()`'s `return
    # report_outdated(...)` into `sys.exit(None)` — which is also 0, so the declared `-> int`
    # was being honoured by accident rather than by the code (T188).
    return 0


LAUNCH_AGENT = Path.home() / "Library/LaunchAgents/com.w0m.tools-weekly.plist"


def _refresh_cadence_days() -> int | None:
    """How often the cache is SUPPOSED to be refreshed, read from the INSTALLED LaunchAgent.

    Read from the installed plist rather than `project/launchd/schedules.jsonc` for two reasons:
    it is the schedule that actually runs (a declared-but-never-installed agent refreshes nothing),
    and `plistlib` is stdlib — parsing the JSONC declaration would mean importing the estate's one
    JSONC reader, which lives in `authz_blanket_gate` and pulls `authz_probe` (database access) in
    at module level. A pre-push warn must not reach for a DB dependency to decide a threshold.

    A `Weekday` key means weekly; a bare Hour/Minute means daily.

    Returns None when the agent is not installed or unreadable, and staleness is then NOT asserted
    at all — better silent than confidently wrong about a cadence that was never measured.
    """
    import plistlib
    try:
        agent = plistlib.loads(LAUNCH_AGENT.read_bytes())
    except (OSError, ValueError):
        return 7 if sys.platform != "darwin" else None
    interval = agent.get("StartCalendarInterval")
    if isinstance(interval, dict):
        return 7 if "Weekday" in interval else 1
    secs = agent.get("StartInterval")
    return max(1, int(secs) // 86400) if isinstance(secs, int) else None


def warn_cached() -> int:
    """Fast, non-blocking: warn from the cached outdated result (no brew call). Always exit 0.

    Used on pre-push. The cache is refreshed by the scheduled `just tools-weekly` run.

    🔴 This reports a SNAPSHOT and it must say so. It used to print
    "N CLI tool update(s) available" — present tense, from a file up to a week old. Measured
    2026-08-21: that line read "1 update available (1 auto): gcloud" while live detection found
    NINE (4 auto), including a pending `infisical` patch. The count was wrong by eight, it printed
    on ten consecutive pushes, and the owner found the update from infisical's own CLI notice
    instead. A stale number phrased as a current one is worse than no number: it reads as
    reassurance.
    """
    import datetime
    if not CACHE.exists():
        return 0  # never nag before the first scheduled run
    try:
        data = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    ups = data.get("updates", [])
    age_days = None
    try:
        gen = datetime.datetime.fromisoformat(data["generated"])
        age_days = (datetime.datetime.now() - gen).days
    except (KeyError, ValueError):
        pass

    # T247 AC1 — the last run's OUTCOME, read before anything else because a failed run is a
    # bigger fact than a pending update. Independent of the cache on purpose: see STATUS.
    held: list[str] = []
    status_age = None
    try:
        st = json.loads(STATUS.read_text(encoding="utf-8"))
        held = list(st.get("held") or [])
        ran = datetime.datetime.fromisoformat(st["ran"])
        status_age = (datetime.datetime.now() - ran).days
    except (OSError, ValueError, KeyError):
        pass

    cadence = _refresh_cadence_days()
    # A cache older than its own refresh cadence means a scheduled run did not happen, or ran and
    # FAILED. `tools_upgrade.py` returns non-zero if ANY tool is held, and that exit code surfaces
    # nowhere but `~/Library/Logs/w0m-tools-weekly.log` — so this is the only place a missed or
    # failed run becomes visible to a human. It is the headline, above whatever the snapshot holds.
    #
    # The threshold used to be a hardcoded 10 days against a 7-day cycle, so a cache that had
    # missed an entire scheduled run could never be reported stale. A threshold that cannot fire
    # inside its own cadence is not a threshold.
    missed_run = age_days is not None and cadence is not None and age_days > cadence

    # A run that HELD a tool exited non-zero. Report it whether or not anything is pending: the
    # held tool is now running a version the estate never verified, and `tools-upgrade` cannot fix
    # that by itself (installed ends up AHEAD of known_good, so there is nothing left to upgrade).
    if held:
        age = f" {status_age}d ago" if status_age is not None else ""
        print(f" [WARN] the last toolchain run{age} FAILED — held: {', '.join(held)}")
        print("     those tools run versions the policy never verified; "
              "`just tools-check` lists the drift")

    if not ups and not missed_run and not held:
        return 0

    if missed_run:
        print(f" [WARN] tools-outdated cache is {age_days}d old but refreshes every {cadence}d — "
              f"a scheduled run was MISSED or FAILED")
        print("     check `~/Library/Logs/w0m-tools-weekly.log`, then `just tools-weekly`")

    if ups:
        n_auto = sum(1 for u in ups if u.get("mode") == "AUTO")
        names = ", ".join(u["tool"] for u in ups[:6])
        # `is not None`, not truthiness: a 0-day-old cache is the freshest possible and used to
        # print no age at all, so "fresh" and "timestamp unreadable" looked identical.
        asof = f" as of {age_days}d ago" if age_days is not None else " (age unknown)"
        # Phrased as a snapshot deliberately — never "N updates available".
        print(f" [WARN] {len(ups)} tool update(s) in the last snapshot{asof} ({n_auto} auto): {names}")
        print("     the live count may be HIGHER — `just tools-outdated` measures now; "
              "`just tools-upgrade --apply` applies the auto subset")
    return 0


def main() -> int:
    strict = "--strict" in sys.argv
    update = "--update-known-good" in sys.argv
    outdated = "--outdated" in sys.argv
    policy = json.loads(POLICY.read_text(encoding="utf-8"))
    tools = policy["tools"]
    if "--warn-cached" in sys.argv:
        return warn_cached()
    if outdated:
        return report_outdated(tools, cache="--cache" in sys.argv)

    fails: list[str] = []
    warns: list[str] = []
    infos: list[str] = []
    # T247 AC4 — REQUIRED-tool drift is its own bucket. It used to land in `infos` beside optional
    # tools and the verdict printed `ok — … 4 drift`: the number was right there and ignored. A
    # required tool running a version the estate never verified is not informational — `osv-scanner`
    # gates every commit in seven repos and sat drifted for days under an "ok".
    drift_req: list[str] = []
    rows: list[tuple[str, str, str]] = []
    changed = False

    for name, spec in tools.items():
        if name.startswith("_"):
            continue
        arg = spec.get("version_arg", "--version")
        req = spec.get("required", False)
        cur = installed_version(name, arg, spec)
        if cur is None:
            mark = "✗ MISSING" + (" (required)" if req else " (optional)")
            (fails if req else infos).append(f"{name}: not installed — {spec.get('note','')}")
        else:
            if ver_tuple(cur) < ver_tuple(spec["min"]):
                mark = f"✗ {cur} < min {spec['min']}"
                (fails if req else warns).append(f"{name}: {cur} below min {spec['min']}")
            elif cur != spec["known_good"]:
                mark = f"~ {cur} (known-good {spec['known_good']})"
                msg = f"{name}: {cur} != known-good {spec['known_good']}"
                (drift_req if req else infos).append(msg)
            else:
                mark = f"✓ {cur}"
            if update and cur != spec.get("known_good"):
                spec["known_good"] = cur
                changed = True
        rows.append((name, "req" if req else "opt", mark))

    if update:
        if changed:
            POLICY.write_text(json.dumps(policy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print("  updated known_good to installed versions")
        else:
            print("  known_good already matches installed")
        return 0

    for name, kind, mark in rows:
        print(f"  {name:12} [{kind}] {mark}")
    if drift_req:
        print(f"\n  \u26a0  {len(drift_req)} REQUIRED tool(s) on an unverified version:")
        for d in drift_req:
            print(f"    \u00b7 {d}")
        print("     `just tools-weekly` proposes verified bumps and `just tools-promote` lands them (T546), or pin the tool back.")
    if infos:
        print("\n  drift / optional (informational):")
        for i in infos:
            print(f"    · {i}")
    if warns:
        print("\n [WARN] below min (optional tools):")
        for w in warns:
            print(f"    - {w}")
    if fails:
        print(f"\n  ✗ {len(fails)} required tool problem(s):")
        for f in fails:
            print(f"    - {f}")
        if strict:
            return 1
    # T247 AC4 — the verdict may no longer say `ok` while a REQUIRED tool is unverified. Tiering is
    # deliberate rather than maximal: this check is advisory per-machine by design (`--strict` is
    # what gates `just audit --deep`), so required drift earns a distinct non-ok verdict here and a
    # hard failure under --strict. Optional-tool drift stays informational — `omlx` and `tart` are
    # not commit gates, and reddening on them is how a gate trains people to ignore it.
    if fails and strict:
        verdict = "FAIL"
    elif drift_req:
        verdict = "DRIFT"
    else:
        verdict = "ok"
    pending = pending_proposals_line()
    if pending:
        print(f"\n  · {pending}")
    print(f"\n  {'strict: ' if strict else ''}{verdict} — "
          f"{len(rows)} tools, {len(fails)} required-problem(s), {len(warns)} warn, "
          f"{len(drift_req)} required-drift, {len(infos)} optional-drift")
    return 1 if (strict and (fails or drift_req)) else 0


if __name__ == "__main__":
    sys.exit(main())
