#!/usr/bin/env python3
"""mcp_ratchet.py — the host's exposure may SHRINK, never grow. (T154 AC5 + AC7)

`just mcp-exposure` answers *"is anything open right now?"*. This answers a different question —
*"did it get WORSE than what we accepted?"* — and they need different exit codes, because the
first one is red today and will be red tomorrow for a surface that is somebody else's container.
A gate that is permanently red gets muted, and a muted gate is worse than no gate. So the open
finding is RECORDED as `known-open` and pinned: it may not gain a tool, a wider bind, or LAN
reachability without failing.

Modelled on `typecheck_ratchet.py` (T149), with three differences the security shape demands:

  1. **A new surface is never auto-accepted.** `--save` locks in an IMPROVEMENT on a surface you
     already declared; accepting a *new* one is a human edit with a written reason. A ratchet that
     accepts what it finds ratifies the breach it was meant to catch. It prints the stanza to paste.
  2. **Every entry carries a `reason`.** An accepted list without reasons is a rubber stamp, and
     the reason is what tells the next reader that `com.docke:4004` is a LAN-reachable Postgres.
  3. **`status` separates `accepted` from `known-open`.** Both are pinned; only the second is
     printed in red and counted in the summary, so recording a finding never launders it.

SCOPE — what counts as exposure (deliberately narrower than the inventory):
a surface is tracked when it is **not loopback-only**, or when the probe **identified MCP** (either
confirmed or auth-gated). A loopback listener that is not MCP is a dev server, and a ratchet that
fires when `pnpm dev` starts is one that gets muted. ⚠️ This means an MCP server that does not
speak HTTP (stdio, or another transport) is invisible here — a limit of the inventory, recorded
rather than papered over.

⚠️ **Worst-wins merge.** One server appears once per address family; `localhost` is `127.0.0.1`
AND `::1` and a server can be gated on one and open on the other. The merged posture takes the
WORST of the two — taking the first row seen reports an open server as gated.

⚠️ **`command:*` keys a surface by PROCESS, for ephemeral ports.** `rapportd` picks new high ports
every boot, so a port-keyed entry would cry wolf every reboot; the wildcard covers port identity
only — bind, auth and tool posture are still gated on it.

Exit: 0 at-or-below baseline · 1 exposure GREW (or `--save` refused to launder it) · 2 config /
parse / vacuous input.
Run: `just mcp-ratchet` · `just mcp-ratchet --save` · `just mcp-ratchet --json`
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "wom7web"
BASELINE = WEB / "project" / "mcp-exposure-baseline.json"

# Ordered risk ladders. Comparison is by RANK, never by equality: `loopback → host` is a widening
# even though both are "not wildcard", and `unknown → true` means auth stopped gating `initialize`.
BIND_RANK = {"loopback": 0, "host": 1, "wildcard": 2}
MCP_RANK = {False: 0, "unknown": 1, True: 2}
STATUSES = ("accepted", "known-open")


def posture_of(s: dict, lan: dict) -> dict:
    """One address:port row → its risk posture."""
    p = s.get("probe")
    wild = bool(s.get("wildcard"))
    return {"bind": "wildcard" if wild else ("loopback" if s.get("loopback") else "host"),
            "lan_reachable": lan.get((s["command"], s["port"])) if wild else None,
            # `probe` ABSENT means never asked (the surface does not speak HTTP); `probe: null`
            # means asked and not MCP. Conflating them turns a blind spot into a clean bill of health.
            "probed": bool(s.get("probed", "probe" in s)),
            "mcp": p.get("mcp", False) if p else False,
            "unauth_tools_list": p.get("unauth_tools_list") if p else None,
            "tools": sorted(set(p.get("tools") or [])) if p else [],
            "addrs": [s.get("addr")], "ports": [s["port"]]}


def merge(a: dict, b: dict) -> dict:
    """Worst-wins. Used for BOTH merges — the two address families of one server, and the several
    ephemeral ports behind one `command:*` entry. One definition, because the failure mode is the
    same both times: take the first row seen and an open server reports as gated."""
    tl_a, tl_b = a["unauth_tools_list"], b["unauth_tools_list"]
    return {"bind": max(a["bind"], b["bind"], key=lambda x: BIND_RANK[x]),
            "lan_reachable": True if (a["lan_reachable"] or b["lan_reachable"])
                             else (a["lan_reachable"] if a["lan_reachable"] is not None else b["lan_reachable"]),
            "probed": a["probed"] or b["probed"],
            "mcp": max(a["mcp"], b["mcp"], key=lambda x: MCP_RANK[x]),
            # 200 anywhere means the surface is open, whatever the other family answered. A merge
            # that only fills an EMPTY slot lets a 401 on ::1 mask a 200 on 127.0.0.1.
            "unauth_tools_list": 200 if 200 in (tl_a, tl_b) else (tl_a if tl_a is not None else tl_b),
            "tools": sorted(set(a["tools"]) | set(b["tools"])),
            "addrs": a["addrs"] + b["addrs"], "ports": sorted(set(a["ports"]) | set(b["ports"]))}


def postures(snap: dict) -> dict[str, dict]:
    """Collapse an `mcp-exposure --json` snapshot into one tracked posture per `command:port`."""
    lan = {(w.get("command"), w.get("port")): w.get("lan_reachable")
           for w in snap.get("wildcard_binds") or []}
    out: dict[str, dict] = {}
    for s in snap.get("detail") or []:
        if s.get("loopback") and not s.get("probe"):
            continue  # not exposure — see SCOPE above
        key = f"{s['command']}:{s['port']}"
        p = posture_of(s, lan)
        out[key] = merge(out[key], p) if key in out else p
    return out


def resolve(current: dict, accepted: dict) -> dict[str, dict]:
    """Fold the current surfaces onto the baseline key each one is compared against.

    Only `command:*` entries fold — several live ports behind one declared entry. Without this the
    ratchet compares each port against the merged entry and reports a phantom improvement on every
    port that is quieter than the worst one, forever. Undeclared surfaces stay separate: each new
    port is its own new exposure.
    """
    out: dict[str, dict] = {}
    for key in sorted(current):
        bkey, _ = declared_for(key, accepted)
        gkey = bkey if (bkey and bkey.endswith(":*")) else key
        out[gkey] = merge(out[gkey], current[key]) if gkey in out else current[key]
    return out


def declared_for(key: str, accepted: dict) -> tuple[str, dict] | tuple[None, None]:
    """Exact `command:port`, else the `command:*` ephemeral-port form."""
    if key in accepted:
        return key, accepted[key]
    command = key.rsplit(":", 1)[0]
    wild = f"{command}:*"
    if wild in accepted:
        return wild, accepted[wild]
    return None, None


def compare(accepted: dict, current: dict) -> dict:
    """Pure: baseline × snapshot → report. Every rule here has a red test in test_mcp_ratchet.py."""
    regressions, improvements, known_open, matched = [], [], [], set()

    for key in sorted(current):
        cur = current[key]
        bkey, base = declared_for(key, accepted)
        if base is None:
            regressions.append({"key": key, "kind": "undeclared", "detail": describe(cur),
                                "posture": cur})
            continue
        matched.add(bkey)
        if base.get("status") == "known-open":
            known_open.append({"key": key, "reason": base.get("reason", ""), "posture": cur})

        b_bind, c_bind = base.get("bind", "loopback"), cur["bind"]
        if BIND_RANK[c_bind] > BIND_RANK.get(b_bind, 0):
            regressions.append({"key": key, "kind": "bind",
                                "detail": f"bind widened {b_bind} → {c_bind}"})
        elif BIND_RANK[c_bind] < BIND_RANK.get(b_bind, 0):
            improvements.append({"key": key, "detail": f"bind narrowed {b_bind} → {c_bind}"})

        if cur["lan_reachable"] and not base.get("lan_reachable"):
            regressions.append({"key": key, "kind": "lan",
                                "detail": "now reachable from the LAN (was not)"})
        elif base.get("lan_reachable") and not cur["lan_reachable"]:
            improvements.append({"key": key, "detail": "no longer reachable from the LAN"})

        if MCP_RANK[cur["mcp"]] > MCP_RANK.get(base.get("mcp", False), 0):
            regressions.append({"key": key, "kind": "mcp",
                                "detail": f"protocol posture {base.get('mcp')!r} → {cur['mcp']!r} "
                                          f"(an unauthenticated `initialize` now succeeds)"})
        elif MCP_RANK[cur["mcp"]] < MCP_RANK.get(base.get("mcp", False), 0):
            improvements.append({"key": key, "detail": f"MCP posture {base.get('mcp')!r} → {cur['mcp']!r}"})

        if cur["unauth_tools_list"] == 200 and base.get("unauth_tools_list") != 200:
            regressions.append({"key": key, "kind": "auth",
                                "detail": "serves tools/list with NO credentials (was gated)"})
        elif base.get("unauth_tools_list") == 200 and cur["unauth_tools_list"] != 200:
            improvements.append({"key": key, "detail": "tools/list is gated again"})

        # Names, not lengths: swapping `read_doc` for `invoke_function` keeps the count and
        # changes the blast radius completely (AC5).
        new_tools = sorted(set(cur["tools"]) - set(base.get("tools") or []))
        gone_tools = sorted(set(base.get("tools") or []) - set(cur["tools"]))
        if new_tools:
            regressions.append({"key": key, "kind": "tools",
                                "detail": f"new tool(s) exposed: {', '.join(new_tools)}"})
        if gone_tools:
            improvements.append({"key": key, "detail": f"tool(s) gone: {', '.join(gone_tools)}"})

        # A surface that stopped answering the probe is not proof it is gated — it may just be
        # asleep. Reported as an improvement (it can only be locked in by a human running --save).
        if base.get("probed") and not cur["probed"]:
            improvements.append({"key": key, "detail": "no longer answers HTTP (unmeasured, not proven safe)"})

    absent = [{"key": k, "reason": v.get("reason", ""), "status": v.get("status")}
              for k, v in sorted(accepted.items()) if k not in matched]
    return {"regressions": regressions, "improvements": improvements, "known_open": known_open,
            "declared_absent": absent, "tracked": current}


def describe(p: dict) -> str:
    bits = [p["bind"]]
    if len(p.get("ports") or []) > 1:
        bits.insert(0, f"{len(p['ports'])} ports {min(p['ports'])}–{max(p['ports'])}")
    if p["lan_reachable"]:
        bits.append("LAN-reachable")
    if p["mcp"] is True:
        bits.append(f"MCP, {len(p['tools'])} tool(s)"
                    + (" UNAUTHENTICATED" if p["unauth_tools_list"] == 200 else ", gated"))
    elif p["mcp"] == "unknown":
        bits.append("auth-gated, protocol unknown")
    elif not p["probed"]:
        bits.append("does not speak HTTP — protocol UNMEASURED")
    return ", ".join(bits)


def stanza(key: str, p: dict) -> str:
    body = {"status": "accepted", "reason": "", "bind": p["bind"],
            "lan_reachable": p["lan_reachable"], "probed": p["probed"], "mcp": p["mcp"],
            "unauth_tools_list": p["unauth_tools_list"], "tools": p["tools"]}
    return f'    "{key}": ' + json.dumps(body, indent=6)[:-1] + "    }"


def validate(accepted: dict) -> str | None:
    """A malformed baseline must stop the run, not be half-read into a weaker gate."""
    for key, e in accepted.items():
        where = f"accepted[{key!r}]"
        if not isinstance(e, dict):
            return f"{where} is not an object"
        if e.get("status") not in STATUSES:
            return f"{where}.status is {e.get('status')!r} — must be one of {STATUSES}"
        if not str(e.get("reason") or "").strip():
            return (f"{where} has no reason. A baseline without reasons is a rubber stamp: the "
                    f"reason is what tells the next reader what this surface actually is.")
        if e.get("bind") not in BIND_RANK:
            return f"{where}.bind is {e.get('bind')!r} — must be one of {tuple(BIND_RANK)}"
        if e.get("mcp") not in MCP_RANK:
            return f"{where}.mcp is {e.get('mcp')!r} — must be true, false or \"unknown\""
        if not isinstance(e.get("tools"), list):
            return f"{where}.tools must be a list of tool NAMES"
    return None


def snapshot(from_json: str | None, all_ports: bool) -> dict:
    if from_json:
        try:
            return json.loads(Path(from_json).read_text(encoding="utf-8"))
        except (OSError, ValueError) as e:
            print(f"✗ mcp-ratchet: cannot read snapshot {from_json}: {e}", file=sys.stderr)
            sys.exit(2)
    import mcp_exposure  # same directory; imported so the measurement has exactly one definition
    return mcp_exposure.collect(all_ports=all_ports)


def evaluate(baseline_path: Path | None = None, from_json: str | None = None,
             all_ports: bool = False) -> dict:
    """Baseline × host → report, or `{"error": ...}`. The single entry point, so the CLI and
    `w0m_audit.py`'s standing sweep (T154 AC6) cannot drift into two different verdicts."""
    bpath = Path(baseline_path or BASELINE)
    if not bpath.is_file():
        return {"error": f"baseline {bpath} not found — refusing to run without one, because "
                         f"'no baseline' would read as 'nothing accepted' and fail everything."}
    try:
        data = json.loads(bpath.read_text(encoding="utf-8"))
    except ValueError as e:
        return {"error": f"{bpath} is not valid JSON: {e}"}
    accepted = data.get("accepted")
    if not isinstance(accepted, dict):
        return {"error": f"{bpath} has no `accepted` object"}
    bad = validate(accepted)
    if bad:
        return {"error": bad}

    snap = snapshot(from_json, all_ports)
    if not (snap.get("detail") or []):
        return {"error": "the snapshot enumerated no surfaces at all. That is a broken sweep, "
                         "not a clean host."}
    current = resolve(postures(snap), accepted)
    if not current and not accepted:
        # Nothing declared and nothing tracked: the gate would pass having compared nothing.
        return {"error": "no tracked surfaces AND an empty baseline — this run compared nothing "
                         "and its green would mean nothing. Check the snapshot."}
    return {**compare(accepted, current), "path": bpath, "data": data, "accepted": accepted,
            "measured": data.get("measured"), "surfaces": snap.get("surfaces")}


