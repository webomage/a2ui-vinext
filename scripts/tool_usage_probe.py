#!/usr/bin/env python3
"""T164 AC1 / T620 AC1 — which host, agent, custom-fork, and ephemeral CLIs does the estate invoke?

`project/policies/tools-policy.json` (configured in `.w0m/sdlc.json -> toolchain.policy`) must be
grounded in real usage and explicit cross-workstation classification rather than implicit assumptions.
This probe scans command-position, subprocess, agent-provider, `package.json`, `.mcp.json`, hook,
and ephemeral `pnpm dlx` / `npx` / `uvx` surfaces across all estate repositories.

Method, and why it is not a grep
--------------------------------
A naive `grep -c '<tool>'` over the estate reported **tree=73** and **uv=67**. Both were prose:
"worktree" matches `tree`, "uvx" matches `uv`, and Python/TS locals named `tree`, `fd`, `rg`, `sg`
matched too.

So a tool counts only where it is invoked or declared as an executable command:
1. In shell/justfile/Makefile/hook files and `package.json` `"scripts"` values: command position —
   start of line, or after a pipe, `&&`, `||`, `;`, backtick, `$(`, `xargs`, `sudo`, `then`/`do`/`else`,
   or `sh -c '...'`, on non-comment lines, and not followed by `:` or `=`.
2. In YAML files (`.pre-commit-config.yaml`, CI workflows): inside `entry:`, `run:` blocks, or shell
   pipe/chain/subshell expressions (so Backstage/metadata list items do not false-positive).
3. In `.mcp.json` manifests: `mcpServers[*].command` basename (`python3`, `node`, `uvx`, etc.).
4. In Python/JS/TS scripts (excluding test fixtures and this probe): argv0 of `subprocess.*`,
   `execFileSync`/`execSync`/`spawn*`, `shutil.which`, local `sh([...])`/`run([...])` helpers, or
   `AgentProviderSpec` `binaries=(...)` declarations (`scripts/agent_provider.py`).
5. Ephemeral runners (`scan_ephemeral_runners`): `pnpm dlx <pkg>`, `npx <pkg>`, and `uvx <pkg>`
   across manifests, hooks, recipes, workflows, and scripts, enforcing `ephemeral_policy` (`forbid_npx`
   and `must_pin`, e.g. `pagefind@1.5.2` for `x86-64-v2` ABI safety per `T617`).

Symlinked files are deduplicated by resolved path so canonical invocations are counted once.

Every candidate in `TOOLS` must be either:
- governed in `tools-policy.json -> tools` (with `min`, `known_good`, `required`, `source`, `auto`, `note`), or
- recorded in `tools-policy.json -> out_of_scope` with a non-empty written reason and 0 measured uses.
And conversely, every key in `tools-policy.json -> tools` and `out_of_scope` must appear in `TOOLS`.
"""
from __future__ import annotations

import argparse
from collections.abc import Iterable, Iterator
import json
from pathlib import Path
import re
import subprocess
import sys
from typing import Any

# scripts/ -> the estate root
ROOT = Path(__file__).resolve().parents[1]
SDLC_JSON = ROOT / ".w0m" / "sdlc.json"

REPOS = [
    ".",
    "w0m-web",
    "w0m-api",
    "w0m-cf",
    "w0m-ext",
    "w0m-skills",
    "w0m-sec",
    "w0m-mlx/w0m-mlx",
]

