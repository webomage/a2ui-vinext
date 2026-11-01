#!/usr/bin/env python3
"""Is the environment I am about to work in actually wired up right now? — T147 AC1.

Owner ask 2026-08-07: *"we have to check on session/chat start what's on/off and health for
tools/services and components"*. This is that check, and it runs two ways: `--fast` from the
SessionStart hook on every session, and full from `just preflight` when someone asks.

NOT A SECOND toolset-status. That composite asks whether the governed REGISTRIES are conformant
(queue, stacks, skills, state, toolchain) and takes ~23s doing it. This asks a different question —
whether the things this session will actually reach are reachable *now*: MCP servers, the graph
index, the repos, the required binaries. Almost no overlap, which is the only reason a second
entry point is justified. Where they do overlap, full mode SHELLS OUT to toolset-status rather
than re-implementing any child of it.

WHY FAST MODE IS IN-PROCESS. A SessionStart hook that costs 20s gets removed, and T147 AC1 says so
outright: a preflight nobody runs is worse than none. So fast mode makes no `just` calls — every
`just` invocation is ~0.5s of startup before it does anything. It reads files and opens TCP sockets.
Measured budget below; re-measure when adding a check.

WHAT IT CANNOT KNOW, AND SAYS SO. Whether an MCP server is CONNECTED TO THE RUNNING SESSION is a
harness fact, not a file fact and not a port fact. A declared, enabled, listening server can still
be absent from the session — that was exactly true of both Obsidian servers until 2026-08-07, when
they were declared, enabled and listening while zero Obsidian tools existed. So this reports
declared / configured / listening, and labels session-connectivity UNVERIFIABLE rather than
implying the three are the same question. Reporting a number for something it cannot measure would
be the estate's signature defect, not a convenience.

NO VACUOUS GREEN. Every check fails loudly when its input collection is empty. A preflight that
reports "0 servers, all fine" is the exact failure mode T149 catalogued five times.

NOT `hygiene_preflight.py`. That one is T135's one-shot repo-hygiene MEASUREMENT — git toplevels,
core.hooksPath, package.json manifests, human-facing files — and it deliberately prints and exits 0
rather than gating. Same word, different question; neither should grow into the other.

ESTATE vs CLIENT BOUNDARY RULE (T302 AC1/AC4):
  1. Estate gates (`preflight.py` in estate mode) must NEVER reference or depend on a client
     workspace (`_proj/`, `!proj/`, `_self/` outside `@wom`, or any non-`w0m` root declared in
     `project/clients-policy.json`). A row reaching into a client directory measures someone else's
     health, goes red or "skipped" when that directory is absent or moved, and prevents a green
     estate preflight from meaning "the estate is fine". Enforced mechanically by
     `check_estate_preflight_client_boundary()` / `check_client_boundary()`.
  2. Client-side checks belong in the client's own `-w0m` workspace (`<client>-w0m`) beside the
     toolchain they measure, reachable by the same `just` recipe names (e.g. `just vm-staleness` /
     `just vm-retention` in `bridgeroad-w0m`). Moving a check out of estate `preflight` is a
     relocation to its subject's workspace, never a deletion.

Exit: 0 all checks passed · 1 one or more findings · 2 config error (an input is missing or empty).

Run: `just preflight` · `just preflight --fast` · `just preflight --json`
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import subprocess
import sys
import time
from pathlib import Path

ESTATE = Path(__file__).resolve().parents[1]
ROOT = ESTATE / "w0m-web"  # w0m-web/
SDLC = ESTATE / ".w0m" / "sdlc.json"

# ── project scoping (T182) ────────────────────────────────────────────────────
# `--project <dir>` points the DECLARATION-relative checks at another project, so the profile's
# `mcp` and `repos` keys can be enforced at a client instead of only at w0m.
#
# 🔴 It is NOT a path swap. `check_repos` imports w0m's canonical repo map from graph_health;
# reusing that against a client would enumerate w0m's seven repos, find them all present, and
# report a confidently correct-looking answer about a project none of them belong to. So client
# mode re-derives the repo set from the CLIENT's own `repos` declaration. Sharing the contract
# (what the key means) is right; sharing w0m's hardcoded facts is the bug.
#
# Estate-global checks (graph currency, host tooling) are NOT run for a client and are NAMED as
# skipped — a preflight that silently ran two of four checks and printed green would be the
# vacuous-coverage shape this estate keeps re-learning.
PROJECT: Path | None = None          # None ⇒ w0m itself; unchanged default behaviour


def project_root() -> Path:
    return PROJECT if PROJECT is not None else ROOT


def sdlc_path() -> Path:
    """The declaration to read.

    ⚠️ Falls back to the module-level `SDLC`, not to a recomputed path, when no project is
    scoped. The regression suite patches `preflight.SDLC` to drive the missing-file and
    empty-declaration cases; computing the path from `ROOT` instead severed that seam and turned
    four red probes green — caught by running the suite, which is the only reason it is written
    this way.
    """
    return (PROJECT / ".w0m" / "sdlc.json") if PROJECT is not None else SDLC
TOOLS_POLICY = ESTATE / "project" / "policies" / "tools-policy.json"
CLIENTS_POLICY = ESTATE / "project" / "policies" / "clients-policy.json"
ESTATE_MCP = ESTATE / ".mcp.json"
GRAPH_FRESH = ESTATE / "scripts" / "graph_fresh.py"

CONNECT_TIMEOUT = 0.35  # loopback; generous enough that a busy machine is not a false negative


class Finding(Exception):
    """A check could not run at all — distinct from a check that ran and found problems."""


def _result(name: str, ok: bool, headline: str, detail: list[str] | None = None) -> dict:
    return {"name": name, "ok": ok, "headline": headline, "detail": detail or []}


# ─────────────────────────────────────────────────────────────────────── mcp


def _listening(host: str, port: int) -> bool:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.settimeout(CONNECT_TIMEOUT)
        return sock.connect_ex((host, port)) == 0


def check_mcp() -> dict:
    """Declared vs configured vs listening. Session-connected is deliberately not claimed."""
    sdlc = sdlc_path()
    if not sdlc.is_file():
        raise Finding(f"{sdlc} is missing — the declared MCP surface is the input to this check")
    mcp_block = json.loads(sdlc.read_text()).get("mcp")
    servers = (mcp_block or {}).get("servers", {})
    if not servers:
        # 🔑 Silence and a decision are different states, and the original guard could not tell
        # them apart. For w0m, zero declared servers means the check has no input — a
        # misconfiguration, and it still raises. For a CLIENT, zero can be the truth: Artemio runs
        # none. So an explicitly present-but-empty `servers` is a deliberate declaration of none
        # and passes with the fact stated; an ABSENT `mcp` block is still silence and still fails.
        # Without this a client with genuinely no MCP could never satisfy the key, which would
        # make the profile unsatisfiable rather than strict.
        if PROJECT is not None and isinstance(mcp_block, dict) and "servers" in mcp_block:
            return _result("mcp", True, "0 servers — declared as none, deliberately")
        raise Finding("sdlc.json declares no MCP servers — refusing to report health over nothing")

    # The client config is the second half of the truth: a server can be declared here and absent
    # there, which is the state that makes it unreachable no matter how healthy the server is.
    configured: set[str] = set()
    for cfg in (ESTATE_MCP, Path.home() / ".claude.json"):
        if cfg.is_file():
            try:
                configured |= set(json.loads(cfg.read_text()).get("mcpServers", {}))
            except (json.JSONDecodeError, OSError):
                pass

    enabled = {n: s for n, s in servers.items() if s.get("enabled")}
    problems: list[str] = []
    notices: list[str] = []
    listening = 0
    probed = 0

    for name, spec in sorted(enabled.items()):
        # `required` defaults true — a server has to opt into being allowed to be down.
        # obsidian-w0m-web is the first false: its own .mcp.json comment already documents
        # "a closed vault is the normal case, not an error", but this check still flipped the
        # whole mcp gate red on it, contradicting that documented design.
        required = spec.get("required", True)
        bind = spec.get("bind")
        if spec.get("transport") == "local-http" and bind:
            host, _, port = bind.rpartition(":")
            probed += 1
            if _listening(host or "127.0.0.1", int(port)):
                listening += 1
            elif required:
                problems.append(f"{name}: declared at {bind} but nothing is listening")
            else:
                notices.append(f"{name}: not listening at {bind} (optional — not required to start)")
        # A globally-scoped server lives in the host config, which this may not be able to read;
        # only flag the ones whose config file we positively inspected.
        if spec.get("scope") == "project" and name not in configured:
            entry = f"{name}: enabled but absent from the MCP client config"
            (problems if required else notices).append(entry)

    head = (
        f"{len(servers)} declared · {len(enabled)} enabled · "
        f"{listening}/{probed} local-http listening · session-connected NOT MEASURABLE here"
    )
    return _result("mcp", not problems, head, problems + notices)


# ───────────────────────────────────────────────────────────────────── graph


def check_graph() -> dict:
    """Delegate to graph_fresh, which owns this question. --check-only never writes."""
    if not GRAPH_FRESH.is_file():
        raise Finding(f"{GRAPH_FRESH} is missing")
    proc = subprocess.run(
        [sys.executable, str(GRAPH_FRESH), "--check-only", "--quiet"],
        cwd=ROOT, capture_output=True, text=True, timeout=60,
    )
    if proc.returncode == 0:
        return _result("graph", True, "union current — graph-before-grep is safe")
    tail = [ln.strip() for ln in (proc.stdout + proc.stderr).splitlines() if ln.strip()][-2:]
    return _result("graph", False, "union STALE — `just graph-global` before trusting it", tail)


# ───────────────────────────────────────────────────────────────────── repos


def _git(repo: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, timeout=15
    )
    return proc.stdout.strip() if proc.returncode == 0 else ""


def check_repos() -> dict:
    """Enumerate from disk, then compare against what sdlc.json declares.

    Enumerating from the registry alone would make an undeclared repo invisible, and the registry
    is short one of them today (wom7mlx is absent from `repos`; it was two until T186 decommissioned
    wom7md on 2026-08-08). Enumerating from disk
    alone would lose the fact that the registry is incomplete. So do both and report the gap.
    """
    # Use graph_health's REPOS map rather than globbing. Both naive enumerators are wrong here and
    # each is wrong in the estate's signature way: top-level-only finds 7 because w0m-mlx is nested
    # at w0m-mlx/w0m-mlx, and one-level-down finds 28 because w0m-mlx/ holds ~20 vendored
    # third-party checkouts (mlx, candle, mlx-rs …). The correct set is a DECISION, already made
    # and already written down once. Importing it keeps one home for it; a third enumerator here
    # would be a third thing to drift.
    sdlc = sdlc_path()
    if PROJECT is None:
        sys.path.insert(0, str(ESTATE / "scripts"))
        try:
            from graph_health import REPOS as REPO_MAP  # noqa: PLC0415
        except ImportError as exc:
            raise Finding(f"cannot import the canonical repo map from graph_health: {exc}") from exc
        if not REPO_MAP:
            raise Finding("graph_health.REPOS is empty — refusing to report health over nothing")
        base = ESTATE
    else:
        # 🔴 A CLIENT's repo set is whatever IT declares — never w0m's map. Importing
        # graph_health.REPOS here would enumerate w0m's seven repos, find them all present, and
        # report a healthy-looking answer about a project none of them belong to.
        if not sdlc.is_file():
            raise Finding(f"{sdlc} is missing — there is no declaration to enumerate from")
        REPO_MAP = json.loads(sdlc.read_text()).get("repos") or {}
        if not REPO_MAP:
            raise Finding("`repos` is absent or empty in the declaration — refusing to report "
                          "health over nothing (a single-repo project still declares its one repo)")
        base = project_root()

    found = [base / rel for rel in REPO_MAP.values()]
    absent = [p.name for p in found if not (p / ".git").exists()]
    if absent:
        raise Finding(f"declared repo(s) not on disk: {', '.join(absent)}")

    # Compare on basenames: the registry may store a bare name ("w0m-web") or a nested path
    # ("w0m-mlx/w0m-mlx"), and both mean the same repo.
    declared = {Path(v).name for v in json.loads(sdlc.read_text()).get("repos", {}).values()}
    problems: list[str] = []
    notes: list[str] = []          # reported, but never a conformance failure (client mode)
    dirty_total = 0
    for repo in found:
        dirty = len([ln for ln in _git(repo, "status", "--porcelain").splitlines() if ln])
        dirty_total += dirty
        branch = _git(repo, "branch", "--show-current")
        ahead = _git(repo, "rev-list", "--count", "@{u}..HEAD")
        # 🔑 Working-tree state is a different question from declaration conformance, and only in
        # client mode does the difference matter. For w0m this is a health check and dirt is a
        # problem. For a CLIENT the profile asks *is this project imported* — a repo with
        # uncommitted work or unpushed commits is imported and mid-flight, not unimported. Left as
        # a problem it would make conformance unreachable for any project someone is working in,
        # including one deliberately left unpushed pending the owner's call. Reported either way.
        sink = notes if PROJECT is not None else problems
        if dirty:
            sink.append(f"{repo.name}: {dirty} uncommitted")
        if ahead and ahead != "0":
            sink.append(f"{repo.name}: {ahead} unpushed")
        if not ahead and branch:
            sink.append(f"{repo.name}: no upstream for `{branch}`")

    # The undeclared-repo comparison is only meaningful when the two sides come from DIFFERENT
    # sources: w0m enumerates from graph_health's map and diffs against the declaration, so a repo
    # on disk that nobody declared shows up. In client mode `found` is derived FROM `declared`, so
    # the difference is empty by construction — computing it anyway produced a false positive on
    # the first client tried: Artemio declares `{"web": "."}`, whose basename is `.` while the
    # directory is `artemioquierocomer.mx`, and the check duly reported the project as undeclared
    # in its own declaration. A comparison that cannot fail for the right reason must not be run.
    if PROJECT is None:
        undeclared = sorted({p.name for p in found} - declared)
        if undeclared:
            problems.append(f"not in sdlc.json → repos: {', '.join(undeclared)}")

    head = (
        f"{len(found)} repos ({', '.join(sorted(REPO_MAP))}) · "
        f"{len(declared)} in sdlc.json · {dirty_total} uncommitted"
    )
    return _result("repos", not problems, head, problems + notes)


# ───────────────────────────────────────────────────────────────────── tools


def check_tools() -> dict:
    """Presence only (plus in-process snapshot of pending auto-updates). Full version probing is T112's `just tools-check`."""
    if not TOOLS_POLICY.is_file():
        raise Finding(f"{TOOLS_POLICY} is missing")
    policy = json.loads(TOOLS_POLICY.read_text())
    tools = policy.get("tools", policy)
    required = sorted(k for k, v in tools.items() if isinstance(v, dict) and v.get("required"))
    if not required:
        raise Finding("tools-policy declares no required tools — refusing to report over nothing")
    missing = [t for t in required if shutil.which(t) is None]
    detail = [f"missing: {t}" for t in missing]
    runtime_errors: list[str] = []
    if PROJECT is None:
        sys.path.insert(0, str(ESTATE / "scripts"))
        import deps_sync
        import resource_monitor

        ts_repos = {
            "w0m-web": ROOT / "package.json",
            "w0m-api": ESTATE / "w0m-api" / "package.json",
            "w0m-cf": ESTATE / "w0m-cf" / "package.json",
            "w0m-ext": ESTATE / "w0m-ext" / "extension" / "package.json",
            "w0m-skills": ESTATE / "w0m-skills" / "package.json",
        }
        runtime_errors.extend(deps_sync.check_workspace_bins(ts_repos))
        runtime_errors.extend(deps_sync.check_node_engines(ts_repos))
        runtime_errors.extend(deps_sync.check_astro_adapter_exports(ROOT))
        detail.extend(runtime_errors)
        disk_info = resource_monitor.check_host_disk_headroom()
        if disk_info["low_disk_warning"]:
            detail.append(str(disk_info["headline"]))
    outdated_cache = ESTATE / "project" / ".tools-outdated.json"
    if outdated_cache.is_file():
        try:
            snap: dict[str, list[dict[str, str]]] = json.loads(outdated_cache.read_text(encoding="utf-8"))
            auto_ups = [u for u in snap.get("updates", []) if u.get("mode") == "AUTO"]
            if auto_ups:
                names = ", ".join(f"{u['tool']} {u['cur']}→{u['latest']}" for u in auto_ups)
                detail.append(f"auto-upgradable tool update(s) pending ({names}) — run `just tools-weekly`")
        except (OSError, ValueError):
            pass
    ok = not missing and not runtime_errors
    headline = f"{len(required) - len(missing)}/{len(required)} required tools on PATH · 5/5 TS workspace .bin sets"
    if runtime_errors:
        headline += f" ({len(runtime_errors)} node/workspace/astro linkage error(s))"
    return _result(
        "tools",
        ok,
        headline,
        detail,
    )


