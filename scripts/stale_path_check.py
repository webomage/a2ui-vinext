#!/usr/bin/env python3
"""T509 Unit U0 — Stale-path probe (`just stale-path-check`).

Verifies that every script file or delegated recipe referenced across the 5 estate carriers
actually exists on disk:
  1. `justfile` recipe bodies (`just --dump --dump-format json` on root `justfile` and
     `wom7api/justfile`): every invoked script (`python3`, `bash`, `sh`, `node`, `tsx`) and
     every `--justfile <path> <recipe>` / `-f <path> <recipe>` target exists.
  2. JSON/JSONC policy and profile files (`project/policies/*.json`, `.w0m/sdlc.json`,
     `wom7web/project/*.json`), scanning both keys and string values.
  3. Hook configs (`.pre-commit-config.yaml`, `wom7web/.husky/*`, `scripts/hooks/*`).
  4. Test-runner config (`wom7web/project/test-suites.json`).
  5. Host-level launch agents (`~/Library/LaunchAgents/com.w0m.*.plist`, conditional on
     `sys.platform == "darwin"` or explicit `--launchd-dir`).

Exit codes:
  0 = clean (every checked script path and `--justfile` recipe target exists)
  1 = stale script path, dangling `--justfile` target, or unreasoned/stale exemption found
  2 = could not measure (corrupt/unreadable carrier or empty scan set)
"""
from __future__ import annotations

import argparse
import json
import plistlib
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]

# Script invocation pattern in shell lines (`python3 <path>`, `bash <path>`, `sh <path>`, `node <path>`, `tsx <path>`)
SCRIPT_INVOKE_RE = re.compile(
    r"(?<![\w./-])(?:python3|bash|sh|node|tsx)\s+"
    r"(?:(?:-[A-Za-z0-9_-]+|--[A-Za-z0-9_-]+(?:\s+[^\s'\"`;|&><()$]+)?)\s+)*"
    r"([^\s'\"`;|&><()$]+?\.(?:py|sh|js|mjs|ts|swift))(?=\s|$|;|' |\"|\)|&|\|)"
)

# Repo-relative script path pattern in JSON keys/values and hook configs
SCRIPT_PATH_RE = re.compile(
    r"(?<![\w/.~$-])((?:\.\./)*(?:wom7[a-z]+/)?(?:project/scripts/|scripts/)[A-Za-z0-9_./-]+\.(?:py|sh|ts|mjs|js|swift))(?::\d+)?"
)

# Delegated `just --justfile <path> <recipe>` or `just -f <path> <recipe>` calls
JUSTFILE_DELEGATE_RE = re.compile(
    r"(?<![\w./-])just\s+(?:--justfile|-f)\s+([^\s'\"`;|&><()]+)\s+([A-Za-z_][\w{}.-]*)"
)

# Pending root `justfile` forwarder removals (T509 U0 / T510) — all 11 removed in T509 U0.
PENDING_ROOT_JUSTFILE_FORWARDERS: dict[str, str] = {}

# Explicit exemptions require a non-empty `why` reason; stale exemptions (whose path now exists) fail.
EXEMPTIONS: dict[str, str] = {}


