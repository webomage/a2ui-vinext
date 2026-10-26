#!/usr/bin/env python3
"""mcp_exposure.py — what is listening on this host, and can it be USED without credentials? (T154)

T154 exists because an unauthenticated MCP server sat on `0.0.0.0` and nobody knew, and because a
second all-interfaces listener had to be chased down by hand. This is the recipe that stops both
from needing a human.

Three questions, in order, because each one is useless without the previous:

  1. **AC3 — what is listening?** Every TCP listener, its owning process, and whether the bind is
     loopback or reachable from the network.
  2. **AC4 — is it USABLE without credentials?** Liveness is not the risk. The risk is an
     unauthenticated caller reaching `tools/list`. Reported per surface: does `initialize` succeed
     with no credentials, does `tools/list`, and how many tools come back.
  3. **AC5 — what would that get them?** The tool NAMES, not just the count. A read-only `graph`
     server and one exposing `edit`/`system` are not comparable risks, and a new *tool* appearing on
     an already-accepted server is a change the count alone would hide.

🔴 **ENUMERATE ONLY — this never invokes a tool.** `initialize` and `tools/list` are discovery
calls. A monitor that calls `edit` to find out whether it can is itself the breach (AC4).

⚠️ **Probe the surface as itself** ([[T152]]): a `GET /v1/models` against an MCP server reports a
healthy server as dead. MCP here means JSON-RPC over `POST`, and the live servers answer with
**SSE** (`event: message` + a `data:` line), not a JSON body — parsing that as JSON reports a
working server as broken. The endpoint is `/mcp`, not `/`. All of this was learned the hard way
closing AC1b; it is encoded below so the next person does not repeat it.

⚠️ **A hostname is not an address.** `localhost` resolves to `127.0.0.1` **and** `::1`, and a
server can be gated on one and open on the other. Wildcard binds are expanded to both families.

Scope is the **HOST**, not just w0m: the 2026-07-27 incident was a non-w0m listener, and an
inventory that stops at your own ports only tells you what you already knew.

Usage:
    just mcp-exposure                # human report
    just mcp-exposure --json         # machine-readable (for AC6 monitoring / AC7 baseline)
    just mcp-exposure --all-ports    # probe every listener, not just HTTP-speaking ones

Exit: 0 clean · 1 an MCP surface answered `tools/list` without credentials · 2 bad input
(no listeners enumerated at all — an empty sweep is a missing input, not a clean host).
"""
from __future__ import annotations

import argparse
import json
import re
import socket
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import mcp_declared

# The declared side (T154 AC8). SDLC_JSON is tracked and authoritative; CLAUDE_JSON is
# machine-wide and may only EXPLAIN a surface, never fail the run.
SDLC_JSON = ROOT / ".w0m" / "sdlc.json"
CLAUDE_JSON = Path.home() / ".claude.json"

# Paths a JSON-RPC/MCP server is plausibly mounted at. `/mcp` first: it is what the live
# Semantic Notes Vault MCP uses, and `/` returns "Cannot POST /" there.
MCP_PATHS = ("mcp", "sse", "messages", "api/mcp", "")
TIMEOUT = 3.0

LOOPBACK = {"127.0.0.1", "::1", "localhost"}
WILDCARD = {"*", "0.0.0.0", "::", "[::]"}

INIT = {
    "jsonrpc": "2.0", "id": 1, "method": "initialize",
    "params": {"protocolVersion": "2024-11-05", "capabilities": {},
               "clientInfo": {"name": "w0m-mcp-exposure", "version": "1"}},
}


def listeners() -> list[dict]:
    """Every listening TCP socket with its owning process, via lsof.

    Parsed defensively: lsof output varies by platform and a malformed line must skip that row,
    never abort the sweep — a crashed inventory and a clean host look identical to a cron job.
    """
    try:
        r = subprocess.run(["lsof", "-nP", "-iTCP", "-sTCP:LISTEN"],
                           capture_output=True, text=True, timeout=20)
    except (OSError, subprocess.SubprocessError) as e:
        print(f"mcp-exposure: cannot run lsof ({e}) — refusing to report a clean host.", file=sys.stderr)
        sys.exit(2)

    out = []
    for line in (r.stdout or "").splitlines()[1:]:
        parts = line.split()
        if len(parts) < 9:
            continue
        name = parts[8]
        m = re.match(r"^(.*):(\d+)$", name)
        if not m:
            continue
        host, port = m.group(1), int(m.group(2))
        out.append({"command": parts[0], "pid": parts[1], "user": parts[2],
                    "host": host, "port": port})
    return out