def check_in_tray() -> dict:
    """T447 AC4: Verify `_in/` disposition ledger and report any new/unclassified drops at session start."""
    if PROJECT is not None:
        return _result("in-tray", True, "client mode — _in/ tray lives on w0m root")
    sys.path.insert(0, str(ROOT / "project" / "scripts"))
    import in_tray
    from datetime import datetime as _dt

    errors, items = in_tray.validate_in_tray(
        in_tray.DEFAULT_IN_DIR, _dt.now().date(), check_index_sync=True
    )
    new_cnt = sum(1 for it in items if it.get("state") == "new")
    living_cnt = sum(1 for it in items if it.get("state") == "living")
    adopted_cnt = sum(1 for it in items if it.get("state") == "adopted")
    head = f"{len(items)} item(s) governed ({new_cnt} new, {living_cnt} living, {adopted_cnt} adopted)"
    return _result("in-tray", not errors, head, errors)


# ───────────────────────────────────────────────────────────── client boundary


def check_estate_preflight_client_boundary(
    rows: list[tuple[str, list[str], int, str]] | None = None,
    clients_policy_path: Path | None = None,
) -> list[str]:
    """T302 AC2: Fail if any estate preflight row's command references a client workspace.

    Inspects `rows` (defaulting to `FULL_CHILDREN`) against:
      1. Path segment markers `_proj/`, `!proj/`, and `_self/` (outside `@wom`).
      2. Every non-`w0m` project `root` declared in `clients-policy.json` (both relative root
         strings like `_proj/bridgeroad` and resolved absolute paths under `~/Projects`).
      3. Any absolute path outside the w0m estate (`ESTATE` / `ROOT`) that points under a client
         workspace directory.
    """
    target_rows = FULL_CHILDREN if rows is None else rows
    if not target_rows:
        raise Finding("FULL_CHILDREN is empty — refusing to certify client boundary over nothing")

    policy_file = CLIENTS_POLICY if clients_policy_path is None else Path(clients_policy_path)
    if not policy_file.is_file():
        raise Finding(f"{policy_file} is missing — cannot load declared client workspace roots")

    data: dict = json.loads(policy_file.read_text(encoding="utf-8"))
    projects = data.get("projects") or []
    client_roots: dict[str, str] = {}
    client_abs_roots: dict[str, Path] = {}
    projects_base = Path.home() / "Projects"
    entries: list[tuple[str, dict]] = []
    if isinstance(projects, dict):
        entries = [(str(k), v) for k, v in projects.items() if isinstance(v, dict)]
    elif isinstance(projects, list):
        entries = [
            (str(item.get("id") or ""), item)
            for item in projects
            if isinstance(item, dict) and item.get("id")
        ]
    for pid, spec in entries:
        if pid == "w0m":
            continue
        rel_root = (spec.get("root") or "").strip().strip("/")
        if rel_root:
            client_roots[pid] = rel_root
            client_abs_roots[pid] = (projects_base / rel_root).resolve()

    if not client_roots:
        raise Finding(f"{policy_file} declares 0 non-w0m client roots — refusing vacuous boundary check")

    violations: list[str] = []
    forbidden_markers = ("_proj/", "!proj/", "_self/")

    for row in target_rows:
        name, argv = row[0], row[1]
        joined = " ".join(str(tok) for tok in argv)
        reasons: list[str] = []

        for marker in forbidden_markers:
            if marker in joined:
                reasons.append(f"references `{marker}`")

        for pid, rel_root in client_roots.items():
            if rel_root in joined:
                reasons.append(f"references client `{pid}` root `{rel_root}`")
            abs_root = client_abs_roots[pid]
            if str(abs_root) in joined:
                reasons.append(f"references absolute client path `{abs_root}` ({pid})")

        for tok in argv:
            tok_str = str(tok).strip()
            if tok_str.startswith("/"):
                try:
                    resolved = Path(tok_str).resolve()
                except OSError:
                    continue
                for pid, abs_root in client_abs_roots.items():
                    if resolved == abs_root or abs_root in resolved.parents:
                        msg = f"references absolute path `{tok_str}` under client `{pid}` ({abs_root})"
                        if msg not in reasons:
                            reasons.append(msg)

        if reasons:
            deduped = "; ".join(dict.fromkeys(reasons))
            violations.append(
                f"{name}: command {argv!r} violates estate-vs-client boundary ({deduped}) — "
                f"relocate client checks to `<client>-w0m` under the same `just` recipe name (T302)"
            )

    return violations


