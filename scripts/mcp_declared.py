#!/usr/bin/env python3
"""Declared-vs-listening reconciliation for the MCP inventory (T154 AC8).

`mcp_exposure.py` answers *"what is listening?"*. This answers the question the original finding
actually raised: **"is what is listening the same set as what we say we run?"** — an undeclared,
unauthenticated MCP with execution tools was found by hand, and nothing compared it to the
declared set.

WHY THE SCHEMA COMES FIRST
--------------------------
A declaration that does not say whether the server *listens* cannot be compared to a port scan at
all — the comparison is undefined, not merely noisy. Most declared servers are stdio and never
bind a port, so a naive `declared − listening` diff would report ~11 of 12 as missing on every
run, forever. This ticket already paid for that lesson in AC7, which split `mcp-ratchet` out of
`mcp-exposure` because *a gate that cannot be green gets muted*. Hence `transport`, and hence
three values rather than a boolean:

    stdio       launched as a subprocess — never listens, never comparable
    remote      a vendor-hosted endpoint (Cloudflare, Hostinger, …) — reachable over the internet
                but NOT a local listener, so a local port scan says nothing about it
    local-http  listens on THIS machine — the only comparable kind, and the only kind that can be
                the finding. Must record `bind` and `auth`.

`remote` exists because "http" alone is ambiguous: the Hostinger and Cloudflare connectors speak
HTTP, but to someone else's server. Folding them in with local listeners would have recreated the
same permanent-red problem one level down.

Kept free of network code so the tests are fixture-driven — a security gate whose tests depend on
what happens to be listening is a gate whose tests are a coin flip.
"""

from __future__ import annotations

import json
from pathlib import Path

TRANSPORTS = ("stdio", "remote", "local-http")
COMPARABLE = "local-http"


class DeclarationError(Exception):
    """The declared side could not be loaded or is not well-formed.

    Always fatal. A reconcile that loads no declarations would report zero undeclared listeners
    and exit clean — the most dangerous output this tool could produce.
    """


def load_declared(path: Path | str) -> dict[str, dict]:
    """Read `mcp.servers` and validate every entry. Raises DeclarationError, never returns empty."""
    path = Path(path)
    if not path.is_file():
        raise DeclarationError(f"declaration source not found: {path}")
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError) as e:
        raise DeclarationError(f"declaration source is malformed: {path} ({e})") from e

    servers = (cfg.get("mcp") or {}).get("servers")
    if servers is None:
        raise DeclarationError(f"no mcp.servers key in {path}")
    if not servers:
        raise DeclarationError(f"no declarations to reconcile against in {path}")

    for name, entry in servers.items():
        transport = entry.get("transport")
        if not transport:
            raise DeclarationError(
                f"declaration '{name}' records no transport — cannot be reconciled. "
                f"Add one of: {', '.join(TRANSPORTS)}")
        if transport not in TRANSPORTS:
            raise DeclarationError(
                f"declaration '{name}' has unknown transport '{transport}' — "
                f"expected one of: {', '.join(TRANSPORTS)}")
        if transport == COMPARABLE:
            missing = [k for k in ("bind", "auth") if not entry.get(k)]
            if missing:
                raise DeclarationError(
                    f"declaration '{name}' is {COMPARABLE} but records no "
                    f"{' or '.join(missing)} — a listening server must declare where it listens "
                    f"and whether it asks for credentials")
    return dict(servers)


