#!/usr/bin/env python3
"""Data-driven live verification helper replacing per-ticket verify_t44x scripts (T517 AC1, T518 AC4).

Expresses ticket live-verification probes (T440, T443, T444) as declarative check lists
evaluated over read-only SQL / `BEGIN ... SET LOCAL ROLE ... ROLLBACK` blocks via `authz_probe.run_sql`,
plus the configurable crawler worker enqueue smoke check (`crawler-smoke`, T518 AC4).

Usage:
    python3 scripts/live_verify_helper.py --help
    python3 scripts/live_verify_helper.py list
    python3 scripts/live_verify_helper.py t440
    python3 scripts/live_verify_helper.py t443
    python3 scripts/live_verify_helper.py t444
    python3 scripts/live_verify_helper.py crawler-smoke [--crawler-url URL]
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
import json
import os
from pathlib import Path
import sys
from typing import Any, Callable, cast
import urllib.error
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
WEB_SCRIPTS = ROOT / "w0m-web" / "project" / "scripts"
if str(WEB_SCRIPTS) not in sys.path:
    sys.path.insert(0, str(WEB_SCRIPTS))

import authz_probe as ap  # noqa: E402

ALEKSEI_ID = "8d16aff5-d996-4759-80b0-39b60e3c0920"
CASUALUSER_ID = "5691add5-48f9-4ac5-ab54-7ca5757e44da"
HOST_ORG_ID = "00000000-0000-0000-0000-000000000001"

LEADERSHIP_ID = "8129a1a0-8870-49b9-93d5-fe2e3d34e41b"
ENGINEERING_ID = "903a4879-b8f9-4841-bcd7-22eefd923946"
ELENA_UNIT_ID = "f84f7cad-bc19-46de-b397-ce9d1332cde3"
ALEKSEI_UNIT_ID = "cfb52773-75f8-4f54-8dfa-422b7785d4e8"

EXTERNAL_LINKS_REQUIRED_KEYS: tuple[str, ...] = (
    "github_url",
    "linkedin_url",
    "upwork_url",
    "telegram_url",
    "calendly_url",
    "job_board_url",
    "join_network_url",
    "custom_links",
)


@dataclass(frozen=True)
class CheckSpec:
    ticket: str
    check_id: str
    label: str
    sql: str
    evaluator: Callable[[str], tuple[bool, str]]
    role: str | None = None
    claims: dict[str, Any] | None = None

    def build_sql(self) -> str:
        if not self.role:
            return self.sql
        claims_sql = (
            f"SET LOCAL request.jwt.claims TO '{json.dumps(self.claims)}';\n"
            if self.claims is not None
            else ""
        )
        return f"BEGIN;\nSET LOCAL ROLE {self.role};\n{claims_sql}{self.sql}\nROLLBACK;\n"


def _eval_pipe_ints(min_expected: tuple[int, ...], exact: bool = False) -> Callable[[str], tuple[bool, str]]:
    def _fn(raw: str) -> tuple[bool, str]:
        pipe_lines = [ln.strip() for ln in (raw or "").strip().splitlines() if "|" in ln]
        if not pipe_lines:
            return False, f"no pipe-delimited row in output: {raw!r}"
        parts = [p.strip() for p in pipe_lines[-1].split("|")]
        if len(parts) != len(min_expected):
            return False, f"expected {len(min_expected)} columns, got {len(parts)}: {pipe_lines[-1]!r}"
        try:
            vals = tuple(int(x) for x in parts)
        except ValueError:
            return False, f"non-integer column values: {pipe_lines[-1]!r}"
        if exact:
            ok = vals == min_expected
            return ok, f"actual={vals} expected={min_expected}"
        ok = all(v >= exp for v, exp in zip(vals, min_expected))
        return ok, f"actual={vals} min_expected={min_expected}"

    return _fn


def _eval_int_min(minimum: int) -> Callable[[str], tuple[bool, str]]:
    def _fn(raw: str) -> tuple[bool, str]:
        nums = [ln.strip() for ln in (raw or "").strip().splitlines() if ln.strip().lstrip("-").isdigit()]
        if not nums:
            return False, f"no integer in output: {raw!r}"
        val = int(nums[-1])
        return val >= minimum, f"actual={val} min={minimum}"

    return _fn


def _eval_substrings(*needles: str) -> Callable[[str], tuple[bool, str]]:
    def _fn(raw: str) -> tuple[bool, str]:
        text = (raw or "").strip()
        missing = [n for n in needles if n not in text]
        return len(missing) == 0, f"missing={missing} raw={text!r}" if missing else text

    return _fn


def _eval_json_keys(required_keys: tuple[str, ...]) -> Callable[[str], tuple[bool, str]]:
    def _fn(raw: str) -> tuple[bool, str]:
        text = (raw or "").strip()
        if not text:
            return False, "empty output"
        try:
            parsed: Any = json.loads(text)
        except (ValueError, TypeError) as exc:
            return False, f"invalid JSON: {exc}"
        if not isinstance(parsed, dict):
            return False, f"expected JSON object, got {type(parsed).__name__}"
        missing = [k for k in required_keys if k not in parsed]
        return len(missing) == 0, f"missing keys: {missing}" if missing else "all required keys present"

    return _fn


def build_check_specs() -> dict[str, list[CheckSpec]]:
    aleksei_claims: dict[str, Any] = {
        "sub": ALEKSEI_ID,
        "email": "aleksei@webomage.com",
        "role": "authenticated",
        "wom_roles": ["member"],
        "wom_active_role": "member",
    }

    t440: list[CheckSpec] = [
        CheckSpec(
            ticket="t440",
            check_id="t440-ac1-aleksei-counts",
            label="T440 AC1: Aleksei profile row counts (contracts>=95, proposals>=1782, rooms>=55, messages>=170, tokens>=3)",
            sql=(
                "SELECT "
                f"(SELECT count(*) FROM public.contracts WHERE profile_id = '{ALEKSEI_ID}'::uuid), "
                f"(SELECT count(*) FROM public.proposals WHERE profile_id = '{ALEKSEI_ID}'::uuid), "
                f"(SELECT count(*) FROM public.platform_rooms WHERE profile_id = '{ALEKSEI_ID}'::uuid), "
                f"(SELECT count(*) FROM public.platform_messages WHERE profile_id = '{ALEKSEI_ID}'::uuid), "
                f"(SELECT count(*) FROM public.upwork_auth_tokens WHERE profile_id = '{ALEKSEI_ID}'::uuid);"
            ),
            evaluator=_eval_pipe_ints((95, 1782, 55, 170, 3), exact=False),
        ),
        CheckSpec(
            ticket="t440",
            check_id="t440-ac1-casualuser-zero",
            label="T440 AC1: old casualuser profile has 0 rows across all 5 tables",
            sql=(
                "SELECT "
                f"(SELECT count(*) FROM public.contracts WHERE profile_id = '{CASUALUSER_ID}'::uuid), "
                f"(SELECT count(*) FROM public.proposals WHERE profile_id = '{CASUALUSER_ID}'::uuid), "
                f"(SELECT count(*) FROM public.platform_rooms WHERE profile_id = '{CASUALUSER_ID}'::uuid), "
                f"(SELECT count(*) FROM public.platform_messages WHERE profile_id = '{CASUALUSER_ID}'::uuid), "
                f"(SELECT count(*) FROM public.upwork_auth_tokens WHERE profile_id = '{CASUALUSER_ID}'::uuid);"
            ),
            evaluator=_eval_pipe_ints((0, 0, 0, 0, 0), exact=True),
        ),
        CheckSpec(
            ticket="t440",
            check_id="t440-ac3-member-rls-counts",
            label="T440 AC3: signed-in member sees contracts>=95 and proposals>=1782 through RLS",
            sql=(
                "SELECT "
                "(SELECT count(*) FROM public.contracts), "
                "(SELECT count(*) FROM public.proposals);"
            ),
            role="authenticated",
            claims=aleksei_claims,
            evaluator=_eval_pipe_ints((95, 1782), exact=False),
        ),
        CheckSpec(
            ticket="t440",
            check_id="t440-ac5-host-org-contracts",
            label="T440 AC5: contracts linked to Webomage host_org_id >= 95",
            sql=f"SELECT count(*) FROM public.contracts WHERE host_org_id = '{HOST_ORG_ID}'::uuid;",
            evaluator=_eval_int_min(95),
        ),
    ]

    t443: list[CheckSpec] = [
        CheckSpec(
            ticket="t443",
            check_id="t443-ac1-elena-unit",
            label="T443 AC1: Elena unit is 'Co-founder, CFO & COO' in Leadership at sort_order 20",
            sql=(
                "SELECT title, squad, squad_id, sort_order, status "
                f"FROM public.units WHERE id = '{ELENA_UNIT_ID}'::uuid;"
            ),
            evaluator=_eval_substrings("Co-founder, CFO & COO", "Leadership", LEADERSHIP_ID, "|20|"),
        ),
        CheckSpec(
            ticket="t443",
            check_id="t443-ac1-aleksei-unit",
            label="T443 AC1: Aleksei unit is 'Co-founder, CEO & CTO' in Leadership at sort_order 10",
            sql=(
                "SELECT title, squad, squad_id, sort_order, status "
                f"FROM public.units WHERE id = '{ALEKSEI_UNIT_ID}'::uuid;"
            ),
            evaluator=_eval_substrings("Co-founder, CEO & CTO", "Leadership", LEADERSHIP_ID, "|10|"),
        ),
        CheckSpec(
            ticket="t443",
            check_id="t443-ac2-engineering-slot",
            label="T443 AC2: Engineering (Matrix) retains open slot 'Senior Fullstack Specialist (Hybrid) I' at sort_order 100",
            sql=(
                "SELECT title, squad_id, sort_order, status "
                f"FROM public.units WHERE squad_id = '{ENGINEERING_ID}'::uuid AND sort_order = 100;"
            ),
            evaluator=_eval_substrings("Senior Fullstack Specialist (Hybrid) I", "open"),
        ),
        CheckSpec(
            ticket="t443",
            check_id="t443-ac3-team-members-link",
            label="T443 AC3: both co-founders linked in team_members to Leadership units",
            sql=(
                "SELECT tm.name, tm.email, u.title, s.name AS squad_name, u.sort_order "
                "FROM public.team_members tm "
                "JOIN public.units u ON u.id = tm.unit_id "
                "JOIN public.squads s ON s.id = u.squad_id "
                f"WHERE tm.unit_id IN ('{ELENA_UNIT_ID}'::uuid, '{ALEKSEI_UNIT_ID}'::uuid) "
                "ORDER BY u.sort_order;"
            ),
            evaluator=_eval_substrings("Elena Shatalova", "Aleksei Tcelishchev"),
        ),
    ]

    t444: list[CheckSpec] = [
        CheckSpec(
            ticket="t444",
            check_id="t444-ac1-external-links-json",
            label="T444 AC1: site_settings.external_links contains all 8 required keys",
            sql="SELECT value FROM public.site_settings WHERE key = 'external_links';",
            evaluator=_eval_json_keys(EXTERNAL_LINKS_REQUIRED_KEYS),
        ),
        CheckSpec(
            ticket="t444",
            check_id="t444-ac3-anon-rls-read",
            label="T444 AC3: anon role can read site_settings.external_links under RLS",
            sql="SELECT count(*) FROM public.site_settings WHERE key = 'external_links';",
            role="anon",
            evaluator=_eval_int_min(1),
        ),
    ]

    return {"t440": t440, "t443": t443, "t444": t444}


def run_suite(
    suite_name: str,
    run_sql_fn: Callable[[str], str] = ap.run_sql,
) -> tuple[int, list[dict[str, Any]]]:
    specs_map = build_check_specs()
    if suite_name == "all":
        selected: list[CheckSpec] = [c for grp in specs_map.values() for c in grp]
    else:
        key = suite_name.removeprefix("verify-")
        if key not in specs_map:
            raise ValueError(f"Unknown suite {suite_name!r}; choose from {sorted(specs_map)} or 'all'")
        selected = specs_map[key]

    results: list[dict[str, Any]] = []
    failures = 0
    for spec in selected:
        raw = run_sql_fn(spec.build_sql())
        ok, detail = spec.evaluator(raw)
        if not ok:
            failures += 1
        results.append(
            {
                "ticket": spec.ticket,
                "id": spec.check_id,
                "label": spec.label,
                "ok": ok,
                "detail": detail,
            }
        )
    return (1 if failures else 0), results


def run_crawler_smoke(
    worker_url: str | None = None,
    post_fn: Callable[[str, dict[str, Any]], tuple[int, str]] | None = None,
) -> tuple[bool, str]:
    resolved_url = (
        worker_url
        or os.environ.get("CRAWLER_WORKER_URL")
        or os.environ.get("WORKERS_URL")
        or "https://webnames-crawler.webomage.workers.dev"
    ).rstrip("/")
    if not resolved_url.startswith(("https://", "http://")):
        return False, f"Invalid crawler worker URL scheme: {resolved_url!r}"

    payload: dict[str, Any] = {"urls": ["https://ycombinator.com", "https://www.webomage.com"]}
    target = f"{resolved_url}/enqueue"

    if post_fn is not None:
        status, body = post_fn(target, payload)
    else:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            target,
            data=data,
            headers={
                "Content-Type": "application/json",
                "User-Agent": "w0m-live-smoke/1.0",
            },
            method="POST",
        )
        try:
            # nosemgrep: python.lang.security.audit.dynamic-urllib-use-detected.dynamic-urllib-use-detected
            with urllib.request.urlopen(req, timeout=15) as resp:
                status = int(resp.getcode() or 0)
                body = resp.read().decode("utf-8", errors="replace")
        except urllib.error.HTTPError as exc:
            status = int(exc.code)
            body = exc.read().decode("utf-8", errors="replace")
        except OSError as exc:
            return False, f"Crawler smoke request failed ({target}): {exc}"

    ok = status == 200
    return ok, f"HTTP {status} from {target}: {body[:160]}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Declarative live-verification helper for T440, T443, T444, and crawler-smoke (T517 AC1, T518 AC4)."
    )
    parser.add_argument(
        "target",
        nargs="?",
        default="list",
        choices=[
            "list",
            "t440",
            "t443",
            "t444",
            "verify-t440",
            "verify-t443",
            "verify-t444",
            "all",
            "crawler-smoke",
        ],
        help="Verification check suite to run (default: list)",
    )
    parser.add_argument("--crawler-url", default=None, help="Override crawler worker URL for crawler-smoke")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")
    args = parser.parse_args(argv)

    specs_map = build_check_specs()
    if args.target == "list":
        if args.json:
            summary = {
                k: [{"id": c.check_id, "label": c.label, "role": c.role} for c in v]
                for k, v in specs_map.items()
            }
            print(json.dumps(summary, indent=2))
        else:
            for k, checks in specs_map.items():
                print(f"[{k}] ({len(checks)} checks)")
                for c in checks:
                    print(f"  - {c.check_id}: {c.label}")
        return 0

    if args.target == "crawler-smoke":
        ok, detail = run_crawler_smoke(worker_url=args.crawler_url)
        tag = "PASS" if ok else "FAIL"
        print(f"  [{tag}] crawler-smoke: {detail}")
        return 0 if ok else 1

    rc, results = run_suite(args.target)
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for r in results:
            tag = "PASS" if r["ok"] else "FAIL"
            print(f"  [{tag}] {r['label']} ({r['detail']})")
    return rc


if __name__ == "__main__":
    sys.exit(main())