# Full T164 / T595 / T622 / T620 candidate CLI surface (90 host, agent, fork & workstation CLIs).
TOOLS = [
    "agy",
    "ansible",
    "ast-grep",
    "aws",
    "az",
    "bat",
    "btop",
    "caddy",
    "cargo",
    "cargo-clippy",
    "claude",
    "cloudflared",
    "cmake",
    "code-review-graph",
    "codegraph",
    "codex",
    "colima",
    "ctop",
    "curl",
    "deno",
    "direnv",
    "docker",
    "duf",
    "fd",
    "fzf",
    "gauge",
    "gcloud",
    "gemini",
    "gh",
    "git",
    "gitleaks",
    "go",
    "google-chrome",
    "goose",
    "gpg",
    "graphify",
    "headroom",
    "helm",
    "htmlq",
    "infisical",
    "java",
    "jq",
    "just",
    "kubectl",
    "lazydocker",
    "minikube",
    "mkcert",
    "mlr",
    "moksha",
    "mypy",
    "ncdu",
    "node",
    "omlx",
    "opencode",
    "openspec",
    "orca",
    "osv-scanner",
    "pdftotext",
    "pip3",
    "pnpm",
    "podman",
    "pre-commit",
    "psql",
    "python3",
    "redis-cli",
    "rg",
    "ruff",
    "rustc",
    "rustfmt",
    "rustup",
    "sd",
    "semgrep",
    "serena",
    "sg",
    "shellcheck",
    "sqlite3",
    "sshpass",
    "supabase",
    "tart",
    "terraform",
    "tree",
    "uv",
    "virtual-fido",
    "w0m-obsidian-uri",
    "warp-cli",
    "wasm-pack",
    "wget",
    "worker-build",
    "yq",
    "zeroclaw",
]

SHELL_SUFFIXES = {".sh", ".bash", ".zsh", ".just"}
YAML_SUFFIXES = {".yml", ".yaml"}
CODE_SUFFIXES = {".py", ".mjs", ".js", ".ts"}
JSON_NAMES = {"package.json", ".mcp.json"}
SUFFIXES = SHELL_SUFFIXES | YAML_SUFFIXES | CODE_SUFFIXES
NAMES = {"justfile", "Makefile", "pre-commit", "pre-push", "commit-msg", "post-commit"} | JSON_NAMES

SHELL_PREFIX = (
    r"(?:^|\|\||&&|[|;`]|\$\("
    r"|\b(?:xargs|sudo|then|do|else)\s+"
    r"|\b(?:ba)?sh\s+-c\s+[\"\x27]"
    r"|\bentry:\s*[\"\x27]?)\s*"
)

YAML_CMD_PREFIX = (
    r"(?:\|\||&&|[|;`]|\$\("
    r"|\b(?:xargs|sudo|then|do|else)\s+"
    r"|\b(?:ba)?sh\s+-c\s+[\"\x27]"
    r"|\b(?:entry|run):\s*[\"\x27|>+-]*\s*)\s*"
)

SHELL_DLX_RE = re.compile(r"\bpnpm\s+dlx\s+(?:--package[=\s]+\S+\s+|--silent\s+|-q\s+)*(?P<spec>@[A-Za-z0-9._-]+/[A-Za-z0-9._@-]+|[A-Za-z0-9._@-]+)")
SHELL_NPX_RE = re.compile(
    r"(?:^|\|\||&&|[|;`]|\$\(|\bentry:\s*[\"\x27]?|\b(?:ba)?sh\s+-c\s+[\"\x27])\s*npx\s+(?:--yes\s+|-y\s+|--no-install\s+)*(?P<spec>@[A-Za-z0-9._-]+/[A-Za-z0-9._@-]+|[A-Za-z0-9._@-]+)",
    re.M,
)
SHELL_UVX_RE = re.compile(
    r"\buvx\s+(?:--quiet\s+|-q\s+)*(?:--from[=\s]+(?P<from_spec>\S+)\s+)?(?P<spec>[A-Za-z0-9._+@:/-]+)"
)

