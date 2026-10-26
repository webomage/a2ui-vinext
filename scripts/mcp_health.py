#!/usr/bin/env python3
"""Do the declared MCP servers actually START and SERVE TOOLS? (health / integration)

    python3 scripts/mcp_health.py             # report
    python3 scripts/mcp_health.py --enforce   # exit 1 if a governed server is dead
    python3 scripts/mcp_health.py --only serena

THE GAP THIS CLOSES
-------------------
serena was DEAD FOR 18 DAYS and every gate stayed green.

  · `just tools-check` smoke-tests `serena --version`. That command never loads a project config,
    so it passed while the server died at startup on every session with `KeyError: 'languages'`.
    A version check proves a binary exists. It does not prove the thing RUNS.
  · `just mcp-exposure` measures TCP listeners and whether they are reachable without credentials.
    serena is **stdio** — it never binds a port — so it is structurally invisible there. That gate
    answers a security question, and answering it well says nothing about health.

The cause was worth the gate on its own: an UNPINNED serena from a marketplace plugin rewrote
`.serena/project.yml` to a newer schema, and the PINNED one could no longer read it. Two
registrations of the same tool, one governed, and the ungoverned one silently disabled the other.

WHAT THIS MEASURES, AND WHAT IT DOES NOT
----------------------------------------
It speaks MCP: spawn the server, `initialize`, `notifications/initialized`, `tools/list`. A server
that starts and serves at least one tool is HEALTHY. That is an integration check — the protocol
actually round-tripped — not a liveness guess from a log line.

It does NOT measure whether a tool WORKS, only that the server offers it. And it cannot see
session-level connection state: `.w0m/sdlc.json` already records that declared != configured !=
listening != session-CONNECTED, and this adds one rung (STARTS + SERVES) rather than closing that
gap. Say which rung you measured.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
ESTATE = ROOT
POLICY = ROOT / "project" / "policies" / "mcp-health-policy.json"

GREEN, RED, YELLOW, DIM, RESET = "\033[32m", "\033[31m", "\033[33m", "\033[2m", "\033[0m"


def declared() -> dict[str, dict]:
    """stdio MCP servers declared for this estate, from user config and the estate .mcp.json."""
    out: dict[str, dict] = {}
    est = ESTATE / ".mcp.json"
    if est.exists():
        try:
            out.update(json.loads(est.read_text()).get("mcpServers") or {})
        except (OSError, json.JSONDecodeError):
            pass
    user = Path.home() / ".claude.json"
    if user.exists():
        try:
            d = json.loads(user.read_text())
        except (OSError, json.JSONDecodeError):
            d = {}
        # Top-level first: this estate declares its servers globally, not per-project. An earlier
        # version read ONLY `projects[<estate>]`, found 0 there, and reported "no servers
        # declared" — which the empty-sweep guard correctly turned into a FAIL rather than a
        # clean run. Both scopes are read now, project-scoped last so it wins on a name clash.
        out.update(d.get("mcpServers") or {})
        for proj, pd in (d.get("projects") or {}).items():
            if Path(proj).resolve() == ESTATE.resolve():
                out.update(pd.get("mcpServers") or {})
    # Only stdio servers can be spawned here; an http/sse server is someone else's uptime.
    return {k: v for k, v in out.items() if v.get("command")}


def probe(name: str, spec: dict, timeout: float) -> tuple[str, str]:
    """(state, detail). state in {healthy, dead, unmeasurable}."""
    cmd = [spec["command"], *spec.get("args", [])]
    env = {**os.environ, **(spec.get("env") or {})}
    try:
        p = subprocess.Popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, env=env, cwd=str(ESTATE))
    except OSError as e:
        return "dead", f"cannot spawn: {e}"

    def send(obj: dict) -> None:
        assert p.stdin
        p.stdin.write(json.dumps(obj) + "\n")
        p.stdin.flush()

    try:
        send({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": "2024-11-05",
            "capabilities": {},
            "clientInfo": {"name": "w0m-mcp-health", "version": "1"}}})
        send({"jsonrpc": "2.0", "method": "notifications/initialized", "params": {}})
        send({"jsonrpc": "2.0", "id": 2, "method": "tools/list", "params": {}})

        deadline = time.time() + timeout
        tools = None
        # Keep the non-JSON lines instead of discarding them. A server logs its crash on the same
        # stdout it would answer on, and the read loop below skips anything that is not JSON — so
        # the first version of this probe consumed `KeyError: 'languages'` and then reported "no
        # response within 90s". A gate that says DEAD without saying why costs the next person the
        # same twenty minutes it just cost me.
        noise: list[str] = []
        assert p.stdout
        while time.time() < deadline:
            # A server that has EXITED will never answer, so waiting out the timeout wastes the
            # whole budget and throws away the reason. The dead serena pin died instantly with
            # `KeyError: 'languages'` and the first version of this probe reported only "no
            # response within 90s" — true, useless, and slow.
            if p.poll() is not None:
                err = (p.stderr.read(4000) if p.stderr else "") or ""
                key = next((l.strip() for l in reversed(err.splitlines())
                            if "Error" in l or "error:" in l), "")
                return "dead", f"exited {p.returncode}: {key[:100]}" if key else \
                       f"exited {p.returncode} without answering"
            line = p.stdout.readline()
            if not line:
                break
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                noise.append(line.rstrip())
                continue  # servers log to stdout too; keep it for the failure message
            if msg.get("id") == 2:
                if "error" in msg:
                    return "dead", f"tools/list error: {str(msg['error'])[:90]}"
                tools = (msg.get("result") or {}).get("tools") or []
                break
        if tools is None:
            # Drain BOTH streams. serena writes its traceback to STDOUT, not stderr, so a
            # stderr-only scan reported "no response within 90s" — true, and useless, when the
            # actual cause (`KeyError: 'languages'`) was sitting in the output already read past.
            # Let it finish dying before reading. Draining immediately after EOF on stdout can
            # catch stderr mid-write and come back empty, which is how this reported a bare
            # timeout while `KeyError: 'languages'` was still being flushed.
            try:
                p.wait(timeout=10)
            except subprocess.TimeoutExpired:
                p.kill()
            rest = "\n".join(noise[-40:])
            for stream in (p.stdout, p.stderr):
                if stream:
                    try:
                        # Read it ALL, not a prefix. `read(4000)` returned the first 4000 bytes —
                        # which is 84 lines of INFO logging — while the traceback sits at the END.
                        # Looking for an error in the head of a log finds nothing and reports a
                        # bare timeout, which is how this probe hid `KeyError: 'languages'` from
                        # itself three times.
                        rest += stream.read() or ""
                    except (OSError, ValueError):
                        pass
            key = next((l.strip() for l in reversed(rest.splitlines())
                        if "Error" in l or "error:" in l), "")
            return "dead", key[:110] or f"no tools/list response within {timeout:.0f}s"
        if not tools:
            return "dead", "served ZERO tools — started but useless"
        return "healthy", f"{len(tools)} tool(s)"
    except (BrokenPipeError, OSError) as e:
        return "dead", f"pipe closed: {e}"
    finally:
        p.kill()
        try:
            p.wait(timeout=5)
        except subprocess.TimeoutExpired:
            pass


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--enforce", action="store_true")
    ap.add_argument("--only")
    ap.add_argument("--timeout", type=float, default=60.0)
    args = ap.parse_args()

    pol = json.loads(POLICY.read_text(encoding="utf-8")) if POLICY.exists() else {}
    skip = pol.get("skip", {})

    servers = declared()
    if args.only:
        servers = {k: v for k, v in servers.items() if k == args.only}
    if not servers:
        # An empty sweep is a broken probe, not a clean host.
        print(f"{RED}[FAIL] no stdio MCP servers declared — cannot measure{RESET}")
        return 1

    print(f"{DIM}▶ mcp health — {len(servers)} stdio server(s) declared{RESET}")
    dead: list[str] = []
    for name in sorted(servers):
        if name in skip:
            print(f"  {YELLOW}skip{RESET}  {name:<26} {skip[name]}")
            continue
        state, detail = probe(name, servers[name], args.timeout)
        mark = {"healthy": f"{GREEN}ok{RESET}  ", "dead": f"{RED}DEAD{RESET}"}[state]
        print(f"  {mark}  {name:<26} {detail}")
        if state == "dead":
            dead.append(f"{name}: {detail}")

    print(f"\n  {len(servers) - len(skip)} probed, {len(dead)} dead")
    if dead:
        print(f"{RED}[FAIL] a declared MCP server does not start or serves no tools{RESET}")
        for d in dead:
            print(f"  {RED}·{RESET} {d}")
        print(f"  {DIM}A `--version` smoke test cannot see this: it never loads a project "
              f"config.{RESET}")
        return 1 if args.enforce else 0
    print(f"{GREEN}✅ every governed MCP server starts and serves tools{RESET}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