def lan_addr() -> str | None:
    """This host's primary LAN address, or None. Needed because a wildcard bind's real exposure
    is the LAN address — reporting it as `127.0.0.1` (which is what the first version did) makes a
    network-wide bind read as loopback-only, inverting the finding."""
    for iface in ("en0", "en1"):
        try:
            r = subprocess.run(["ipconfig", "getifaddr", iface], capture_output=True, text=True, timeout=5)
            if r.returncode == 0 and r.stdout.strip():
                return r.stdout.strip()
        except (OSError, subprocess.SubprocessError):
            pass
    return None


def expand(host: str) -> list[str]:
    """Every address this bind is reachable on. A wildcard is BOTH families, and a hostname is not
    an address — `localhost` is 127.0.0.1 AND ::1, and a server can be gated on one, open on the
    other."""
    if host in WILDCARD or host == "localhost":
        return ["127.0.0.1", "::1"]
    return [host.strip("[]")]


def reachable(addr: str, port: int, timeout: float = 2.0) -> bool:
    """Can this actually be connected to? A wildcard bind behind a host firewall is bound wide but
    NOT reachable wide — measured, because `0.0.0.0` alone overstates the exposure."""
    fam = socket.AF_INET6 if ":" in addr else socket.AF_INET
    try:
        with socket.socket(fam, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect((addr, port))
            return True
    except Exception:
        return False


def is_loopback(host: str) -> bool:
    return host.strip("[]") in LOOPBACK


def url_for(addr: str, port: int, path: str) -> str:
    hostpart = f"[{addr}]" if ":" in addr else addr
    return f"http://{hostpart}:{port}/{path}"


def rpc(url: str, payload: dict, sid: str | None = None) -> tuple[int | None, str, str | None]:
    headers = {"Content-Type": "application/json",
               "Accept": "application/json, text/event-stream"}
    if sid:
        headers["Mcp-Session-Id"] = sid
    # Scheme is asserted, not assumed. `urllib` honours `file://`, so a dynamic URL is a file-read
    # primitive if anything upstream can influence the scheme. Here every URL comes from `url_for`,
    # which hardcodes `http://` over an lsof-derived host+port — but assert it anyway, so the
    # property is enforced at the call site instead of inferred from a caller three functions away.
    if not url.startswith("http://"):
        raise ValueError(f"refusing a non-http URL: {url!r}")
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers)
    try:
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read(8192).decode(errors="replace"), resp.headers.get("Mcp-Session-Id")
    except urllib.error.HTTPError as e:
        # 🔴 The body can vanish mid-read: a server that rejects the POST may reset the connection
        # before its error page is fully read. An exception raised INSIDE an `except` block is not
        # caught by the clauses after it, so that ConnectionResetError escaped `rpc` entirely and
        # aborted the whole sweep — one rude peer meant NOTHING was measured, and the ratchet
        # reported a traceback instead of an exposure count. The status line is still known and
        # still classifies (401/403 -> gated), so an unreadable body loses nothing but its text.
        try:
            body = e.read(512).decode(errors="replace")
        except Exception as read_err:
            body = f"<unreadable: {type(read_err).__name__}>"
        return e.code, body, None
    except Exception:
        return None, "", None


def decode(body: str) -> dict | None:
    """MCP replies are JSON *or* SSE. Trying only `json.loads` reads a healthy SSE server as dead."""
    body = body.strip()
    if not body:
        return None
    m = re.search(r"^data:\s*(.+)$", body, re.M)
    candidate = m.group(1) if m else body
    try:
        return json.loads(candidate)
    except (ValueError, TypeError):
        return None


def speaks_http(addr: str, port: int) -> bool:
    """Cheap pre-filter so a sweep does not POST JSON at every database on the box."""
    fam = socket.AF_INET6 if ":" in addr else socket.AF_INET
    try:
        with socket.socket(fam, socket.SOCK_STREAM) as s:
            s.settimeout(TIMEOUT)
            s.connect((addr, port))
            s.sendall(b"HEAD / HTTP/1.0\r\n\r\n")
            return b"HTTP/" in s.recv(64)
    except Exception:
        return False


