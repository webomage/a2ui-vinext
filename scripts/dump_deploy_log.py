#!/usr/bin/env python3
"""Emit deploy_log rows as TSV for changelog generation.

Usage:
    python3 scripts/dump_deploy_log.py
"""

from __future__ import annotations

import os
import subprocess
import sys


def dump_rows(db_url: str) -> str:
    sql = (
        "SELECT deployed_at, version, service, COALESCE(commit,''), COALESCE(actor,'') "
        "FROM public.deploy_log ORDER BY deployed_at DESC LIMIT 500"
    )
    try:
        res = subprocess.run(
            ["psql", db_url, "-At", "-F", "\t", "-c", sql],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if res.returncode != 0:
            return ""
        return res.stdout
    except Exception:
        return ""


def main() -> int:
    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print("DATABASE_URL not set", file=sys.stderr)
        return 1

    rows = dump_rows(db_url)
    sys.stdout.write(rows)
    return 0


if __name__ == "__main__":
    sys.exit(main())
