#!/usr/bin/env python3
"""T658 AC5 — Offline Tinybird ClickHouse surface drift & regional host gate.

Verifies:
1. Canonical Tinybird Forward SSOT (`w0m-web/lib/tinybird.ts`) and Python schema
   provisioner (`w0m-api/scripts/init_tinybird_schemas.py`) declare the exact same
   8 datasources and 6 SQL endpoint pipes.
2. Every cross-repo SDK copy (`w0m-api/src/lib/tinybird.ts`,
   `w0m-api/supabase/functions/_shared/tinybird.ts`, `w0m-cf/src/lib/tinybird.ts`)
   declares the exact same 8 datasources and 6 SQL endpoint pipes.
3. Every runtime `/v0/events?name=<ds>`, `OBSERVABILITY_LOGS_DATASOURCE`, and
   `/v0/pipes/<pipe>.json` reference across `w0m-web`, `w0m-api`, and `w0m-cf`
   resolves to a declared datasource or pipe (catching `marketJobs` camelCase or
   undeclared pipes like `observability_logs_query` before deploy).
4. Zero non-test runtime files across `w0m-web`, `w0m-api`, and `w0m-cf` hardcode
   the legacy EU host `https://api.tinybird.co`.
5. RED mutation probes prove undeclared datasources, undeclared pipes, and
   hardcoded `https://api.tinybird.co` strings are caught deterministically.
"""

from __future__ import annotations

import importlib.util
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "w0m-web"
API_ROOT = ROOT / "w0m-api"
CF_ROOT = ROOT / "w0m-cf"

EXPECTED_DATASOURCES = {
    "linkedin_analytics",
    "market_jobs",
    "worker_logs",
    "observability_logs",
    "agent_evaluations",
    "onboarding_funnel",
    "upwork_telemetry",
    "gamification_events",
}

EXPECTED_PIPES = {
    "top_linkedin_posts",
    "observability_logs_by_trace",
    "observability_logs_query",
    "observability_service_error_rates",
    "guardrail_hit_rate",
    "top_players_this_week",
}

DEFINE_DS_RE = re.compile(r'defineDatasource\(\s*["\']([a-zA-Z0-9_]+)["\']')
DEFINE_EP_RE = re.compile(r'defineEndpoint\(\s*["\']([a-zA-Z0-9_]+)["\']')
EVENTS_NAME_RE = re.compile(r"/v0/events\?name=([a-zA-Z0-9_]+)")
PIPE_JSON_RE = re.compile(r"/v0/pipes/([a-zA-Z0-9_]+)\.json")
OBS_CONST_RE = re.compile(r'OBSERVABILITY_LOGS_DATASOURCE\s*=\s*["\']([a-zA-Z0-9_]+)["\']')
EU_HOST_RE = re.compile(r'["\']https?://api\.tinybird\.co(?:["\'/])')


def _load_init_tinybird_module():
    mod_path = API_ROOT / "scripts" / "init_tinybird_schemas.py"
    spec = importlib.util.spec_from_file_location("init_tinybird_schemas_drift", mod_path)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def extract_sdk_definitions(source_text: str) -> tuple[set[str], set[str]]:
    datasources = set(DEFINE_DS_RE.findall(source_text))
    pipes = set(DEFINE_EP_RE.findall(source_text))
    return datasources, pipes


def scan_source_drift(
    rel_path: str,
    source_text: str,
    allowed_datasources: set[str],
    allowed_pipes: set[str],
) -> list[str]:
    findings: list[str] = []
    for ds in DEFINE_DS_RE.findall(source_text):
        if ds not in allowed_datasources:
            findings.append(f"{rel_path}: undeclared defineDatasource('{ds}')")
    for ds in EVENTS_NAME_RE.findall(source_text):
        if ds not in allowed_datasources:
            findings.append(f"{rel_path}: undeclared /v0/events?name={ds}")
    for ds in OBS_CONST_RE.findall(source_text):
        if ds not in allowed_datasources:
            findings.append(f"{rel_path}: undeclared OBSERVABILITY_LOGS_DATASOURCE='{ds}'")
    for pipe in DEFINE_EP_RE.findall(source_text):
        if pipe not in allowed_pipes:
            findings.append(f"{rel_path}: undeclared defineEndpoint('{pipe}')")
    for pipe in PIPE_JSON_RE.findall(source_text):
        if pipe not in allowed_pipes:
            findings.append(f"{rel_path}: undeclared /v0/pipes/{pipe}.json")
    if EU_HOST_RE.search(source_text):
        findings.append(f"{rel_path}: hardcoded legacy EU host https://api.tinybird.co")
    return findings