def probe(addr: str, port: int) -> dict | None:
    """Is this MCP, and what does it give up unauthenticated? Discovery calls only."""
    for path in MCP_PATHS:
        url = url_for(addr, port, path)
        code, body, sid = rpc(url, INIT)
        if code is None:
            continue

        # 🔴 A 401/403 is NOT evidence of MCP. Any HTTP server rejects an unknown POST the same
        # way — the first version of this script classified macOS AirPlay (:5000/:7000) as "gated
        # MCP servers" on exactly this reasoning. Without credentials the protocol is
        # unknowable, so say UNKNOWN rather than inventing a classification. Recorded as its own
        # bucket: an auth-gated surface is not a finding, but it is also not identified.
        if code in (401, 403):
            return {"endpoint": url, "mcp": "unknown", "unauth_initialize": code,
                    "unauth_tools_list": None, "tools": [], "gated": True}

        parsed = decode(body)
        if code == 200 and parsed and "result" in parsed and "protocolVersion" in str(parsed.get("result")):
            server = (parsed["result"].get("serverInfo") or {})
            rpc(url, {"jsonrpc": "2.0", "method": "notifications/initialized"}, sid)
            code2, body2, _ = rpc(url, {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}, sid)
            listed = decode(body2) or {}
            tools = [t.get("name", "?") for t in ((listed.get("result") or {}).get("tools") or [])]
            return {"endpoint": url, "mcp": True, "server": server.get("name"),
                    "version": server.get("version"), "unauth_initialize": code,
                    "unauth_tools_list": code2, "tools": tools, "gated": False}
    return None


def collect(all_ports: bool = False) -> dict:
    """The whole measurement, as the `--json` payload. One definition, two consumers: this
    script's report and `mcp_ratchet.py` — a ratchet that re-implemented the sweep would drift
    from the inventory it is supposed to be ratcheting."""
    socks = listeners()
    lan = lan_addr()
    surfaces, seen = [], set()
    for s in socks:
        wild = s["host"] in WILDCARD
        for addr in expand(s["host"]):
            key = (addr, s["port"])
            if key in seen:
                continue
            seen.add(key)
            entry = {**s, "addr": addr, "wildcard": wild,
                     "loopback": is_loopback(addr) and not wild}
            # `probed` is recorded explicitly because a MISSING probe and a probe that came back
            # not-MCP are different facts: the first is a blind spot (the surface does not speak
            # HTTP at all — e.g. a Postgres on `0.0.0.0`), the second is a measurement. Reading
            # them as one turns "never asked" into "asked and clean".
            entry["probed"] = bool(all_ports or speaks_http(addr, s["port"]))
            if entry["probed"]:
                # A probe that RAISES is a third state, and collapsing it into either of the other
                # two is the same error in a new place: treated as not-MCP it becomes "asked and
                # clean", treated as unprobed it becomes "never asked". Recorded as itself, and
                # counted, so a sweep that could not look somewhere says so instead of aborting.
                try:
                    entry["probe"] = probe(addr, s["port"])
                except Exception as exc:
                    entry["probe"] = None
                    entry["probe_error"] = f"{type(exc).__name__}: {exc}"
            surfaces.append(entry)

    # Confirmed MCP only. An auth-gated surface stays UNKNOWN — see `probe()`.
    mcp = [s for s in surfaces if s.get("probe") and s["probe"]["mcp"] is True]
    gated = [s for s in surfaces if s.get("probe") and s["probe"]["mcp"] == "unknown"]
    open_mcp = [s for s in mcp if s["probe"]["unauth_tools_list"] == 200]

    # A wildcard bind is the exposure, reported ONCE per (process, port) with its real reachability
    # — not once per loopback address, which is what made a network bind read as loopback-only.
    wide, wseen = [], set()
    for s in surfaces:
        if not s["wildcard"] or (s["command"], s["port"]) in wseen:
            continue
        wseen.add((s["command"], s["port"]))
        s = dict(s)
        s["lan_reachable"] = reachable(lan, s["port"]) if lan else None
        wide.append(s)

    return {"listeners": len(socks), "surfaces": len(surfaces), "mcp_confirmed": len(mcp),
            "auth_gated_unknown": len(gated), "unauthenticated_mcp": len(open_mcp),
            "lan_addr": lan, "wildcard_binds": wide, "detail": surfaces}