def main() -> int:
    ap = argparse.ArgumentParser(description="MCP/network exposure ratchet (T154 AC7)")
    ap.add_argument("--baseline", default=str(BASELINE))
    ap.add_argument("--from-json", help="compare a saved `mcp-exposure --json` snapshot "
                                        "instead of measuring the host now")
    ap.add_argument("--all-ports", action="store_true")
    ap.add_argument("--save", action="store_true", help="lock in improvements on DECLARED surfaces")
    ap.add_argument("--prune", action="store_true", help="with --save, drop declared surfaces that "
                                                         "are no longer listening")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    rep = evaluate(Path(args.baseline), args.from_json, args.all_ports)
    if "error" in rep:
        print(f"✗ mcp-ratchet: {rep['error']}", file=sys.stderr)
        return 2
    bpath, data, accepted, current = rep["path"], rep["data"], rep["accepted"], rep["tracked"]

    if args.json:
        print(json.dumps({"baseline": str(bpath), "measured": rep["measured"],
                          **{k: rep[k] for k in ("regressions", "improvements", "known_open",
                                                 "declared_absent", "tracked")}}, indent=2))
        return 1 if rep["regressions"] else 0

    print(f"▶ mcp-ratchet — {len(current)} tracked surface(s) vs {len(accepted)} declared "
          f"(baseline measured {rep['measured'] or '?'})")
    print(f"   scope: non-loopback binds + identified MCP surfaces. {rep.get('surfaces', '?')} "
          f"address:port surface(s) seen; loopback non-MCP listeners are not exposure.")

    if rep["known_open"]:
        print(f"\n  ── 🔴 KNOWN-OPEN ({len(rep['known_open'])}) — recorded so it cannot get WORSE. "
              f"Recorded is not fixed.")
        for k in rep["known_open"]:
            print(f"     🔴 {k['key']}  {describe(k['posture'])}")
            print(f"        {k['reason']}")

    if rep["regressions"]:
        print(f"\n  ── ❌ REGRESSIONS ({len(rep['regressions'])}) — exposure GREW")
        for r in rep["regressions"]:
            print(f"     ✗ {r['key']}  [{r['kind']}] {r['detail']}")
        undeclared = [r for r in rep["regressions"] if r["kind"] == "undeclared"]
        if undeclared:
            print("\n     To accept one deliberately, paste it into "
                  f"{bpath.name} → accepted and WRITE THE REASON:")
            for r in undeclared:
                print(stanza(r["key"], r["posture"]))

    if rep["improvements"]:
        print(f"\n  ── ✅ IMPROVEMENTS ({len(rep['improvements'])})")
        for i in rep["improvements"]:
            print(f"     ✅ {i['key']}  {i['detail']}")

    if rep["declared_absent"]:
        print(f"\n  ── · DECLARED, NOT LISTENING ({len(rep['declared_absent'])}) — kept; the app "
              f"may simply be closed. `--save --prune` drops them.")
        for a in rep["declared_absent"]:
            print(f"     · {a['key']}  ({a['status']})")

    if args.save:
        if rep["regressions"]:
            print("\n✗ mcp-ratchet: refusing to --save while exposure has GROWN. Close it, or "
                  "declare it by hand with a reason. --save locks in improvements; it does not "
                  "ratify findings.", file=sys.stderr)
            return 1
        for key, p in current.items():
            bkey, base = declared_for(key, accepted)
            if base is None:
                continue
            # Human fields are preserved: the tool measures posture, it does not decide policy.
            base.update({"bind": p["bind"], "lan_reachable": p["lan_reachable"],
                         "probed": p["probed"], "mcp": p["mcp"],
                         "unauth_tools_list": p["unauth_tools_list"], "tools": p["tools"]})
        if args.prune:
            for a in rep["declared_absent"]:
                accepted.pop(a["key"], None)
        data["accepted"] = accepted
        data["measured"] = _dt.date.today().isoformat()
        bpath.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"\n✅ baseline updated → {bpath}"
              + (f" ({len(rep['declared_absent'])} pruned)" if args.prune else ""))
        return 0

    if rep["regressions"]:
        print(f"\n❌ mcp-ratchet FAILED — {len(rep['regressions'])} regression(s). The accepted "
              f"exposure may shrink, never grow.")
        return 1
    if rep["improvements"]:
        print("\n✅ mcp-ratchet passed, and exposure SHRANK. Lock it in: `just mcp-ratchet --save`.")
        return 0
    tail = (f" {len(rep['known_open'])} known-open finding(s) remain open."
            if rep["known_open"] else "")
    print(f"\n✅ mcp-ratchet passed — no new exposure.{tail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
