#!/usr/bin/env python3
"""T154 AC8 regression proof for mcp_declared.py — declared vs listening reconciliation.

Fixture-driven, never the network. A security gate whose tests depend on what happens to be
listening is a gate whose tests are a coin flip (the rule test_mcp_ratchet.py already sets).

Covers, with a RED case for every rule:
  AC8a  schema — missing transport, local-http missing bind/auth, unknown transport value
  AC8b  the three outcomes — listening+undeclared (fails), declared+absent (does not),
        known only from machine-wide config (does not)
  AC8c  non-comparable declarations counted AND named; an all-stdio set is not green
  AC8d  fail closed — missing / malformed / empty declaration source, each distinct

Run: `just mcp-declared-test`
"""
import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"
sys.path.insert(0, str(ROOT / "scripts"))
TMP = Path(tempfile.mkdtemp(prefix="t154-ac8-"))

failures: list[str] = []


def check(label: str, ok: bool, detail: str = "") -> None:
    print(f"  {'✅' if ok else '❌'} {label}")
    if not ok:
        failures.append(f"{label}{(' — ' + detail) if detail else ''}")


# A missing module would make every "raises" assertion below pass for the wrong reason.
try:
    import mcp_declared
except ImportError as e:  # pragma: no cover
    print(f"❌ mcp_declared.py is not importable ({e}) — the suite cannot prove anything.")
    sys.exit(2)


def write(name: str, obj) -> Path:
    p = TMP / name
    p.write_text(json.dumps(obj))
    return p


def surface(addr: str, port: int, server: str, mcp=True, unauth=200) -> dict:
    """A confirmed-MCP entry in `mcp_exposure --json` shape."""
    return {"addr": addr, "port": port, "command": server, "pid": 1,
            "probed": True,
            "probe": {"mcp": mcp, "server": server, "version": "1.0.0",
                      "endpoint": f"http://{addr}:{port}/mcp",
                      "unauth_initialize": unauth, "unauth_tools_list": unauth,
                      "tools": ["do_thing"]}}


print("\n── AC8d — fail closed on a bad declaration source ──")

for label, payload, needle in [
    ("missing file", None, "not found"),
    ("malformed json", "{not json", "malformed"),
    ("no mcp.servers key", {"other": 1}, "no mcp.servers"),
    ("empty declaration list", {"mcp": {"servers": {}}}, "no declarations"),
]:
    if payload is None:
        path = TMP / "does-not-exist.json"
    elif isinstance(payload, str):
        path = TMP / "bad.json"
        path.write_text(payload)
    else:
        path = write(f"{label.replace(' ', '-')}.json", payload)
    try:
        mcp_declared.load_declared(path)
        check(f"{label} raises", False, "no exception")
    except mcp_declared.DeclarationError as e:
        check(f"{label} raises DeclarationError mentioning '{needle}'", needle in str(e).lower(),
              str(e))

print("\n── AC8a — schema validation ──")

bad_missing = write("m.json", {"mcp": {"servers": {"a": {"enabled": True}}}})
try:
    mcp_declared.load_declared(bad_missing)
    check("a declaration with no transport is rejected", False, "no exception")
except mcp_declared.DeclarationError as e:
    check("a declaration with no transport is rejected BY NAME", "a" in str(e), str(e))

bad_bind = write("b.json", {"mcp": {"servers": {"srv": {"enabled": True, "transport": "local-http"}}}})
try:
    mcp_declared.load_declared(bad_bind)
    check("local-http without bind/auth is rejected", False, "no exception")
except mcp_declared.DeclarationError as e:
    check("local-http without bind/auth is rejected BY NAME", "srv" in str(e), str(e))

bad_val = write("v.json", {"mcp": {"servers": {"srv": {"enabled": True, "transport": "carrier-pigeon"}}}})
try:
    mcp_declared.load_declared(bad_val)
    check("an unknown transport value is rejected", False, "no exception")
except mcp_declared.DeclarationError as e:
    check("an unknown transport value is rejected", "carrier-pigeon" in str(e), str(e))

good = write("good.json", {"mcp": {"servers": {
    "graphify": {"enabled": True, "transport": "stdio"},
    "cloudflare": {"enabled": True, "transport": "remote"},
    "inngest-dev": {"enabled": True, "transport": "local-http",
                    "bind": "127.0.0.1:4011", "auth": "none"},
}}})
try:
    d = mcp_declared.load_declared(good)
    check("a well-formed declaration set loads", len(d) == 3)
except mcp_declared.DeclarationError as e:  # pragma: no cover
    check("a well-formed declaration set loads", False, str(e))

print("\n── AC8b — the three outcomes ──")

declared = mcp_declared.load_declared(good)

