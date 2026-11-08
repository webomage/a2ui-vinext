#!/usr/bin/env python3
"""Serve `w0m-pr/linuxontab` locally with COOP/COEP headers for `v86` SharedArrayBuffer (`T678`)."""

from __future__ import annotations

import argparse
import http.server
import os
from pathlib import Path
import socketserver
import sys

REPO_ROOT = Path(__file__).resolve().parent.parent


def resolve_linuxontab_dir() -> Path:
    env_override = os.environ.get("LINUXONTAB_ROOT", "").strip()
    if env_override:
        p = Path(env_override).expanduser().resolve()
        if p.exists():
            return p
    local_fork = REPO_ROOT / "w0m-pr" / "linuxontab"
    if local_fork.exists():
        return local_fork
    canonical_fork = Path("/home/aleksei/Projects/!self/w0m/w0m-pr/linuxontab")
    return canonical_fork


class CoopCoepHandler(http.server.SimpleHTTPRequestHandler):
    def end_headers(self) -> None:
        self.send_header("Cross-Origin-Opener-Policy", "same-origin")
        self.send_header("Cross-Origin-Embedder-Policy", "require-corp")
        self.send_header("Cache-Control", "no-store")
        super().end_headers()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Serve LinuxOnTab with COOP/COEP headers.")
    parser.add_argument("port", nargs="?", type=int, default=8770, help="Port to bind (default: 8770)")
    parser.add_argument("--module", default="hub", help="Initial @k7 module slug")
    parser.add_argument("--project", default="w0m", help="Active project tenant")
    parser.add_argument("--env", default="beta", help="Active Infisical environment")
    parser.add_argument("--dry-run", action="store_true", help="Print resolved URL and exit")
    args = parser.parse_args(argv)

    lot_dir = resolve_linuxontab_dir()
    url = (
        f"http://127.0.0.1:{args.port}/shell/"
        f"?autoboot=1&iso=alpine.iso&k7={args.module}&project={args.project}&env={args.env}"
    )
    print(f"LinuxOnTab Root : {lot_dir}")
    print(f"Active URL      : {url}")
    if args.dry_run:
        return 0
    if not lot_dir.exists():
        print(f"ERROR: LinuxOnTab checkout not found at {lot_dir}", file=sys.stderr)
        return 1

    os.chdir(lot_dir)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("127.0.0.1", args.port), CoopCoepHandler) as httpd:
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            return 0
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
