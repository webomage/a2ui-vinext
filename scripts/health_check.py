#!/usr/bin/env python3
"""T22 AC3 — probe every deployed app's health endpoint and fail loudly on a bad one.

WHY THIS EXISTS
    T22 shipped the pre-deploy security gate (AC1/AC2) and then AC3 — "continuous /health
    monitoring + alerting" — sat open for three weeks with nothing checking anything. Model B
    (hooks + manual `just`, no CI) means the *manual* half has to exist before the continuous half
    is worth wiring: a cron that calls a probe nobody has ever run is two unknowns stacked.

🔴 THE PATH IN THE TICKET WAS WRONG, AND ONLY PROBING FOUND IT
    T22 and the release-versioning notes both talk about "app /health". Measured 2026-08-02:
      https://webomage.com/health      → 404
      https://api.webomage.com/health  → 000 (no connection)
      https://webomage.com/api/health  → 200
    The endpoints are at **`/api/health` on each app domain**. A monitor built on the recorded
    path would have alerted on 404s forever, or — worse, and far more likely — been "fixed" by
    someone relaxing it until it passed.

WHAT COUNTS AS HEALTHY
    200 + JSON + `status == "ok"` + a non-empty `version` and `commit`. The version fields are not
    decoration: a deploy that half-lands leaves an app answering 200 with a stale build, which is
    exactly the shape of the w0m-api/w0m-cf script collision that left 19 Workflows
    orphaned for two weeks while everything still returned 200 (T156).

DIVISION OF LABOUR — TWO HEALTH SURFACES, NO THIRD (T164 AC3)
    1. `just health-check` (`scripts/health_check.py`, T22 AC3 — THIS SCRIPT):
       Probes deployed Astro app `/api/health` endpoints (`web`, `cp`, `join`, `job`, `demo`) and
       verifies HTTP 200 + `status == "ok"` + non-empty build `version` and `commit`.
    2. `just health` / `just check-status` (`w0m-api/scripts/healthcheck.py`, T164 AC2):
       Full platform diagnostic dashboard — live CDN/Edge/Supabase/Workers SLA latency, deep
       recurrent dependencies, external API connectivity, AND Host CLI Toolchain Health (`T164`)
       read from `project/policies/tools-policy.json` via `scripts/tools_check.py`.

Run: `just health-check`   ·   `--json` for machine output (what the cron half will consume)
"""
from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request

# The deployed surface. Kept beside the probe rather than derived: there is no single registry of
# live app domains in the repo, and inventing one here would be a second source of truth. Adding an
# app means adding it here — visible in review, which is the point.
TARGETS = [
    ("web", "https://webomage.com/api/health"),
    ("cp", "https://cp.webomage.com/api/health"),
    ("join", "https://join.webomage.com/api/health"),
    ("job", "https://job.webomage.com/api/health"),
    ("demo", "https://demo.webomage.com/api/health"),
]
TIMEOUT = 15


def probe(name: str, url: str) -> dict:
    """Never raises. A probe that dies on the first bad target cannot report on the rest —
    the exact defect the wom7cfworkers cron had until 2026-08-01 (one throw killed every
    later call in the branch)."""
    out = {"service": name, "url": url, "ok": False, "status": None, "problem": None}

    # https ONLY, checked before the URL reaches urllib. urllib honours `file://`, so a target
    # entry typo'd (or edited) to `file:///etc/passwd` would be opened and its contents parsed
    # as a health payload. Flagged by semgrep `dynamic-urllib-use-detected`; fixed rather than
    # suppressed, because the risk is real even with a hardcoded list — the list is editable.
    if not url.startswith("https://"):
        out["problem"] = f"refusing non-https target: {url!r}"
        return out

    try:
        # Cloudflare answers the stock urllib User-Agent with 403/error 1010, which reads as a
        # dead app when the app is fine.
        req = urllib.request.Request(url, headers={"User-Agent": "curl/8.7.1"})
        if req.type != "https":  # belt and braces after any redirect-time rewrite
            out["problem"] = f"refusing non-https scheme: {req.type}"
            return out
        # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected -- scheme pinned to https above (both on the raw string and on req.type) and the target list is a module constant, so file:// cannot reach here; verified: probe('file:///etc/passwd') returns refused
        with urllib.request.urlopen(req, timeout=TIMEOUT) as r:
            out["status"] = r.status
            body = r.read(8192).decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        out["status"] = e.code
        out["problem"] = f"HTTP {e.code}"
        return out
    except Exception as e:  # noqa: BLE001 — DNS, TLS, timeout, connection refused
        out["problem"] = f"unreachable: {type(e).__name__}"
        return out

    if out["status"] != 200:
        out["problem"] = f"HTTP {out['status']}"
        return out
    try:
        data = json.loads(body)
    except json.JSONDecodeError:
        out["problem"] = "200 but body is not JSON"
        return out

    out["version"] = data.get("version")
    out["commit"] = data.get("commit")
    out["reported"] = data.get("status")
    if data.get("status") != "ok":
        out["problem"] = f"status={data.get('status')!r}"
    elif not data.get("version") or not data.get("commit"):
        # 200 + ok + no build identity = an app that cannot tell you WHICH build is answering.
        out["problem"] = "healthy but reports no version/commit"
    else:
        out["ok"] = True
    return out


def main() -> int:
    ap = argparse.ArgumentParser(
        description=(
            "Deployed-app /api/health & build-identity probe (T22 AC3, `just health-check`). "
            "For platform endpoint SLA latency and host CLI toolchain health (T164 AC2/AC3), "
            "use `just health` (`w0m-api/scripts/healthcheck.py`)."
        )
    )
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    # An empty target list must FAIL. "0 targets, 0 failures, all green" is the vacuous-pass
    # shape this estate keeps re-finding.
    if not TARGETS:
        print("❌ no health targets configured — refusing to report a healthy estate")
        return 2

    results = [probe(n, u) for n, u in TARGETS]
    bad = [r for r in results if not r["ok"]]

    if args.json:
        print(json.dumps({"ok": not bad, "results": results}, indent=2))
        return 1 if bad else 0

    print(f"\n▶ health — {len(results)} deployed app(s)")
    for r in results:
        if r["ok"]:
            print(f"  ✅ {r['service']:<6} {r['version']}  {r['commit']}")
        else:
            print(f"  ❌ {r['service']:<6} {r['problem']}  ({r['url']})")

    if bad:
        print(f"\n❌ {len(bad)} of {len(results)} unhealthy: "
              f"{', '.join(r['service'] for r in bad)}")
        return 1
    print(f"\n✅ all {len(results)} apps healthy and reporting a build identity")
    return 0


if __name__ == "__main__":
    sys.exit(main())
