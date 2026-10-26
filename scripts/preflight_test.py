#!/usr/bin/env python3
"""Prove the preflight's checks go RED — T147 AC6.

AC6 asks for two distinct things, and only the first is the one people usually write:

  1. each check FAILS when it should (a real fault produces a finding);
  2. each check fails rather than PASSES when its input set is EMPTY.

The second is the one this estate keeps shipping without. `0 managed skill(s) match the
lockfile ✓` came out of T127; T149 catalogued the same shape five more times. An empty
corpus is not a clean corpus, and a check that cannot tell the difference is decorative.

So every case below drives the real function with a doctored input and asserts on the
outcome. Nothing here asserts that a check passes on good input — `just preflight` does
that every session, and a test that only proves the happy path is how a check that can
never fire gets shipped.

Run: `just preflight-test`
"""

from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import preflight  # noqa: E402

PASS, FAIL = "✅", "❌"
results: list[tuple[bool, str]] = []


def case(name: str, fn) -> None:
    try:
        fn()
        results.append((True, name))
    except AssertionError as exc:
        results.append((False, f"{name} — {exc}"))
    except Exception as exc:  # noqa: BLE001
        results.append((False, f"{name} — unexpected {exc!r}"))


def expect_cannot_run(fn, why: str) -> None:
    """The check must refuse, not return a passing result."""
    try:
        got = fn()
    except preflight.Finding:
        return
    raise AssertionError(f"{why}: expected a Finding, got ok={got['ok']} {got['headline']!r}")


def write(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload))


# ── empty-input guards: the vacuous-green cases ────────────────────────────────────────

def t_mcp_empty():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sdlc.json"
        write(p, {"mcp": {"servers": {}}})
        preflight.SDLC = p
        expect_cannot_run(preflight.check_mcp, "zero declared MCP servers")


def t_mcp_missing_file():
    preflight.SDLC = Path("/nonexistent/sdlc.json")
    expect_cannot_run(preflight.check_mcp, "missing sdlc.json")


def t_tools_none_required():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "tools-policy.json"
        write(p, {"tools": {"just": {"required": False}}})
        preflight.TOOLS_POLICY = p
        expect_cannot_run(preflight.check_tools, "zero required tools")


def t_tools_missing_file():
    preflight.TOOLS_POLICY = Path("/nonexistent/tools-policy.json")
    expect_cannot_run(preflight.check_tools, "missing tools-policy.json")


def t_graph_missing_helper():
    preflight.GRAPH_FRESH = Path("/nonexistent/graph_fresh.py")
    expect_cannot_run(preflight.check_graph, "missing graph_fresh.py")


def t_repos_empty_map():
    """The canonical repo map going empty must refuse, not report a healthy zero."""
    sys.path.insert(0, str(preflight.ROOT / "scripts"))
    import graph_health

    saved = dict(graph_health.REPOS)
    graph_health.REPOS.clear()
    try:
        expect_cannot_run(preflight.check_repos, "empty canonical repo map")
    finally:
        graph_health.REPOS.update(saved)


def t_repos_declared_but_absent():
    """A repo in the map that is not on disk is a Finding, not a silent skip."""
    sys.path.insert(0, str(preflight.ROOT / "scripts"))
    import graph_health

    saved = dict(graph_health.REPOS)
    graph_health.REPOS["ghost"] = "definitely-not-a-repo"
    try:
        expect_cannot_run(preflight.check_repos, "declared repo missing from disk")
    finally:
        graph_health.REPOS.clear()
        graph_health.REPOS.update(saved)


# ── real-fault cases: the check must go RED, not merely not-crash ──────────────────────

def t_mcp_declared_not_listening():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sdlc.json"
        # Port 1 on loopback: privileged, and nothing this estate runs binds it.
        write(p, {"mcp": {"servers": {"ghost": {
            "enabled": True, "transport": "local-http", "bind": "127.0.0.1:1", "scope": "host"}}}})
        preflight.SDLC = p
        got = preflight.check_mcp()
        assert not got["ok"], "a declared local-http server with nothing listening must be RED"
        assert any("nothing is listening" in x for x in got["detail"]), got["detail"]


def t_mcp_optional_not_listening_is_green():
    """`required: false` downgrades a dead local-http server to a notice, not a RED finding."""
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sdlc.json"
        write(p, {"mcp": {"servers": {"ghost": {
            "enabled": True, "required": False, "transport": "local-http",
            "bind": "127.0.0.1:1", "scope": "host"}}}})
        preflight.SDLC = p
        got = preflight.check_mcp()
        assert got["ok"], f"an optional server not listening must stay GREEN, got {got}"
        assert any("optional" in x for x in got["detail"]), got["detail"]


