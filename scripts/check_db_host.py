#!/usr/bin/env python3
"""Pre-deploy check that the DATABASE HOST resolves and accepts a TCP connection (T542).

Usage:
    python3 scripts/check_db_host.py --host db.<project-ref>.supabase.co [--port 5432] [--timeout 5]

Why this exists: on 2026-10-03 a deploy passed its preflight and about 19 minutes of tests, then failed at `db-migrate` with "could not translate host name". The database host
has an AAAA record and no A record. The machine's resolver had stopped answering IPv6-only names (`getaddrinfo` failed for it and for any other AAAA-only name while `dig` still
answered, a TCP connect to the address still worked, and WARP still said Connected). The old preflight ran `curl -6 https://cloudflare.com`, a dual-stack site and a connection
test, and when that failed printed "no IPv6 - advisory only, the deploy path is IPv4", which is false for the database. A check has to ask the question the failing step asks.

This asks it: `socket.getaddrinfo(host, port)`, the call psql and Python make, then a plain TCP connect to each answer.

  stage resolve  the resolver gave no answer. Not a network outage: the route usually still works. Known cause on this machine: macOS stops resolving IPv6-only names while no
                 IPv6 service is registered. Fix: reconnect WARP (`warp-cli disconnect` then `warp-cli connect`, or toggle it in the app), then re-run.
  stage connect  the name resolves but no address accepted a connection within the timeout.

Output carries address FAMILIES, never an address, and never the text of an unexpected error (only its type). Any unexpected error is a failure (fail closed).
Exit 0 ok, 1 check failed, 2 bad arguments.
"""
from __future__ import annotations

import argparse
import re
import socket
import sys
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

DEFAULT_PORT = 5432
DEFAULT_TIMEOUT = 5.0
DEFAULT_RESOLVER = socket.getaddrinfo
MAX_TIMEOUT = 60.0
_LABEL = re.compile(r"^[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?$")

FIX = "reconnect WARP (`warp-cli disconnect`, then `warp-cli connect`, or toggle it in the app), then re-run"
RESOLVE_MESSAGE = (
    "the system resolver (getaddrinfo, the call psql makes) cannot resolve {host}. This is a resolver failure, not a network outage: the route usually still works. "
    "Known cause on this machine: macOS stops resolving IPv6-only names while no IPv6 service is registered, even though WARP says Connected (LESSONS.md, 2026-10-03). Fix: " + FIX + "."
)
CONNECT_MESSAGE = "{host} resolves ({families}) but no address accepted a TCP connection on port {port} within {timeout:g}s. Check WARP and the network, then re-run."


@dataclass
class Result:
    ok: bool
    stage: str
    message: str
    families: list[str] = field(default_factory=list)


def valid_host(host: Any) -> str:
    """A bare hostname: letters, digits, dots and hyphens in labels of 1 to 63 characters, at most 253 in all. Anything else (a URL, a port, a path) is refused."""
    if not isinstance(host, str) or len(host) > 253:
        raise ValueError("host must be a bare hostname")
    if not all(_LABEL.fullmatch(label) for label in host.split(".")):
        raise ValueError("host must be a bare hostname")
    return host


def family_name(family: int) -> str:
    return {socket.AF_INET6: "IPv6", socket.AF_INET: "IPv4"}.get(family, "other")  # type: ignore[call-overload]


def tcp_connect(address: tuple[Any, ...], timeout: float, family: int = socket.AF_INET) -> None:
    s = socket.socket(family, socket.SOCK_STREAM)
    try:
        s.settimeout(timeout)
        s.connect(address)
    finally:
        s.close()


def check(host: str, port: int, timeout: float, resolver: Callable[..., Any] = DEFAULT_RESOLVER,
          connector: Optional[Callable[..., None]] = None) -> Result:
    try:
        answers = resolver(host, port, 0, socket.SOCK_STREAM)
    except socket.gaierror:
        return Result(False, "resolve", RESOLVE_MESSAGE.format(host=host))
    except Exception as e:  # noqa: BLE001 - anything else from the resolver is still a failure; only its type is ever shown, never its text
        return Result(False, "resolve", RESOLVE_MESSAGE.format(host=host) + f" (the resolver raised {type(e).__name__})")
    if not answers:
        return Result(False, "resolve", RESOLVE_MESSAGE.format(host=host))
    families = [family_name(a[0]) for a in answers]
    connect = connector or tcp_connect
    for fam, _type, _proto, _canon, sockaddr in answers:
        try:
            if connector is None:
                connect(sockaddr, timeout, family=fam)
            else:
                connect(sockaddr, timeout)
        except Exception:  # noqa: BLE001 - connect refused, timeout, no route or anything unexpected: try the next address, never print the error text
            continue
        return Result(True, "ok", f"{host} resolves ({', '.join(families)}) and accepts a TCP connection on port {port}", families)
    return Result(False, "connect", CONNECT_MESSAGE.format(host=host, families=", ".join(families), port=port, timeout=timeout), families)


def main(argv: Optional[list[str]] = None, resolver: Callable[..., Any] = DEFAULT_RESOLVER, connector: Optional[Callable[..., None]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--host", required=True)
    ap.add_argument("--port", type=int, default=DEFAULT_PORT)
    ap.add_argument("--timeout", type=float, default=DEFAULT_TIMEOUT)
    a = ap.parse_args(argv)
    try:
        host = valid_host(a.host)
    except ValueError:
        print("refused: --host must be a bare hostname (no scheme, credentials, port or path)", file=sys.stderr)
        return 2
    if not 1 <= a.port <= 65535 or not 0 < a.timeout <= MAX_TIMEOUT:
        print("refused: --port must be 1..65535 and --timeout 0..60 seconds", file=sys.stderr)
        return 2
    r = check(host, a.port, a.timeout, resolver, connector)
    print(f"  ✅ OK {r.message}" if r.ok else f"❌ FAIL [{r.stage}] {r.message}")
    return 0 if r.ok else 1


if __name__ == "__main__":
    sys.exit(main())
