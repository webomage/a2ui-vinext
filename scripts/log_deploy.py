#!/usr/bin/env python3
"""Best-effort append to public.deploy_log table.

Tolerant: never fails a deploy if the table is missing (pre-migration)
or the DB is unreachable.

Usage:
    python3 scripts/log_deploy.py <service> <version> [commit] [actor]
"""

from __future__ import annotations

import os
import subprocess
import sys


def main() -> int:
    if len(sys.argv) < 3:
        print("Usage: log_deploy.py <service> <version> [commit] [actor]", file=sys.stderr)
        return 1

    service = sys.argv[1]
    version = sys.argv[2]
    commit = sys.argv[3] if len(sys.argv) > 3 else ""
    actor = sys.argv[4] if len(sys.argv) > 4 else ""

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print(f"⚠️  deploy_log insert skipped ({service} @ {version} — DATABASE_URL unset)")
        return 0

    # Sanitize inputs to prevent SQL injection in internal tooling
    clean_service = service.replace("'", "''")
    clean_version = version.replace("'", "''")
    clean_commit = commit.replace("'", "''")
    clean_actor = actor.replace("'", "''")

    sql = (
        "INSERT INTO public.deploy_log (service, version, commit, actor) "
        f"VALUES ('{clean_service}', '{clean_version}', '{clean_commit}', '{clean_actor}');"
    )

    try:
        res = subprocess.run(
            ["psql", db_url, "-v", "ON_ERROR_STOP=0", "-c", sql],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            timeout=10,
        )
        if res.returncode == 0:
            print(f"📝 deploy_log: {service} @ {version}")
        else:
            print(f"⚠️  deploy_log insert skipped ({service} @ {version} — table missing or DB unreachable)")
    except Exception as e:
        print(f"⚠️  deploy_log insert skipped ({service} @ {version} — {e})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
