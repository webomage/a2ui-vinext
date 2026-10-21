#!/usr/bin/env python3
"""Best-effort append to public.deploy_log table (T421, T432 AC2/AC3).

Tolerant of DB unreachability or pre-migration schema, but FAILS CLOSED (exit 1)
if `outcome` or `trigger` is missing or not in the canonical enum:
  outcome: success | failed | rolled_back | hotfixed
  trigger: planned | incident

Usage:
    python3 scripts/log_deploy.py <service> <version> [commit] [actor] \
        [--outcome success|failed|rolled_back|hotfixed] \
        [--trigger planned|incident] \
        [--incident-ref INC-...]
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys

VALID_OUTCOMES: frozenset[str] = frozenset({"success", "failed", "rolled_back", "hotfixed"})
VALID_TRIGGERS: frozenset[str] = frozenset({"planned", "incident"})


def validate_deploy_metadata(
    outcome: str,
    trigger: str,
    incident_ref: str | None = None,
) -> tuple[str, str, str | None]:
    clean_outcome = outcome.strip()
    clean_trigger = trigger.strip()
    clean_ref = incident_ref.strip() if incident_ref and incident_ref.strip() else None

    if not clean_outcome or clean_outcome not in VALID_OUTCOMES:
        raise ValueError(
            f"Invalid or missing deploy outcome {outcome!r}; must be one of {sorted(VALID_OUTCOMES)}"
        )
    if not clean_trigger or clean_trigger not in VALID_TRIGGERS:
        raise ValueError(
            f"Invalid or missing deploy trigger {trigger!r}; must be one of {sorted(VALID_TRIGGERS)}"
        )
    return clean_outcome, clean_trigger, clean_ref


def build_insert_sql(
    service: str,
    version: str,
    commit: str,
    actor: str,
    outcome: str,
    trigger: str,
    incident_ref: str | None = None,
    *,
    legacy_schema: bool = False,
) -> str:
    clean_service = service.replace("'", "''")
    clean_version = version.replace("'", "''")
    clean_commit = commit.replace("'", "''")
    clean_actor = actor.replace("'", "''")
    if legacy_schema:
        return (
            "INSERT INTO public.deploy_log (service, version, commit, actor) "
            f"VALUES ('{clean_service}', '{clean_version}', '{clean_commit}', '{clean_actor}');"
        )
    val_outcome, val_trigger, val_ref = validate_deploy_metadata(outcome, trigger, incident_ref)
    ref_sql = f"'{val_ref.replace(chr(39), chr(39) * 2)}'" if val_ref else "NULL"
    return (
        "INSERT INTO public.deploy_log (service, version, commit, actor, outcome, trigger, incident_ref) "
        f"VALUES ('{clean_service}', '{clean_version}', '{clean_commit}', '{clean_actor}', "
        f"'{val_outcome}', '{val_trigger}', {ref_sql});"
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Append a deploy event to public.deploy_log.")
    parser.add_argument("service", nargs="?")
    parser.add_argument("version", nargs="?")
    parser.add_argument("commit", nargs="?", default="")
    parser.add_argument("actor", nargs="?", default="")
    parser.add_argument(
        "--outcome",
        default=os.environ.get("W0M_DEPLOY_OUTCOME", "success"),
        help="Deploy outcome: success | failed | rolled_back | hotfixed",
    )
    parser.add_argument(
        "--trigger",
        default=os.environ.get("W0M_DEPLOY_TRIGGER", "planned"),
        help="Deploy trigger: planned | incident",
    )
    parser.add_argument(
        "--incident-ref",
        default=os.environ.get("W0M_DEPLOY_INCIDENT_REF", ""),
        help="Optional incident ID (e.g. INC-2026-09-30-001)",
    )
    args = parser.parse_args(argv)

    if not args.service or not args.version:
        print(
            "Usage: log_deploy.py <service> <version> [commit] [actor] [--outcome ...] [--trigger ...] [--incident-ref ...]",
            file=sys.stderr,
        )
        return 1

    try:
        outcome, trigger, incident_ref = validate_deploy_metadata(
            str(args.outcome),
            str(args.trigger),
            str(args.incident_ref) if args.incident_ref else None,
        )
    except ValueError as err:
        print(f"❌ {err}", file=sys.stderr)
        return 1

    db_url = os.environ.get("DATABASE_URL")
    if not db_url:
        print(
            f"⚠️  deploy_log insert skipped ({args.service} @ {args.version} "
            f"[{outcome}/{trigger}] — DATABASE_URL unset)"
        )
        return 0

    sql = build_insert_sql(
        str(args.service),
        str(args.version),
        str(args.commit),
        str(args.actor),
        outcome,
        trigger,
        incident_ref,
    )

    try:
        res = subprocess.run(
            ["psql", db_url, "-v", "ON_ERROR_STOP=1", "-c", sql],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        if res.returncode == 0:
            ref_suffix = f" incident={incident_ref}" if incident_ref else ""
            print(f"📝 deploy_log: {args.service} @ {args.version} ({outcome}, {trigger}{ref_suffix})")
            return 0

        # Pre-migration tolerance if outcome/trigger columns are not yet applied via db-migrate
        if "column" in (res.stderr or "") and "does not exist" in (res.stderr or ""):
            legacy_sql = build_insert_sql(
                str(args.service),
                str(args.version),
                str(args.commit),
                str(args.actor),
                outcome,
                trigger,
                incident_ref,
                legacy_schema=True,
            )
            res_legacy = subprocess.run(
                ["psql", db_url, "-v", "ON_ERROR_STOP=0", "-c", legacy_sql],
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
                timeout=10,
            )
            if res_legacy.returncode == 0:
                print(f"📝 deploy_log: {args.service} @ {args.version} (legacy schema; run `just db-migrate` for T432 columns)")
                return 0

        print(f"⚠️  deploy_log insert skipped ({args.service} @ {args.version} — table missing or DB unreachable)")
    except Exception as e:
        print(f"⚠️  deploy_log insert skipped ({args.service} @ {args.version} — {e})")

    return 0


if __name__ == "__main__":
    sys.exit(main())