def main() -> int:
    ap = argparse.ArgumentParser(description="MCP/network exposure inventory (T154 AC3-AC5)")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--all-ports", action="store_true",
                    help="probe every listener, not only those that answer HTTP")
    args = ap.parse_args()

    payload = collect(all_ports=args.all_ports)
    if not payload["listeners"]:
        print("mcp-exposure: enumerated 0 listening sockets — that is a broken sweep, not a clean "
              "host. Check lsof permissions.", file=sys.stderr)
        return 2

    surfaces, lan, wide = payload["detail"], payload["lan_addr"], payload["wildcard_binds"]
    mcp = [s for s in surfaces if s.get("probe") and s["probe"]["mcp"] is True]
    gated = [s for s in surfaces if s.get("probe") and s["probe"]["mcp"] == "unknown"]
    open_mcp = [s for s in mcp if s["probe"]["unauth_tools_list"] == 200]

    # The reconcile is computed BEFORE the --json branch on purpose. It used to run only on the
    # human path, so `--json` never evaluated it and its exit code ignored undeclared surfaces
    # entirely: the two output modes of a security gate disagreed about whether the host was
    # clean, and any CI consuming --json would have read 0 with a rogue MCP listening.
    try:
        declared = mcp_declared.load_declared(SDLC_JSON)
    except mcp_declared.DeclarationError as e:
        print(f"\n❌ declared-vs-listening could not run: {e}", file=sys.stderr)
        return 2
    rec = mcp_declared.reconcile(declared, mcp_declared.load_external(CLAUDE_JSON), mcp,
                                 all_listening=surfaces)
    payload["declared_vs_listening"] = rec

    if args.json:
        print(json.dumps(payload, indent=2))
        return 1 if (open_mcp or rec["undeclared"]) else 0

    print(f"▶ mcp-exposure — {payload['listeners']} listening socket(s) → {len(surfaces)} address:port "
          f"surface(s) · {len(mcp)} confirmed MCP · {len(gated)} auth-gated (protocol unknown)")

    print(f"\n  ── WILDCARD BINDS ({len(wide)}) — bound to all interfaces"
          + (f"; LAN reachability tested against {lan}" if lan else "; no LAN address found"))
    for s in sorted(wide, key=lambda x: x["port"]):
        if s["lan_reachable"] is None:
            verdict = "untested"
        elif s["lan_reachable"]:
            verdict = "🔴 REACHABLE from the LAN"
        else:
            verdict = "🟡 bound wide, NOT reachable (host firewall)"
        print(f"     :{s['port']:<6} {s['command']}(pid {s['pid']})  {verdict}")
    if not wide:
        print("     (none)")

    print(f"\n  ── MCP SURFACES ({len(mcp)} confirmed) — enumerated, never invoked")
    for s in mcp:
        p = s["probe"]
        mark = "🔴" if p["unauth_tools_list"] == 200 else "🟡"
        who = f"{p.get('server') or '?'} {p.get('version') or ''}".strip()
        print(f"     {mark} {p['endpoint']}  {who}")
        print(f"        unauth initialize={p['unauth_initialize']} "
              f"tools/list={p['unauth_tools_list']} · {len(p['tools'])} tool(s): "
              f"{', '.join(p['tools']) or '—'}")
    if not mcp:
        print("     (none found — a PROBE result, not proof of absence)")

    print(f"\n  ── AUTH-GATED, PROTOCOL UNKNOWN ({len(gated)}) — rejected the probe, so it is not "
          f"identifiable\n     (a 401/403 is NOT evidence of MCP: any HTTP server answers an "
          f"unknown POST that way)")
    for s in gated:
        print(f"     ✅ {s['probe']['endpoint']}  HTTP {s['probe']['unauth_initialize']} "
              f"· {s['command']}(pid {s['pid']})")
    if not gated:
        print("     (none)")

    # ── Declared vs listening (T154 AC8) ──────────────────────────────────────
    # Computed above, before the --json branch, so both output modes agree. Fails closed: a
    # reconcile that loaded no declarations would report zero undeclared listeners and exit
    # clean, which is the most dangerous output this tool has.
    for line in mcp_declared.render(rec):
        print(line)

    failed = []
    if open_mcp:
        print(f"\n🔴 {len(open_mcp)} MCP surface(s) served tools/list with NO credentials.")
        failed.append("unauthenticated")
    else:
        print("\n✅ no MCP surface answered tools/list without credentials.")
    if rec["undeclared"]:
        print(f"🔴 {len(rec['undeclared'])} listening MCP surface(s) are UNDECLARED — "
              f"an exposure nobody wrote down is exactly what T154 was opened for.")
        failed.append("undeclared")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
