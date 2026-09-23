#!/usr/bin/env python3
"""Render deploy_log rows into CHANGELOG.md, grouped by version (newest first).

Reads TSV on stdin (deployed_at<TAB>version<TAB>service<TAB>commit<TAB>actor)
or queries DATABASE_URL directly if stdin is not piped. Writes CHANGELOG.md in the cwd.
Part of the release-versioning change; run via `just changelog`.
"""

from __future__ import annotations

import os
import subprocess
import sys
from collections import OrderedDict

OUT = "CHANGELOG.md"


def fetch_rows_from_db(db_url: str) -> list[str]:
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
        if res.returncode == 0:
            return res.stdout.splitlines()
    except Exception:
        pass
    return []


def main() -> int:
    lines: list[str] = []
    if not sys.stdin.isatty():
        lines = [line.rstrip("\n") for line in sys.stdin]
    else:
        db_url = os.environ.get("DATABASE_URL")
        if db_url:
            lines = fetch_rows_from_db(db_url)
        else:
            print("DATABASE_URL not set and nothing on stdin", file=sys.stderr)
            return 1

    groups: OrderedDict[str, dict] = OrderedDict()
    for line in lines:
        if not line:
            continue
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        deployed_at, version, service = parts[0], parts[1], parts[2]
        commit = parts[3] if len(parts) > 3 else ""
        actor = parts[4] if len(parts) > 4 else ""
        g = groups.setdefault(version, {"first_seen": deployed_at, "rows": []})
        g["rows"].append((service, commit, actor, deployed_at))

    out = [
        "# Changelog",
        "",
        "_Generated from the `deploy_log` table by `just changelog`. "
        "Each heading is one deploy stamp (`YYYY.MM.DD-<unixtimestamp>`)._",
        "",
    ]
    for version, g in groups.items():
        out.append(f"## {version}")
        out.append(f"_First deployed: {g['first_seen']}_")
        out.append("")
        out.append("| Service | Commit | Actor | Deployed at |")
        out.append("|---|---|---|---|")
        for service, commit, actor, deployed_at in g["rows"]:
            out.append(f"| {service} | `{commit or '-'}` | {actor or '-'} | {deployed_at} |")
        out.append("")

    with open(OUT, "w", encoding="utf-8") as f:
        f.write("\n".join(out) + "\n")
    print(f"Wrote {OUT} ({len(groups)} version(s)).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