def iter_runtime_files() -> list[Path]:
    roots = [
        WEB_ROOT / "lib",
        WEB_ROOT / "packages" / "logger" / "src",
        WEB_ROOT / "apps" / "cp" / "src",
        API_ROOT / "src",
        API_ROOT / "supabase" / "functions",
        API_ROOT / "scripts",
        CF_ROOT / "src",
    ]
    collected: list[Path] = []
    for base in roots:
        if not base.exists():
            continue
        for path in sorted(base.rglob("*")):
            if not path.is_file():
                continue
            if path.suffix not in {".ts", ".js", ".mjs", ".py"}:
                continue
            parts = set(path.parts)
            if "__tests__" in parts or "tests" in parts or "node_modules" in parts:
                continue
            if path.name.endswith((".test.ts", ".spec.ts", "_test.py")) or path.name.startswith("test_"):
                continue
            collected.append(path)
    if (WEB_ROOT / "tinybird.config.mjs").is_file():
        collected.append(WEB_ROOT / "tinybird.config.mjs")
    return collected


class TestTinybirdSurfaceDrift(unittest.TestCase):
    def test_canonical_forward_ssot_and_python_provisioner_match(self) -> None:
        ssot_text = (WEB_ROOT / "lib" / "tinybird.ts").read_text(encoding="utf-8")
        ssot_ds, ssot_pipes = extract_sdk_definitions(ssot_text)
        self.assertEqual(ssot_ds, EXPECTED_DATASOURCES)
        self.assertEqual(ssot_pipes, EXPECTED_PIPES)
        self.assertIn('"timestamp + toIntervalDay(30)"', ssot_text)
        self.assertIn("ttl: OBSERVABILITY_LOGS_TTL_EXPRESSION", ssot_text)

        init_mod = _load_init_tinybird_module()
        py_ds = {item["name"] for item in init_mod.DATASOURCES}
        py_pipes = {item["name"] for item in init_mod.PIPES}
        self.assertEqual(py_ds, ssot_ds)
        self.assertEqual(py_pipes, ssot_pipes)

    def test_cross_repo_tinybird_sdk_modules_stay_in_parity(self) -> None:
        sdk_files = [
            API_ROOT / "src" / "lib" / "tinybird.ts",
            API_ROOT / "supabase" / "functions" / "_shared" / "tinybird.ts",
            CF_ROOT / "src" / "lib" / "tinybird.ts",
        ]
        for sdk_path in sdk_files:
            ds, pipes = extract_sdk_definitions(sdk_path.read_text(encoding="utf-8"))
            self.assertEqual(ds, EXPECTED_DATASOURCES, f"Datasource drift in {sdk_path}")
            self.assertEqual(pipes, EXPECTED_PIPES, f"Pipe drift in {sdk_path}")

    def test_wrangler_configs_declare_regional_tinybird_url(self) -> None:
        expected = "https://api.northamerica-northeast2.gcp.tinybird.co"
        for cfg in (API_ROOT / "wrangler.jsonc", CF_ROOT / "wrangler.jsonc"):
            text = cfg.read_text(encoding="utf-8")
            vars_keys = re.findall(r'^\s*"vars"\s*:', text, re.MULTILINE)
            self.assertEqual(
                len(vars_keys),
                1,
                f"Expected exactly 1 uncommented \"vars\" block in {cfg}, found {len(vars_keys)}",
            )
            self.assertIn('"TINYBIRD_URL"', text, f"Missing TINYBIRD_URL var in {cfg}")
            self.assertIn(expected, text, f"Missing Toronto GCP Tinybird URL in {cfg}")

    def test_runtime_callsites_have_zero_undeclared_surfaces_or_eu_hosts(self) -> None:
        all_findings: list[str] = []
        files = iter_runtime_files()
        self.assertGreater(len(files), 15)
        for fpath in files:
            rel = str(fpath.relative_to(ROOT))
            text = fpath.read_text(encoding="utf-8")
            all_findings.extend(
                scan_source_drift(rel, text, EXPECTED_DATASOURCES, EXPECTED_PIPES)
            )
        self.assertEqual(all_findings, [], "\n".join(all_findings))

    def test_red_probe_detects_undeclared_datasource_pipe_and_eu_host(self) -> None:
        synthetic = """
        const host = "https://api.tinybird.co/v0/events?name=marketJobs";
        const pipe = `${base}/v0/pipes/missing_shadow_pipe.json?limit=10`;
        """
        findings = scan_source_drift(
            "synthetic/bad-caller.ts",
            synthetic,
            EXPECTED_DATASOURCES,
            EXPECTED_PIPES,
        )
        self.assertEqual(len(findings), 3, findings)
        self.assertTrue(any("marketJobs" in f for f in findings))
        self.assertTrue(any("missing_shadow_pipe" in f for f in findings))
        self.assertTrue(any("api.tinybird.co" in f for f in findings))


if __name__ == "__main__":
    result = unittest.main(verbosity=2, exit=False).result
    sys.exit(0 if result.wasSuccessful() else 1)
