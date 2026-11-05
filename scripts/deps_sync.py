#!/usr/bin/env python3
"""Cross-repo pnpm & tracked-npm dependency alignment for the w0m TS repos (T140, T298).

One canonical policy (`project/deps-policy.json`) drives three checks against every TS repo's
`package.json` `pnpm.overrides`, `pnpm-lock.yaml`, and tracked `package-lock.json`:

  - lockstep : named deps must be byte-identical across a set of repos (e.g. hono → web/api/cf)
  - floors   : security floors — every repo that HAS the override must satisfy both the lower
               bound (`>=x.y.z`) and optional upper ceiling (`<a.b.c` or `<a`), and its
               `pnpm-lock.yaml` + tracked npm `package-lock.json` files must not resolve a
               version `< lower` or `>= upper` (T140, T298)
  - advisory : should-align deps that are only warned about (a bump needs per-repo testing)

Non-vacuous reporting (T298 AC1/AC2):
  A repo where zero floors land is reported in its own state (`no_floor_applies` /
  `no floor applies`) and is NEVER counted as aligned alongside repos where floors were checked.
  A repo carrying zero `pnpm.overrides` in `package.json` is explicitly distinguished from
  override-bearing repos in the summary line.

Preventive vs detective division of labour (T298 AC6):
  - `deps-check` (`deps_sync.py` / `deps_check.py`) is PREVENTIVE and authoritative for cross-repo
    version alignment (`lockstep`, `toolchain`) and preventing regression below established security
    floors (`floors`) across `package.json`, `pnpm-lock.yaml`, and tracked `package-lock.json`.
  - `osv-scanner` is DETECTIVE and authoritative for discovering newly published CVEs/GHSAs across
    all lockfiles before a floor exists in `deps-policy.json`.

Usage (from anywhere):
    python3 scripts/deps_sync.py            # check, exit 1 on drift or missing workspace .bin tools
    python3 scripts/deps_sync.py --apply    # fix in place, then `pnpm install` per repo
    python3 scripts/deps_sync.py --install  # install missing node_modules/.bin across all TS repos
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path
from typing import Any, cast

# workspace root = .../@wom  (this file is scripts/deps_sync.py)
ROOT = Path(__file__).resolve().parents[1]
POLICY = ROOT / "project" / "policies" / "deps-policy.json"


def _ver_tuple(major: str, minor: str | None, patch: str | None) -> tuple[int, int, int]:
    return (int(major), int(minor or 0), int(patch or 0))


def parse_range(spec: str) -> tuple[tuple[int, int, int], tuple[int, int, int] | None]:
    """Parse a version range into `(lower, upper | None)` (T140 AC1).

    Supports:
      - `>=x.y.z`          -> `((x, y, z), None)`
      - `>=x.y.z <a.b.c`   -> `((x, y, z), (a, b, c))`
      - `>=x.y.z <a`       -> `((x, y, z), (a, 0, 0))`
      - `^x.y.z` / `x.y.z` -> `((x, y, z), None)`
    """
    raw = spec or ""
    upper: tuple[int, int, int] | None = None
    upper_match = re.search(r"<(?!=)\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?", raw)
    if upper_match:
        u_maj, u_min, u_pat = upper_match.groups()
        upper = _ver_tuple(u_maj, u_min, u_pat)
        lower_part = raw[: upper_match.start()]
    else:
        lower_part = raw

    lower_match = re.search(r"(\d+)\.(\d+)\.(\d+)", lower_part)
    if lower_match:
        l_maj, l_min, l_pat = lower_match.groups()
        lower = _ver_tuple(l_maj, l_min, l_pat)
    else:
        short_match = re.search(r"(?:>=|\^|~|=)?\s*(\d+)(?:\.(\d+))?", lower_part)
        if short_match and short_match.group(1):
            lower = _ver_tuple(short_match.group(1), short_match.group(2), None)
        else:
            lower = (0, 0, 0)

    return lower, upper


def semver(spec: str) -> tuple[int, int, int]:
    """First x.y.z lower bound found in a range spec ('>=0.35.0', '^2.110.7', '>=7.6.5 <8') -> tuple."""
    return parse_range(spec)[0]


def load(path: Path) -> tuple[dict, str]:
    text = path.read_text(encoding="utf-8")
    return cast(dict[str, Any], json.loads(text)), text


def overrides_of(pkg: dict) -> dict:
    return pkg.get("pnpm", {}).get("overrides", {})


def declared_version(pkg: dict, dep: str) -> tuple[str | None, str]:
    """Where a repo pins `dep`, and in which section. Returns (version, section).

    ⚠️ lockstep originally read ONLY `pnpm.overrides`, while the floors check beside it merged
    dependencies + devDependencies. That asymmetry made lockstep silently unusable for a DIRECT
    dependency: declaring one produced `has None` on every repo that plainly declared it
    (wrangler, 2026-08-11). Overrides still win — they are the stronger claim, forcing the whole
    transitive tree — but a direct dep now counts, because "these repos must agree on this
    version" is the intent regardless of which section expresses it.
    """
    ov = overrides_of(pkg).get(dep)
    if ov is not None:
        return ov, "pnpm.overrides"
    dev = pkg.get("devDependencies", {}).get(dep)
    if dev is not None:
        return dev, "devDependencies"
    return pkg.get("dependencies", {}).get(dep), "dependencies"


def lockfile_versions(repo_dir: Path, dep: str) -> list[tuple[int, int, int]]:
    """All resolved versions of `dep` in the repo's `pnpm-lock.yaml` (empty list if absent).

    Supports both direct package keys (`undici@7.30.0`) and parent-scoped overrides (`postcss>nanoid`,
    resolved inside the `postcss@...:` snapshot block).
    """
    lock = repo_dir / "pnpm-lock.yaml"
    if not lock.exists():
        return []
    content = lock.read_text(encoding="utf-8")
    found: list[tuple[int, int, int]] = []

    if ">" in dep:
        parent, child = dep.rsplit(">", 1)
        block_pat = re.compile(
            rf"^\s{{2}}['\"]?{re.escape(parent)}@[^\n:]+\n(?:\s{{4,}}[^\n]+\n)*",
            re.M,
        )
        child_pat = re.compile(rf"^\s{{6}}{re.escape(child)}:\s*(\d+)\.(\d+)\.(\d+)", re.M)
        for block in block_pat.findall(content):
            for maj, min_, pat_ in child_pat.findall(block):
                found.append((int(maj), int(min_), int(pat_)))
        return found

    # lockfile keys look like "  '@hono/node-server@1.19.14':" or "  sharp@0.34.5:" —
    # allow a leading line-start, whitespace, quote or slash before the name token.
    pat = re.compile(rf"(?:^|[\s'\"/]){re.escape(dep)}@(\d+\.\d+\.\d+)", re.M)
    for m in pat.findall(content):
        major, minor, patch = m.split(".")
        found.append((int(major), int(minor), int(patch)))
    return found


def lockfile_min(repo_dir: Path, dep: str) -> tuple[int, int, int] | None:
    """Lowest resolved version of `dep` in the repo's pnpm-lock.yaml, or None if absent.

    Lets a security floor be INJECTED into a repo that resolves a vulnerable version but has
    no override yet (the w0m-cf case) — without over-constraining repos that don't use it.
    """
    found = lockfile_versions(repo_dir, dep)
    return min(found) if found else None


def lockfile_max(repo_dir: Path, dep: str) -> tuple[int, int, int] | None:
    """Highest resolved version of `dep` in the repo's pnpm-lock.yaml, or None if absent (T140 AC5)."""
    found = lockfile_versions(repo_dir, dep)
    return max(found) if found else None


def tracked_npm_lockfiles(repo_dir: Path) -> list[Path]:
    """Return tracked npm `package-lock.json` files inside `repo_dir` (T298 AC3).

    In git-backed repos (`w0m-web`, `w0m-ext`, `w0m-skills`, etc.), `git ls-files` is used so
    untracked vendored trees (`w0m-web`'s 43 and `w0m-ext`'s 1 untracked package-lock.json files)
    are never picked up. In non-git synthetic test fixtures, falls back to walking `repo_dir`
    while excluding `node_modules` and `.git`.
    """
    if not repo_dir.exists():
        return []
    has_git = (repo_dir / ".git").exists() or (repo_dir.parent / ".git").exists()
    if has_git:
        env = {**os.environ, "LC_ALL": "C"}
        proc = subprocess.run(
            [
                "git",
                "--no-pager",
                "-C",
                str(repo_dir),
                "ls-files",
                "package-lock.json",
                "*/package-lock.json",
                "**/package-lock.json",
            ],
            capture_output=True,
            text=True,
            env=env,
            check=False,
        )
        if proc.returncode == 0:
            seen: set[Path] = set()
            result: list[Path] = []
            for raw in proc.stdout.splitlines():
                rel = raw.strip()
                if not rel:
                    continue
                candidate = (repo_dir / rel).resolve()
                if candidate.exists() and candidate not in seen:
                    seen.add(candidate)
                    result.append(candidate)
            return sorted(result)
    return sorted(
        p.resolve()
        for p in repo_dir.rglob("package-lock.json")
        if "node_modules" not in p.parts and ".git" not in p.parts
    )


