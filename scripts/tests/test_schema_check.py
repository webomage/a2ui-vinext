#!/usr/bin/env python3
"""T301 regression proof for project/scripts/schema_check.py (AC1-AC5).

Verifies that:
  1. Every config in the estate declaring a local `$schema` is discovered from the
     files themselves (not a hardcoded list) and validates with 0 errors.
  2. AC3 schemas (`hygiene-policy.schema.json`, `authz-allowlist.schema.json`) and
     AC4 schema (`.w0m/sdlc.schema.json`) exist, resolve, and reject invalid mutations.
  3. AC5 generic check (`check_all_schemas`) catches a deliberately broken
     `clients-policy.json` (tier key `'half-mananged'` outside the contract) and names
     both the key and `clients-policy.schema.json`.
  4. When `jsonschema` is unavailable, validation reports `skipped, not passed` /
     `unmeasurable, not passing` as an error rather than passing.

Run standalone: `just schema-check-test`
Run via pytest: `uv run pytest ../w0m-web/project/scripts/tests/test_schema_check.py`
"""
from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import mock

HERE = Path(__file__).resolve()
SCRIPTS_DIR = HERE.parents[1]
ESTATE_ROOT = HERE.parents[2]
WEB_ROOT = ESTATE_ROOT / "w0m-web"

if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import schema_check  # noqa: E402


def _write_variant(tmp_dir: Path, src_path: Path, schema_abs: Path, mutate_fn) -> tuple[Path, dict]:
    data = copy.deepcopy(schema_check.load_json_or_jsonc(src_path))
    assert isinstance(data, dict)
    data["$schema"] = str(schema_abs)
    mutate_fn(data)
    target = tmp_dir / src_path.name
    target.write_text(json.dumps(data, indent=2))
    return target, data


