#!/usr/bin/env python3
"""Monitor the host CLI tool versions the w0m workflow depends on (T112 / T164 / T247 / T546).

Reads `.w0m/sdlc.json -> toolchain.policy` (`project/policies/tools-policy.json`), runs each
tool's version command, validates `out_of_scope` coverage, and reports:
  - MISSING     : not on PATH        (FAIL if required, else note)
  - below min   : older than policy min   (FAIL if required, else WARN)
  - drift       : present & >= min but != known_good (DRIFT if required, else INFO)
  - ok          : == known_good

ADVISORY by default (exit 0) — host tools legitimately vary per machine. `--strict` exits
non-zero on any required tool that is MISSING, below min, or on an unverified version (`DRIFT`),
or when the policy's `out_of_scope` declarations are malformed.
`--update-known-good` rewrites each present tool's known_good to the installed version.

Usage:
    python3 scripts/tools_check.py            # report, exit 0
    python3 scripts/tools_check.py --strict   # exit 1 if a required tool is missing/old/drifted
    python3 scripts/tools_check.py --update-known-good
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys
from typing import Any

ROOT = Path(__file__).resolve().parent.parent
SDLC_JSON = ROOT / ".w0m" / "sdlc.json"


def resolve_policy_path(root: Path | None = None, sdlc_path: Path | None = None) -> Path:
    """Resolve `tools-policy.json` from `.w0m/sdlc.json -> toolchain.policy` (T164 AC5)."""
    base = root if root is not None else ROOT
    cfg_file = sdlc_path if sdlc_path is not None else (base / ".w0m" / "sdlc.json")
    if cfg_file.is_file():
        try:
            cfg: dict[str, Any] = json.loads(cfg_file.read_text(encoding="utf-8"))
            tc = cfg.get("toolchain")
            if isinstance(tc, dict):
                rel = tc.get("policy")
                if isinstance(rel, str) and rel.strip():
                    return base / rel.strip()
        except (OSError, ValueError):
            pass
    return base / "project" / "policies" / "tools-policy.json"


POLICY = resolve_policy_path(ROOT)
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


BREW_FORMULA = {
    "aws": "awscli",
    "az": "azure-cli",
    "gpg": "gnupg",
    "mlr": "miller",
    "pdftotext": "poppler",
    "psql": "libpq",
    "rg": "ripgrep",
    "sqlite3": "sqlite",
}  # tool name -> brew formula when they differ


def brew_latest() -> dict[str, str]:
    """{formula: latest_version} for outdated brew formulae. One `brew outdated` call, best-effort."""
    try:
        out = subprocess.run(
            ["brew", "outdated", "--formula", "--verbose"],
            capture_output=True,
            text=True,
            timeout=60,
        )
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
        out = subprocess.run(
            ["gcloud", "components", "list", "--quiet"],
            capture_output=True,
            text=True,
            timeout=90,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    text = (out.stdout or "") + "\n" + (out.stderr or "")
    cur = re.search(r"current Google Cloud CLI version is:\s*(\S+)", text)
    latest = re.search(r"latest available version is:\s*(\S+)", text)
    if cur and latest:
        return cur.group(1), latest.group(1)
    return None


def bump_level(cur: tuple[int, int, int], new: tuple[int, int, int]) -> str:
    if new[0] != cur[0]:
        return "major"
    if new[1] != cur[1]:
        return "minor"
    return "patch"


def installed_version(tool: str, arg: str = "--version", spec: dict[str, Any] | None = None) -> str | None:
    """First semver anywhere in the tool's version output, or None if not found/installed.

    Normally probes `<tool> <arg>` after a PATH lookup.
    - `source: uvx` tools have NO binary on PATH — uvx materialises them per-run from a pinned
      package — so their declared `version_cmd` or `smoke` command IS the probe (T166 AC1).
    - Non-`uvx` tools that declare `version_cmd` (e.g. `moksha` via `dpkg-query` so X11 session
      binaries are never executed, or `duf` whose Homebrew bottle prints `duf (built from source)`)
      first verify `shutil.which(tool)` is on PATH and then run `version_cmd` as real argv (T620).
    - Non-`uvx` tools with `version_probe: "presence"` (e.g. untagged Go/AppImage wrappers like
      `virtual-fido` and `w0m-obsidian-uri --ensure-links`) verify `<tool> <arg>` exits 0 and
      return `known_good` (T620).
    """
    cfg = spec or {}
    if cfg.get("source") == "uvx":
        cmd = cfg.get("version_cmd") or cfg.get("smoke")
        if not cmd:
            return None
        try:
            out = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=120)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        m = SEMVER.search(out.stdout or "") or SEMVER.search(out.stderr or "")
        return m.group(0) if m else None

    if shutil.which(tool) is None:
        return None

    ver_cmd = cfg.get("version_cmd")
    if isinstance(ver_cmd, str) and ver_cmd.strip():
        try:
            out = subprocess.run(shlex.split(ver_cmd), capture_output=True, text=True, timeout=45)
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
        if out.returncode != 0:
            return None
        m = SEMVER.search(out.stdout or "") or SEMVER.search(out.stderr or "")
        return m.group(0) if m else None

    if cfg.get("version_probe") == "presence":
        try:
            out = subprocess.run([tool, arg], capture_output=True, text=True, timeout=45)
        except (OSError, subprocess.SubprocessError):
            return None
        if out.returncode != 0:
            return None
        return str(cfg.get("known_good") or cfg.get("min") or "0.1.0")

    try:
        out = subprocess.run([tool, arg], capture_output=True, text=True, timeout=45)
    except (OSError, subprocess.SubprocessError):
        return None
    m = SEMVER.search(out.stdout or "") or SEMVER.search(out.stderr or "")
    return m.group(0) if m else None


def all_path_candidates(tool: str, path_env: str | None = None) -> list[tuple[Path, Path]]:
    """Return deduplicated `(entry_path, resolved_path)` executables for `tool` in `PATH` order (`T620` AC3)."""
    raw_path = path_env if path_env is not None else os.environ.get("PATH", "")
    seen_targets: set[Path] = set()
    found: list[tuple[Path, Path]] = []
    for segment in raw_path.split(os.pathsep):
        seg = segment.strip()
        if not seg:
            continue
        candidate = Path(seg) / tool
        try:
            if not candidate.is_file() or not os.access(candidate, os.X_OK):
                continue
            resolved = candidate.resolve()
        except OSError:
            continue
        if resolved not in seen_targets:
            seen_targets.add(resolved)
            found.append((candidate, resolved))
    return found


def _is_homebrew_path(entry_path: Path, resolved_path: Path) -> bool:
    """True when `entry_path` or its symlink target resides inside a macOS or Linuxbrew prefix."""
    for p_str in (entry_path.as_posix(), resolved_path.as_posix()):
        if (
            p_str.startswith("/opt/homebrew/")
            or p_str.startswith("/home/linuxbrew/.linuxbrew/")
            or p_str.startswith("/usr/local/Cellar/")
            or p_str.startswith("/usr/local/opt/")
            or "/Cellar/" in p_str
            or "/linuxbrew/" in p_str
        ):
            return True
    return False


def detect_provenance_issues(
    tools: dict[str, Any],
    path_env: str | None = None,
    has_brew: bool | None = None,
) -> list[str]:
    """Detect `source: brew` provenance mismatches and non-Homebrew `PATH` shadows (`T620` AC3)."""
    notices: list[str] = []
    brew_present = (
        has_brew
        if has_brew is not None
        else (shutil.which("brew", path=path_env) is not None)
    )
    for name, spec in sorted(tools.items()):
        if name.startswith("_") or not isinstance(spec, dict):
            continue
        src = str(spec.get("source", "manual"))
        if src == "uvx":
            continue
        candidates = all_path_candidates(name, path_env=path_env)
        if not candidates:
            continue
        first_entry, first_resolved = candidates[0]
        first_is_brew = _is_homebrew_path(first_entry, first_resolved)

        # Check if a user/version-manager shim shadows an installed Homebrew binary behind it on PATH
        shadowed_brew = next(
            (c_entry for c_entry, c_res in candidates[1:] if _is_homebrew_path(c_entry, c_res)),
            None,
        )
        if not first_is_brew and shadowed_brew is not None:
            notices.append(
                f"[SHADOW] {name}: {first_entry} shadows Homebrew binary {shadowed_brew} on PATH"
            )
        elif src == "brew" and brew_present and not first_is_brew and not spec.get("custom_fork"):
            notices.append(
                f"[PROVENANCE] {name}: declared source=brew but PATH resolves {first_entry} "
                f"(invisible to `just tools-outdated` / `just tools-upgrade`)"
            )
    return notices


CACHE = ROOT / "project" / ".tools-outdated.json"  # gitignored, per-machine; written by the weekly run
# T247 AC1 — the OUTCOME of the last scheduled run, which the cache cannot express.
STATUS = ROOT / "project" / ".tools-weekly-status.json"


# T546 — PROPOSED `known_good` bumps.
def state_dir() -> Path:
    env = os.environ.get("W0M_STATE_DIR")
    return Path(env) if env else Path.home() / ".w0m" / "state"


PROPOSED = state_dir() / "tools-proposed.json"


def load_proposals(path: Path) -> dict[str, Any]:
    """The proposals, or {} when there is no file. A file that exists but cannot be read raises."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return {}
    data: Any = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError(f"{path}: expected a JSON object of proposals")
    return data