r = mcp_declared.reconcile(declared, external={}, surfaces=[surface("127.0.0.1", 4011, "inngest-dev")])
check("a declared, listening server is matched",
      [m["name"] for m in r["matched"]] == ["inngest-dev"], json.dumps(r["matched"]))
check("a matched server does not fail the run", r["exit_code"] == 0, str(r["exit_code"]))

r = mcp_declared.reconcile(declared, external={}, surfaces=[surface("127.0.0.1", 9999, "rogue")])
check("a listening, UNDECLARED server is reported", len(r["undeclared"]) == 1, json.dumps(r["undeclared"]))
check("a listening, undeclared server FAILS the run", r["exit_code"] != 0, str(r["exit_code"]))

r = mcp_declared.reconcile(declared, external={}, surfaces=[])
check("a declared local-http with nothing listening is reported",
      [m["name"] for m in r["absent"]] == ["inngest-dev"], json.dumps(r["absent"]))
check("declared-but-absent does NOT fail the run", r["exit_code"] == 0, str(r["exit_code"]))

r = mcp_declared.reconcile(declared, external={"rogue": {"source": "~/.claude.json"}},
                           surfaces=[surface("127.0.0.1", 9999, "rogue")])
check("a surface known only from machine-wide config is its own outcome",
      len(r["external"]) == 1 and not r["undeclared"], json.dumps(r))
check("declared-outside-the-repo does NOT fail the run", r["exit_code"] == 0, str(r["exit_code"]))

print("\n── AC8c — non-comparable declarations are counted AND named ──")

r = mcp_declared.reconcile(declared, external={}, surfaces=[surface("127.0.0.1", 4011, "inngest-dev")])
check("stdio/remote declarations are counted as not-comparable", r["not_comparable_count"] == 2,
      str(r.get("not_comparable_count")))
check("...and NAMED, not just counted",
      sorted(r["not_comparable"]) == ["cloudflare", "graphify"], json.dumps(r.get("not_comparable")))

all_stdio = mcp_declared.load_declared(write("s.json", {"mcp": {"servers": {
    "a": {"enabled": True, "transport": "stdio"}, "b": {"enabled": True, "transport": "stdio"}}}}))
r = mcp_declared.reconcile(all_stdio, external={}, surfaces=[])
check("an all-stdio declared set does NOT render as a green reconcile",
      r["comparable_count"] == 0 and r["vacuous"] is True, json.dumps(r))

print("\n── review findings 2026-08-01 ──")

# FINDING 1: an IPv6 surface rendered `::1:4011`, which is not how anyone writes an IPv6
# bind. A declaration using the conventional `[::1]:4011` would fail to match, and the server
# would be reported BOTH as "declared, not listening" AND "listening, undeclared" — a double
# false positive on the security-relevant direction.
v6 = mcp_declared.load_declared(write("v6.json", {"mcp": {"servers": {
    "srv": {"enabled": True, "transport": "local-http", "bind": "[::1]:4011", "auth": "none"}}}}))
r = mcp_declared.reconcile(v6, external={}, surfaces=[surface("::1", 4011, "other-name")])
check("an IPv6 surface matches a conventionally-written [::1]:port declaration",
      len(r["matched"]) == 1 and not r["undeclared"], json.dumps(r))

# The bare form must keep working too — the declaration is human-written either way.
v6b = mcp_declared.load_declared(write("v6b.json", {"mcp": {"servers": {
    "srv": {"enabled": True, "transport": "local-http", "bind": "::1:4011", "auth": "none"}}}}))
r = mcp_declared.reconcile(v6b, external={}, surfaces=[surface("::1", 4011, "other-name")])
check("...and the bare ::1:port form still matches", len(r["matched"]) == 1, json.dumps(r))

# FINDING 3: one process listening on both address families was reported as TWO undeclared
# surfaces, inflating the count. mcp_exposure already dedupes wildcard binds per (command, port)
# for exactly this reason — a bind is one exposure, not one per address it resolves to.
r = mcp_declared.reconcile(v6, external={}, surfaces=[
    surface("127.0.0.1", 9999, "rogue"), surface("::1", 9999, "rogue")])
check("one process on two address families is ONE undeclared finding",
      len(r["undeclared"]) == 1, json.dumps(r["undeclared"]))
check("...and both addresses are still recorded, not discarded",
      len(r["undeclared"][0].get("addrs", [])) == 2, json.dumps(r["undeclared"]))

print("\n── security review 2026-08-01 ──")

# The server NAME comes from the probe response — i.e. from the listening process itself. Matching
# on it meant an untrusted server controlled the field that decides whether it is reported.
one = mcp_declared.load_declared(write("one.json", {"mcp": {"servers": {
    "legit": {"enabled": True, "transport": "local-http",
              "bind": "127.0.0.1:1234", "auth": "api-key"}}}}))