def load_external(path: Path | str) -> dict[str, dict]:
    """Servers configured in machine-wide Claude config.

    In scope for REPORTING, never for ENFORCEMENT (decision recorded on T154 AC8). It holds most
    of the servers actually configured on this machine, so ignoring it would wrongly call them
    undeclared — but it is machine-wide, untracked, and contains other projects' servers, so
    treating it as authoritative would make a security check's result depend on which laptop ran
    it. A missing file is normal here, not an error.
    """
    path = Path(path)
    if not path.is_file():
        return {}
    try:
        cfg = json.loads(path.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return {}

    found: dict[str, dict] = {}
    for name in (cfg.get("mcpServers") or {}):
        found[name] = {"source": str(path), "scope": "global"}
    for proj, pcfg in (cfg.get("projects") or {}).items():
        for name in (pcfg.get("mcpServers") or {}):
            found.setdefault(name, {"source": str(path), "scope": f"project:{proj}"})
    return found


def norm_bind(value: str) -> str:
    """Canonical `host:port`, with IPv6 hosts bracketed.

    Without this an IPv6 surface renders `::1:4011` — which is not how anyone writes an IPv6 bind,
    and is genuinely ambiguous about where the host ends. A declaration using the conventional
    `[::1]:4011` then failed to match, and the server was reported BOTH as `declared, not
    listening` AND `listening, undeclared`: a double false positive on the direction that is
    supposed to be the security signal. Both spellings are accepted because the declaration is
    hand-written either way.
    """
    if not value:
        return ""
    value = value.strip()
    if value.startswith("["):  # already bracketed
        return value
    host, _, port = value.rpartition(":")
    if not host or not port.isdigit():
        return value
    return f"[{host}]:{port}" if ":" in host else f"{host}:{port}"


_LOOPBACK_HOSTS = {"127.0.0.1", "::1", "[::1]", "localhost"}


def _is_loopback(bind: str) -> bool:
    """True only for an unambiguously loopback bind. A wildcard (0.0.0.0, ::) is NOT loopback."""
    host = bind.rsplit(":", 1)[0] if bind.count(":") == 1 else bind.rpartition(":")[0]
    return host in _LOOPBACK_HOSTS


def _identity(s: dict) -> tuple[str, str]:
    """(bind, server-name) for a listening surface, as the reconcile matches on."""
    probe = s.get("probe") or {}
    bind = norm_bind(f"{s.get('addr')}:{s.get('port')}")
    return bind, (probe.get("server") or s.get("command") or "")


def reconcile(declared: dict[str, dict], external: dict[str, dict],
              surfaces: list[dict], all_listening: list[dict] | None = None) -> dict:
    """Compare declared against listening.

    `surfaces` are CONFIRMED-MCP entries only — that is deliberate and load-bearing for the
    `undeclared` class: every unrelated listening socket on the host would otherwise be reported
    as a rogue MCP server, which is noise that would get the gate ignored.

    `all_listening` is EVERY enumerated socket, and exists because presence and protocol are
    different questions. 🔴 Found 2026-08-05 (T169): with only `surfaces`, a declared `local-http`
    entry that is not itself an MCP server could NEVER match — the Headroom proxy was live on
    127.0.0.1:8787, answering HTTP 200, and the reconcile called it "declared, not listening",
    a message whose own docstring says "usually just stopped, does not fail". A false negative
    rendered as benign is worse than the vacuous reconcile this check was built to replace.

    Four outcomes, with different severities because the failure modes differ:
      undeclared  a live MCP exposure nobody wrote down — the finding class, and fails
      matched     declared, listening, and confirmed to speak MCP
      present     declared and something IS listening, but it did not answer as MCP. Expected for
                  a non-MCP local-http declaration (an LLM proxy); does not fail
      absent      declared and NOTHING is listening on that bind — usually just stopped
      external    explained by machine-wide config — reported, never fails
    """
    comparable = {n: e for n, e in declared.items()
                  if e.get("transport") == COMPARABLE and e.get("enabled", True)}
    not_comparable = sorted(n for n in declared if n not in comparable)

    # Group by (server, port) BEFORE classifying. One process listening on both address families
    # is one exposure, not two — `mcp_exposure` already dedupes wildcard binds per (command, port)
    # for exactly this reason, and counting per-address inflates "2 undeclared surfaces" out of a
    # single rogue server.
    # Key port is `int | None`, not `int`: it comes from `s.get("port")`, which genuinely
    # returns None for a surface with no port. Declaring `int` claimed a guarantee the
    # lookup does not make — and a wrong key type here would silently merge distinct
    # servers into one group, which is the opposite of what this grouping exists for (T188).
    groups: dict[tuple[str, int | None], dict] = {}
    for s in surfaces:
        bind, name = _identity(s)
        key = (name, s.get("port"))
        groups.setdefault(key, {"name": name, "bind": bind, "addrs": []})["addrs"].append(bind)

    matched, undeclared, ext_hits, seen = [], [], [], set()
    for (name, _port), g in groups.items():
        # Match on BIND ONLY. The server name arrives in the probe RESPONSE — it is asserted by
        # the listening process itself, so matching on it let an untrusted server choose the field
        # that decides whether it gets reported: anything answering to a declared name was waved
        # through on any port, including a wildcard, LAN-reachable one. The bind is observed by us
        # rather than claimed by it, so it is the only trustworthy key here.
        hit = next((n for n, e in comparable.items()
                    if norm_bind(e.get("bind", "")) in g["addrs"]), None)
        if hit:
            seen.add(hit)
            matched.append({"name": hit, **g})
        # Machine-wide config may EXPLAIN a surface, but it cannot make a wildcard bind
        # acceptable: a LAN-reachable MCP is an exposure regardless of who configured it, and
        # T154 was opened by exactly that shape. So `external` only ever covers loopback.
        elif name in external and all(_is_loopback(a) for a in g["addrs"]):
            ext_hits.append({**g, **external[name]})
        else:
            undeclared.append({**g, "name": name or "(unidentified)"})

    # Presence is decided against EVERY listening socket, not just MCP-confirmed ones.
    live_binds = {norm_bind(f"{s.get('addr')}:{s.get('port')}")
                  for s in (all_listening if all_listening is not None else surfaces)}
    present: list[dict] = []
    absent: list[dict] = []
    for n, e in comparable.items():
        if n in seen:
            continue
        b = norm_bind(e.get("bind", ""))
        (present if b in live_binds else absent).append({"name": n, "bind": b})

    return {
        "matched": matched,
        "undeclared": undeclared,
        "present": present,
        "absent": absent,
        "external": ext_hits,
        "comparable_count": len(comparable),
        "not_comparable": not_comparable,
        "not_comparable_count": len(not_comparable),
        # A reconcile with nothing comparable proved nothing. Recorded explicitly so the report
        # can say so: a blind spot must look different from a clean result.
        "vacuous": len(comparable) == 0,
        "exit_code": 1 if undeclared else 0,
    }


def render(r: dict) -> list[str]:
    """The human report block, returned as lines so the caller owns printing."""
    out = [f"\n  ── DECLARED vs LISTENING ({r['comparable_count']} comparable declaration(s)) — T154 AC8"]

    if r["vacuous"]:
        out.append("     ⚠️  compared NOTHING — no declaration is listening-capable, so this "
                   "reconcile proves nothing about exposure.")

    for m in r["undeclared"]:
        out.append(f"     🔴 listening, UNDECLARED  {m['bind']}  {m['name']}")
    for m in r["external"]:
        out.append(f"     🟡 declared-outside-the-repo  {m['bind']}  {m['name']} "
                   f"({m.get('scope', '?')} in {m.get('source', '?')})")
    for m in r.get("present", []):
        out.append(f"     ✅ declared + LISTENING (did not answer as MCP — expected for a "
                   f"non-MCP local-http surface)  {m['bind']}  {m['name']}")
    for m in r["absent"]:
        out.append(f"     🟡 declared, NOTHING listening on that bind  {m['bind']}  {m['name']}")
    for m in r["matched"]:
        out.append(f"     ✅ matched  {m['bind']}  {m['name']}")
    if not any((r["undeclared"], r["external"], r["absent"], r["matched"],
                r.get("present"))):
        out.append("     (nothing to compare)")

    # Named, not just counted: "12 declared, 2 matched" would otherwise read as ten missing.
    if r["not_comparable_count"]:
        out.append(f"     · {r['not_comparable_count']} declaration(s) excluded as not "
                   f"listening-capable (stdio/remote): {', '.join(r['not_comparable'])}")
    return out
