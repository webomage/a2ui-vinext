#!/usr/bin/env python3
"""Deploy every edge function, then PROVE each one was updated — retrying only the ones that were not.

Why (2026-09-28, release 2026.09.28-1790652354): `supabase functions deploy --use-api -j 5` uploaded 58 functions and
Supabase's API answered `500 Function deploy failed due to an internal error` for 11 of them, with no function named.
No code, dependency or size pattern separated the 11 from the 47 that worked (checked), and the previous attempt had
zero 500s: a transient platform failure. The recipe had no retry, so one flaky upload failed the whole release and
left live MIXED — 47 functions at the new version, 11 at the old — with nothing saying which.

What this does instead:
  1. bulk deploy, exactly as before;
  2. ask the Management API when each function was last updated (read-only) and treat every repo function not
     updated since this run started as FAILED — whatever the CLI's exit code said (a silent partial deploy must
     not pass either);
  3. redeploy just those, fewer at a time, with backoff, up to ROUNDS times;
  4. still stale after that: exit 1 NAMING them, so a human sees exactly what is out of date. Never a silent pass.

Runs under `infisical run` (SUPABASE_ACCESS_TOKEN reaches it by process injection, as everywhere in this estate).
"""
from __future__ import annotations

import argparse
import http.client
import json
import os
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FUNCTIONS = ROOT / "w0m-api" / "supabase" / "functions"
ROUNDS = 3
BACKOFF_S = (20, 60, 120)
CLOCK_SKEW_S = 90      # local clock vs Supabase's: an update stamped this much before our start still counts as stale


def repo_functions() -> list[str]:
    """Deployable functions: a directory with an index.ts, not a `_shared`-style helper directory."""
    return sorted(d.name for d in FUNCTIONS.iterdir() if d.is_dir() and not d.name.startswith("_") and (d / "index.ts").exists())


def live_updated(project_ref: str, token: str) -> dict[str, float]:
    """slug -> seconds since epoch of its last update, from the Management API. Read-only."""
    conn = http.client.HTTPSConnection("api.supabase.com", timeout=30)
    try:
        conn.request("GET", f"/v1/projects/{project_ref}/functions", headers={"Authorization": f"Bearer {token}"})
        r = conn.getresponse()
        body = r.read()
    finally:
        conn.close()
    if r.status != 200:
        raise SystemExit(f"  ❌ cannot verify: Management API {r.status} listing functions: {body[:200]!r}")
    return {f["slug"]: f["updated_at"] / 1000.0 for f in json.loads(body)}


def stale(wanted: list[str], live: dict[str, float], started: float) -> list[str]:
    """Functions in `wanted` not updated since `started` (with clock-skew allowance). A missing one is stale too."""
    return [n for n in wanted if live.get(n, 0.0) < started - CLOCK_SKEW_S]


def deploy(names: list[str] | None, project_ref: str, jobs: int) -> int:
    cmd = ["supabase", "functions", "deploy", *(names or []), "--use-api", "-j", str(jobs), "--project-ref", project_ref]
    return subprocess.run(cmd, cwd=str(ROOT / "w0m-api"), check=False).returncode


def self_test() -> int:
    live = {"a": 1000.0, "b": 1900.0, "c": 2000.0}
    cases = [
        ("a function updated before the run started is stale", stale(["a"], live, 2000.0) == ["a"]),
        ("one updated after it started is not", stale(["c"], live, 1000.0) == []),
        ("a function missing from live is stale, not skipped", stale(["zzz"], live, 1000.0) == ["zzz"]),
        ("clock skew within the allowance is not stale", stale(["b"], live, 1950.0) == []),
        ("only the stale ones are returned, in order", stale(["a", "b", "c"], live, 1995.0) == ["a", "b"]),
        ("nothing wanted, nothing stale", stale([], live, 1000.0) == []),
    ]
    for n, ok in cases:
        print(f"  {'✅' if ok else '❌'} {n}")
    bad = sum(not ok for _, ok in cases)
    print(f"{len(cases) - bad}/{len(cases)} probes pass")
    return 1 if bad else 0


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--project-ref", help="Supabase project ref")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    token = os.environ.get("SUPABASE_ACCESS_TOKEN", "")
    if not a.project_ref or not token:
        print("  ❌ need --project-ref and SUPABASE_ACCESS_TOKEN (run under `infisical run`).")
        return 2
    wanted = repo_functions()
    if not wanted:
        print(f"  ❌ found no functions under {FUNCTIONS} — nothing to deploy is not a success.")
        return 2

    started = time.time()
    rc = deploy(None, a.project_ref, jobs=5)
    todo = stale(wanted, live_updated(a.project_ref, token), started)
    if rc != 0 and not todo:
        print("  ⚠️  the CLI reported failure but every function shows as updated on live — continuing.")
    for rnd in range(1, ROUNDS + 1):
        if not todo:
            break
        wait = BACKOFF_S[min(rnd - 1, len(BACKOFF_S) - 1)]
        print(f"  ↻ {len(todo)} of {len(wanted)} function(s) not updated: {' '.join(todo)}\n"
              f"    retry {rnd}/{ROUNDS} in {wait}s, 2 at a time", flush=True)
        time.sleep(wait)
        deploy(todo, a.project_ref, jobs=2)
        todo = stale(todo, live_updated(a.project_ref, token), started)
    if todo:
        print(f"  ❌ {len(todo)} function(s) STILL not updated after {ROUNDS} retries — live is MIXED: {' '.join(todo)}")
        return 1
    print(f"  ✅ all {len(wanted)} function(s) updated on live.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