CODE_DLX_RE = re.compile(
    r"[\"\x27]pnpm[\"\x27]\s*,\s*(?:\[\s*)?[\"\x27]dlx[\"\x27]\s*,\s*[\"\x27](?P<spec>[^\"\x27]+)[\"\x27]"
)
CODE_NPX_RE = re.compile(
    r"(?:subprocess\.(?:run|Popen|call|check_output|check_call)|execFileSync|execSync|spawnSync|spawn)\s*\(\s*\[?\s*[\"\x27]npx[\"\x27](?:\s*,\s*\[?\s*[\"\x27](?:--yes|-y)[\"\x27])?\s*(?:,\s*[\"\x27](?P<arg>[^\"\x27]+)[\"\x27]|\s+(?P<inline>[A-Za-z0-9._@/-]+))?"
)
CODE_UVX_RE = re.compile(
    r"[\"\x27]uvx[\"\x27]\s*,\s*(?:\[\s*)?(?:[\"\x27](?:--quiet|-q)[\"\x27]\s*,\s*)*(?:[\"\x27]--from[\"\x27]\s*,\s*[\"\x27](?P<from_spec>[^\"\x27]+)[\"\x27]\s*,\s*)?[\"\x27](?P<spec>[^\"\x27]+)[\"\x27]"
)


def resolve_policy_path(root: Path | None = None) -> Path:
    """Resolve `tools-policy.json` from `.w0m/sdlc.json -> toolchain.policy` (AC5)."""
    base = root or ROOT
    sdlc_file = base / ".w0m" / "sdlc.json"
    if sdlc_file.is_file():
        try:
            cfg: dict[str, Any] = json.loads(sdlc_file.read_text(encoding="utf-8"))
            tc = cfg.get("toolchain")
            if isinstance(tc, dict):
                rel = tc.get("policy")
                if isinstance(rel, str) and rel.strip():
                    return base / rel.strip()
        except (OSError, ValueError):
            pass
    return base / "project" / "policies" / "tools-policy.json"