def run_all_probes() -> tuple[int, list[str]]:
    checks = 0
    fails: list[str] = []

    def check(label: str, cond: bool, detail: str = "") -> None:
        nonlocal checks
        checks += 1
        if not cond:
            fails.append(f"{label}{f' ({detail})' if detail else ''}")
        print(f"  {'✓' if cond else '✗'} {label}")

    print("\n  T301 — schema_check.py regression proof (AC1–AC5)\n")

    # 1. Live estate discovery & validation (AC3, AC4, AC5)
    valid_configs, errors = schema_check.check_all_schemas(ESTATE_ROOT)
    rels = {str(p.resolve().relative_to(ESTATE_ROOT.resolve())) for p in valid_configs}
    expected_configs = {
        ".w0m/sdlc.json",
        "project/policies/clients-policy.json",
        "project/policies/hygiene-policy.json",
        "project/policies/ide-policy.json",
        "project/policies/profiles-policy.json",
        "project/policies/skills-policy.json",
        "project/policies/stacks-policy.json",
        "w0m-web/project/authz-allowlist.jsonc",
        "w0m-web/project/client-profile.json",
    }
    check(
        "AC5: live estate discovers all 9 local-$schema configs dynamically and validates with 0 errors",
        errors == [] and expected_configs.issubset(rels),
        f"errors={errors}, missing={expected_configs - rels}",
    )

    # 2. Dynamic discovery proof (AC5): adding a new config in a temp tree is discovered automatically
    with tempfile.TemporaryDirectory(prefix="t301-disc-") as td:
        tmp = Path(td)
        schema_file = tmp / "sample.schema.json"
        schema_file.write_text(json.dumps({
            "$schema": "http://json-schema.org/draft-07/schema#",
            "type": "object",
            "required": ["$schema", "mode"],
            "properties": {
                "$schema": {"type": "string"},
                "mode": {"type": "string", "enum": ["strict"]},
            },
            "additionalProperties": False,
        }))
        cfg_ok = tmp / "sample.json"
        cfg_ok.write_text(json.dumps({"$schema": "./sample.schema.json", "mode": "strict"}))
        v_ok, e_ok = schema_check.check_all_schemas(tmp)
        check(
            "AC5: newly added config declaring local $schema is discovered without editing a list",
            len(v_ok) == 1 and e_ok == [],
        )

        # Break the file in the temp tree and verify check_all_schemas catches it
        cfg_ok.write_text(json.dumps({"$schema": "./sample.schema.json", "mode": "loose"}))
        v_bad, e_bad = schema_check.check_all_schemas(tmp)
        check(
            "AC5: breaking a discovered config causes check_all_schemas to fail",
            len(v_bad) == 0 and len(e_bad) == 1 and "sample.schema.json" in e_bad[0],
        )

        # Config naming a non-existent schema fails closed
        cfg_missing = tmp / "dangling.json"
        cfg_missing.write_text(json.dumps({"$schema": "./nonexistent.schema.json"}))
        _, e_dangling = schema_check.check_all_schemas(tmp)
        check(
            "AC5: config naming a non-existent $schema fails with 'schema that does not exist'",
            any("schema that does not exist" in e and "nonexistent.schema.json" in e for e in e_dangling),
        )

    # 3. Red probes on real estate schemas (AC1, AC3, AC4, AC5)
    with tempfile.TemporaryDirectory(prefix="t301-red-") as td:
        tmp = Path(td)

        # AC1 / AC5 DoD: clients-policy.json with unknown tier key 'half-mananged'
        clients_src = ESTATE_ROOT / "project" / "policies" / "clients-policy.json"
        clients_schema = ESTATE_ROOT / "project" / "policies" / "clients-policy.schema.json"
        bad_clients, bad_clients_doc = _write_variant(
            tmp,
            clients_src,
            clients_schema,
            lambda d: d["tiers"].__setitem__("half-mananged", d["tiers"]["half-managed"]),
        )
        errs_clients = schema_check.validate_declared_schema(bad_clients, bad_clients_doc)
        msg_clients = " | ".join(errs_clients)
        check(
            "AC1/AC5: broken clients-policy.json ('half-mananged' tier key) fails and names key + schema",
            bool(errs_clients) and "half-mananged" in msg_clients and "clients-policy.schema.json" in msg_clients,
            msg_clients,
        )

        # AC3: hygiene-policy.json with invalid first_party_license
        hygiene_src = ESTATE_ROOT / "project" / "policies" / "hygiene-policy.json"
        hygiene_schema = ESTATE_ROOT / "project" / "policies" / "hygiene-policy.schema.json"
        bad_hygiene, bad_hygiene_doc = _write_variant(
            tmp,
            hygiene_src,
            hygiene_schema,
            lambda d: d.__setitem__("first_party_license", "MIT"),
        )
        errs_hygiene = schema_check.validate_declared_schema(bad_hygiene, bad_hygiene_doc)
        msg_hygiene = " | ".join(errs_hygiene)
        check(
            "AC3: broken hygiene-policy.json (first_party_license='MIT') fails against hygiene-policy.schema.json",
            bool(errs_hygiene) and "hygiene-policy.schema.json" in msg_hygiene,
            msg_hygiene,
        )

        # AC3: authz-allowlist.jsonc with verdict='defect' missing required 'ticket'
        authz_src = WEB_ROOT / "project" / "authz-allowlist.jsonc"
        authz_schema = WEB_ROOT / "project" / "authz-allowlist.schema.json"
        bad_authz, bad_authz_doc = _write_variant(
            tmp,
            authz_src,
            authz_schema,
            lambda d: d["allow"].append({
                "table": "public.broken_probe",
                "cmd": "SELECT",
                "verdict": "defect",
                "shape": "admin-manage",
                "reason": "Deliberately missing the ticket key required when verdict is defect.",
            }),
        )
        errs_authz = schema_check.validate_declared_schema(bad_authz, bad_authz_doc)
        msg_authz = " | ".join(errs_authz)
        check(
            "AC3: broken authz-allowlist.jsonc (defect without ticket) fails against authz-allowlist.schema.json",
            bool(errs_authz) and "authz-allowlist.schema.json" in msg_authz and "ticket" in msg_authz,
            msg_authz,
        )

        # AC4: .w0m/sdlc.json missing state_surface.retention
        sdlc_src = ESTATE_ROOT / ".w0m" / "sdlc.json"
        sdlc_schema = ESTATE_ROOT / ".w0m" / "sdlc.schema.json"
        bad_sdlc, bad_sdlc_doc = _write_variant(
            tmp,
            sdlc_src,
            sdlc_schema,
            lambda d: d["state_surface"].pop("retention", None),
        )
        errs_sdlc = schema_check.validate_declared_schema(bad_sdlc, bad_sdlc_doc)
        msg_sdlc = " | ".join(errs_sdlc)
        check(
            "AC4: broken .w0m/sdlc.json (missing state_surface.retention) fails against sdlc.schema.json",
            bool(errs_sdlc) and "sdlc.schema.json" in msg_sdlc and "retention" in msg_sdlc,
            msg_sdlc,
        )

    # 4. Missing jsonschema dependency reports skipped/unmeasurable and fails closed (never passes)
    with mock.patch.dict(sys.modules, {"jsonschema": None}):
        sdlc_file = ESTATE_ROOT / ".w0m" / "sdlc.json"
        sdlc_doc = schema_check.load_json_or_jsonc(sdlc_file)
        errs_unavail = schema_check.validate_declared_schema(sdlc_file, sdlc_doc)
        v_unavail, e_unavail = schema_check.check_all_schemas(ESTATE_ROOT)
        check(
            "DoD: missing jsonschema reports 'skipped, not passed — unmeasurable, not passing' and fails closed",
            bool(errs_unavail)
            and "unmeasurable, not passing" in errs_unavail[0]
            and len(v_unavail) == 0
            and len(e_unavail) > 0,
        )

    # 5. CLI --file failure exits 1 and names key + schema
    with tempfile.TemporaryDirectory(prefix="t301-cli-") as td:
        tmp = Path(td)
        clients_src = ESTATE_ROOT / "project" / "policies" / "clients-policy.json"
        clients_schema = ESTATE_ROOT / "project" / "policies" / "clients-policy.schema.json"
        bad_cli, _ = _write_variant(
            tmp,
            clients_src,
            clients_schema,
            lambda d: d["tiers"].__setitem__("half-mananged", d["tiers"]["half-managed"]),
        )
        proc = subprocess.run(
            [sys.executable, str(SCRIPTS_DIR / "schema_check.py"), "--file", str(bad_cli)],
            capture_output=True,
            text=True,
        )
        out = proc.stdout + proc.stderr
        check(
            "DoD: CLI `schema_check.py --file <broken>` exits 1 and prints FAIL with key + schema",
            proc.returncode == 1 and "[FAIL]" in out and "half-mananged" in out and "clients-policy.schema.json" in out,
            out.strip(),
        )

    print(f"\n  {checks - len(fails)}/{checks} passed\n")
    return checks, fails


def test_schema_check_suite() -> None:
    _, fails = run_all_probes()
    assert not fails, f"schema_check probes failed: {fails}"


if __name__ == "__main__":
    _, failures = run_all_probes()
    if failures:
        for f in failures:
            print(f"    ✗ {f}")
        sys.exit(1)
