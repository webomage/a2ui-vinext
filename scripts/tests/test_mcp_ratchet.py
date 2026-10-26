#!/usr/bin/env python3
"""T154 AC7 regression proof for mcp_ratchet.py — drives it on fixture snapshots, never the network.

The ratchet's whole value is that it fails on the RIGHT changes and stays quiet on the wrong ones,
so every rule gets a red case here rather than a hopeful one live. Fixtures are snapshots in
`mcp_exposure --json` shape fed through `--from-json`, so no test touches a socket: a security
gate whose tests depend on what happens to be listening is a gate whose tests are a coin flip.

Covers: scope (loopback non-MCP is not exposure), undeclared exposure, bind widening, LAN
reachability, gated→ungated (the AC1b regression), a new tool on an accepted server, the
`command:*` ephemeral-port form, worst-wins address-family merge, known-open recording, the
improvement path, `--save` refusing to launder a regression, and the vacuity guards.

Run: `just mcp-ratchet-test`
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB = ROOT / "w0m-web"
SCRIPT = ROOT / "scripts" / "mcp_ratchet.py"
TMP = Path(tempfile.mkdtemp(prefix="t154-"))

failures: list[str] = []

# A missing script exits 2 for every run, which would let the four "exit 2" vacuity checks below
# report GREEN over an implementation that does not exist. Fail here instead — the same
# vacuous-green this suite is written to catch, one level up.
if not SCRIPT.is_file():
    sys.exit(f"✗ {SCRIPT} not found — every check would read as exit 2. Nothing was tested.")


def surface(command="svc", port=9000, addr="127.0.0.1", *, wildcard=False, loopback=True,
            probed=False, mcp=None, tools_list=None, tools=(), user="proto", pid="1", lan=True):
    """One address:port row in `mcp_exposure --json` → `detail` shape.

    `probed=False` omits the `probe` key entirely, which is how the inventory says "never asked"
    — distinct from `probe: null`, which says "asked, not MCP". Conflating the two turns a blind
    spot into a clean bill of health.
    """
    s = {"command": command, "pid": pid, "user": user, "host": "*" if wildcard else addr,
         "port": port, "addr": addr, "wildcard": wildcard, "loopback": loopback, "_lan": lan}
    if probed:
        s["probe"] = None if mcp is None else {
            "endpoint": f"http://{addr}:{port}/mcp", "mcp": mcp,
            "unauth_initialize": 200 if mcp is True else 401,
            "unauth_tools_list": tools_list, "tools": list(tools),
            "gated": mcp == "unknown"}
    return s


def snapshot(*surfaces, lan="192.168.1.9"):
    wild, seen = [], set()
    for s in surfaces:
        if s["wildcard"] and (s["command"], s["port"]) not in seen:
            seen.add((s["command"], s["port"]))
            wild.append({**s, "lan_reachable": s.get("_lan", True)})
    return {"listeners": len(surfaces), "surfaces": len(surfaces), "lan_addr": lan,
            "wildcard_binds": wild, "detail": list(surfaces)}


def entry(reason="declared for the test", status="accepted", bind="loopback", lan_reachable=None,
          probed=True, mcp=False, unauth_tools_list=None, tools=()):
    return {"status": status, "reason": reason, "bind": bind, "lan_reachable": lan_reachable,
            "probed": probed, "mcp": mcp, "unauth_tools_list": unauth_tools_list,
            "tools": list(tools)}


def run(name, baseline, snap, *flags):
    """Run the ratchet on a fixture pair; return (exit code, parsed --json report)."""
    bpath = TMP / f"{name}-baseline.json"
    spath = TMP / f"{name}-snapshot.json"
    bpath.write_text(json.dumps(baseline, indent=2))
    spath.write_text(json.dumps(snap, indent=2))
    r = subprocess.run([sys.executable, str(SCRIPT), "--baseline", str(bpath),
                        "--from-json", str(spath), *flags],
                       capture_output=True, text=True)
    report = None
    if "--json" in flags:
        try:
            report = json.loads(r.stdout)
        except ValueError:
            report = None
    return r.returncode, report, r.stdout + r.stderr, bpath


def check(label, cond, detail=""):
    if cond:
        print(f"  ✅ {label}")
    else:
        failures.append(f"{label} — {detail}")
        print(f"  ✗  {label}  {detail}")


def kinds(report):
    return sorted({x["kind"] for x in report["regressions"]}) if report else []


# ─────────────────────────────────────────────────────────────────────────────
print("▶ mcp-ratchet tests\n")

# 1. Scope: a loopback listener that is not MCP is not exposure. A ratchet that fires when
#    `pnpm dev` starts gets muted, and a muted gate is worse than no gate.
base = {"measured": "2026-07-31", "accepted": {"docker:4011": entry(bind="wildcard", lan_reachable=True)}}
code, rep, out, _ = run("scope", base,
                        snapshot(surface("docker", 4011, wildcard=True, loopback=False),
                                 surface("vite", 4321), surface("node", 5173)), "--json")
check("loopback non-MCP listeners are out of scope", code == 0 and not rep["regressions"],
      f"exit={code} {kinds(rep)}")
check("...and are not silently counted as tracked", rep and len(rep["tracked"]) == 1,
      f"tracked={list((rep or {}).get('tracked', {}))}")

# 2. An undeclared wildcard bind is the finding this ticket opened with.
code, rep, out, _ = run("undeclared", {"measured": "x", "accepted": {}},
                        snapshot(surface("mystery", 8099, wildcard=True, loopback=False)), "--json")
check("undeclared non-loopback bind fails", code == 1 and kinds(rep) == ["undeclared"],
      f"exit={code} {kinds(rep)}")

# 3. An undeclared MCP surface fails even on loopback — loopback is not safe, it is narrower.
code, rep, out, _ = run("undeclared-mcp", {"measured": "x", "accepted": {}},
                        snapshot(surface("vault", 3001, probed=True, mcp="unknown")), "--json")
check("undeclared loopback MCP surface fails", code == 1 and kinds(rep) == ["undeclared"],
      f"exit={code} {kinds(rep)}")

# 4. Widening: the exposure may shrink, never grow.
base = {"measured": "x", "accepted": {"vault:3001": entry(bind="loopback", probed=True, mcp="unknown")}}
code, rep, out, _ = run("widen", base,
                        snapshot(surface("vault", 3001, wildcard=True, loopback=False,
                                         probed=True, mcp="unknown")), "--json")
check("loopback → wildcard fails", code == 1 and "bind" in kinds(rep), f"exit={code} {kinds(rep)}")

# 5. LAN reachability rising on an already-wildcard bind (a firewall rule went away).
base = {"measured": "x", "accepted": {"svc:7000": entry(bind="wildcard", lan_reachable=False)}}
snap = snapshot(surface("svc", 7000, wildcard=True, loopback=False))
code, rep, out, _ = run("lan", base, snap, "--json")
check("not-reachable → LAN-reachable fails", code == 1 and "lan" in kinds(rep),
      f"exit={code} {kinds(rep)}")

# 6. 🔴 The AC1b regression: a server that was gated starts serving tools/list unauthenticated.
base = {"measured": "x", "accepted": {"vault:3001": entry(probed=True, mcp="unknown")}}
code, rep, out, _ = run("auth", base,
                        snapshot(surface("vault", 3001, probed=True, mcp=True, tools_list=200,
                                         tools=("edit", "system"))), "--json")
check("gated → unauthenticated tools/list fails", code == 1 and "auth" in kinds(rep),
      f"exit={code} {kinds(rep)}")
check("...and the identification firming up is its own finding", "mcp" in kinds(rep), kinds(rep))

# 7. AC5's change detection: a NEW TOOL on an already-accepted server. The count alone hides this
#    when a tool is added and another removed, so names are compared, not lengths.
base = {"measured": "x", "accepted": {
    "inngest:4011": entry(status="known-open", bind="wildcard", lan_reachable=True, probed=True,
                          mcp=True, unauth_tools_list=200, tools=("read_doc", "send_event"))}}
code, rep, out, _ = run("tools", base,
                        snapshot(surface("inngest", 4011, wildcard=True, loopback=False, probed=True,
                                         mcp=True, tools_list=200,
                                         tools=("read_doc", "invoke_function"))), "--json")
check("a new tool name on an accepted server fails", code == 1 and "tools" in kinds(rep),
      f"exit={code} {kinds(rep)}")
check("...even though the tool COUNT is unchanged",
      rep and any("invoke_function" in str(x["detail"]) for x in rep["regressions"]), rep)

# 8. Known-open, unchanged: recorded so it cannot get worse, still reported, does not fail.
base = {"measured": "x", "accepted": {
    "inngest:4011": entry(status="known-open", bind="wildcard", lan_reachable=True, probed=True,
                          mcp=True, unauth_tools_list=200, tools=("read_doc", "send_event"))}}
snap = snapshot(surface("inngest", 4011, wildcard=True, loopback=False, probed=True, mcp=True,
                        tools_list=200, tools=("read_doc", "send_event")))
code, rep, out, _ = run("known-open", base, snap, "--json")
check("a known-open finding at baseline does not fail the ratchet", code == 0, f"exit={code}")
check("...but is still reported as open", rep and len(rep["known_open"]) == 1, rep)
check("...and the human report says so out loud", "known-open" in run("ko2", base, snap)[2].lower())

# 9. Ephemeral ports: `command:*` keys the surface by process, because rapportd picks new high
#    ports every boot and a port-keyed baseline would cry wolf every reboot.
base = {"measured": "x", "accepted": {"rapportd:*": entry(bind="wildcard", lan_reachable=True)}}
code, rep, out, _ = run("ephemeral", base,
                        snapshot(surface("rapportd", 61234, wildcard=True, loopback=False),
                                 surface("rapportd", 61235, wildcard=True, loopback=False)), "--json")
check("`command:*` accepts any port of that process", code == 0 and not rep["regressions"],
      f"exit={code} {kinds(rep)}")
code, rep, out, _ = run("ephemeral-mcp", base,
                        snapshot(surface("rapportd", 61234, wildcard=True, loopback=False,
                                         probed=True, mcp=True, tools_list=200, tools=("x",))),
                        "--json")
check("...but posture is still gated on it", code == 1 and "auth" in kinds(rep),
      f"exit={code} {kinds(rep)}")
# Found live, not by reading the code: several ports fold onto ONE `command:*` entry, so they must
# be merged BEFORE comparing. Comparing each port against the merged entry reports every quieter
# port as an improvement — on every run, forever — and `--save` then writes whichever port happened
# to be last. A gate that always says "you improved!" is a gate nobody reads.
fold_base = {"measured": "x", "accepted": {
    "rapportd:*": entry(bind="wildcard", lan_reachable=True, probed=False)}}
code, rep, out, _ = run("ephemeral-fold", fold_base,
                        snapshot(surface("rapportd", 61234, wildcard=True, loopback=False, lan=True),
                                 surface("rapportd", 61235, wildcard=True, loopback=False, lan=False),
                                 surface("rapportd", 61236, wildcard=True, loopback=False, lan=False)),
                        "--json")
check("ports folded onto one `command:*` entry produce no phantom improvement",
      code == 0 and not rep["improvements"] and not rep["regressions"],
      f"exit={code} imp={rep and rep['improvements']}")

# 10. Worst-wins across address families. `localhost` is 127.0.0.1 AND ::1 and a server can be
#     gated on one and open on the other; taking the first row seen reports the open one as gated.
base = {"measured": "x", "accepted": {"vault:3001": entry(probed=True, mcp="unknown")}}
code, rep, out, _ = run("family", base,
                        snapshot(surface("vault", 3001, addr="::1", probed=True, mcp="unknown"),
                                 surface("vault", 3001, addr="127.0.0.1", probed=True, mcp=True,
                                         tools_list=200, tools=("edit",))), "--json")
check("one open family makes the surface open, whatever order it is seen in",
      code == 1 and "auth" in kinds(rep), f"exit={code} {kinds(rep)}")
# The sharp case, found by mutation testing: the gated family answers a CODE (401), not nothing.
# A merge that only overwrites an empty slot keeps the 401 and reports the open server as gated —
# and the version above passes anyway, because `None` happens to be falsy in the right places.
base = {"measured": "x", "accepted": {
    "vault:3001": entry(probed=True, mcp=True, unauth_tools_list=401, tools=("edit",))}}
code, rep, out, _ = run("family-401", base,
                        snapshot(surface("vault", 3001, addr="::1", probed=True, mcp=True,
                                         tools_list=401, tools=("edit",)),
                                 surface("vault", 3001, addr="127.0.0.1", probed=True, mcp=True,
                                         tools_list=200, tools=("edit",))), "--json")
check("a 401 on one family does not mask a 200 on the other",
      code == 1 and "auth" in kinds(rep), f"exit={code} {kinds(rep)}")

# 11. Improvement path: shrinking is reported, never auto-saved.
base = {"measured": "x", "accepted": {
    "vault:3001": entry(bind="wildcard", lan_reachable=True, probed=True, mcp=True,
                        unauth_tools_list=200, tools=("edit", "system"))}}
snap = snapshot(surface("vault", 3001, probed=True, mcp="unknown"))
code, rep, out, bpath = run("improved", base, snap, "--json")
check("a tightened surface passes and is reported as an improvement",
      code == 0 and rep["improvements"], f"exit={code} {rep}")
check("...and the baseline file is NOT rewritten without --save",
      json.loads(bpath.read_text())["accepted"]["vault:3001"]["unauth_tools_list"] == 200)
code, rep, out, bpath = run("improved-save", base, snap, "--save")
saved = json.loads(bpath.read_text())["accepted"]["vault:3001"]
check("--save locks in the tightened posture",
      code == 0 and saved["unauth_tools_list"] is None and saved["bind"] == "loopback", saved)
check("--save preserves the human fields it has no business inventing",
      saved["reason"] == "declared for the test" and saved["status"] == "accepted", saved)

# 12. --save must never launder a regression, and must never invent an acceptance.
base = {"measured": "x", "accepted": {"vault:3001": entry(probed=True, mcp="unknown")}}
code, rep, out, bpath = run("save-regression", base,
                            snapshot(surface("vault", 3001, probed=True, mcp=True, tools_list=200,
                                             tools=("edit",))), "--save")
check("--save refuses while a regression stands", code == 1,
      f"exit={code}")
check("...and leaves the baseline untouched",
      json.loads(bpath.read_text())["accepted"]["vault:3001"]["mcp"] == "unknown")
code, rep, out, bpath = run("save-new", {"measured": "x", "accepted": {}},
                            snapshot(surface("mystery", 8099, wildcard=True, loopback=False)),
                            "--save")
check("--save does not accept an undeclared surface for you", code == 1
      and "mystery:8099" not in json.loads(bpath.read_text())["accepted"], out[-200:])
check("...it prints a paste-ready stanza with an empty reason instead", '"reason"' in out, out[-200:])

# 13. A declared surface that stopped listening is reported, not silently dropped — a laptop with
#     Docker closed must not quietly ratchet its own baseline away.
base = {"measured": "x", "accepted": {"gone:1234": entry(bind="wildcard", lan_reachable=True),
                                      "here:9000": entry(probed=True, mcp="unknown")}}
snap = snapshot(surface("here", 9000, probed=True, mcp="unknown"))
code, rep, out, bpath = run("absent", base, snap, "--json")
check("a declared-but-absent surface passes and is reported", code == 0 and rep["declared_absent"],
      f"exit={code} {rep}")
code, rep, out, bpath = run("absent-save", base, snap, "--save")
check("--save keeps absent entries (they come back when the app reopens)",
      "gone:1234" in json.loads(bpath.read_text())["accepted"])
code, rep, out, bpath = run("absent-prune", base, snap, "--save", "--prune")
check("--prune drops them, deliberately",
      "gone:1234" not in json.loads(bpath.read_text())["accepted"])

# 14. Vacuity guards. Every one of these is a way this gate could report green over nothing —
#     the failure mode this estate has now found five times.
code, rep, out, _ = run("vacuous", {"measured": "x", "accepted": {}}, snapshot(surface("vite", 4321)))
check("empty baseline + nothing tracked is exit 2, not a clean pass", code == 2, out[-160:])
code, rep, out, _ = run("no-detail", {"measured": "x", "accepted": {"a:1": entry()}},
                        {"listeners": 0, "surfaces": 0, "wildcard_binds": [], "detail": []})
check("a snapshot that enumerated nothing is exit 2", code == 2, out[-160:])
code, rep, out, _ = run("no-reason", {"measured": "x", "accepted": {"svc:1": {
    "status": "accepted", "reason": "", "bind": "loopback", "probed": True, "mcp": False,
    "unauth_tools_list": None, "tools": []}}}, snapshot(surface("svc", 1, probed=True, mcp="unknown")))
check("an accepted entry with no reason is exit 2 (a baseline without reasons is a rubber stamp)",
      code == 2, out[-160:])
code, rep, out, _ = run("bad-status", {"measured": "x", "accepted": {"svc:1": {
    **entry(), "status": "fine"}}}, snapshot(surface("svc", 1, probed=True, mcp="unknown")))
check("an unknown status value is exit 2, not treated as accepted", code == 2, out[-160:])

r = subprocess.run([sys.executable, str(SCRIPT), "--baseline", str(TMP / "nope.json"),
                    "--from-json", str(TMP / "scope-snapshot.json")], capture_output=True, text=True)
check("a missing baseline file is exit 2", r.returncode == 2, r.stderr[-160:])

print()
if failures:
    print(f"❌ {len(failures)} failure(s):")
    for f in failures:
        print(f"   · {f}")
    sys.exit(1)
print("✅ mcp-ratchet: all checks passed")