def t_mcp_enabled_but_unconfigured():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "sdlc.json"
        write(p, {"mcp": {"servers": {"ghost": {
            "enabled": True, "transport": "stdio", "scope": "project"}}}})
        preflight.SDLC = p
        got = preflight.check_mcp()
        assert not got["ok"], "a project-scope server absent from the client config must be RED"
        assert any("absent from the MCP client config" in x for x in got["detail"]), got["detail"]


def t_tools_missing_binary():
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "tools-policy.json"
        write(p, {"tools": {"definitely-not-a-real-binary-xyz": {"required": True}}})
        preflight.TOOLS_POLICY = p
        got = preflight.check_tools()
        assert not got["ok"], "a missing required binary must be RED"


def t_hook_mode_always_exits_zero():
    """A SessionStart hook that exits non-zero is noise; the findings are in the text."""
    import subprocess

    proc = subprocess.run(
        [sys.executable, str(preflight.ROOT / "scripts" / "preflight.py"),
         "--fast", "--hook"],
        capture_output=True, text=True, timeout=120,
    )
    assert proc.returncode == 0, f"--hook must exit 0, got {proc.returncode}"
    assert "preflight" in proc.stdout, "hook mode must still report"


def t_boundary_empty_rows() -> None:
    saved = list(preflight.FULL_CHILDREN)
    preflight.FULL_CHILDREN.clear()
    try:
        expect_cannot_run(preflight.check_boundary, "empty FULL_CHILDREN rows")
    finally:
        preflight.FULL_CHILDREN[:] = saved


def t_boundary_bridgeroad_row_is_red() -> None:
    saved = list(preflight.FULL_CHILDREN)
    preflight.FULL_CHILDREN.append(
        ("vm-image", ["python3", "../_proj/bridgeroad/scripts/vm_staleness.py"], 60, "BridgeRoad VM")
    )
    try:
        got = preflight.check_boundary()
        assert not got["ok"], "a preflight row reaching into _proj/bridgeroad must be RED"
        assert any("_proj/bridgeroad" in x for x in got["detail"]), got["detail"]
    finally:
        preflight.FULL_CHILDREN[:] = saved


CASES = [
    ("mcp: zero declared servers refuses", t_mcp_empty),
    ("mcp: missing sdlc.json refuses", t_mcp_missing_file),
    ("mcp: declared but nothing listening is RED", t_mcp_declared_not_listening),
    ("mcp: optional server not listening stays GREEN", t_mcp_optional_not_listening_is_green),
    ("mcp: enabled but unconfigured is RED", t_mcp_enabled_but_unconfigured),
    ("tools: zero required refuses", t_tools_none_required),
    ("tools: missing policy refuses", t_tools_missing_file),
    ("tools: missing binary is RED", t_tools_missing_binary),
    ("graph: missing helper refuses", t_graph_missing_helper),
    ("repos: empty canonical map refuses", t_repos_empty_map),
    ("repos: declared-but-absent refuses", t_repos_declared_but_absent),
    ("boundary: empty FULL_CHILDREN refuses", t_boundary_empty_rows),
    ("boundary: _proj/bridgeroad row is RED (T302)", t_boundary_bridgeroad_row_is_red),
    ("hook mode always exits 0", t_hook_mode_always_exits_zero),
]


def main() -> int:
    if not CASES:
        print("✗ preflight-test: no cases — refusing to report a green over nothing")
        return 2

    saved = (preflight.SDLC, preflight.TOOLS_POLICY, preflight.GRAPH_FRESH)
    for name, fn in CASES:
        # Restore between cases: each doctors module globals, and a leaked path would make a
        # later case pass for the wrong reason.
        preflight.SDLC, preflight.TOOLS_POLICY, preflight.GRAPH_FRESH = saved
        case(name, fn)
    preflight.SDLC, preflight.TOOLS_POLICY, preflight.GRAPH_FRESH = saved

    for ok, name in results:
        print(f"  {PASS if ok else FAIL} {name}")
    bad = [n for ok, n in results if not ok]
    print(f"\n{'✅' if not bad else '❌'} preflight-test — {len(results) - len(bad)}/{len(results)} passed")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