r = mcp_declared.reconcile(one, external={},
                           surfaces=[surface("0.0.0.0", 9999, "legit")])
check("a server claiming a declared NAME on an undeclared bind does NOT count as matched",
      not r["matched"], json.dumps(r["matched"]))
check("...it FAILS the run", r["exit_code"] != 0, str(r["exit_code"]))

r = mcp_declared.reconcile(one, external={},
                           surfaces=[surface("127.0.0.1", 1234, "anything-it-likes")])
check("a surface at a declared BIND matches regardless of the name it reports",
      len(r["matched"]) == 1, json.dumps(r["matched"]))

# ~/.claude.json may explain a surface, but machine-wide config cannot make a wildcard bind
# acceptable — a LAN-reachable MCP is an exposure no matter who configured it.
r = mcp_declared.reconcile(one, external={"rogue": {"source": "~/.claude.json"}},
                           surfaces=[surface("127.0.0.1", 7777, "rogue")])
check("machine-wide config explains a LOOPBACK surface", len(r["external"]) == 1, json.dumps(r))
check("...and does not fail the run", r["exit_code"] == 0, str(r["exit_code"]))

r = mcp_declared.reconcile(one, external={"rogue": {"source": "~/.claude.json"}},
                           surfaces=[surface("0.0.0.0", 7777, "rogue")])
check("machine-wide config does NOT explain away a WILDCARD bind",
      len(r["undeclared"]) == 1 and not r["external"], json.dumps(r))
check("...and it FAILS the run", r["exit_code"] != 0, str(r["exit_code"]))


print("\n── T169 2026-08-05 — presence and protocol are different questions ──")
# 🔴 The defect this section exists for: `reconcile` was passed ONLY confirmed-MCP surfaces, so a
# declared local-http entry that is not itself an MCP server could never match. The Headroom proxy
# was live on 127.0.0.1:8787 answering HTTP 200 and the gate reported "declared, not listening" —
# a false negative rendered in the language of a benign one ("usually just stopped, does not fail").
declared = {"proxy": {"transport": "local-http", "bind": "127.0.0.1:8787", "auth": "none"}}

# Something IS listening on the declared bind, but it does not speak MCP (an LLM proxy).
# `surfaces` (MCP-confirmed) is empty; `all_listening` carries it.
live = surface("127.0.0.1", 8787, "headroom", mcp=False, unauth=None)
r = mcp_declared.reconcile(declared, external={}, surfaces=[], all_listening=[live])
check("a declared non-MCP local-http surface that IS listening reports PRESENT, not absent",
      [m["name"] for m in r["present"]] == ["proxy"] and r["absent"] == [], repr(r))
check("...and it does NOT fail the run", r["exit_code"] == 0)

# RED: nothing on that bind at all must still be reported absent — the fix must not make
# every declaration look alive, which would be the opposite failure and equally silent.
r = mcp_declared.reconcile(declared, external={}, surfaces=[],
                           all_listening=[surface("127.0.0.1", 9999, "other", mcp=False)])
check("RED — nothing listening on the declared bind is still ABSENT",
      [m["name"] for m in r["absent"]] == ["proxy"] and r["present"] == [], repr(r))

# RED: a mis-declared bind must not match a live socket (T169 AC4's explicit probe).
mis = {"proxy": {"transport": "local-http", "bind": "127.0.0.1:8788", "auth": "none"}}
r = mcp_declared.reconcile(mis, external={}, surfaces=[], all_listening=[live])
check("RED — a MIS-DECLARED bind does not match the live socket next to it",
      [m["name"] for m in r["absent"]] == ["proxy"] and r["present"] == [], repr(r))

# The undeclared class must stay MCP-only. Widening presence must not turn every unrelated
# listening socket into a rogue-MCP finding — that noise is what gets a security gate ignored.
r = mcp_declared.reconcile(declared, external={}, surfaces=[],
                           all_listening=[live, surface("0.0.0.0", 5000, "ControlCe", mcp=False)])
check("an unrelated non-MCP listener is NOT reported as an undeclared MCP surface",
      r["undeclared"] == [] and r["exit_code"] == 0, repr(r))

# And a genuinely undeclared MCP surface must still fail — the property the widening could break.
r = mcp_declared.reconcile(declared, external={},
                           surfaces=[surface("0.0.0.0", 9999, "rogue")],
                           all_listening=[live, surface("0.0.0.0", 9999, "rogue")])
check("RED — a real undeclared MCP surface still FAILS after the widening",
      [m["name"] for m in r["undeclared"]] != [] and r["exit_code"] == 1, repr(r))

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ mcp-declared: all checks passed")