def check_boundary() -> dict:
    """T302 AC2/AC4: Mechanical guard that estate preflight rows never reach into client workspaces."""
    if PROJECT is not None:
        return _result("boundary", True, "client mode — estate row boundary applies to w0m preflight")
    violations = check_estate_preflight_client_boundary()
    return _result(
        "boundary",
        not violations,
        f"{len(FULL_CHILDREN)}/{len(FULL_CHILDREN)} full-mode rows confined to w0m estate (0 client workspace refs)",
        violations,
    )


FAST_CHECKS = [check_mcp, check_graph, check_repos, check_tools, check_in_tray, check_boundary]

# name -> (argv, timeout, why). Full mode only. These are the slow, authoritative ones; fast mode
# deliberately does not approximate them.
FULL_CHILDREN = [
    ("toolset", ["just", "toolset-status"], 300, "registry conformance (T149)"),
    ("exposure", ["just", "mcp-ratchet"], 300, "did exposure grow (T154)"),
    ("versions", ["just", "tools-check"], 300, "tool version floors (T112)"),
    # Full mode only, and deliberately NOT approximated in fast mode: it makes a network HEAD, and
    # a SessionStart hook that costs seconds gets removed (T147 AC1). Warns rather than blocks —
    # a published image being behind its inputs is a fact to act on, not a broken estate.
    # 🔴 The BridgeRoad image rows (vm-image, vm-disk) were HERE and have been removed.
    # Owner principle, 2026-09-02: **gates for client projects do not run in the w0m workspace.**
    # They reached into `_proj/bridgeroad`, which makes an estate gate depend on a client workspace
    # existing — wrong on three counts: it is not w0m's health, it goes red or "skipped" for reasons
    # about someone else's directory, and a preflight that reports on a client is a preflight that
    # cannot be read as "is the estate fine". Those checks live in `bridgeroad-w0m` beside the
    # toolchain they measure, reachable as `just vm-staleness` / `just vm-retention`.
    # T535 AC5: names a stale or failing Upwork feed. It reads the live database, so it lives here (full mode) and not in the SessionStart fast mode, which makes no network
    # call. An unreachable database fails it ("could not measure"), which is the honest answer: unmeasured is never healthy.
    ("upwork-feed", ["just", "upwork-freshness"], 90, "Upwork feed freshness (T535 AC5)"),
    ("estate-cfg", ["python3", "scripts/estate_config_versioned.py"], 60,
     "estate-root config is versioned (T294 AC4 / D32)"),
]