def save_proposals(path: Path, proposals: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(proposals, indent=2, sort_keys=True, ensure_ascii=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def pending_proposals_line(path: Path | None = None) -> str:
    """One line for the full check: what the weekly run verified and nobody has promoted yet. '' when there is nothing."""
    target = PROPOSED if path is None else path
    try:
        props = load_proposals(target)
    except (OSError, ValueError) as exc:
        return f"proposed bumps: state file unreadable ({exc}) — fix or delete {target}"
    if not props:
        return ""
    names = ", ".join(f"{p['tool']} {p['from']}→{p['to']}" for _k, p in sorted(props.items()))
    return f"{len(props)} proposed known_good bump(s) awaiting promotion: {names} — `just tools-promote` (dry run), then `--apply` in an agent tree"


def report_outdated(tools: dict[str, Any], cache: bool = False) -> int:
    """Read-only: which policy tools have an upstream update, and would tools-upgrade take it?"""
    import datetime

    brew = brew_latest()
    gcloud = gcloud_latest() if any(isinstance(s, dict) and s.get("source") == "gcloud" for s in tools.values()) else None
    ranked = {"patch": 0, "minor": 1, "major": 2}
    rows: list[tuple[str, str, str, str, str, str]] = []
    for name, spec in tools.items():
        if name.startswith("_") or not isinstance(spec, dict):
            continue
        cur = installed_version(name, spec.get("version_arg", "--version"), spec)
        src = str(spec.get("source", "manual"))
        if src == "brew":
            latest = brew.get(BREW_FORMULA.get(name, name))
        elif src == "gcloud":
            cur = (gcloud[0] if gcloud else cur) or cur
            latest = gcloud[1] if gcloud else None
        else:
            latest = None
        if cur is None or latest is None or ver_tuple(latest) <= ver_tuple(cur):
            continue
        lvl = bump_level(ver_tuple(cur), ver_tuple(latest))
        allow = str(spec.get("auto", "none"))
        auto_ok = allow != "none" and ranked[lvl] <= ranked[allow]
        rows.append((name, cur, latest, lvl, "AUTO" if auto_ok else "manual", src))
    if cache:
        CACHE.write_text(
            json.dumps(
                {
                    "generated": datetime.datetime.now().isoformat(timespec="seconds"),
                    "updates": [
                        {
                            "tool": r[0],
                            "cur": r[1],
                            "latest": r[2],
                            "level": r[3],
                            "mode": r[4],
                            "source": r[5],
                        }
                        for r in rows
                    ],
                },
                indent=2,
            )
            + "\n",
            encoding="utf-8",
        )
    if not rows:
        print("  ✓ all policy tools up to date (brew-resolvable)")
        return 0
    print("  updates available:")
    for name, cur, latest, lvl, mode, src in sorted(rows, key=lambda r: (r[4] != "AUTO", r[0])):
        print(f"    {name:12} {cur:>10} → {latest:<10} [{lvl}]  {mode} ({src})")
    n_auto = sum(1 for r in rows if r[4] == "AUTO")
    print(
        f"\n  {len(rows)} update(s): {n_auto} auto-eligible (`just tools-upgrade`), "
        f"{len(rows) - n_auto} manual (prod-gating / major / non-brew)"
    )
    return 0


LAUNCH_AGENT = Path.home() / "Library/LaunchAgents/com.w0m.tools-weekly.plist"
SYSTEMD_TIMER = Path.home() / ".config/systemd/user/com.w0m.tools-weekly.timer"
LINUX_TOOLS_LOG = Path.home() / ".local/state/w0m/logs/w0m-tools-weekly.log"


def _refresh_cadence_days() -> int | None:
    """How often the cache is SUPPOSED to be refreshed.

    Multi-OS safe (T164 / T778): on non-macOS (`sys.platform != 'darwin'`, e.g. Linux `x86_64`),
    reads `SYSTEMD_TIMER` (`OnCalendar=`) if installed, falling back to the 7-day weekly cadence
    without probing `~/Library/LaunchAgents`. On macOS, reads the installed launchd plist via
    `plistlib`.
    """
    plat: str = getattr(sys, "platform", "")
    if plat != "darwin":
        try:
            timer_text = SYSTEMD_TIMER.read_text(encoding="utf-8")
        except OSError:
            return 7
        for raw_line in timer_text.splitlines():
            line = raw_line.strip()
            if line.startswith("OnCalendar="):
                cal = line.split("=", 1)[1].strip()
                return 1 if cal.startswith("*-*-*") else 7
        return 7
    import plistlib

    try:
        agent = plistlib.loads(LAUNCH_AGENT.read_bytes())
    except (OSError, ValueError):
        return None
    interval = agent.get("StartCalendarInterval")
    if isinstance(interval, dict):
        return 7 if "Weekday" in interval else 1
    secs = agent.get("StartInterval")
    return max(1, int(secs) // 86400) if isinstance(secs, int) else None


def warn_cached() -> int:
    """Fast, non-blocking: warn from the cached outdated result (no brew call). Always exit 0."""
    import datetime

    if not CACHE.exists():
        return 0
    try:
        data: dict[str, Any] = json.loads(CACHE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    ups = data.get("updates", [])
    age_days: int | None = None
    try:
        gen = datetime.datetime.fromisoformat(data["generated"])
        age_days = (datetime.datetime.now() - gen).days
    except (KeyError, ValueError):
        pass

    held: list[str] = []
    status_age: int | None = None
    try:
        st: dict[str, Any] = json.loads(STATUS.read_text(encoding="utf-8"))
        held = list(st.get("held") or [])
        ran = datetime.datetime.fromisoformat(st["ran"])
        status_age = (datetime.datetime.now() - ran).days
    except (OSError, ValueError, KeyError):
        pass

    cadence = _refresh_cadence_days()
    missed_run = age_days is not None and cadence is not None and age_days > cadence

    if held:
        age = f" {status_age}d ago" if status_age is not None else ""
        print(f" [WARN] the last toolchain run{age} FAILED — held: {', '.join(held)}")
        print("     those tools run versions the policy never verified; `just tools-check` lists the drift")

    if not ups and not missed_run and not held:
        return 0

    if missed_run:
        print(
            f" [WARN] tools-outdated cache is {age_days}d old but refreshes every {cadence}d — "
            f"a scheduled run was MISSED or FAILED"
        )
        if getattr(sys, "platform", "") == "darwin":
            print("     check `~/Library/Logs/w0m-tools-weekly.log`, then `just tools-weekly`")
        elif SYSTEMD_TIMER.exists():
            print(f"     check `{LINUX_TOOLS_LOG}`, then `just tools-weekly`")
        else:
            print("     run `just tools-schedule` to enable timers and `just tools-weekly` to refresh")

    if ups:
        n_auto = sum(1 for u in ups if u.get("mode") == "AUTO")
        names = ", ".join(u["tool"] for u in ups[:6])
        asof = f" as of {age_days}d ago" if age_days is not None else " (age unknown)"
        print(f" [WARN] {len(ups)} tool update(s) in the last snapshot{asof} ({n_auto} auto): {names}")
        print(
            "     the live count may be HIGHER — `just tools-outdated` measures now; "
            "`just tools-upgrade --apply` applies the auto subset"
        )
    return 0


def validate_out_of_scope(policy: dict[str, Any]) -> list[str]:
    """Validate the `out_of_scope` map in `tools-policy.json` (T164 AC1)."""
    problems: list[str] = []
    oos = policy.get("out_of_scope")
    if oos is None:
        return []
    if not isinstance(oos, dict) or not oos:
        return ["tools-policy.json: `out_of_scope` must be a non-empty object mapping CLI names to written reasons"]
    tools = policy.get("tools") or {}
    overlap = sorted(set(tools) & set(oos))
    if overlap:
        problems.append(f"tools-policy.json: tool(s) declared in both `tools` and `out_of_scope`: {', '.join(overlap)}")
    for name, reason in sorted(oos.items()):
        if name.startswith("_"):
            continue
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"out_of_scope.{name}: missing written reason")
    return problems


def evaluate_toolchain(
    policy: dict[str, Any] | None = None,
    policy_path: Path | None = None,
    strict: bool = False,
) -> dict[str, Any]:
    """Evaluate every tool in `tools-policy.json` and return a structured report (T164 AC2/AC4/AC6)."""
    target_path = policy_path or POLICY
    loaded: dict[str, Any] = (
        policy if policy is not None else json.loads(target_path.read_text(encoding="utf-8"))
    )
    tools: dict[str, Any] = loaded.get("tools", {})
    policy_problems = validate_out_of_scope(loaded)

    fails: list[str] = list(policy_problems)
    warns: list[str] = []
    infos: list[str] = []
    drift_req: list[str] = []
    rows: list[tuple[str, str, str]] = []
    details: list[dict[str, Any]] = []

    for name, spec in tools.items():
        if name.startswith("_") or not isinstance(spec, dict):
            continue
        arg = str(spec.get("version_arg", "--version"))
        req = bool(spec.get("required", False))
        min_ver = str(spec.get("min", "0.0.0"))
        kg_ver = str(spec.get("known_good", "0.0.0"))
        cur = installed_version(name, arg, spec)
        if cur is None:
            status = "missing"
            mark = "✗ MISSING" + (" (required)" if req else " (optional)")
            (fails if req else infos).append(f"{name}: not installed — {spec.get('note', '')}")
        elif ver_tuple(cur) < ver_tuple(min_ver):
            status = "below_min"
            mark = f"✗ {cur} < min {min_ver}"
            (fails if req else warns).append(f"{name}: {cur} below min {min_ver}")
        elif cur != kg_ver:
            status = "drift"
            mark = f"~ {cur} (known-good {kg_ver})"
            msg = f"{name}: {cur} != known-good {kg_ver}"
            (drift_req if req else infos).append(msg)
        else:
            status = "ok"
            mark = f"✓ {cur}"
        rows.append((name, "req" if req else "opt", mark))
        details.append(
            {
                "name": name,
                "required": req,
                "installed": cur,
                "min": min_ver,
                "known_good": kg_ver,
                "source": str(spec.get("source", "manual")),
                "auto": str(spec.get("auto", "none")),
                "status": status,
                "mark": mark,
            }
        )

    if fails and strict:
        verdict = "FAIL"
    elif fails:
        verdict = "FAIL"
    elif drift_req:
        verdict = "DRIFT"
    else:
        verdict = "ok"

    out_of_scope_raw = loaded.get("out_of_scope")
    out_of_scope: dict[str, str] = (
        {k: str(v) for k, v in out_of_scope_raw.items() if not k.startswith("_")}
        if isinstance(out_of_scope_raw, dict)
        else {}
    )
    provenance_notices = detect_provenance_issues(tools)

    return {
        "policy_path": str(target_path),
        "verdict": verdict,
        "rows": rows,
        "details": details,
        "fails": fails,
        "warns": warns,
        "drift_req": drift_req,
        "infos": infos,
        "provenance_notices": provenance_notices,
        "out_of_scope": out_of_scope,
        "required_problems": len(fails),
    }


def main() -> int:
    strict = "--strict" in sys.argv
    update = "--update-known-good" in sys.argv
    outdated = "--outdated" in sys.argv

    pol_path = POLICY
    if "--policy" in sys.argv:
        idx = sys.argv.index("--policy")
        if idx + 1 < len(sys.argv):
            pol_path = Path(sys.argv[idx + 1])
    elif "--project" in sys.argv:
        idx = sys.argv.index("--project")
        if idx + 1 < len(sys.argv):
            pol_path = resolve_policy_path(Path(sys.argv[idx + 1]))

    policy: dict[str, Any] = json.loads(pol_path.read_text(encoding="utf-8"))
    tools: dict[str, Any] = policy["tools"]
    if "--warn-cached" in sys.argv:
        return warn_cached()
    if outdated:
        return report_outdated(tools, cache="--cache" in sys.argv)

    if update:
        changed = False
        for name, spec in tools.items():
            if name.startswith("_") or not isinstance(spec, dict):
                continue
            arg = str(spec.get("version_arg", "--version"))
            cur = installed_version(name, arg, spec)
            if cur is not None and cur != spec.get("known_good"):
                spec["known_good"] = cur
                changed = True
        if changed:
            pol_path.write_text(json.dumps(policy, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print("  updated known_good to installed versions")
        else:
            print("  known_good already matches installed")
        return 0

    report = evaluate_toolchain(policy=policy, policy_path=pol_path, strict=strict)
    rows: list[tuple[str, str, str]] = report["rows"]
    fails: list[str] = report["fails"]
    warns: list[str] = report["warns"]
    drift_req: list[str] = report["drift_req"]
    infos: list[str] = report["infos"]

    for name, kind, mark in rows:
        print(f"  {name:12} [{kind}] {mark}")
    if drift_req:
        print(f"\n  \u26a0  {len(drift_req)} REQUIRED tool(s) on an unverified version:")
        for d in drift_req:
            print(f"    \u00b7 {d}")
        print(
            "     `just tools-weekly` proposes verified bumps and `just tools-promote` lands them (T546), or pin the tool back."
        )
    if infos:
        print("\n  drift / optional (informational):")
        for i in infos:
            print(f"    · {i}")
    prov_notices: list[str] = report.get("provenance_notices", [])
    if prov_notices:
        print("\n  provenance / PATH shadows (advisory, T620):")
        for pnote in prov_notices:
            print(f"    · {pnote}")
    if warns:
        print("\n [WARN] below min (optional tools):")
        for w in warns:
            print(f"    - {w}")
    if fails:
        print(f"\n  ✗ {len(fails)} required tool problem(s):")
        for f in fails:
            print(f"    - {f}")

    if fails and strict:
        verdict = "FAIL"
    elif drift_req:
        verdict = "DRIFT"
    else:
        verdict = "ok"
    pending = pending_proposals_line()
    if pending:
        print(f"\n  · {pending}")
    print(
        f"\n  {'strict: ' if strict else ''}{verdict} — "
        f"{len(rows)} tools, {len(fails)} required-problem(s), {len(warns)} warn, "
        f"{len(drift_req)} required-drift, {len(infos)} optional-drift"
    )
    return 1 if (strict and (fails or drift_req)) else 0


if __name__ == "__main__":
    sys.exit(main())