def _extract_v1_npm_deps(deps_obj: dict, dep: str, out: list[tuple[int, int, int]]) -> None:
    """Recursively extract resolved versions from npm lockfileVersion 1 `dependencies`."""
    for name, info in deps_obj.items():
        if not isinstance(info, dict):
            continue
        if name == dep and isinstance(info.get("version"), str):
            m = re.match(r"^(\d+)\.(\d+)\.(\d+)", info["version"].strip())
            if m:
                out.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
        nested = info.get("dependencies")
        if isinstance(nested, dict):
            _extract_v1_npm_deps(nested, dep, out)


def npm_lockfile_versions_by_file(
    repo_dir: Path, dep: str
) -> list[tuple[Path, list[tuple[int, int, int]]]]:
    """Resolved versions of `dep` across tracked `package-lock.json` files in `repo_dir` (T298 AC3)."""
    results: list[tuple[Path, list[tuple[int, int, int]]]] = []
    for lock_path in tracked_npm_lockfiles(repo_dir):
        try:
            data: dict = json.loads(lock_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        found: list[tuple[int, int, int]] = []
        packages = data.get("packages")
        if isinstance(packages, dict):
            if ">" in dep:
                parent, child = dep.rsplit(">", 1)
                suffix = f"node_modules/{parent}/node_modules/{child}"
                for key, info in packages.items():
                    if not isinstance(info, dict):
                        continue
                    if key == suffix or key.endswith(f"/{suffix}"):
                        ver = info.get("version")
                        if isinstance(ver, str):
                            m = re.match(r"^(\d+)\.(\d+)\.(\d+)", ver.strip())
                            if m:
                                found.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
            else:
                for key, info in packages.items():
                    if not key.startswith("node_modules/") or not isinstance(info, dict):
                        continue
                    pkg_name = key.rsplit("node_modules/", 1)[-1]
                    if pkg_name == dep:
                        ver = info.get("version")
                        if isinstance(ver, str):
                            m = re.match(r"^(\d+)\.(\d+)\.(\d+)", ver.strip())
                            if m:
                                found.append((int(m.group(1)), int(m.group(2)), int(m.group(3))))
        elif isinstance(data.get("dependencies"), dict) and ">" not in dep:
            _extract_v1_npm_deps(data["dependencies"], dep, found)
        if found:
            results.append((lock_path, found))
    return results


def npm_lockfile_versions(repo_dir: Path, dep: str) -> list[tuple[int, int, int]]:
    """Flattened list of resolved versions of `dep` in tracked `package-lock.json` files."""
    out: list[tuple[int, int, int]] = []
    for _, vers in npm_lockfile_versions_by_file(repo_dir, dep):
        out.extend(vers)
    return out


# T135 task 1.3: mirrors the rule discovery.py enforces on stacks-policy.json's `exempt`.
# Kept in step with scripts/discovery.py -> MIN_REASON_LEN.
MIN_REASON_LEN = 25


def check_policy_integrity(policy: dict) -> list[str]:
    """T135 task 1.3: every documented divergence carries a substantive reason.

    `exceptions` is deps-policy's exemption surface: listing a dep here tells `--check` never to
    flag it. That silences a real signal, so the entry must say WHY, at enough length that a
    successor can re-evaluate it — the undici entry is the model (it records the jsdom/undici-8
    incompatibility and warns against 'aligning' api/cfworkers back to 7).

    A bare `"undici": "exception"` would suppress the check while recording nothing, which is the
    same vacuous-record failure as an unreasoned stack exemption.
    """
    problems: list[str] = []
    exceptions = policy.get("exceptions")
    if exceptions is None:
        exceptions_dict: dict = {}
    elif not isinstance(exceptions, dict):
        return [
            "deps-policy `exceptions` must be an object mapping each dep to a reason, "
            f"not {type(exceptions).__name__} — a bare name records no decision"
        ]
    else:
        exceptions_dict = exceptions
        for dep, reason in exceptions.items():
            if dep.startswith("_"):
                continue  # `_comment` is documentation, not an entry
            if not isinstance(reason, str) or not reason.strip():
                problems.append(f"exceptions {dep}: missing a reason — a suppressed check must say why")
            elif reason.strip().strip(".").lower() == dep.strip().lower():
                problems.append(f"exceptions {dep}: the reason merely restates the dep name")
            elif len(reason.strip()) < MIN_REASON_LEN:
                problems.append(
                    f"exceptions {dep}: reason is {len(reason.strip())} chars, needs >= {MIN_REASON_LEN}"
                )

    repo_floors = policy.get("repo_floors", {})
    if isinstance(repo_floors, dict):
        for dep in repo_floors:
            if dep.startswith("_"):
                continue
            if dep not in exceptions_dict:
                problems.append(
                    f"repo_floors {dep}: per-repo floor override requires a documented reason in `exceptions`"
                )

    # T56 AC2/AC3: lagging entries must not hardcode static 'N minors behind' counts,
    # and structured entries must carry a substantive reason + YYYY-MM-DD recheck_by date.
    advisory = policy.get("aligned_advisory", {})
    if isinstance(advisory, dict):
        for dep, rule in advisory.items():
            if dep.startswith("_") or not isinstance(rule, dict):
                continue
            lagging = rule.get("lagging") or {}
            if not isinstance(lagging, dict):
                continue
            for site, entry in lagging.items():
                if site.startswith("_"):
                    continue
                if isinstance(entry, str):
                    if re.search(r"\b\d+\s+minors?\s+behind\b", entry, re.I):
                        problems.append(
                            f"aligned_advisory {dep} ({site}): lagging entry hardcodes 'N minors behind' — "
                            "minor lag must be derived dynamically at check time (T56 AC3)"
                        )
                elif isinstance(entry, dict):
                    reason = str(entry.get("reason") or "").strip()
                    recheck_by = str(entry.get("recheck_by") or "").strip()
                    if len(reason) < MIN_REASON_LEN:
                        problems.append(
                            f"aligned_advisory {dep} ({site}): lagging reason is {len(reason)} chars, "
                            f"needs >= {MIN_REASON_LEN} (T56 AC2)"
                        )
                    if re.search(r"\b\d+\s+minors?\s+behind\b", reason, re.I):
                        problems.append(
                            f"aligned_advisory {dep} ({site}): lagging reason hardcodes 'N minors behind' — "
                            "minor lag must be derived dynamically at check time (T56 AC3)"
                        )
                    if not re.match(r"^\d{4}-\d{2}-\d{2}$", recheck_by):
                        problems.append(
                            f"aligned_advisory {dep} ({site}): lagging entry requires a valid YYYY-MM-DD "
                            "`recheck_by` date (T56 AC2)"
                        )
    return problems


def load_jsonc(path: Path) -> dict:
    """Parse a `.jsonc` file (JSON with `//` / `/* ... */` comments and trailing commas) (T113 AC5)."""
    text = path.read_text(encoding="utf-8")
    stripped = re.sub(
        r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
        lambda m: m.group(0) if m.group(0).startswith('"') else "",
        text,
    )
    cleaned = re.sub(r",\s*([\]}])", r"\1", stripped)
    return cast(dict, json.loads(cleaned))


def compute_minor_lag(current_spec: str, target_spec: str) -> int:
    """Dynamically compute how many minor versions `current_spec` is behind `target_spec` (T56 AC3)."""
    c_maj, c_min, _ = semver(current_spec)
    t_maj, t_min, _ = semver(target_spec)
    if (c_maj, c_min) == (0, 0) or (t_maj, t_min) == (0, 0):
        return 0
    if c_maj == t_maj:
        return max(0, t_min - c_min)
    if c_maj < t_maj:
        return max(1, (t_maj - c_maj) * 100 + (t_min - c_min))
    return 0


def _parse_workspace_globs(workspace_yaml: Path) -> list[str]:
    """Extract `packages:` globs from `pnpm-workspace.yaml` without external YAML dependencies (T56 AC1)."""
    if not workspace_yaml.is_file():
        return []
    try:
        lines = workspace_yaml.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    globs: list[str] = []
    in_packages = False
    for raw in lines:
        stripped = raw.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if re.match(r"^packages\s*:", stripped):
            in_packages = True
            continue
        if in_packages:
            if not raw.startswith((" ", "\t", "-")):
                break
            m = re.match(r"^\s*-\s*['\"]?([^'\"#]+?)['\"]?\s*(?:#.*)?$", raw)
            if m:
                pat = m.group(1).strip()
                if pat and not pat.startswith("!"):
                    globs.append(pat)
    return globs


_EXCLUDED_WS_PARTS = frozenset({"node_modules", ".astro", "dist", ".git", ".wrangler", ".agents"})


def discover_workspace_packages(
    repos: dict[str, Path],
    root_pkgs: dict[str, dict] | None = None,
) -> list[tuple[str, str, Path, dict]]:
    """Enumerate every `package.json` in each repo's pnpm workspace, not just the root (T56 AC1).

    Returns a deterministic list of `(ws_key, repo_name, pkg_path, pkg_dict)` tuples where
    `ws_key` is the workspace-qualified identifier (e.g. `"w0m-web"`, `"w0m-web/apps/me"`,
    `"w0m-web/packages/lib"`, `"w0m-ext/extension"`).
    """
    discovered: list[tuple[str, str, Path, dict]] = []
    seen_paths: set[Path] = set()

    for repo_name, root_pkg_path in repos.items():
        if root_pkgs is not None and repo_name in root_pkgs:
            root_pkg = root_pkgs[repo_name]
        elif root_pkg_path.is_file():
            try:
                root_pkg, _ = load(root_pkg_path)
            except (OSError, json.JSONDecodeError):
                continue
        else:
            continue

        repo_dir = root_pkg_path.parent
        if repo_dir.name != repo_name and repo_dir.parent.name == repo_name:
            root_ws_key = f"{repo_name}/{repo_dir.name}"
        else:
            root_ws_key = repo_name

        resolved_root = root_pkg_path.resolve() if root_pkg_path.exists() else root_pkg_path
        seen_paths.add(resolved_root)
        discovered.append((root_ws_key, repo_name, root_pkg_path, root_pkg))

        if not repo_dir.is_dir():
            continue

        ws_globs = _parse_workspace_globs(repo_dir / "pnpm-workspace.yaml")
        for default_pat in ("apps/*", "packages/*"):
            if default_pat not in ws_globs:
                ws_globs.append(default_pat)

        sub_candidates: list[Path] = []
        for pat in ws_globs:
            clean_pat = pat.rstrip("/")
            for match_dir in sorted(repo_dir.glob(clean_pat)):
                if not match_dir.is_dir():
                    continue
                rel_parts = match_dir.relative_to(repo_dir).parts
                if any(part in _EXCLUDED_WS_PARTS for part in rel_parts):
                    continue
                cand = match_dir / "package.json"
                if cand.is_file():
                    sub_candidates.append(cand)

        for sub_pkg_path in sorted(sub_candidates):
            res_sub = sub_pkg_path.resolve()
            if res_sub in seen_paths:
                continue
            try:
                sub_pkg, _ = load(sub_pkg_path)
            except (OSError, json.JSONDecodeError):
                continue
            seen_paths.add(res_sub)
            rel_sub = sub_pkg_path.parent.relative_to(repo_dir).as_posix()
            ws_key = f"{root_ws_key}/{rel_sub}"
            discovered.append((ws_key, repo_name, sub_pkg_path, sub_pkg))

    return discovered


def _lookup_lagging_entry(
    lagging: dict,
    ws_key: str,
    repo_name: str,
    is_root: bool,
) -> tuple[str | None, object]:
    """Match a workspace key (`w0m-web/apps/me` or `w0m-ext/extension`) against `lagging` (T56 AC4)."""
    if ws_key in lagging:
        return ws_key, lagging[ws_key]
    if is_root and repo_name in lagging:
        return repo_name, lagging[repo_name]
    return None, None


def check_runtime_alignment(
    policy: dict,
    repos: dict[str, Path],
    pkgs: dict[str, dict],
    estate_root: Path | None = None,
) -> list[str]:
    """T113 AC1/AC2/AC5: Verify CF `compatibility_date`, `nodejs_compat`, `.nvmrc`, and `engines`."""
    rt = policy.get("runtime")
    if not isinstance(rt, dict):
        return []

    if estate_root is not None:
        base_root = estate_root
    elif "w0m-web" in repos:
        base_root = repos["w0m-web"].parent.parent
    elif repos:
        first_repo, first_path = next(iter(repos.items()))
        base_root = (
            first_path.parent.parent.parent
            if first_path.parent.name != first_repo and first_path.parent.parent.name == first_repo
            else first_path.parent.parent
        )
    else:
        base_root = ROOT

    problems: list[str] = []

    want_nvmrc = rt.get("nvmrc")
    if isinstance(want_nvmrc, str) and want_nvmrc.strip():
        for rel_nvm in rt.get("nvmrc_files", []):
            nvm_path = base_root / rel_nvm
            if not nvm_path.is_file():
                problems.append(f"runtime .nvmrc: missing {rel_nvm} (expected {want_nvmrc!r})")
            else:
                actual = nvm_path.read_text(encoding="utf-8").strip().lstrip("v")
                if actual != want_nvmrc.lstrip("v"):
                    problems.append(
                        f"runtime .nvmrc: {rel_nvm} has {actual!r}, must be {want_nvmrc!r}"
                    )

    want_engines = rt.get("engines")
    if isinstance(want_engines, dict):
        for r in rt.get("engines_repos", []):
            if r not in pkgs:
                continue
            eng = pkgs[r].get("engines") or {}
            for eng_key, want_range in want_engines.items():
                cur_range = eng.get(eng_key)
                if cur_range != want_range:
                    problems.append(
                        f"runtime engines.{eng_key}: {r} has {cur_range!r}, must be {want_range!r}"
                    )

    want_cdate = rt.get("compatibility_date")
    req_flags = list(rt.get("required_compatibility_flags") or [])
    for rel_cfg in rt.get("wrangler_configs", []):
        cfg_path = base_root / rel_cfg
        if not cfg_path.is_file():
            problems.append(f"runtime wrangler: missing {rel_cfg}")
            continue
        try:
            wdata = load_jsonc(cfg_path)
        except (OSError, json.JSONDecodeError) as exc:
            problems.append(f"runtime wrangler: failed to parse {rel_cfg}: {exc}")
            continue
        cdate = wdata.get("compatibility_date")
        if isinstance(want_cdate, str) and cdate != want_cdate:
            problems.append(
                f"runtime compatibility_date: {rel_cfg} has {cdate!r}, must be {want_cdate!r}"
            )
        cflags = wdata.get("compatibility_flags") or []
        for flag in req_flags:
            if flag not in cflags:
                problems.append(
                    f"runtime compatibility_flags: {rel_cfg} missing {flag!r} (has {cflags!r})"
                )

    return problems


def effective_floor(policy: dict, dep: str, repo: str, default_floor: str) -> str:
    """Return the effective floor string for `(dep, repo)`, honoring documented `repo_floors`."""
    repo_floors = policy.get("repo_floors", {})
    if isinstance(repo_floors, dict):
        per_dep = repo_floors.get(dep)
        if isinstance(per_dep, dict):
            override = per_dep.get(repo)
            if isinstance(override, str) and override.strip():
                return override
    return default_floor


def _detect_host_node_version() -> tuple[int, int, int] | None:
    """Return the active host `node -v` as `(major, minor, patch)`, or None if unavailable."""
    try:
        proc = subprocess.run(
            ["node", "-v"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if proc.returncode != 0:
        return None
    m = re.search(r"v?(\d+)\.(\d+)\.(\d+)", proc.stdout.strip())
    if not m:
        return None
    return (int(m.group(1)), int(m.group(2)), int(m.group(3)))


def version_satisfies_range(ver: tuple[int, int, int], spec: str) -> bool:
    """Check whether `(major, minor, patch)` satisfies a semver range expression (including `||` unions).

    Supports:
      - `>=x.y.z`, `>=x.y.z <a.b.c`
      - `^x.y.z` (same major `x` and `>= (x, y, z)` for `x > 0`; same `0.y` for `x == 0`)
      - `~x.y.z` (same `(x, y)` and `>= (x, y, z)`)
      - union clauses separated by `||`
    """
    clauses = [c.strip() for c in (spec or "").split("||") if c.strip()]
    if not clauses:
        return True
    for clause in clauses:
        caret = re.match(r"^\^\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?$", clause)
        if caret:
            maj, min_, pat_ = _ver_tuple(caret.group(1), caret.group(2), caret.group(3))
            caret_upper = (maj + 1, 0, 0) if maj > 0 else (0, min_ + 1, 0)
            if (maj, min_, pat_) <= ver < caret_upper:
                return True
            continue
        tilde = re.match(r"^~\s*(\d+)(?:\.(\d+))?(?:\.(\d+))?$", clause)
        if tilde:
            maj, min_, pat_ = _ver_tuple(tilde.group(1), tilde.group(2), tilde.group(3))
            if (maj, min_, pat_) <= ver < (maj, min_ + 1, 0):
                return True
            continue
        lower, upper = parse_range(clause)
        if ver >= lower and (upper is None or ver < upper):
            return True
    return False


WORKSPACE_CRITICAL_BINS: tuple[tuple[str, str], ...] = (
    ("tsx", "tsx"),
    ("wrangler", "wrangler"),
    ("vitest", "vitest"),
    ("typescript", "tsc"),
    ("oxlint", "oxlint"),
    ("oxfmt", "oxfmt"),
    ("astro", "astro"),
    ("drizzle-kit", "drizzle-kit"),
)


def _resolve_worktree_main_repo_dir(repo_dir: Path) -> Path | None:
    """If `repo_dir` is inside a git linked worktree, return the corresponding directory in the main checkout."""
    for candidate in (repo_dir, repo_dir.parent):
        git_marker = candidate / ".git"
        if git_marker.is_file():
            try:
                raw = git_marker.read_text(encoding="utf-8").strip()
            except OSError:
                return None
            if not raw.startswith("gitdir:"):
                return None
            gitdir_str = raw.split(":", 1)[1].strip()
            gitdir_path = Path(gitdir_str)
            if not gitdir_path.is_absolute():
                gitdir_path = (candidate / gitdir_path).resolve()
            if gitdir_path.parent.name == "worktrees" and gitdir_path.parent.parent.name == ".git":
                main_root = gitdir_path.parent.parent.parent
                rel = repo_dir.relative_to(candidate)
                return (main_root / rel).resolve()
            return None
        if git_marker.is_dir():
            return None
    return None


def _effective_node_modules(repo_dir: Path, *, strict_local: bool = False) -> Path:
    """Return `repo_dir / 'node_modules'`, or the main checkout's `node_modules` when in a linked worktree."""
    local_nm = repo_dir / "node_modules"
    if strict_local or local_nm.is_dir():
        return local_nm
    main_repo_dir = _resolve_worktree_main_repo_dir(repo_dir)
    if main_repo_dir is not None:
        main_nm = main_repo_dir / "node_modules"
        if main_nm.is_dir():
            return main_nm
    return local_nm


def check_workspace_bins(
    repos: dict[str, Path],
    pkgs: dict[str, dict] | None = None,
    *,
    strict_local: bool = False,
) -> list[str]:
    """T595: Verify every TS repo has `node_modules/.bin` and all critical CLI binaries it declares."""
    problems: list[str] = []
    for repo_name, pkg_path in repos.items():
        if pkgs is not None and repo_name in pkgs:
            pkg = pkgs[repo_name]
        elif pkg_path.is_file():
            try:
                pkg, _ = load(pkg_path)
            except (OSError, json.JSONDecodeError):
                continue
        else:
            continue

        all_deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }
        expected = [
            (dep_name, bin_name)
            for dep_name, bin_name in WORKSPACE_CRITICAL_BINS
            if dep_name in all_deps
        ]
        if not expected:
            continue

        repo_dir = pkg_path.parent
        nm = _effective_node_modules(repo_dir, strict_local=strict_local)
        bin_dir = nm / ".bin"
        rel_dir = (
            repo_dir.relative_to(ROOT).as_posix()
            if repo_dir.is_relative_to(ROOT)
            else repo_name
        )
        if not bin_dir.is_dir():
            bins_str = ", ".join(b for _, b in expected)
            problems.append(
                f"workspace-bins: {repo_name} missing node_modules/.bin (declares {bins_str}) — "
                f"run `just deps-install` or `pnpm --dir {rel_dir} install --frozen-lockfile`"
            )
            continue

        missing_bins = [
            f"{bin_name} (from {dep_name})"
            for dep_name, bin_name in expected
            if not (bin_dir / bin_name).exists()
        ]
        if missing_bins:
            problems.append(
                f"workspace-bins: {repo_name} missing {', '.join(missing_bins)} in node_modules/.bin — "
                f"run `just deps-install` or `pnpm --dir {rel_dir} install --frozen-lockfile`"
            )
    return problems


def install_workspace_deps(
    repos: dict[str, Path],
    pkgs: dict[str, dict] | None = None,
) -> int:
    """T595: Install missing `node_modules/.bin` across TS repos using `pnpm install --frozen-lockfile`."""
    reinstalled: list[str] = []
    for repo_name, pkg_path in repos.items():
        if not pkg_path.is_file():
            continue
        single_repo = {repo_name: pkg_path}
        single_pkg = {repo_name: pkgs[repo_name]} if (pkgs and repo_name in pkgs) else None
        missing = check_workspace_bins(single_repo, single_pkg, strict_local=True)
        if not missing:
            continue
        repo_dir = pkg_path.parent
        print(f"  ▶ installing workspace dependencies in {repo_name} ({repo_dir})...")
        proc = subprocess.run(
            ["pnpm", "--dir", str(repo_dir), "install", "--frozen-lockfile", "--prefer-offline"],
            check=False,
        )
        if proc.returncode != 0:
            print(f"  ✗ pnpm install failed in {repo_name} (exit {proc.returncode})", file=sys.stderr)
            return proc.returncode
        reinstalled.append(repo_name)

    post_problems = check_workspace_bins(repos, pkgs, strict_local=True)
    if post_problems:
        for p in post_problems:
            print(f"  ✗ {p}", file=sys.stderr)
        return 1
    if reinstalled:
        print(f"  ✓ installed workspace binaries in {len(reinstalled)} repo(s): {', '.join(reinstalled)}")
    else:
        print(f"  ✓ all {len(repos)} TS repos already have complete node_modules/.bin toolchains")
    return 0


def check_node_engines(
    repos: dict[str, Path],
    host_node_version: tuple[int, int, int] | None = None,
) -> list[str]:
    """T566 AC2: Verify host `node -v` satisfies `engines.node` of installed critical packages."""
    node_ver = host_node_version if host_node_version is not None else _detect_host_node_version()
    if node_ver is None:
        return []
    node_str = ".".join(map(str, node_ver))
    problems: list[str] = []
    critical_pkgs = ("astro", "wrangler", "vite", "vitest", "tsx")

    for repo_name, pkg_path in repos.items():
        repo_dir = pkg_path.parent
        nm = _effective_node_modules(repo_dir)
        if not nm.is_dir():
            continue
        candidates: list[Path] = [pkg_path]
        for c in critical_pkgs:
            p = nm / c / "package.json"
            if p.is_file():
                candidates.append(p)
        astrojs_dir = nm / "@astrojs"
        if astrojs_dir.is_dir():
            candidates.extend(sorted(astrojs_dir.glob("*/package.json")))

        for mf in candidates:
            try:
                data: dict[str, object] = json.loads(mf.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            engines_raw = data.get("engines")
            eng_node = engines_raw.get("node") if isinstance(engines_raw, dict) else None
            if not isinstance(eng_node, str) or not eng_node.strip():
                continue
            if not version_satisfies_range(node_ver, eng_node):
                pkg_name = data.get("name") or mf.parent.name
                pkg_ver = data.get("version") or "unknown"
                problems.append(
                    f"engines.node: {repo_name} installed {pkg_name}@{pkg_ver} requires node {eng_node!r}, "
                    f"but host node is {node_str}"
                )
    return problems


def _collect_esm_exports(js_file: Path, _seen: set[Path] | None = None) -> set[str]:
    """Extract static ESM named exports from `js_file` (following relative re-exports)."""
    seen = _seen if _seen is not None else set()
    resolved = js_file.resolve()
    if resolved in seen or not resolved.is_file():
        return set()
    seen.add(resolved)
    try:
        text = resolved.read_text(encoding="utf-8")
    except OSError:
        return set()

    exports: set[str] = set()
    # 1. `export { a, b as c }` or `export { a, b as c } from "./other.js"`
    for m in re.finditer(r"export\s*\{([^}]+)\}(?:\s*from\s*['\"]([^'\"]+)['\"])?", text):
        spec_block = m.group(1)
        for item in spec_block.split(","):
            tok = item.strip()
            if not tok:
                continue
            parts = re.split(r"\s+as\s+", tok)
            exported_name = parts[-1].strip()
            if re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", exported_name):
                exports.add(exported_name)

    # 2. `export function foo`, `export async function foo`, `export const/let/var/class foo`
    for m in re.finditer(
        r"export\s+(?:async\s+)?(?:function\*?|const|let|var|class)\s+([A-Za-z_$][A-Za-z0-9_$]*)",
        text,
    ):
        exports.add(m.group(1))

    # 3. `export * from "./other.js"`
    for m in re.finditer(r"export\s*\*\s*from\s*['\"]([^'\"]+)['\"]", text):
        rel = m.group(1)
        if rel.startswith("."):
            target = (resolved.parent / rel).resolve()
            exports.update(_collect_esm_exports(target, seen))

    return exports


def _resolve_astro_subpath(astro_dir: Path, astro_pkg: dict, specifier: str) -> Path | None:
    """Resolve `"astro"` or `"astro/<subpath>"` via `astro/package.json -> exports`."""
    exports_map = astro_pkg.get("exports") or {}
    subkey = "." if specifier == "astro" else "./" + specifier[len("astro/") :]
    entry = exports_map.get(subkey)
    rel_target: str | None = None
    if isinstance(entry, str):
        rel_target = entry
    elif isinstance(entry, dict):
        rel_target = entry.get("default") or entry.get("import")
    if not rel_target or not rel_target.endswith((".js", ".mjs")):
        return None
    return (astro_dir / rel_target).resolve()


def check_astro_adapter_exports(web_dir: Path) -> list[str]:
    """T566 AC2: Verify `@astrojs/*` ESM named imports resolve in `astro/*` and peerDependencies match."""
    nm = web_dir / "node_modules"
    astro_link = nm / "astro"
    if not (astro_link / "package.json").is_file():
        return []
    astro_dir = astro_link.resolve()
    astro_pkg_path = astro_dir / "package.json"
    try:
        astro_pkg: dict = json.loads(astro_pkg_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []

    astro_ver_str = str(astro_pkg.get("version") or "0.0.0")
    astro_ver = semver(astro_ver_str)

    wrangler_ver: tuple[int, int, int] | None = None
    wrangler_ver_str = ""
    wrangler_pkg_path = nm / "wrangler" / "package.json"
    if wrangler_pkg_path.is_file():
        try:
            wpkg: dict = json.loads(wrangler_pkg_path.read_text(encoding="utf-8"))
            wrangler_ver_str = str(wpkg.get("version") or "")
            if wrangler_ver_str:
                wrangler_ver = semver(wrangler_ver_str)
        except (OSError, json.JSONDecodeError):
            pass

    problems: list[str] = []
    export_cache: dict[Path, set[str]] = {}
    seen_pkg_dirs: set[Path] = set()

    astrojs_dirs = [nm / "@astrojs"]
    apps_dir = web_dir / "apps"
    if apps_dir.is_dir():
        astrojs_dirs.extend(sorted(apps_dir.glob("*/node_modules/@astrojs")))

    for astrojs_dir in astrojs_dirs:
        if not astrojs_dir.is_dir():
            continue
        for pkg_json in sorted(astrojs_dir.glob("*/package.json")):
            pkg_dir = pkg_json.parent.resolve()
            if pkg_dir in seen_pkg_dirs:
                continue
            seen_pkg_dirs.add(pkg_dir)
            try:
                pdata: dict = json.loads(pkg_json.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                continue
            pkg_name = pdata.get("name") or f"@astrojs/{pkg_json.parent.name}"
            pkg_ver = pdata.get("version") or "unknown"
            peers = pdata.get("peerDependencies") or {}
            peer_astro = peers.get("astro")
            if isinstance(peer_astro, str) and not version_satisfies_range(astro_ver, peer_astro):
                problems.append(
                    f"astro-peer: {pkg_name}@{pkg_ver} requires peer astro {peer_astro!r}, "
                    f"but installed astro is {astro_ver_str}"
                )
            peer_wrangler = peers.get("wrangler")
            local_wrangler_pkg = pkg_dir.parent.parent / "wrangler" / "package.json"
            eff_wrangler_ver = wrangler_ver
            eff_wrangler_str = wrangler_ver_str
            if local_wrangler_pkg.is_file():
                try:
                    lwp: dict = json.loads(local_wrangler_pkg.read_text(encoding="utf-8"))
                    if lwp.get("version"):
                        eff_wrangler_str = str(lwp["version"])
                        eff_wrangler_ver = semver(eff_wrangler_str)
                except (OSError, json.JSONDecodeError):
                    pass
            if (
                isinstance(peer_wrangler, str)
                and eff_wrangler_ver is not None
                and not version_satisfies_range(eff_wrangler_ver, peer_wrangler)
            ):
                problems.append(
                    f"wrangler-peer: {pkg_name}@{pkg_ver} requires peer wrangler {peer_wrangler!r}, "
                    f"but installed wrangler is {eff_wrangler_str}"
                )

            # Inspect @cloudflare/vite-plugin inside @astrojs/cloudflare's pnpm virtual store dir if present
            cf_vp_pkg = pkg_dir.parent.parent / "@cloudflare" / "vite-plugin" / "package.json"
            if not cf_vp_pkg.is_file():
                cf_vp_pkg = pkg_dir / "node_modules" / "@cloudflare" / "vite-plugin" / "package.json"
            if cf_vp_pkg.is_file():
                try:
                    vp_real = cf_vp_pkg.resolve()
                    vp_data: dict = json.loads(vp_real.read_text(encoding="utf-8"))
                    vp_wrangler = (vp_data.get("peerDependencies") or {}).get("wrangler")
                    vp_wrangler_pkg = vp_real.parent.parent.parent / "wrangler" / "package.json"
                    vp_w_ver = eff_wrangler_ver
                    vp_w_str = eff_wrangler_str
                    if vp_wrangler_pkg.is_file():
                        w_data: dict = json.loads(vp_wrangler_pkg.read_text(encoding="utf-8"))
                        if w_data.get("version"):
                            vp_w_str = str(w_data["version"])
                            vp_w_ver = semver(vp_w_str)
                    if (
                        isinstance(vp_wrangler, str)
                        and vp_w_ver is not None
                        and not version_satisfies_range(vp_w_ver, vp_wrangler)
                    ):
                        problems.append(
                            f"wrangler-peer: @cloudflare/vite-plugin@{vp_data.get('version')} "
                            f"(via {pkg_name}@{pkg_ver}) requires peer wrangler {vp_wrangler!r}, "
                            f"but resolved wrangler is {vp_w_str}"
                        )
                except (OSError, json.JSONDecodeError):
                    pass

            dist_dir = pkg_dir / "dist"
            if not dist_dir.is_dir():
                continue
            for js_path in sorted(dist_dir.rglob("*.js")):
                try:
                    src = js_path.read_text(encoding="utf-8")
                except OSError:
                    continue
                for m in re.finditer(
                    r"import\s*\{([^}]+)\}\s*from\s*['\"](astro(?:/[^'\"]+)?)['\"]",
                    src,
                ):
                    imports_raw, specifier = m.group(1), m.group(2)
                    target_js = _resolve_astro_subpath(astro_dir, astro_pkg, specifier)
                    if target_js is None or not target_js.is_file():
                        continue
                    if target_js not in export_cache:
                        export_cache[target_js] = _collect_esm_exports(target_js)
                    available = export_cache[target_js]
                    for item in imports_raw.split(","):
                        tok = item.strip()
                        if not tok or tok.startswith("type "):
                            continue
                        imported_sym = re.split(r"\s+as\s+", tok)[0].strip()
                        if (
                            re.match(r"^[A-Za-z_$][A-Za-z0-9_$]*$", imported_sym)
                            and imported_sym not in available
                        ):
                            rel_js = js_path.resolve().relative_to(pkg_dir)
                            rel_astro = target_js.relative_to(astro_dir)
                            problems.append(
                                f"astro-export-linkage: {pkg_name}@{pkg_ver} ({rel_js}) imports missing symbol "
                                f"{imported_sym!r} from {specifier!r} (astro@{astro_ver_str} -> {rel_astro})"
                            )
    return problems


_WS_IMPORT_RE = re.compile(
    r"""(?:"""
    r"""\bfrom\s+["']((?:@webomage|@wom)/[a-z0-9-]+)(?:/[^"']*)?["']"""
    r"""|\bimport\s+["']((?:@webomage|@wom)/[a-z0-9-]+)(?:/[^"']*)?["']"""
    r"""|\bimport\s*\(\s*["']((?:@webomage|@wom)/[a-z0-9-]+)(?:/[^"']*)?["']"""
    r""")"""
)
_BLOCK_COMMENT_RE = re.compile(r"/\*[\s\S]*?\*/")
_LINE_COMMENT_RE = re.compile(r"(?m)(?:^|(?<=\s))//[^\n]*")


def check_workspace_package_imports(web_dir: Path) -> list[str]:
    """Verify every internal `@webomage/*` / `@wom/*` workspace import is declared in `package.json` (T611 AC2).

    `astro check` skips `.svelte` files and TypeScript `paths` can mask undeclared workspace packages
    during typecheck, while pnpm's strict `node_modules` isolation makes Vite/Rolldown fail at
    `astro build` time during `deploy-*` if `"@webomage/<pkg>": "workspace:*"` is absent from the
    importing app or package's `package.json`.
    """
    pkgs_root = web_dir / "packages"
    if not pkgs_root.is_dir():
        return []

    internal_names: set[str] = set()
    for pj in sorted(pkgs_root.glob("*/package.json")):
        try:
            pkg_doc: dict[str, Any] = json.loads(pj.read_text(encoding="utf-8"))
            name = pkg_doc.get("name")
        except (OSError, ValueError):
            continue
        if isinstance(name, str) and (name.startswith("@webomage/") or name.startswith("@wom/")):
            internal_names.add(name)
    if not internal_names:
        return []

    problems: list[str] = []
    scan_exts = {".ts", ".tsx", ".js", ".mjs", ".svelte", ".astro"}
    skip_dirs = {"node_modules", "dist", ".astro", ".svelte-kit", "coverage"}

    for group in ("apps", "packages"):
        group_dir = web_dir / group
        if not group_dir.is_dir():
            continue
        for member_dir in sorted(group_dir.iterdir()):
            pj = member_dir / "package.json"
            if not member_dir.is_dir() or not pj.is_file():
                continue
            try:
                manifest: dict[str, Any] = json.loads(pj.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue
            own_name = manifest.get("name")
            declared = (
                set((manifest.get("dependencies") or {}).keys())
                | set((manifest.get("devDependencies") or {}).keys())
                | set((manifest.get("peerDependencies") or {}).keys())
            )
            missing_first_file: dict[str, Path] = {}
            for src_root_name in ("src", "tests"):
                src_root = member_dir / src_root_name
                if not src_root.is_dir():
                    continue
                for fpath in sorted(src_root.rglob("*")):
                    if fpath.suffix not in scan_exts or not fpath.is_file():
                        continue
                    if skip_dirs.intersection(fpath.relative_to(member_dir).parts):
                        continue
                    try:
                        raw = fpath.read_text(encoding="utf-8", errors="ignore")
                    except OSError:
                        continue
                    cleaned = _LINE_COMMENT_RE.sub("", _BLOCK_COMMENT_RE.sub("", raw))
                    for m in _WS_IMPORT_RE.finditer(cleaned):
                        imp_pkg = m.group(1) or m.group(2) or m.group(3)
                        if (
                            imp_pkg
                            and imp_pkg in internal_names
                            and imp_pkg != own_name
                            and imp_pkg not in declared
                            and imp_pkg not in missing_first_file
                        ):
                            missing_first_file[imp_pkg] = fpath

            rel_member = f"{group}/{member_dir.name}"
            for imp_pkg, sample_file in sorted(missing_first_file.items()):
                rel_sample = sample_file.relative_to(member_dir).as_posix()
                problems.append(
                    f'workspace-import-linkage: w0m-web/{rel_member} ({rel_sample}) imports workspace package '
                    f'{imp_pkg!r} without declaring "{imp_pkg}": "workspace:*" in w0m-web/{rel_member}/package.json'
                )
    return problems



def evaluate_policy_detailed(
    policy: dict,
    repos: dict[str, Path],
    pkgs: dict[str, dict],
    *,
    include_npm_lockfiles: bool = True,
    check_bins: bool = False,
) -> tuple[list[str], list[str], dict[str, dict[str, str]], dict[str, object]]:
    """Evaluate `policy` against loaded `pkgs`, `pnpm-lock.yaml`, and tracked `package-lock.json`.

    Returns `(hard, warn, edits, report)` where `report` classifies each repo's floor coverage
    non-vacuously (T298 AC1–AC5):
      - `override_repos`: repos carrying >=1 policy floor in `package.json -> pnpm.overrides`
      - `lockfile_only_repos`: repos carrying 0 policy floors in `pnpm.overrides`, but where >=1
        policy floor was evaluated against `pnpm-lock.yaml` or tracked `package-lock.json`
      - `no_floor_applies`: repos where 0 policy floors landed anywhere (neither in `pnpm.overrides`
        nor in `pnpm-lock.yaml` nor in tracked `package-lock.json`)
      - `no_override_floor_applies`: repos carrying 0 policy floors in `pnpm.overrides`
      - `checked_repos`: repos where >=1 floor was actually evaluated (`override_repos + lockfile_only_repos`)
      - `aligned_repos`: subset of `checked_repos` with 0 hard violations (never includes `no_floor_applies`)
      - `violated_repos`: repos with >=1 hard violation
      - `npm_lockfiles_scanned`: mapping `repo -> list[str]` of tracked `package-lock.json` files
    """
    hard: list[str] = []
    warn: list[str] = []
    edits: dict[str, dict[str, str]] = {}
    violated_repos: set[str] = set()

    override_hits: dict[str, int] = {r: 0 for r in pkgs}
    pnpm_lock_hits: dict[str, int] = {r: 0 for r in pkgs}
    npm_lock_hits: dict[str, int] = {r: 0 for r in pkgs}
    npm_lockfiles_scanned: dict[str, list[str]] = {}
    for r in pkgs:
        rdir = repos[r].parent
        if include_npm_lockfiles:
            npm_files = tracked_npm_lockfiles(rdir)
            npm_lockfiles_scanned[r] = [
                str(p.relative_to(rdir.resolve())) if p.is_relative_to(rdir.resolve()) else str(p)
                for p in npm_files
            ]
        else:
            npm_lockfiles_scanned[r] = []

    # ---- policy integrity: an unreasoned exception silences a check for free (T135 1.3) ----
    hard.extend(check_policy_integrity(policy))

    # ---- toolchain: packageManager identical across every repo ----
    tc = policy.get("toolchain", {})
    want_pm = tc.get("packageManager")
    if want_pm:
        for r, pkg in pkgs.items():
            cur = pkg.get("packageManager")
            if cur != want_pm:
                hard.append(f"toolchain packageManager: {r} has {cur!r}, must be {want_pm!r}")
                edits.setdefault(r, {})["__packageManager__"] = want_pm
                violated_repos.add(r)

    # ---- T56 AC1: enumerate all workspace package.json files across every repo ----
    workspace_packages = discover_workspace_packages(repos, pkgs)
    workspace_edits: dict[str, dict[str, str]] = {}

    # ---- lockstep: identical across the named set + single resolved version in lockfiles (T56 AC5) ----
    for dep, rule in policy.get("lockstep", {}).items():
        if dep.startswith("_") or not isinstance(rule, dict):
            continue
        want, in_repos = rule["version"], rule["repos"]
        lockstep_resolved: dict[str, list[str]] = {}
        for r in in_repos:
            cur, section = declared_version(pkgs.get(r, {}), dep)
            if cur != want:
                where = f" (in {section})" if cur is not None else ""
                hard.append(f"lockstep {dep}: {r} has {cur!r}{where}, must be {want!r}")
                edits.setdefault(r, {})[dep] = want
                violated_repos.add(r)
            if r in repos:
                lvers = sorted(set(".".join(map(str, v)) for v in lockfile_versions(repos[r].parent, dep)))
                if lvers:
                    lockstep_resolved[r] = lvers
                    if len(lvers) > 1:
                        hard.append(
                            f"lockstep-lockfile {dep}: {r} pnpm-lock.yaml resolves multiple versions "
                            f"{lvers} (expected at most 1 resolved version)"
                        )
                        violated_repos.add(r)

        distinct_lockstep = sorted({v for vs in lockstep_resolved.values() for v in vs})
        if len(distinct_lockstep) > 1:
            detail = ", ".join(f"{r}: {'/'.join(vs)}" for r, vs in sorted(lockstep_resolved.items()))
            hard.append(
                f"lockstep-lockfile {dep}: repos resolve multiple versions across pnpm-lock.yaml "
                f"({detail}), expected at most 1 resolved version"
            )
            for r in lockstep_resolved:
                violated_repos.add(r)

    # ---- floors: every repo that has the override or lockfile resolution must satisfy bounds (T140, T298) ----
    for dep, raw_floor in policy.get("floors", {}).items():
        if dep.startswith("_"):
            continue
        for r, pkg in pkgs.items():
            rdir = repos[r].parent
            floor = effective_floor(policy, dep, r, raw_floor)
            fmin, fmax = parse_range(floor)
            cur = overrides_of(pkg).get(dep)
            pnpm_vers = lockfile_versions(rdir, dep)
            if pnpm_vers:
                pnpm_lock_hits[r] += 1
            npm_by_file = npm_lockfile_versions_by_file(rdir, dep) if include_npm_lockfiles else []
            if npm_by_file:
                npm_lock_hits[r] += 1

            if cur is not None:
                override_hits[r] += 1
                cmin, cmax = parse_range(cur)
                if cmin < fmin:
                    hard.append(f"floor {dep}: {r} has {cur!r}, below canonical {floor!r}")
                    edits.setdefault(r, {})[dep] = floor
                    violated_repos.add(r)
                elif fmax is not None:
                    if cmax is None:
                        hard.append(
                            f"floor {dep}: {r} has {cur!r} (missing upper bound), must respect ceiling in {floor!r}"
                        )
                        edits.setdefault(r, {})[dep] = floor
                        violated_repos.add(r)
                    elif cmax > fmax:
                        hard.append(
                            f"floor {dep}: {r} has {cur!r} (upper bound looser than policy ceiling), must respect {floor!r}"
                        )
                        edits.setdefault(r, {})[dep] = floor
                        violated_repos.add(r)
            else:
                # No override yet — inject if the repo resolves a version below floor in pnpm-lock.yaml.
                lmin = min(pnpm_vers) if pnpm_vers else None
                if lmin is not None and lmin < fmin:
                    ver = ".".join(map(str, lmin))
                    hard.append(
                        f"floor {dep}: {r} resolves {ver} (no override), below canonical {floor!r}"
                    )
                    edits.setdefault(r, {})[dep] = floor
                    violated_repos.add(r)

            # T140 AC5: When a floor declares an upper bound, verify no resolved version in
            # pnpm-lock.yaml is >= upper.
            if fmax is not None:
                lmax = max(pnpm_vers) if pnpm_vers else None
                if lmax is not None and lmax >= fmax:
                    ver = ".".join(map(str, lmax))
                    ceil = ".".join(map(str, fmax))
                    hard.append(
                        f"floor {dep}: {r} lockfile resolves {ver} (>= upper ceiling <{ceil} from {floor!r})"
                    )
                    violated_repos.add(r)
                    if cur is None:
                        edits.setdefault(r, {})[dep] = floor

            # T298 AC3/AC4: Inspect tracked npm `package-lock.json` files against floor lower and upper bounds.
            for lock_path, nvers in npm_by_file:
                rel_lock = (
                    str(lock_path.relative_to(rdir.resolve()))
                    if lock_path.is_relative_to(rdir.resolve())
                    else lock_path.name
                )
                nmin = min(nvers)
                if nmin < fmin:
                    ver = ".".join(map(str, nmin))
                    hard.append(
                        f"floor {dep}: {r} npm lockfile ({rel_lock}) resolves {ver}, below canonical {floor!r}"
                    )
                    violated_repos.add(r)
                if fmax is not None:
                    nmax = max(nvers)
                    if nmax >= fmax:
                        ver = ".".join(map(str, nmax))
                        ceil = ".".join(map(str, fmax))
                        hard.append(
                            f"floor {dep}: {r} npm lockfile ({rel_lock}) resolves {ver} (>= upper ceiling <{ceil} from {floor!r})"
                        )
                        violated_repos.add(r)

    # ---- T56 AC1–AC6: workspace-wide declaration + single lockfile version gate for aligned_advisory ----
    for dep, rule in policy.get("aligned_advisory", {}).items():
        if dep.startswith("_") or not isinstance(rule, dict):
            continue
        target = rule["target"]
        resolved_target = rule.get("resolved_target")
        lagging_map = rule.get("lagging") or {}
        non_lagging_repos_for_dep: set[str] = set()

        for ws_key, repo_name, ws_pkg_path, ws_pkg in workspace_packages:
            is_root = ws_pkg_path == repos.get(repo_name)
            cur = {
                **ws_pkg.get("dependencies", {}),
                **ws_pkg.get("devDependencies", {}),
            }.get(dep)
            matched_key, lag_entry = _lookup_lagging_entry(lagging_map, ws_key, repo_name, is_root)

            if matched_key is not None:
                decl_lag = compute_minor_lag(cur or "", target) if cur else 0
                rdir = repos[repo_name].parent if repo_name in repos else ws_pkg_path.parent
                lock_vers = sorted(set(".".join(map(str, v)) for v in lockfile_versions(rdir, dep)))
                if isinstance(lag_entry, dict):
                    rec_decl = lag_entry.get("declared")
                    rec_inst = lag_entry.get("installed")
                    reason = lag_entry.get("reason", "")
                    recheck_by = lag_entry.get("recheck_by", "")
                    if rec_decl and cur != rec_decl:
                        hard.append(
                            f"advisory {dep}: {ws_key} declares {cur!r}, but lagging entry records {rec_decl!r}"
                        )
                        violated_repos.add(repo_name)
                    if rec_inst and lock_vers and lock_vers != [rec_inst]:
                        hard.append(
                            f"advisory {dep}: {ws_key} lockfile resolves {lock_vers}, "
                            f"but lagging entry records {rec_inst!r}"
                        )
                        violated_repos.add(repo_name)
                    inst_str = ", ".join(lock_vers) if lock_vers else (rec_inst or "n/a")
                    inst_lag = (
                        compute_minor_lag(inst_str, resolved_target or target)
                        if inst_str != "n/a"
                        else 0
                    )
                    warn.append(
                        f"advisory {dep}: {ws_key} @ {cur} ({decl_lag} minors behind target {target}; "
                        f"installed {inst_str}, {inst_lag} minors behind) — {reason} (recheck_by: {recheck_by})"
                    )
                else:
                    warn.append(
                        f"advisory {dep}: {ws_key} @ {cur} ({decl_lag} minors behind target {target}) — {lag_entry}"
                    )
            else:
                if cur is not None:
                    non_lagging_repos_for_dep.add(repo_name)
                    if cur != target:
                        hard.append(
                            f"workspace {dep}: {ws_key} declares {cur!r}, must be {target!r} "
                            f"(or record in aligned_advisory.{dep}.lagging)"
                        )
                        workspace_edits.setdefault(str(ws_pkg_path), {})[dep] = target
                        violated_repos.add(repo_name)

        non_lagging_resolved: dict[str, list[str]] = {}
        for r in sorted(non_lagging_repos_for_dep):
            if r not in repos:
                continue
            vers = sorted(set(".".join(map(str, v)) for v in lockfile_versions(repos[r].parent, dep)))
            if not vers:
                continue
            allowed_lag_inst = {
                e.get("installed")
                for k, e in lagging_map.items()
                if isinstance(e, dict)
                and (k == r or k.startswith(f"{r}/"))
                and e.get("installed")
            }
            unexcused_vers = [v for v in vers if v not in allowed_lag_inst or v == resolved_target]
            non_lagging_resolved[r] = unexcused_vers
            if len(unexcused_vers) > 1:
                hard.append(
                    f"lockfile-spread {dep}: {r} pnpm-lock.yaml resolves {len(unexcused_vers)} "
                    f"versions {unexcused_vers} (expected at most 1 resolved version)"
                )
                violated_repos.add(r)
            elif resolved_target and unexcused_vers and unexcused_vers != [resolved_target]:
                hard.append(
                    f"lockfile-spread {dep}: {r} pnpm-lock.yaml resolves {unexcused_vers}, "
                    f"expected {[resolved_target]}"
                )
                violated_repos.add(r)

        distinct_non_lag = sorted({v for vs in non_lagging_resolved.values() for v in vs})
        if len(distinct_non_lag) > 1:
            detail = ", ".join(f"{r}: {'/'.join(vs)}" for r, vs in sorted(non_lagging_resolved.items()))
            hard.append(
                f"lockfile-spread {dep}: non-lagging repos resolve multiple versions across "
                f"pnpm-lock.yaml ({detail}), expected single resolved version"
            )
            for r in non_lagging_resolved:
                violated_repos.add(r)

    # ---- T113 AC5: cross-repo runtime alignment (CF compatibility_date, nodejs_compat, .nvmrc, engines) ----
    for rt_err in check_runtime_alignment(policy, repos, pkgs):
        hard.append(rt_err)
        for r in pkgs:
            if f": {r} " in rt_err or f" {r}/" in rt_err:
                violated_repos.add(r)

    # ---- T566 AC2 & T595: host node engines + workspace .bin CLIs + @astrojs/* ESM export & peer linkage ----
    if check_bins:
        for bin_err in check_workspace_bins(repos, pkgs):
            hard.append(bin_err)
            for r in pkgs:
                if f": {r} " in bin_err:
                    violated_repos.add(r)
    for eng_err in check_node_engines(repos):
        hard.append(eng_err)
        for r in pkgs:
            if f": {r} " in eng_err:
                violated_repos.add(r)
    if "w0m-web" in repos:
        web_root = repos["w0m-web"].parent
        astro_errs = check_astro_adapter_exports(web_root)
        ws_imp_errs = check_workspace_package_imports(web_root)
        if astro_errs or ws_imp_errs:
            hard.extend(astro_errs)
            hard.extend(ws_imp_errs)
            violated_repos.add("w0m-web")

    override_repos = [r for r in pkgs if override_hits[r] > 0]
    no_override_floor_applies = [r for r in pkgs if override_hits[r] == 0]
    lockfile_only_repos = [
        r for r in pkgs if override_hits[r] == 0 and (pnpm_lock_hits[r] > 0 or npm_lock_hits[r] > 0)
    ]
    no_floor_applies = [
        r for r in pkgs if override_hits[r] == 0 and pnpm_lock_hits[r] == 0 and npm_lock_hits[r] == 0
    ]
    checked_repos = [r for r in pkgs if r not in no_floor_applies]
    aligned_repos = [r for r in checked_repos if r not in violated_repos]

    report: dict[str, object] = {
        "override_repos": override_repos,
        "lockfile_only_repos": lockfile_only_repos,
        "no_floor_applies": no_floor_applies,
        "no_override_floor_applies": no_override_floor_applies,
        "checked_repos": checked_repos,
        "aligned_repos": aligned_repos,
        "violated_repos": sorted(violated_repos),
        "override_hits": override_hits,
        "pnpm_lock_hits": pnpm_lock_hits,
        "npm_lock_hits": npm_lock_hits,
        "npm_lockfiles_scanned": npm_lockfiles_scanned,
        "workspace_packages_checked": [ws_key for ws_key, _, _, _ in workspace_packages],
        "workspace_package_count": len(workspace_packages),
        "repo_count": len(pkgs),
        "workspace_edits": workspace_edits,
    }
    return hard, warn, edits, report


def evaluate_policy(
    policy: dict,
    repos: dict[str, Path],
    pkgs: dict[str, dict],
) -> tuple[list[str], list[str], dict[str, dict[str, str]]]:
    """Evaluate `policy` against loaded `pkgs` and lockfiles, returning `(hard, warn, edits)`."""
    hard, warn, edits, _ = evaluate_policy_detailed(policy, repos, pkgs, include_npm_lockfiles=True)
    return hard, warn, edits


def format_summary(
    policy: dict,
    pkgs: dict[str, dict],
    warn: list[str],
    report: dict[str, object],
) -> str:
    """Format the non-vacuous summary line naming workspace package.json count and checked repos (T56 AC1, T298 AC1/AC2)."""
    floor_count = len([k for k in policy.get("floors", {}) if not k.startswith("_")])
    lockstep_count = len([k for k in policy.get("lockstep", {}) if not k.startswith("_")])
    want_pm = policy.get("toolchain", {}).get("packageManager")
    pm_label = want_pm.split("@")[-1] if want_pm else "—"

    override_repos: list[str] = list(report.get("override_repos", []))  # type: ignore[call-overload]
    lockfile_only_repos: list[str] = list(report.get("lockfile_only_repos", []))  # type: ignore[call-overload]
    no_floor_applies: list[str] = list(report.get("no_floor_applies", []))  # type: ignore[call-overload]
    npm_scanned: dict[str, list[str]] = dict(report.get("npm_lockfiles_scanned", {}))  # type: ignore[call-overload]
    total_npm_locks = sum(len(v) for v in npm_scanned.values())
    ws_pkg_raw = report.get("workspace_package_count")
    ws_pkg_count = ws_pkg_raw if isinstance(ws_pkg_raw, int) else len(pkgs)
    repo_raw = report.get("repo_count")
    repo_count = repo_raw if isinstance(repo_raw, int) else len(pkgs)

    notes: list[str] = []
    if lockfile_only_repos:
        names = ", ".join(lockfile_only_repos)
        verb = "carries" if len(lockfile_only_repos) == 1 else "carry"
        notes.append(f"{names} {verb} no overrides — no override floor applies (lockfile-checked only)")
    if no_floor_applies:
        names = ", ".join(no_floor_applies)
        verb = "carries" if len(no_floor_applies) == 1 else "carry"
        notes.append(f"{names} {verb} no overrides — no floor applies")
    if total_npm_locks:
        notes.append(f"{total_npm_locks} tracked npm lockfile(s) checked")

    notes_suffix = f"; {'; '.join(notes)}" if notes else ""
    warn_suffix = f"; {len(warn)} advisory warning(s)" if warn else ""
    return (
        f"  ✓ deps aligned ({ws_pkg_count} package.json across {repo_count} repos): "
        f"{floor_count} floors across {len(override_repos)} override repo(s)"
        f"{notes_suffix} "
        f"({lockstep_count} lockstep, pnpm {pm_label})"
        f"{warn_suffix}"
    )


def main() -> int:
    apply = "--apply" in sys.argv
    install = "--install" in sys.argv
    policy, _ = load(POLICY)
    repos = {name: ROOT / rel for name, rel in policy["repos"].items()}
    pkgs = {name: load(path)[0] for name, path in repos.items() if path.exists()}
    missing = [n for n in policy["repos"] if n not in pkgs]
    if missing:
        print(f"  ! policy lists repos with no package.json: {missing}")

    if install:
        return install_workspace_deps(repos, pkgs)

    hard, warn, edits, report = evaluate_policy_detailed(
        policy, repos, pkgs, include_npm_lockfiles=True, check_bins=True
    )
    ws_edits: dict[str, dict[str, str]] = cast(
        dict[str, dict[str, str]], report.get("workspace_edits") or {}
    )

    # ---- report / apply ----
    if apply and (edits or ws_edits):
        touched_repos: list[str] = list(edits.keys())
        for r, changes in edits.items():
            path = repos[r]
            pkg, _ = load(path)
            for dep, v in changes.items():
                if dep == "__packageManager__":
                    pkg["packageManager"] = v
                else:
                    pkg.setdefault("pnpm", {}).setdefault("overrides", {})[dep] = v
            path.write_text(json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            for dep, v in changes.items():
                label = "packageManager" if dep == "__packageManager__" else dep
                print(f"  ~ {r}: {label} -> {v}")
        for raw_path, changes in ws_edits.items():
            ws_path = Path(raw_path)
            pkg, _ = load(ws_path)
            for dep, v in changes.items():
                if dep in pkg.get("devDependencies", {}):
                    pkg["devDependencies"][dep] = v
                else:
                    pkg.setdefault("dependencies", {})[dep] = v
            ws_path.write_text(json.dumps(pkg, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            rel_label = ws_path.relative_to(ROOT).as_posix() if ws_path.is_relative_to(ROOT) else str(ws_path)
            for dep, v in changes.items():
                print(f"  ~ {rel_label}: {dep} -> {v}")
        total_changes = sum(len(c) for c in edits.values()) + sum(len(c) for c in ws_edits.values())
        print(
            f"\n  applied {total_changes} change(s). "
            f"Now run `pnpm install` in: {', '.join(touched_repos or ['affected repos'])}"
        )
        return 0

    for w in warn:
        print(f" [WARN] {w}")
    if hard:
        print(f"\n  ✗ {len(hard)} dependency-policy violation(s):")
        for h in hard:
            print(f"    - {h}")
        print("\n  fix: python3 scripts/deps_sync.py --apply  (then pnpm install per repo)")
        return 1
    print(format_summary(policy, pkgs, warn, report))
    return 0


if __name__ == "__main__":
    sys.exit(main())