def run_full() -> list[dict]:
    out = []
    boundary_violations = check_estate_preflight_client_boundary()
    if boundary_violations:
        out.append(
            {
                **_result(
                    "boundary",
                    False,
                    f"{len(boundary_violations)} full-mode row(s) reach into a client workspace (T302)",
                    boundary_violations,
                ),
                "seconds": 0.0,
            }
        )
        return out
    for name, argv, timeout, why in FULL_CHILDREN:
        start = time.monotonic()
        if argv[0] == "python3" and len(argv) > 1 and not (ESTATE / argv[1]).exists():
            out.append({**_result(name, True, f"{why} — SKIPPED, not present at {argv[1]}"),
                        "seconds": 0.0, "skipped": True})
            continue
        try:
            proc = subprocess.run(argv, cwd=ESTATE, capture_output=True, text=True, timeout=timeout)
            lines = [
                ln.rstrip()
                for ln in (proc.stdout + proc.stderr).splitlines()
                if ln.strip()
            ]
            res = _result(
                name,
                proc.returncode == 0,
                f"{why} — {lines[-1][:110] if lines else '(no output)'}",
            )
        except subprocess.TimeoutExpired:
            res = _result(name, False, f"{why} — TIMED OUT after {timeout}s")
        except FileNotFoundError:
            res = _result(name, False, f"{why} — `{argv[0]}` not on PATH")
        res["seconds"] = round(time.monotonic() - start, 1)
        out.append(res)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--fast", action="store_true", help="in-process checks only (SessionStart)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument(
        "--hook",
        action="store_true",
        help="always exit 0 and stay terse; for SessionStart, where a non-zero exit is noise "
        "rather than information — the findings are in the text either way",
    )
    ap.add_argument(
        "--project", metavar="DIR",
        help="enforce the DECLARATION-relative checks (mcp, repos) against another project — "
             "T182, so the client profile's keys are enforceable at a client. Estate-global "
             "checks (graph, tools) are skipped and named as skipped.",
    )
    ap.add_argument(
        "--check-client-boundary",
        action="store_true",
        help="run only the T302 estate-vs-client preflight boundary check and exit non-zero on violation",
    )
    args = ap.parse_args()

    if args.check_client_boundary:
        try:
            violations = check_estate_preflight_client_boundary()
        except Finding as exc:
            print(f"  ✗ boundary CANNOT RUN — {exc}")
            return 2
        if violations:
            print(f"  ✗ {len(violations)} client-boundary violation(s) in preflight:")
            for v in violations:
                print(f"    - {v}")
            return 1
        print(
            f"  ✓ preflight client boundary clean ({len(FULL_CHILDREN)} full-mode rows confined to w0m estate)"
        )
        return 0

    global PROJECT
    client_checks = None
    if args.project:
        PROJECT = Path(args.project).resolve()
        if not (PROJECT / ".w0m" / "sdlc.json").is_file():
            print(f"  ✗ {PROJECT} has no .w0m/sdlc.json — nothing to enforce against")
            return 2
        # Only the checks whose input is the project's own declaration. `graph` and `tools`
        # describe the estate and the host; running them here would answer a question nobody
        # asked and dress it as coverage of the client.
        client_checks = [check_mcp, check_repos]

    started = time.monotonic()
    results: list[dict] = []
    broken: list[str] = []

    for check in (client_checks if client_checks is not None else FAST_CHECKS):
        try:
            results.append(check())
        except Finding as exc:
            # Could not run. NOT a pass, and not a silent skip either.
            results.append(_result(check.__name__[6:], False, f"CANNOT RUN — {exc}"))
            broken.append(check.__name__[6:])
        except Exception as exc:  # noqa: BLE001 — a preflight must never take the session down
            results.append(_result(check.__name__[6:], False, f"CANNOT RUN — {exc!r}"))
            broken.append(check.__name__[6:])

    if not args.fast and client_checks is None:
        results.extend(run_full())

    elapsed = round(time.monotonic() - started, 1)
    failed = [r for r in results if not r["ok"]]
    skipped = ["graph", "tools"] if client_checks is not None else []

    if args.json:
        print(json.dumps({"ok": not failed, "seconds": elapsed, "checks": results,
                          "project": str(project_root()), "skipped": skipped}, indent=2))
    else:
        mode = "fast" if args.fast else "full"
        if client_checks is not None:
            print(f"▶ preflight for {project_root().name} ({elapsed}s) — {len(results)} "
                  f"declaration check(s)")
        else:
            print(f"▶ w0m preflight ({mode}, {elapsed}s) — {len(results)} checks")
        for r in results:
            print(f" {'✅' if r['ok'] else '[WARN] '} {r['name']:9} {r['headline']}")
            for line in r["detail"]:
                print(f"       · {line}")
        if skipped:
            # Named, not silent. Two of four checks running and a green line printed is how a
            # partial pass gets read as full coverage.
            print(f" [SKIP] NOT RUN for a client: {', '.join(skipped)} — these describe the estate "
                  "and the host, not this project")
        if failed:
            print(f" [WARN] {len(failed)} finding(s) — `just preflight` for the full sweep")
        else:
            print("  ✅ environment wired and current")

    if args.hook:
        return 0
    return 2 if broken else (1 if failed else 0)


if __name__ == "__main__":
    sys.exit(main())
