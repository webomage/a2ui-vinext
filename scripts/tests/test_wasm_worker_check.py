#!/usr/bin/env python3
"""T273 AC1–AC7 — Unit and red-probe regression tests for `scripts/wasm_worker_check.py`."""

from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import wasm_worker_check as wwc  # noqa: E402


def test_live_estate_wasm_worker_check_passes() -> None:
    """Verify the real estate configuration, crate, WASM binary, bundle budget, and AgDR-0044 pass."""
    rc = wwc.main(["--check"])
    assert rc == 0


def test_deterministic_wasm_binary_matches_committed_pkg() -> None:
    """Verify `pkg/w0m_wasm_utils.wasm` is byte-identical to the deterministic emitter."""
    expected = wwc.build_deterministic_wasm_bytes()
    actual = wwc.WASM_BIN_PATH.read_bytes()
    assert actual == expected
    assert len(actual) == 550

    parsed = wwc.parse_wasm_binary(actual)
    assert parsed["valid_header"] is True
    assert parsed["error"] is None
    for exp_name in ("memory", "fnv1a64", "levenshtein_distance", "score_token_overlap"):
        assert exp_name in parsed["exports"]


def test_bundle_budget_measurement_and_red_probe_on_free_tier_breach() -> None:
    """AC2: Verify bundle measurement is well under 1 MiB Free limit and fails closed above 85%."""
    live = wwc.measure_bundle_budget()
    assert live["ok"] is True
    assert live["wasm_raw_bytes"] == 550
    assert live["wasm_gzip_bytes"] == 389
    assert live["combined_gzip_bytes"] < wwc.CF_FREE_BUDGET_CEILING_BYTES
    assert live["pushes_to_paid_tier"] is False

    # RED probe: set Free tier limit tiny (1,000 B) so the bundle breaches the 85% ceiling
    breach = wwc.measure_bundle_budget(free_limit_bytes=1000, budget_ratio=0.85)
    assert breach["ok"] is False
    assert any("85% Free-tier safety ceiling" in p for p in breach["problems"])


def test_ac1_toolchain_policy_red_probes() -> None:
    """AC1: Missing `wasm-pack`/`worker-build` or missing `wasm-worker` stack fails closed."""
    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        bad_tools = tdir / "tools-policy.json"
        bad_stacks = tdir / "stacks-policy.json"
        bad_suites = tdir / "test-suites.json"

        bad_tools.write_text(json.dumps({"tools": {"rustup": {"note": "no wasm target"}}}), encoding="utf-8")
        bad_stacks.write_text(json.dumps({"stacks": {}}), encoding="utf-8")
        bad_suites.write_text(json.dumps({"suites": []}), encoding="utf-8")

        res = wwc.check_toolchain_policies(
            tools_policy_path=bad_tools,
            stacks_policy_path=bad_stacks,
            suites_path=bad_suites,
        )
        assert res["ok"] is False
        joined = "\n".join(res["problems"])
        assert "wasm-pack" in joined
        assert "worker-build" in joined
        assert "wasm32-unknown-unknown" in joined
        assert "wasm-worker" in joined
        assert "wasm-worker-check" in joined


def test_ac3_crate_lint_and_wasm_abi_red_probes() -> None:
    """AC3: Verify `#![no_std]` removal, `use std::` import, or corrupted WASM magic fails closed."""
    with tempfile.TemporaryDirectory() as tmp:
        tdir = Path(tmp)
        bad_toml = tdir / "Cargo.toml"
        bad_rs = tdir / "lib.rs"
        bad_wasm = tdir / "bad.wasm"

        bad_toml.write_text('[package]\nname = "wrong"\n', encoding="utf-8")
        bad_rs.write_text("use std::collections::HashMap;\npub fn hello() {}\n", encoding="utf-8")
        bad_wasm.write_bytes(b"NOT_WASM_BYTES")

        res = wwc.check_crate_lint_and_abi(
            cargo_toml_path=bad_toml,
            lib_rs_path=bad_rs,
            wasm_path=bad_wasm,
        )
        assert res["ok"] is False
        joined = "\n".join(res["problems"])
        assert "#![no_std]" in joined
        assert "must not import `std::`" in joined
        assert "Invalid WASM magic" in joined


def test_ac5_ac7_agdr_boundary_red_probe() -> None:
    """AC5 & AC7: Verify AgDR-0044 check fails if ZeroClaw 31.7 MB or 4th-language cost is omitted."""
    with tempfile.TemporaryDirectory() as tmp:
        bad_agdr = Path(tmp) / "AgDR-0044.md"
        bad_agdr.write_text("---\nid: AgDR-0044\nstatus: accepted\nticket: T273\n---\n", encoding="utf-8")
        res = wwc.check_agdr_boundary_doc(agdr_path=bad_agdr)
        assert res["ok"] is False
        joined = "\n".join(res["problems"])
        assert "ZeroClaw" in joined
        assert "31,699,216" in joined
        assert "fourth" in joined