def dump_justfile(justfile: Path, cache: dict[Path, dict | None]) -> dict | None:
    resolved = justfile.resolve()
    if resolved in cache:
        return cache[resolved]
    if not resolved.is_file():
        cache[resolved] = None
        return None
    try:
        r = subprocess.run(
            ["just", "--justfile", str(resolved), "--dump", "--dump-format", "json"],
            cwd=resolved.parent,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        cache[resolved] = None
        return None
    if r.returncode != 0:
        cache[resolved] = None
        return None
    try:
        data: dict[str, Any] = json.loads(r.stdout)
    except json.JSONDecodeError:
        cache[resolved] = None
        return None
    cache[resolved] = data
    return data


def join_body_lines(recipe: dict) -> list[str]:
    """Flatten `just --dump` recipe body fragments and join `\\`-continued lines."""
    raw_lines = [
        "".join(frag if isinstance(frag, str) else "{{}}" for frag in line)
        for line in recipe.get("body", [])
    ]
    joined: list[str] = []
    buf = ""
    for line in raw_lines:
        stripped_r = line.rstrip()
        if stripped_r.endswith("\\"):
            buf += stripped_r[:-1] + " "
        else:
            joined.append(buf + line)
            buf = ""
    if buf:
        joined.append(buf)
    return joined


def strip_comments_and_echo_quotes(line: str) -> str:
    """Strip leading `@`/`-`, full-line comments, and quoted prose in `echo`/`printf`."""
    s = line.lstrip().lstrip("@-").lstrip()
    if s.startswith("#"):
        return ""
    if re.match(r"^(?:echo|printf)\b", s) and "$(" not in s and "`" not in s:
        return ""
    # Replace quoted strings after echo/printf so prose mentions are never treated as commands
    s = re.sub(
        r"\b(?:echo|printf)\s+(?:'[^']*'|\"[^\"]*\")+",
        "echo ''",
        s,
    )
    return s


def resolve_script_in_estate(path_str: str, base_dir: Path, root: Path = ROOT) -> bool:
    """Return True if `path_str` resolves to an existing file from `base_dir` or estate roots."""
    if (base_dir / path_str).is_file() or (root / path_str).is_file():
        return True
    if not path_str.startswith(("wom7", "../", "/")):
        if (root / "wom7web" / path_str).is_file() or (root / "wom7api" / path_str).is_file():
            return True
    return False


def scan_justfiles(
    justfiles: list[Path],
    *,
    root: Path = ROOT,
    strict_forwarders: bool = False,
) -> tuple[int, list[str], list[str], bool]:
    """Scan Carrier 1: justfile recipe bodies for missing scripts and dangling `--justfile` calls."""
    cache: dict[Path, dict | None] = {}
    checked = 0
    findings: list[str] = []
    acknowledged: list[str] = []
    unmeasured = False

    canonical_root_jf = (root / "justfile").resolve()

    for jf in justfiles:
        data = dump_justfile(jf, cache)
        if not data or not isinstance(data.get("recipes"), dict) or not data["recipes"]:
            findings.append(f"justfile {jf}: could not dump recipes via `just --dump --dump-format json`")
            unmeasured = True
            continue

        jf_dir = jf.resolve().parent
        rel_jf = jf.resolve().relative_to(root) if jf.resolve().is_relative_to(root) else jf
        is_canonical_root = jf.resolve() == canonical_root_jf and not strict_forwarders

        for rname, recipe in sorted(data["recipes"].items()):
            lines = join_body_lines(recipe)
            is_shebang = bool(lines and lines[0].lstrip().startswith("#!"))
            shebang_cwd: Path | None = jf_dir if is_shebang else None

            for raw_line in lines:
                line = strip_comments_and_echo_quotes(raw_line)
                if not line:
                    continue

                if is_shebang and shebang_cwd is not None:
                    m_cd_only = re.match(r"^cd\s+([^\s;&|()]+)\s*$", line)
                    if m_cd_only:
                        cd_target = m_cd_only.group(1).strip("'\"")
                        if "{{" not in cd_target and "$" not in cd_target:
                            if cd_target.startswith("~"):
                                shebang_cwd = None
                            else:
                                cand_cwd = (shebang_cwd / cd_target).resolve()
                                shebang_cwd = cand_cwd if cand_cwd.is_dir() else None

                # 1a. Check `--justfile <path> <recipe>` / `-f <path> <recipe>` forwarders
                line_no_quotes = re.sub(r"'[^']*'|\"[^\"]*\"", "''", line)
                for m_del in JUSTFILE_DELEGATE_RE.finditer(line_no_quotes):
                    target_jf_str, target_rec = m_del.group(1), m_del.group(2)
                    if "{{" in target_jf_str or "{{" in target_rec or "$" in target_jf_str or "$" in target_rec:
                        continue
                    checked += 1
                    base = (shebang_cwd or jf_dir) if is_shebang else jf_dir
                    prefix = line[: m_del.start()]
                    for m_cd in re.finditer(r"\bcd\s+([^\s;&|()]+)\s*(?:&&|;)", prefix):
                        cd_arg = m_cd.group(1).strip("'\"")
                        if "{{" not in cd_arg and "$" not in cd_arg and not cd_arg.startswith("~"):
                            base = (base / cd_arg).resolve()
                    target_jf = (base / target_jf_str).resolve()
                    target_data = dump_justfile(target_jf, cache)
                    if target_data is None:
                        findings.append(
                            f"[justfile {rel_jf}:{rname}] `--justfile {target_jf_str} {target_rec}` — "
                            f"target justfile does not exist or could not be parsed"
                        )
                        continue
                    target_names = set(target_data.get("recipes", {})) | set(target_data.get("aliases", {}))
                    if target_rec not in target_names:
                        if is_canonical_root and rname in PENDING_ROOT_JUSTFILE_FORWARDERS:
                            acknowledged.append(
                                f"[justfile {rel_jf}:{rname}] `{target_rec}` — "
                                f"{PENDING_ROOT_JUSTFILE_FORWARDERS[rname]}"
                            )
                        else:
                            findings.append(
                                f"[justfile {rel_jf}:{rname}] dangling `--justfile {target_jf_str} {target_rec}` — "
                                f"no such recipe `{target_rec}` in {target_jf_str}"
                            )

                # 1b. Check script invocations (`python3`, `bash`, `sh`, `node`, `tsx`)
                for m_scr in SCRIPT_INVOKE_RE.finditer(line):
                    spath = m_scr.group(1).strip("'\"")
                    if "{{" in spath or "$" in spath:
                        continue
                    if is_shebang and shebang_cwd is None:
                        continue
                    base = (shebang_cwd or jf_dir) if is_shebang else jf_dir
                    prefix = line[: m_scr.start()]
                    skip_external = False
                    for m_cd in re.finditer(r"\bcd\s+([^\s;&|()]+)\s*(?:&&|;)", prefix):
                        cd_arg = m_cd.group(1).strip("'\"")
                        if "{{" in cd_arg or "$" in cd_arg or cd_arg.startswith("~"):
                            skip_external = True
                            break
                        cand_base = (base / cd_arg).resolve()
                        if not cand_base.is_dir():
                            # Untracked/external tool directory (e.g. `.quartz-engine`)
                            if cd_arg.startswith("."):
                                skip_external = True
                                break
                        base = cand_base
                    if skip_external:
                        continue

                    # Handle `pnpm --dir <dir>` or `pnpm -C <dir>` preceding `tsx`/`node`
                    m_pnpm_dir = re.search(r"\bpnpm\s+(?:--dir|-C)\s+([^\s;&|()]+)", prefix)
                    if m_pnpm_dir:
                        pdir = m_pnpm_dir.group(1).strip("'\"")
                        if "{{" not in pdir and "$" not in pdir:
                            base = (base / pdir).resolve()

                    checked += 1
                    candidate = (base / spath).resolve()
                    if not candidate.is_file():
                        findings.append(
                            f"[justfile {rel_jf}:{rname}] missing script `{spath}` "
                            f"(resolved: {candidate.relative_to(root) if candidate.is_relative_to(root) else candidate})"
                        )

    return checked, findings, acknowledged, unmeasured


def _walk_json(obj: object, trail: str = "") -> list[tuple[str, str, str]]:
    items: list[tuple[str, str, str]] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            items.append(("key", f"{trail}.{k}", str(k)))
            if not str(k).startswith(("_comment", "$comment")):
                items.extend(_walk_json(v, f"{trail}.{k}"))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            items.extend(_walk_json(v, f"{trail}[{i}]"))
    elif isinstance(obj, str):
        items.append(("val", trail, obj))
    return items


def strip_jsonc(text: str) -> str:
    """Strip `//` and `/* ... */` comments outside double-quoted JSON strings."""
    out: list[str] = []
    i, n = 0, len(text)
    in_str = False
    while i < n:
        ch = text[i]
        if in_str:
            out.append(ch)
            if ch == "\\" and i + 1 < n:
                out.append(text[i + 1])
                i += 2
                continue
            if ch == '"':
                in_str = False
            i += 1
        else:
            if ch == '"':
                in_str = True
                out.append(ch)
                i += 1
            elif text[i : i + 2] == "//":
                while i < n and text[i] != "\n":
                    i += 1
            elif text[i : i + 2] == "/*":
                i += 2
                while i + 1 < n and text[i : i + 2] != "*/":
                    i += 1
                i += 2
            else:
                out.append(ch)
                i += 1
    return "".join(out)


def scan_json_files(
    json_files: list[Path],
    *,
    root: Path = ROOT,
) -> tuple[int, list[str], bool]:
    """Scan Carrier 2: JSON/JSONC policy and profile files."""
    checked = 0
    findings: list[str] = []
    unmeasured = False
    seen: set[Path] = set()

    for jf in json_files:
        if not jf.is_file():
            findings.append(f"[json {jf}] file does not exist")
            unmeasured = True
            continue
        real = jf.resolve()
        if real in seen:
            continue
        seen.add(real)
        rel = real.relative_to(root) if real.is_relative_to(root) else jf
        try:
            raw = real.read_text(encoding="utf-8")
            data: object = json.loads(strip_jsonc(raw) if real.suffix == ".jsonc" else raw)
        except Exception as exc:
            findings.append(f"[json {rel}] failed to parse JSON: {exc}")
            unmeasured = True
            continue

        for kind, trail, text in _walk_json(data):
            # Skill-shipped scripts inside skills-policy.json override reasons live in skill dirs, not estate scripts/
            if real.name == "skills-policy.json" and ".overrides." in trail and trail.endswith(".reason"):
                continue
            # Ticket titles in tickets.json may name retired scripts that a ticket deleted
            if real.name == "tickets.json" and trail.endswith(".title"):
                continue
            for m in SCRIPT_PATH_RE.finditer(text):
                pstr = m.group(1)
                checked += 1
                if not resolve_script_in_estate(pstr, real.parent, root=root):
                    findings.append(f"[json {rel}] ({kind} {trail}): stale script path `{pstr}`")

    return checked, findings, unmeasured


def scan_hooks(
    hook_files: list[Path],
    *,
    root: Path = ROOT,
) -> tuple[int, list[str], bool]:
    """Scan Carrier 3: Hook configs (`.pre-commit-config.yaml`, `.husky/*`, `scripts/hooks/*`)."""
    checked = 0
    findings: list[str] = []
    unmeasured = False

    for hf in hook_files:
        if not hf.is_file():
            findings.append(f"[hook {hf}] hook config file does not exist")
            unmeasured = True
            continue
        rel = hf.resolve().relative_to(root) if hf.resolve().is_relative_to(root) else hf
        rel_str = str(rel)
        if rel_str.startswith("wom7web/"):
            base = root / "wom7web"
        elif rel_str.startswith("wom7api/"):
            base = root / "wom7api"
        else:
            base = root

        try:
            lines = hf.read_text(encoding="utf-8", errors="replace").splitlines()
        except OSError as exc:
            findings.append(f"[hook {rel}] could not read file: {exc}")
            unmeasured = True
            continue

        for lineno, raw_line in enumerate(lines, 1):
            line = strip_comments_and_echo_quotes(raw_line)
            if not line:
                continue
            for m in SCRIPT_PATH_RE.finditer(line):
                pstr = m.group(1)
                checked += 1
                if not (base / pstr).resolve().is_file():
                    findings.append(f"[hook {rel}:{lineno}] stale script path `{pstr}`")

    return checked, findings, unmeasured


def scan_test_suites(
    suites_file: Path,
    *,
    root: Path = ROOT,
) -> tuple[int, list[str], bool]:
    """Scan Carrier 4: Test-runner config (`wom7web/project/test-suites.json`)."""
    if not suites_file.is_file():
        return 0, [f"[test-suites {suites_file}] file does not exist"], True
    try:
        data: dict[str, Any] = json.loads(suites_file.read_text(encoding="utf-8"))
    except Exception as exc:
        return 0, [f"[test-suites {suites_file}] invalid JSON: {exc}"], True

    suites = data.get("suites")
    if not isinstance(suites, list) or not suites:
        return 0, [f"[test-suites {suites_file}] missing or empty `suites` list"], True

    checked = 0
    findings: list[str] = []
    rel = suites_file.resolve().relative_to(root) if suites_file.resolve().is_relative_to(root) else suites_file

    for suite in suites:
        if not isinstance(suite, dict):
            continue
        sname = suite.get("name", "<unnamed>")
        checked += 1
        for k, v in suite.items():
            if k in ("why", "reason", "description", "note", "_comment") or not isinstance(v, str):
                continue
            for m in SCRIPT_PATH_RE.finditer(v):
                pstr = m.group(1)
                if not resolve_script_in_estate(pstr, suites_file.parent, root=root):
                    findings.append(f"[test-suites {rel}:{sname}.{k}] stale script path `{pstr}`")

    return checked, findings, False


def scan_launchd(
    launchd_dir: Path | None,
    *,
    root: Path = ROOT,
) -> tuple[int, list[str], bool]:
    """Scan Carrier 5: Host-level launch agents (conditional on Darwin or explicit `--launchd-dir`)."""
    if launchd_dir is None:
        if sys.platform != "darwin":
            return 0, [], False
        launchd_dir = Path.home() / "Library" / "LaunchAgents"
        if not launchd_dir.is_dir():
            return 0, [], False

    if not launchd_dir.is_dir():
        return 0, [f"[launchd {launchd_dir}] directory does not exist"], True

    plists = sorted(launchd_dir.glob("com.w0m.*.plist"))
    checked = 0
    findings: list[str] = []
    for plist_path in plists:
        try:
            pdata = plistlib.loads(plist_path.read_bytes())
        except Exception as exc:
            findings.append(f"[launchd {plist_path.name}] invalid plist: {exc}")
            return checked, findings, True
        prog_args = pdata.get("ProgramArguments", [])
        working_dir = Path(pdata.get("WorkingDirectory", str(root)))
        joined = " ".join(str(x) for x in prog_args)
        checked += 1
        for m in SCRIPT_PATH_RE.finditer(joined):
            pstr = m.group(1)
            if not resolve_script_in_estate(pstr, working_dir, root=root):
                findings.append(f"[launchd {plist_path.name}] stale script path `{pstr}`")

    return checked, findings, False


def check_exemptions(
    findings: list[str],
    exemptions: dict[str, str] | None = None,
    *,
    root: Path = ROOT,
) -> tuple[list[str], list[str]]:
    """Filter findings through `exemptions` and report unreasoned or stale exemptions."""
    ex = EXEMPTIONS if exemptions is None else exemptions
    remaining: list[str] = []
    exempt_errors: list[str] = []

    for key, why in ex.items():
        if not isinstance(why, str) or not why.strip():
            exempt_errors.append(f"[exemption `{key}`] missing written `why` reason")
        elif resolve_script_in_estate(key, root, root=root):
            exempt_errors.append(f"[exemption `{key}`] stale exemption — `{key}` now exists on disk")

    for f in findings:
        if any(k in f and ex.get(k, "").strip() for k in ex):
            continue
        remaining.append(f)

    return remaining + exempt_errors, [k for k in ex if any(k in f for f in findings)]


def default_carriers(root: Path = ROOT) -> tuple[list[Path], list[Path], list[Path], Path]:
    justfiles = [root / "justfile", root / "wom7api" / "justfile"]
    json_files = sorted(
        set(root.glob("project/policies/*.json"))
        | {root / ".w0m" / "sdlc.json"}
        | set(root.glob("wom7web/project/*.json"))
    )
    hook_files = (
        [
            p
            for p in (
                root / ".pre-commit-config.yaml",
                root / "wom7web" / ".pre-commit-config.yaml",
                root / "wom7api" / ".pre-commit-config.yaml",
            )
            if p.is_file()
        ]
        + [p for p in sorted(root.glob("wom7web/.husky/*")) if p.is_file() and not p.name.startswith("_")]
        + [p for p in sorted(root.glob("scripts/hooks/*")) if p.is_file()]
    )
    suites_file = root / "wom7web" / "project" / "test-suites.json"
    return justfiles, json_files, hook_files, suites_file


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="T509 U0 — Verify script paths and --justfile targets across 5 carriers.")
    ap.add_argument("--root", type=Path, default=ROOT, help="Estate root directory")
    ap.add_argument("--justfile", action="append", type=Path, help="Justfile(s) to scan")
    ap.add_argument("--json-file", action="append", type=Path, help="JSON/JSONC policy/profile file(s) to scan")
    ap.add_argument("--hook-file", action="append", type=Path, help="Hook file(s) to scan")
    ap.add_argument("--test-suites", type=Path, default=None, help="test-suites.json path to scan")
    ap.add_argument("--launchd-dir", type=Path, default=None, help="LaunchAgents plist directory to scan")
    ap.add_argument("--strict-forwarders", action="store_true", help="Fail on pending root justfile forwarders")
    args = ap.parse_args(argv)

    root = args.root.resolve()
    def_jf, def_json, def_hooks, def_suites = default_carriers(root)

    custom_mode = any(
        x is not None
        for x in (args.justfile, args.json_file, args.hook_file, args.test_suites, args.launchd_dir)
    )

    justfiles = args.justfile if args.justfile is not None else ([] if custom_mode else def_jf)
    json_files = args.json_file if args.json_file is not None else ([] if custom_mode else def_json)
    hook_files = args.hook_file if args.hook_file is not None else ([] if custom_mode else def_hooks)
    suites_file = args.test_suites if args.test_suites is not None else (None if custom_mode else def_suites)

    total_checked = 0
    all_findings: list[str] = []
    acknowledged: list[str] = []
    unmeasured = False

    if justfiles:
        c, f, ack, u = scan_justfiles(justfiles, root=root, strict_forwarders=args.strict_forwarders)
        total_checked += c
        all_findings.extend(f)
        acknowledged.extend(ack)
        unmeasured |= u

    if json_files:
        c, f, u = scan_json_files(json_files, root=root)
        total_checked += c
        all_findings.extend(f)
        unmeasured |= u

    if hook_files:
        c, f, u = scan_hooks(hook_files, root=root)
        total_checked += c
        all_findings.extend(f)
        unmeasured |= u

    if suites_file is not None:
        c, f, u = scan_test_suites(suites_file, root=root)
        total_checked += c
        all_findings.extend(f)
        unmeasured |= u

    if args.launchd_dir is not None or not custom_mode:
        c, f, u = scan_launchd(args.launchd_dir, root=root)
        total_checked += c
        all_findings.extend(f)
        unmeasured |= u

    if unmeasured or total_checked == 0:
        for f in all_findings:
            print(f"  ✗ {f}")
        print("❌ stale-path-check: could not measure one or more carriers — exit 2 (not passing).")
        return 2

    final_findings, _ = check_exemptions(all_findings, root=root)

    if acknowledged:
        print(f"  [INFO] {len(acknowledged)} pending root justfile forwarder(s) reported for coordinator cleanup:")
        for a in acknowledged:
            print(f"      · {a}")

    if final_findings:
        print(f"❌ stale-path-check: {len(final_findings)} stale path / dangling target finding(s) across {total_checked} check(s):")
        for f in final_findings:
            print(f"  ✗ {f}")
        return 1

    print(f"✅ stale-path-check: {total_checked} reference(s) verified across active carriers, 0 stale paths.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