def candidate_files(root: Path | None = None) -> Iterator[Path]:
    """Yield deduplicated git-tracked script/justfile/manifest/hook files across the estate."""
    base = root or ROOT
    seen: set[Path] = set()
    for repo in REPOS:
        d = base if repo == "." else (base / repo)
        if not (d / ".git").exists():
            continue
        out = subprocess.run(
            ["git", "-C", str(d), "ls-files"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.split("\n")
        for rel in out:
            if not rel:
                continue
            p = d / rel
            if p.name in NAMES or p.suffix in SUFFIXES:
                try:
                    real = p.resolve()
                except OSError:
                    continue
                if real not in seen:
                    seen.add(real)
                    yield p
        hooks_out = subprocess.run(
            ["git", "-C", str(d), "rev-parse", "--git-path", "hooks"],
            capture_output=True,
            text=True,
            check=False,
        ).stdout.strip()
        hooks = (d / hooks_out) if hooks_out and not Path(hooks_out).is_absolute() else (Path(hooks_out) if hooks_out else d / ".git" / "hooks")
        if hooks.is_dir():
            for p in hooks.iterdir():
                if p.is_file() and not p.name.endswith(".sample"):
                    try:
                        real = p.resolve()
                    except OSError:
                        continue
                    if real not in seen:
                        seen.add(real)
                        yield p


def _is_test_or_self(path: Path) -> bool:
    s = path.as_posix()
    return (
        path.name == "tool_usage_probe.py"
        or "/tests/" in s
        or s.endswith("_test.py")
        or s.endswith(".test.ts")
        or s.endswith(".spec.ts")
    )


def _extract_yaml_runnable_lines(text: str) -> str:
    """Extract runnable lines from `.pre-commit-config.yaml` and GitHub workflow `run:` blocks."""
    out: list[str] = []
    in_run_block = False
    run_indent = 0
    for raw in text.splitlines():
        stripped = raw.lstrip()
        if not stripped or stripped.startswith("#"):
            continue
        indent = len(raw) - len(stripped)
        if in_run_block:
            if indent > run_indent:
                out.append(stripped)
                continue
            in_run_block = False
        m_block = re.match(r"^(?:-\s+)?run:\s*[|>][-+]?\s*$", stripped)
        if m_block:
            in_run_block = True
            run_indent = indent
            continue
        if re.match(r"^(?:-\s+)?(?:entry|run):\s*", stripped):
            out.append(re.sub(r"^-\s+", "", stripped))
    return "\n".join(out)


def scan_usage(
    tools: list[str] | None = None,
    files: Iterable[Path] | None = None,
    root: Path | None = None,
) -> tuple[int, dict[str, list[tuple[int, str]]]]:
    """Scan `files` once and return `(scanned_file_count, {tool: [(count, rel_path), ...]})`."""
    base = root or ROOT
    target_tools = list(tools) if tools is not None else list(TOOLS)
    target_set = set(target_tools)
    alt = "|".join(re.escape(t) for t in sorted(target_tools, key=len, reverse=True))
    shell_pat = re.compile(
        SHELL_PREFIX + rf"(?P<tool>{alt})(?=\s|$|[\"\x27])(?!\s*[:=])",
        re.M,
    )
    yaml_pat = re.compile(
        YAML_CMD_PREFIX + rf"(?P<tool>{alt})(?=\s|$|[\"\x27])(?!\s*[:=])",
        re.M,
    )
    code_pat = re.compile(
        r"(?:subprocess\.(?:run|Popen|call|check_output|check_call)|execFileSync|execSync|spawnSync|spawn|shutil\.which|\bsh|\brun)\s*\(\s*\[?\s*[\"\x27](?P<tool>"
        + alt
        + r")[\"\x27]"
    )
    provider_bin_pat = re.compile(r"\bbinaries\s*=\s*\((?P<bins>[^)]*)\)")
    quoted_str_pat = re.compile(r"[\"\x27]([^\"\x27]+)[\"\x27]")

    hits: dict[str, list[tuple[int, str]]] = {t: [] for t in target_tools}
    scanned = 0

    iterable = files if files is not None else candidate_files(base)
    for p in iterable:
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        scanned += 1
        if _is_test_or_self(p):
            continue
        try:
            rel_str = str(p.relative_to(base))
        except ValueError:
            rel_str = str(p)

        if p.name == "package.json":
            try:
                pkg_data: dict[str, Any] = json.loads(text)
            except ValueError:
                continue
            scripts = pkg_data.get("scripts")
            if not isinstance(scripts, dict):
                continue
            counts_pkg: dict[str, int] = {}
            for cmd_val in scripts.values():
                if not isinstance(cmd_val, str):
                    continue
                for m in shell_pat.finditer(cmd_val):
                    t = m.group("tool")
                    counts_pkg[t] = counts_pkg.get(t, 0) + 1
            for t, n in counts_pkg.items():
                hits[t].append((n, rel_str))
        elif p.name == ".mcp.json":
            try:
                mcp_data: dict[str, Any] = json.loads(text)
            except ValueError:
                continue
            servers = mcp_data.get("mcpServers")
            if not isinstance(servers, dict):
                continue
            counts_mcp: dict[str, int] = {}
            for srv in servers.values():
                if not isinstance(srv, dict):
                    continue
                cmd_str = srv.get("command")
                if isinstance(cmd_str, str) and cmd_str.strip():
                    bname = Path(cmd_str.strip()).name
                    if bname in target_set:
                        counts_mcp[bname] = counts_mcp.get(bname, 0) + 1
            for t, n in counts_mcp.items():
                hits[t].append((n, rel_str))
        elif p.suffix in YAML_SUFFIXES:
            runnable_yaml = _extract_yaml_runnable_lines(text)
            if not runnable_yaml:
                continue
            counts_yaml: dict[str, int] = {}
            for m in shell_pat.finditer(runnable_yaml):
                t = m.group("tool")
                counts_yaml[t] = counts_yaml.get(t, 0) + 1
            for m in yaml_pat.finditer(runnable_yaml):
                t = m.group("tool")
                if t not in counts_yaml:
                    counts_yaml[t] = counts_yaml.get(t, 0) + 1
            for t, n in counts_yaml.items():
                hits[t].append((n, rel_str))
        elif p.name in NAMES or p.suffix in SHELL_SUFFIXES:
            is_recipe = p.name in ("justfile", "Makefile") or p.suffix == ".just"
            clean_shell = "\n".join(
                (re.sub(r"^[-@]+\s*", "", ln.lstrip()) if is_recipe else ln.lstrip())
                for ln in text.splitlines()
                if ln.strip() and not ln.lstrip().startswith(("#", "//"))
            )
            counts: dict[str, int] = {}
            for m in shell_pat.finditer(clean_shell):
                t = m.group("tool")
                counts[t] = counts.get(t, 0) + 1
            for t, n in counts.items():
                hits[t].append((n, rel_str))
        elif p.suffix in CODE_SUFFIXES:
            counts_code: dict[str, int] = {}
            for m in code_pat.finditer(text):
                t = m.group("tool")
                counts_code[t] = counts_code.get(t, 0) + 1
            for m_bins in provider_bin_pat.finditer(text):
                for candidate_bin in quoted_str_pat.findall(m_bins.group("bins")):
                    if candidate_bin in target_set:
                        counts_code[candidate_bin] = counts_code.get(candidate_bin, 0) + 1
            for t, n in counts_code.items():
                hits[t].append((n, rel_str))

    return scanned, hits


def _parse_pkg_and_pin(runner: str, raw_spec: str, from_spec: str | None = None) -> tuple[str, str | None, bool]:
    """Normalize `(package_name, version_or_ref, is_pinned)` for `pnpm dlx`, `npx`, and `uvx`."""
    spec = (raw_spec or "").strip()
    if runner == "uvx" and from_spec:
        fspec = from_spec.strip()
        if "@" in fspec and (fspec.startswith("git+") or "://" in fspec):
            base, ref = fspec.rsplit("@", 1)
            pkg = Path(base).stem or spec
            return pkg, ref, bool(ref)
        if "==" in fspec:
            pkg, ver = fspec.split("==", 1)
            return pkg.split("[", 1)[0], ver, bool(ver)
        return spec, None, False

    if spec.startswith("@"):
        # Scoped npm package: @scope/name or @scope/name@1.2.3
        slash_idx = spec.find("/")
        if slash_idx != -1 and "@" in spec[slash_idx + 1 :]:
            pkg, ver = spec.rsplit("@", 1)
            return pkg, ver, bool(ver)
        return spec, None, False

    if "@" in spec:
        pkg, ver = spec.rsplit("@", 1)
        return pkg, ver, bool(ver)
    if "==" in spec:
        pkg, ver = spec.split("==", 1)
        return pkg.split("[", 1)[0], ver, bool(ver)
    return spec, None, False


def scan_ephemeral_runners(
    files: Iterable[Path] | None = None,
    root: Path | None = None,
) -> list[dict[str, Any]]:
    """Scan estate files for ephemeral `pnpm dlx`, `npx`, and `uvx` invocations (`T620` AC1)."""
    base = root or ROOT
    records: list[dict[str, Any]] = []
    iterable = files if files is not None else candidate_files(base)

    def _add(runner: str, spec: str, rel_str: str, from_spec: str | None = None) -> None:
        if not spec or spec.startswith(("-", "$", "{", "{{")):
            return
        pkg, pin_ver, pinned = _parse_pkg_and_pin(runner, spec, from_spec)
        records.append(
            {
                "runner": runner,
                "package": pkg,
                "spec": f"{from_spec} -> {spec}" if from_spec else spec,
                "version": pin_ver,
                "pinned": pinned,
                "file": rel_str,
            }
        )

    for p in iterable:
        if _is_test_or_self(p):
            continue
        try:
            text = p.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        try:
            rel_str = str(p.relative_to(base))
        except ValueError:
            rel_str = str(p)

        # Skip skill markdown/resource prose directories when scanning shell snippets inside skills
        if p.name == "package.json":
            try:
                pkg_raw: dict[str, Any] = json.loads(text)
            except ValueError:
                continue
            scripts = pkg_raw.get("scripts", {})
            if not isinstance(scripts, dict):
                continue
            for cmd_val in scripts.values():
                if not isinstance(cmd_val, str):
                    continue
                for m in SHELL_DLX_RE.finditer(cmd_val):
                    _add("pnpm dlx", m.group("spec"), rel_str)
                for m in SHELL_NPX_RE.finditer(cmd_val):
                    _add("npx", m.group("spec"), rel_str)
                for m in SHELL_UVX_RE.finditer(cmd_val):
                    _add("uvx", m.group("spec"), rel_str, m.group("from_spec"))
        elif p.name == ".mcp.json":
            try:
                mcp_raw: dict[str, Any] = json.loads(text)
            except ValueError:
                continue
            servers = mcp_raw.get("mcpServers", {})
            if not isinstance(servers, dict):
                continue
            for srv in servers.values():
                if not isinstance(srv, dict):
                    continue
                cmd_str = str(srv.get("command") or "").strip()
                raw_args = [str(a) for a in (srv.get("args") or []) if isinstance(a, (str, int, float))]
                bname = Path(cmd_str).name if cmd_str else ""
                joined = " ".join([bname, *raw_args]).strip()
                for m in SHELL_DLX_RE.finditer(joined):
                    _add("pnpm dlx", m.group("spec"), rel_str)
                for m in SHELL_NPX_RE.finditer(joined):
                    _add("npx", m.group("spec"), rel_str)
                for m in SHELL_UVX_RE.finditer(joined):
                    _add("uvx", m.group("spec"), rel_str, m.group("from_spec"))
        elif p.suffix in YAML_SUFFIXES:
            runnable = _extract_yaml_runnable_lines(text)
            for m in SHELL_DLX_RE.finditer(runnable):
                _add("pnpm dlx", m.group("spec"), rel_str)
            for m in SHELL_NPX_RE.finditer(runnable):
                _add("npx", m.group("spec"), rel_str)
            for m in SHELL_UVX_RE.finditer(runnable):
                _add("uvx", m.group("spec"), rel_str, m.group("from_spec"))
        elif p.name in NAMES or p.suffix in SHELL_SUFFIXES:
            for raw_ln in text.splitlines():
                st = raw_ln.strip()
                if not st or st.startswith(("#", "//", "echo ", "@echo ")):
                    continue
                for m in SHELL_DLX_RE.finditer(st):
                    _add("pnpm dlx", m.group("spec"), rel_str)
                for m in SHELL_NPX_RE.finditer(st):
                    _add("npx", m.group("spec"), rel_str)
                for m in SHELL_UVX_RE.finditer(st):
                    _add("uvx", m.group("spec"), rel_str, m.group("from_spec"))
        elif p.suffix in CODE_SUFFIXES:
            for m in CODE_DLX_RE.finditer(text):
                _add("pnpm dlx", m.group("spec"), rel_str)
            for m in CODE_NPX_RE.finditer(text):
                spec = m.group("arg") or m.group("inline") or "npx"
                _add("npx", spec, rel_str)
            for m in CODE_UVX_RE.finditer(text):
                _add("uvx", m.group("spec"), rel_str, m.group("from_spec"))

    return records


def verify_ephemeral_runners(
    records: list[dict[str, Any]],
    policy: dict[str, Any],
) -> list[str]:
    """Enforce `ephemeral_policy` (`forbid_npx` + `must_pin` ABI/ref pins, `T620` AC1/AC2)."""
    problems: list[str] = []
    eph = policy.get("ephemeral_policy")
    if not isinstance(eph, dict):
        return problems
    forbid_npx = bool(eph.get("forbid_npx", True))
    must_pin = eph.get("must_pin") if isinstance(eph.get("must_pin"), dict) else {}

    for rec in records:
        runner = rec["runner"]
        pkg = rec["package"]
        ver = rec["version"]
        pinned = rec["pinned"]
        f = rec["file"]
        if forbid_npx and runner == "npx":
            problems.append(
                f"{f}: runnable `npx {rec['spec']}` violates zero-npx policy (use `pnpm exec` or `pnpm dlx`)"
            )
        if pkg in must_pin:
            expected = str(must_pin[pkg])
            if not pinned:
                problems.append(
                    f"{f}: `{runner} {rec['spec']}` is unpinned; `ephemeral_policy.must_pin` requires `{pkg}@{expected}`"
                )
            elif ver != expected:
                problems.append(
                    f"{f}: `{runner} {rec['spec']}` pins `{ver}`, expected `{expected}` from `ephemeral_policy.must_pin`"
                )
    return problems


def verify_policy_coverage(
    policy: dict[str, Any],
    hits: dict[str, list[tuple[int, str]]],
    candidates: list[str] | None = None,
) -> list[str]:
    """Verify bidirectional candidate <-> `tools-policy.json` coverage (`T164` AC1 / `T620` AC1)."""
    problems: list[str] = []
    governed = policy.get("tools")
    out_of_scope = policy.get("out_of_scope")
    if not isinstance(governed, dict) or not governed:
        return ["tools-policy.json: `tools` map is missing or empty"]
    if not isinstance(out_of_scope, dict) or not out_of_scope:
        return ["tools-policy.json: `out_of_scope` map is missing or empty"]

    overlap = sorted(set(governed) & set(out_of_scope))
    if overlap:
        problems.append(
            f"tools-policy.json: tool(s) declared in BOTH `tools` and `out_of_scope`: {', '.join(overlap)}"
        )

    for tool, reason in sorted(out_of_scope.items()):
        if tool.startswith("_"):
            continue
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"{tool}: `out_of_scope` entry must have a non-empty written reason")

    target_candidates = candidates if candidates is not None else list(TOOLS)
    for t in target_candidates:
        total = sum(n for n, _ in hits.get(t, []))
        in_gov = t in governed
        in_oos = t in out_of_scope
        if not in_gov and not in_oos:
            problems.append(
                f"{t}: unaccounted candidate CLI (uses={total}) — must be governed in `tools` or documented in `out_of_scope`"
            )
        elif in_oos and total > 0:
            problems.append(
                f"{t}: recorded in `out_of_scope` but has {total} real command/subprocess invocation(s) — govern it in `tools`"
            )

    if candidates is None:
        candidate_set = set(target_candidates)
        policy_keys = {k for k in set(governed) | set(out_of_scope) if not k.startswith("_")}
        missing_from_probe = sorted(policy_keys - candidate_set)
        if missing_from_probe:
            problems.append(
                "tool_usage_probe.py: policy key(s) absent from `TOOLS` probe surface: "
                + ", ".join(missing_from_probe)
            )
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="T164/T620 — Host, agent & ephemeral CLI usage probe")
    ap.add_argument("--check", action="store_true", help="verify 100%% candidate + ephemeral runner compliance")
    ap.add_argument("--json", action="store_true", help="emit JSON report")
    ap.add_argument("--policy", type=Path, default=None, help="override tools-policy.json path")
    args = ap.parse_args(argv)

    files = list(candidate_files(ROOT))
    scanned, hits = scan_usage(files=files, root=ROOT)
    if not scanned:
        print("EMPTY CORPUS — refusing to report zeros as evidence", file=sys.stderr)
        return 2

    ephemeral_records = scan_ephemeral_runners(files=files, root=ROOT)

    policy_path = args.policy or resolve_policy_path(ROOT)
    try:
        policy: dict[str, Any] = json.loads(policy_path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"CANNOT READ POLICY {policy_path}: {exc}", file=sys.stderr)
        return 2

    rel_pol_str = str(policy_path.relative_to(ROOT) if policy_path.is_relative_to(ROOT) else policy_path)
    for _tname, tspec in (policy.get("tools") or {}).items():
        if not isinstance(tspec, dict):
            continue
        for cmd_field in ("version_cmd", "smoke"):
            val = tspec.get(cmd_field)
            if not isinstance(val, str):
                continue
            for m_uvx in SHELL_UVX_RE.finditer(val):
                pkg, pin_ver, pinned = _parse_pkg_and_pin("uvx", m_uvx.group("spec"), m_uvx.group("from_spec"))
                ephemeral_records.append(
                    {
                        "runner": "uvx",
                        "package": pkg,
                        "spec": f"{m_uvx.group('from_spec')} -> {m_uvx.group('spec')}" if m_uvx.group("from_spec") else m_uvx.group("spec"),
                        "version": pin_ver,
                        "pinned": pinned,
                        "file": rel_pol_str,
                    }
                )

    problems = verify_policy_coverage(policy, hits) + verify_ephemeral_runners(ephemeral_records, policy)
    governed = policy.get("tools", {})
    out_of_scope = policy.get("out_of_scope", {})

    if args.json:
        summary = {
            "scanned_files": scanned,
            "policy_path": str(policy_path),
            "candidates": {
                t: {
                    "uses": sum(n for n, _ in hits[t]),
                    "files": len(hits[t]),
                    "disposition": (
                        "governed"
                        if t in governed
                        else ("out_of_scope" if t in out_of_scope else "unaccounted")
                    ),
                }
                for t in TOOLS
            },
            "ephemeral_runners": ephemeral_records,
            "problems": problems,
        }
        print(json.dumps(summary, indent=2))
        return 1 if problems else 0

    rel_pol = policy_path.relative_to(ROOT) if policy_path.is_relative_to(ROOT) else policy_path
    print(f"scanned {scanned} files across {len(REPOS)} repos (policy: {rel_pol})\n")
    for t in TOOLS:
        total = sum(n for n, _ in hits[t])
        where = ", ".join(f"{f}×{n}" for n, f in sorted(hits[t], reverse=True)[:4]) or "—"
        if t in governed:
            req = "req" if governed[t].get("required") else "opt"
            disp = f"governed[{req}]"
        elif t in out_of_scope:
            disp = "out-of-scope"
        else:
            disp = "UNACCOUNTED"
        print(f"{t:18} {disp:14} uses={total:<4} files={len(hits[t]):<3} {where}")

    if ephemeral_records:
        by_pkg: dict[tuple[str, str, bool, str], list[str]] = {}
        for rec in ephemeral_records:
            key = (rec["runner"], rec["package"], bool(rec["pinned"]), str(rec["version"] or ""))
            by_pkg.setdefault(key, []).append(rec["file"])
        print(f"\nephemeral runners ({len(ephemeral_records)} invocation(s) across {len(by_pkg)} package spec(s)):")
        for (runner, pkg, pinned, ver), locs in sorted(by_pkg.items()):
            pin_label = f"pinned@{ver}" if pinned else "unpinned"
            uniq_locs = ", ".join(sorted(set(locs))[:4])
            print(f"  {runner:10} {pkg:18} [{pin_label:18}] ×{len(locs):<2} {uniq_locs}")

    if problems:
        print(f"\n✗ {len(problems)} coverage/ephemeral problem(s):", file=sys.stderr)
        for prob in problems:
            print(f"  - {prob}", file=sys.stderr)
        if args.check:
            return 1
    else:
        n_gov = sum(1 for t in TOOLS if t in governed)
        n_oos = sum(1 for t in TOOLS if t in out_of_scope)
        print(
            f"\n✓ all {len(TOOLS)} candidate CLIs accounted for ({n_gov} governed, {n_oos} out_of_scope) "
            f"and {len(ephemeral_records)} ephemeral invocation(s) policy-compliant"
        )
    return 1 if (args.check and problems) else 0


if __name__ == "__main__":
    sys.exit(main())
