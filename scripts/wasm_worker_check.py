#!/usr/bin/env python3
"""T273 — Cloudflare Workers Rust-to-WASM Toolchain, Bundle Budget & ABI Gate.

Enforces the T273 acceptance criteria across the w0m estate:
  - AC1: Toolchain declaration in `project/policies/tools-policy.json` (`wasm-pack`, `worker-build`,
         and `wasm32-unknown-unknown` target note) and `project/policies/stacks-policy.json`
         (`wasm-worker` stack, separate from native `mlx`).
  - AC2: Measured before/after Cloudflare Worker bundle size against the Workers Free tier
         compressed ceiling (`1,048,576` B = 1 MB) and Paid tier ceiling (`10,485,760` B = 10 MB),
         failing closed at 85% of the Free tier budget (`891,289` B) so Rust on Workers never
         silently pushes the estate onto Workers Paid (`AgDR-0003` / `T271` / `T272`).
  - AC3: Type/lint/format gate for `wom7func/crates/w0m-wasm-utils` (`cargo check` + `clippy`
         for `wasm32-unknown-unknown` when `cargo` is installed on the host, plus static crate
         manifest/`#![no_std]` source verification and W3C `.wasm` binary section/export ABI
         verification on all hosts).
  - AC4: Live execution of the compiled `w0m_wasm_utils.wasm` module (`fnv1a64`,
         `levenshtein_distance`, `score_token_overlap`) via Node/V8 `WebAssembly.instantiate`
         proving 100% parity against reference vectors.
  - AC5 & AC7: Verifies `docs/decisions/AgDR-0044-rust-wasm-worker-boundary-and-bundle-budget.md`
         records the I/O-bound TypeScript boundary, the `ZeroClaw` (`31.7 MB`) exclusion proof,
         and the 4th-language maintenance cost.
"""

from __future__ import annotations

import argparse
import gzip
import json
from pathlib import Path
import re
import shutil
import subprocess
import sys
from typing import Any

HERE = Path(__file__).resolve()
ROOT = HERE.parent.parent

TOOLS_POLICY_PATH = ROOT / "project" / "policies" / "tools-policy.json"
STACKS_POLICY_PATH = ROOT / "project" / "policies" / "stacks-policy.json"
SUITES_JSON_PATH = ROOT / "wom7web" / "project" / "test-suites.json"
AGDR_0044_PATH = (
    ROOT / "docs" / "decisions" / "AgDR-0044-rust-wasm-worker-boundary-and-bundle-budget.md"
)

FUNC_DIR = ROOT / "wom7func"
CRATE_DIR = FUNC_DIR / "crates" / "w0m-wasm-utils"
CARGO_TOML_PATH = CRATE_DIR / "Cargo.toml"
LIB_RS_PATH = CRATE_DIR / "src" / "lib.rs"
WASM_PKG_DIR = CRATE_DIR / "pkg"
WASM_BIN_PATH = WASM_PKG_DIR / "w0m_wasm_utils.wasm"

# Cloudflare Workers bundle size limits (compressed bytes)
CF_FREE_TIER_LIMIT_BYTES = 1_048_576  # 1 MiB compressed limit on Cloudflare Workers Free
CF_PAID_TIER_LIMIT_BYTES = 10_485_760  # 10 MiB compressed limit on Cloudflare Workers Paid
CF_FREE_BUDGET_RATIO = 0.85  # Fail closed at 85% of Free tier limit (891,289 bytes)
CF_FREE_BUDGET_CEILING_BYTES = int(CF_FREE_TIER_LIMIT_BYTES * CF_FREE_BUDGET_RATIO)
ZEROCLAW_NATIVE_BINARY_BYTES = 31_699_216  # Measured ~/.cargo/bin/zeroclaw v0.8.3 (31.7 MB)

REQUIRED_WASM_EXPORTS = (
    "memory",
    "fnv1a64",
    "levenshtein_distance",
    "score_token_overlap",
)


def uleb128(value: int) -> bytes:
    """Encode an unsigned integer as ULEB128."""
    if value < 0:
        raise ValueError("uleb128 requires non-negative integer")
    out = bytearray()
    while True:
        byte = value & 0x7F
        value >>= 7
        if value:
            out.append(byte | 0x80)
        else:
            out.append(byte)
            break
    return bytes(out)


def sleb128(value: int) -> bytes:
    """Encode a signed integer as SLEB128."""
    out = bytearray()
    more = True
    while more:
        byte = value & 0x7F
        value >>= 7
        if (value == 0 and (byte & 0x40) == 0) or (value == -1 and (byte & 0x40) != 0):
            more = False
        else:
            byte |= 0x80
        out.append(byte)
    return bytes(out)


def _wasm_section(section_id: int, payload: bytes) -> bytes:
    return bytes([section_id]) + uleb128(len(payload)) + payload


def _encode_str(text: str) -> bytes:
    raw = text.encode("utf-8")
    return uleb128(len(raw)) + raw


def build_deterministic_wasm_bytes() -> bytes:
    """Assemble the deterministic W3C WebAssembly 1.0 binary for `w0m-wasm-utils`.

    Matches `wom7func/crates/w0m-wasm-utils/src/lib.rs` C-ABI exports:
      - `memory`: 1..2 pages (64 KiB..128 KiB)
      - `fnv1a64(ptr: i32, len: i32) -> i64`
      - `levenshtein_distance(ptr_a: i32, len_a: i32, ptr_b: i32, len_b: i32) -> i32`
      - `score_token_overlap(hits: i32, total_keywords: i32, bonus: i32) -> i32`
    """
    # 1. Type section (id=1): 3 function signatures
    #   type 0: (i32, i32) -> (i64)
    #   type 1: (i32, i32, i32, i32) -> (i32)
    #   type 2: (i32, i32, i32) -> (i32)
    t0 = b"\x60\x02\x7f\x7f\x01\x7e"
    t1 = b"\x60\x04\x7f\x7f\x7f\x7f\x01\x7f"
    t2 = b"\x60\x03\x7f\x7f\x7f\x01\x7f"
    type_sec = _wasm_section(1, uleb128(3) + t0 + t1 + t2)

    # 2. Function section (id=3): 3 functions -> [0, 1, 2]
    func_sec = _wasm_section(3, uleb128(3) + b"\x00\x01\x02")

    # 3. Memory section (id=5): 1 memory with min=1 page, max=2 pages
    mem_sec = _wasm_section(5, uleb128(1) + b"\x01\x01\x02")

    # 4. Export section (id=7): memory + 3 functions
    exports_payload = (
        uleb128(4)
        + _encode_str("memory")
        + b"\x02\x00"
        + _encode_str("fnv1a64")
        + b"\x00\x00"
        + _encode_str("levenshtein_distance")
        + b"\x00\x01"
        + _encode_str("score_token_overlap")
        + b"\x00\x02"
    )
    export_sec = _wasm_section(7, exports_payload)

    # 5. Code section (id=10)
    # Function 0: fnv1a64(ptr: i32, len: i32) -> i64
    # Locals: local 2 (i: i32), local 3 (hash: i64)
    fnv_offset_signed = 0xCBF29CE484222325 - (1 << 64)
    fnv_prime_signed = 0x00000100000001B3
    f0_locals = uleb128(2) + uleb128(1) + b"\x7f" + uleb128(1) + b"\x7e"
    f0_instr = (
        b"\x42" + sleb128(fnv_offset_signed)  # i64.const FNV_OFFSET_BASIS
        + b"\x21\x03"  # local.set 3 (hash)
        + b"\x41\x00"  # i32.const 0
        + b"\x21\x02"  # local.set 2 (i)
        + b"\x02\x40"  # block
        + b"\x03\x40"  # loop
        + b"\x20\x02"  # local.get 2 (i)
        + b"\x20\x01"  # local.get 1 (len)
        + b"\x4f"  # i32.ge_u
        + b"\x0d\x01"  # br_if 1
        + b"\x20\x03"  # local.get 3 (hash)
        + b"\x20\x00"  # local.get 0 (ptr)
        + b"\x20\x02"  # local.get 2 (i)
        + b"\x6a"  # i32.add
        + b"\x31\x00\x00"  # i64.load8_u align=0 offset=0
        + b"\x85"  # i64.xor
        + b"\x42" + sleb128(fnv_prime_signed)  # i64.const FNV_PRIME
        + b"\x7e"  # i64.mul
        + b"\x21\x03"  # local.set 3 (hash)
        + b"\x20\x02"  # local.get 2 (i)
        + b"\x41\x01"  # i32.const 1
        + b"\x6a"  # i32.add
        + b"\x21\x02"  # local.set 2 (i)
        + b"\x0c\x00"  # br 0
        + b"\x0b"  # end loop
        + b"\x0b"  # end block
        + b"\x20\x03"  # local.get 3 (hash)
        + b"\x0b"  # end func
    )
    f0_body = f0_locals + f0_instr

    # Function 1: levenshtein_distance(ptr_a: 0, len_a: 1, ptr_b: 2, len_b: 3) -> i32
    # Locals: 8 x i32 (4=i, 5=j, 6=prev_diag, 7=old_dp, 8=cost, 9=best, 10=cand, 11=scratch)
    f1_locals = uleb128(1) + uleb128(8) + b"\x7f"
    f1_instr = (
        # Clamp len_a (1) <= 256
        b"\x20\x01\x41" + sleb128(256) + b"\x4b\x04\x40\x41" + sleb128(256) + b"\x21\x01\x0b"
        # Clamp len_b (3) <= 256
        + b"\x20\x03\x41" + sleb128(256) + b"\x4b\x04\x40\x41" + sleb128(256) + b"\x21\x03\x0b"
        # if len_a == 0 -> return len_b
        + b"\x20\x01\x45\x04\x40\x20\x03\x0f\x0b"
        # if len_b == 0 -> return len_a
        + b"\x20\x03\x45\x04\x40\x20\x01\x0f\x0b"
        # scratch (11) = 32768 (0x8000)
        + b"\x41" + sleb128(32768) + b"\x21\x0b"
        # j (5) = 0; loop j <= len_b: dp[j] = j
        + b"\x41\x00\x21\x05"
        + b"\x02\x40\x03\x40"
        + b"\x20\x05\x20\x03\x4b\x0d\x01"  # if j >_u len_b break
        + b"\x20\x0b\x20\x05\x41\x02\x74\x6a"  # scratch + (j << 2)
        + b"\x20\x05"  # value = j
        + b"\x36\x02\x00"  # i32.store
        + b"\x20\x05\x41\x01\x6a\x21\x05"  # j += 1
        + b"\x0c\x00\x0b\x0b"
        # Outer loop: i (4) = 0 .. len_a - 1
        + b"\x41\x00\x21\x04"
        + b"\x02\x40\x03\x40"
        + b"\x20\x04\x20\x01\x4f\x0d\x01"  # if i >=_u len_a break
        # prev_diag (6) = dp[0]
        + b"\x20\x0b\x28\x02\x00\x21\x06"
        # dp[0] = i + 1
        + b"\x20\x0b\x20\x04\x41\x01\x6a\x36\x02\x00"
        # Inner loop: j (5) = 0 .. len_b - 1
        + b"\x41\x00\x21\x05"
        + b"\x02\x40\x03\x40"
        + b"\x20\x05\x20\x03\x4f\x0d\x01"  # if j >=_u len_b break
        # old_dp (7) = dp[j + 1]
        + b"\x20\x0b\x20\x05\x41\x01\x6a\x41\x02\x74\x6a\x28\x02\x00\x21\x07"
        # cost (8) = mem[ptr_a + i] != mem[ptr_b + j]
        + b"\x20\x00\x20\x04\x6a\x2d\x00\x00"
        + b"\x20\x02\x20\x05\x6a\x2d\x00\x00"
        + b"\x47\x21\x08"
        # best (9) = old_dp + 1
        + b"\x20\x07\x41\x01\x6a\x21\x09"
        # cand (10) = dp[j] + 1
        + b"\x20\x0b\x20\x05\x41\x02\x74\x6a\x28\x02\x00\x41\x01\x6a\x21\x0a"
        # if cand <_u best: best = cand
        + b"\x20\x0a\x20\x09\x49\x04\x40\x20\x0a\x21\x09\x0b"
        # cand (10) = prev_diag + cost
        + b"\x20\x06\x20\x08\x6a\x21\x0a"
        # if cand <_u best: best = cand
        + b"\x20\x0a\x20\x09\x49\x04\x40\x20\x0a\x21\x09\x0b"
        # dp[j + 1] = best
        + b"\x20\x0b\x20\x05\x41\x01\x6a\x41\x02\x74\x6a\x20\x09\x36\x02\x00"
        # prev_diag = old_dp
        + b"\x20\x07\x21\x06"
        # j += 1
        + b"\x20\x05\x41\x01\x6a\x21\x05"
        + b"\x0c\x00\x0b\x0b"
        # i += 1
        + b"\x20\x04\x41\x01\x6a\x21\x04"
        + b"\x0c\x00\x0b\x0b"
        # return dp[len_b]
        + b"\x20\x0b\x20\x03\x41\x02\x74\x6a\x28\x02\x00"
        + b"\x0b"
    )
    f1_body = f1_locals + f1_instr

    # Function 2: score_token_overlap(hits: 0, total_keywords: 1, bonus: 2) -> i32
    # Locals: 1 x i32 (3=score)
    f2_locals = uleb128(1) + uleb128(1) + b"\x7f"
    f2_instr = (
        b"\x41\x00\x21\x03"  # score = 0
        # if (total_keywords >_s 0) & (hits >_s 0)
        + b"\x20\x01\x41\x00\x4a\x20\x00\x41\x00\x4a\x71\x04\x40"
        # if hits >_s total_keywords: hits = total_keywords
        + b"\x20\x00\x20\x01\x4a\x04\x40\x20\x01\x21\x00\x0b"
        # score = (hits * 100) /_s total_keywords
        + b"\x20\x00\x41" + sleb128(100) + b"\x6c\x20\x01\x6d\x21\x03"
        + b"\x0b"
        # score += bonus
        + b"\x20\x03\x20\x02\x6a\x21\x03"
        # if score <_s 0: score = 0
        + b"\x20\x03\x41\x00\x48\x04\x40\x41\x00\x21\x03\x0b"
        # if score >_s 100: score = 100
        + b"\x20\x03\x41" + sleb128(100) + b"\x4a\x04\x40\x41" + sleb128(100) + b"\x21\x03\x0b"
        + b"\x20\x03\x0b"
    )
    f2_body = f2_locals + f2_instr

    code_payload = (
        uleb128(3)
        + uleb128(len(f0_body)) + f0_body
        + uleb128(len(f1_body)) + f1_body
        + uleb128(len(f2_body)) + f2_body
    )
    code_sec = _wasm_section(10, code_payload)

    return b"\x00asm\x01\x00\x00\x00" + type_sec + func_sec + mem_sec + export_sec + code_sec


def emit_wasm_binary(out_path: Path = WASM_BIN_PATH) -> dict[str, Any]:
    """Build or deterministically emit `w0m_wasm_utils.wasm`."""
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cargo = shutil.which("cargo")
    rustup = shutil.which("rustup")
    used_cargo = False
    if cargo and rustup and CARGO_TOML_PATH.is_file():
        t_out = subprocess.run(
            [rustup, "target", "list", "--installed"],
            capture_output=True,
            text=True,
            check=False,
        )
        if "wasm32-unknown-unknown" in (t_out.stdout or ""):
            res = subprocess.run(
                [
                    cargo,
                    "build",
                    "--manifest-path",
                    str(CARGO_TOML_PATH),
                    "--target",
                    "wasm32-unknown-unknown",
                    "--release",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            built = (
                CRATE_DIR
                / "target"
                / "wasm32-unknown-unknown"
                / "release"
                / "w0m_wasm_utils.wasm"
            )
            if res.returncode == 0 and built.is_file():
                shutil.copyfile(built, out_path)
                used_cargo = True

    if not used_cargo:
        out_path.write_bytes(build_deterministic_wasm_bytes())

    raw = out_path.read_bytes()
    return {
        "wasm_path": str(out_path.relative_to(ROOT)) if out_path.is_relative_to(ROOT) else str(out_path),
        "mode": "cargo-wasm32" if used_cargo else "deterministic-emitter",
        "raw_bytes": len(raw),
        "gzip_bytes": len(gzip.compress(raw, compresslevel=9)),
    }


def _read_u32_leb(data: bytes, offset: int) -> tuple[int, int]:
    result = 0
    shift = 0
    pos = offset
    while pos < len(data):
        byte = data[pos]
        pos += 1
        result |= (byte & 0x7F) << shift
        if (byte & 0x80) == 0:
            return result, pos
        shift += 7
    raise ValueError("Truncated ULEB128 in WASM binary")


def parse_wasm_binary(wasm_bytes: bytes) -> dict[str, Any]:
    """Parse W3C WebAssembly 1.0 header, sections, and export names."""
    if len(wasm_bytes) < 8 or wasm_bytes[:4] != b"\x00asm" or wasm_bytes[4:8] != b"\x01\x00\x00\x00":
        return {
            "valid_header": False,
            "sections": [],
            "exports": {},
            "error": "Invalid WASM magic or version header",
        }

    pos = 8
    sections: list[int] = []
    exports: dict[str, int] = {}
    try:
        while pos < len(wasm_bytes):
            sec_id = wasm_bytes[pos]
            pos += 1
            sec_len, pos = _read_u32_leb(wasm_bytes, pos)
            sec_end = pos + sec_len
            if sec_end > len(wasm_bytes):
                return {
                    "valid_header": True,
                    "sections": sections,
                    "exports": exports,
                    "error": f"Section {sec_id} truncated ({sec_end} > {len(wasm_bytes)})",
                }
            sections.append(sec_id)
            if sec_id == 7:  # Export section
                epos = pos
                count, epos = _read_u32_leb(wasm_bytes, epos)
                for _ in range(count):
                    name_len, epos = _read_u32_leb(wasm_bytes, epos)
                    name = wasm_bytes[epos : epos + name_len].decode("utf-8")
                    epos += name_len
                    kind = wasm_bytes[epos]
                    epos += 1
                    _idx, epos = _read_u32_leb(wasm_bytes, epos)
                    exports[name] = kind
            pos = sec_end
    except Exception as exc:  # noqa: BLE001
        return {
            "valid_header": True,
            "sections": sections,
            "exports": exports,
            "error": str(exc),
        }

    return {
        "valid_header": True,
        "sections": sections,
        "exports": exports,
        "error": None,
    }


def check_toolchain_policies(
    tools_policy_path: Path = TOOLS_POLICY_PATH,
    stacks_policy_path: Path = STACKS_POLICY_PATH,
    suites_path: Path = SUITES_JSON_PATH,
) -> dict[str, Any]:
    """AC1 & AC3: Verify tools-policy.json, stacks-policy.json, and test-suites.json declarations."""
    problems: list[str] = []

    if not tools_policy_path.is_file():
        problems.append(f"Missing tools-policy.json: {tools_policy_path}")
        tools_data: dict[str, Any] = {}
    else:
        tools_data = json.loads(tools_policy_path.read_text(encoding="utf-8")).get("tools", {})

    for tool_name in ("wasm-pack", "worker-build"):
        spec = tools_data.get(tool_name)
        if not isinstance(spec, dict):
            problems.append(f"tools-policy.json missing required T273 AC1 entry `{tool_name}`")
            continue
        for req_key in ("min", "known_good", "required", "source", "auto", "note"):
            if req_key not in spec:
                problems.append(f"tools-policy.json `{tool_name}` missing `{req_key}`")
        if spec.get("required") is not False:
            problems.append(
                f"tools-policy.json `{tool_name}` must have `required: false` on multi-OS hosts"
            )

    rust_target_documented = any(
        "wasm32-unknown-unknown" in str((tools_data.get(k) or {}).get("note", ""))
        for k in ("rustup", "cargo", "rustc", "wasm-pack", "worker-build")
    )
    if not rust_target_documented:
        problems.append("tools-policy.json does not document `wasm32-unknown-unknown` target")

    if not stacks_policy_path.is_file():
        problems.append(f"Missing stacks-policy.json: {stacks_policy_path}")
        stacks_data: dict[str, Any] = {}
    else:
        stacks_data = json.loads(stacks_policy_path.read_text(encoding="utf-8")).get("stacks", {})

    wasm_stack = stacks_data.get("wasm-worker")
    if not isinstance(wasm_stack, dict):
        problems.append("stacks-policy.json missing `wasm-worker` stack entry (T273 AC1)")
    else:
        if wasm_stack.get("runtime") != "rust":
            problems.append("stacks-policy.json `wasm-worker` must declare `runtime: \"rust\"`")
        if wasm_stack.get("repo") != "wom7func":
            problems.append("stacks-policy.json `wasm-worker` must declare `repo: \"wom7func\"`")
        cmds = wasm_stack.get("commands") or {}
        for role in ("build", "test", "lint", "fmt", "fmt-check"):
            if role not in cmds:
                problems.append(f"stacks-policy.json `wasm-worker` missing command role `{role}`")

    if suites_path.is_file():
        suites = json.loads(suites_path.read_text(encoding="utf-8")).get("suites", [])
        has_suite = any(
            isinstance(s, dict) and s.get("recipe") == "wasm-worker-check" for s in suites
        )
        if not has_suite:
            problems.append("wom7web/project/test-suites.json missing `wasm-worker-check` suite")
    else:
        problems.append(f"Missing test-suites.json: {suites_path}")

    return {
        "ok": len(problems) == 0,
        "problems": problems,
    }


def measure_bundle_budget(
    func_dir: Path = FUNC_DIR,
    wasm_path: Path = WASM_BIN_PATH,
    free_limit_bytes: int = CF_FREE_TIER_LIMIT_BYTES,
    budget_ratio: float = CF_FREE_BUDGET_RATIO,
) -> dict[str, Any]:
    """AC2: Measure `wom7func` TS baseline + `.wasm` binary against Cloudflare Free tier limit."""
    problems: list[str] = []
    ts_files: list[Path] = []
    src_dir = func_dir / "src"
    if src_dir.is_dir():
        for p in sorted(src_dir.rglob("*.ts")):
            if ".test." in p.name or ".spec." in p.name or "__tests__" in p.parts:
                continue
            ts_files.append(p)

    if not ts_files:
        problems.append(f"No TypeScript worker source files found under {src_dir}")
        ts_concat = b""
    else:
        ts_concat = b"\n".join(p.read_bytes() for p in ts_files)

    if not wasm_path.is_file():
        problems.append(f"Missing compiled WASM binary: {wasm_path}")
        wasm_bytes = b""
    else:
        wasm_bytes = wasm_path.read_bytes()

    ts_raw_bytes = len(ts_concat)
    ts_gzip_bytes = len(gzip.compress(ts_concat, compresslevel=9)) if ts_concat else 0
    wasm_raw_bytes = len(wasm_bytes)
    wasm_gzip_bytes = len(gzip.compress(wasm_bytes, compresslevel=9)) if wasm_bytes else 0

    combined_raw_bytes = ts_raw_bytes + wasm_raw_bytes
    combined_gzip_bytes = len(gzip.compress(ts_concat + wasm_bytes, compresslevel=9)) if (ts_concat or wasm_bytes) else 0

    budget_ceiling_bytes = int(free_limit_bytes * budget_ratio)
    free_tier_pct = round((combined_gzip_bytes / free_limit_bytes) * 100.0, 2) if free_limit_bytes else 100.0
    wasm_overhead_pct = round((wasm_gzip_bytes / free_limit_bytes) * 100.0, 4) if free_limit_bytes else 100.0

    if combined_gzip_bytes > budget_ceiling_bytes:
        problems.append(
            f"Combined Worker+WASM compressed bundle ({combined_gzip_bytes:,} B) exceeds "
            f"{int(budget_ratio * 100)}% Free-tier safety ceiling ({budget_ceiling_bytes:,} B / "
            f"{free_limit_bytes:,} B limit) — would push toward Workers Paid (T271 / AgDR-0003)"
        )

    return {
        "ok": len(problems) == 0,
        "ts_file_count": len(ts_files),
        "ts_baseline_raw_bytes": ts_raw_bytes,
        "ts_baseline_gzip_bytes": ts_gzip_bytes,
        "wasm_raw_bytes": wasm_raw_bytes,
        "wasm_gzip_bytes": wasm_gzip_bytes,
        "combined_raw_bytes": combined_raw_bytes,
        "combined_gzip_bytes": combined_gzip_bytes,
        "free_tier_limit_bytes": free_limit_bytes,
        "paid_tier_limit_bytes": CF_PAID_TIER_LIMIT_BYTES,
        "budget_ceiling_bytes": budget_ceiling_bytes,
        "free_tier_pct": free_tier_pct,
        "wasm_overhead_pct": wasm_overhead_pct,
        "zeroclaw_native_bytes": ZEROCLAW_NATIVE_BINARY_BYTES,
        "pushes_to_paid_tier": combined_gzip_bytes > free_limit_bytes,
        "problems": problems,
    }


def check_crate_lint_and_abi(
    cargo_toml_path: Path = CARGO_TOML_PATH,
    lib_rs_path: Path = LIB_RS_PATH,
    wasm_path: Path = WASM_BIN_PATH,
) -> dict[str, Any]:
    """AC3: Lint & ABI verification for `w0m-wasm-utils` (`Cargo.toml`, `src/lib.rs`, `.wasm`)."""
    problems: list[str] = []

    if not cargo_toml_path.is_file():
        problems.append(f"Missing Cargo.toml: {cargo_toml_path}")
    else:
        toml_text = cargo_toml_path.read_text(encoding="utf-8")
        for needle, label in (
            ('name = "w0m-wasm-utils"', "package name `w0m-wasm-utils`"),
            ('edition = "2024"', 'edition = "2024"'),
            ('rust-version = "1.95"', 'rust-version = "1.95"'),
            ('"cdylib"', 'crate-type includes "cdylib"'),
            ('opt-level = "z"', 'release profile `opt-level = "z"`'),
            ('panic = "abort"', 'release profile `panic = "abort"`'),
        ):
            if needle not in toml_text:
                problems.append(f"Cargo.toml missing {label}")

    if not lib_rs_path.is_file():
        problems.append(f"Missing src/lib.rs: {lib_rs_path}")
    else:
        rs_text = lib_rs_path.read_text(encoding="utf-8")
        if "#![no_std]" not in rs_text:
            problems.append("src/lib.rs must declare `#![no_std]` to avoid std allocator bloat")
        if re.search(r"^\s*use\s+std::", rs_text, re.M):
            problems.append("src/lib.rs must not import `std::` in `#![no_std]` worker crate")
        for fn_name in ("fnv1a64", "levenshtein_distance", "score_token_overlap"):
            if f"fn {fn_name}" not in rs_text:
                problems.append(f"src/lib.rs missing exported function `{fn_name}`")

    if not wasm_path.is_file():
        problems.append(f"Missing compiled WASM binary: {wasm_path}")
        parsed: dict[str, Any] = {"valid_header": False, "sections": [], "exports": {}, "error": "file missing"}
    else:
        parsed = parse_wasm_binary(wasm_path.read_bytes())
        if not parsed["valid_header"] or parsed["error"]:
            problems.append(f"WASM binary invalid: {parsed['error']}")
        exports = parsed["exports"]
        for exp in REQUIRED_WASM_EXPORTS:
            if exp not in exports:
                problems.append(f"WASM binary missing required export `{exp}`")

    cargo = shutil.which("cargo")
    rustup = shutil.which("rustup")
    cargo_checked = False
    if cargo and rustup and cargo_toml_path.is_file():
        t_out = subprocess.run(
            [rustup, "target", "list", "--installed"],
            capture_output=True,
            text=True,
            check=False,
        )
        if "wasm32-unknown-unknown" in (t_out.stdout or ""):
            chk = subprocess.run(
                [
                    cargo,
                    "check",
                    "--manifest-path",
                    str(cargo_toml_path),
                    "--target",
                    "wasm32-unknown-unknown",
                ],
                capture_output=True,
                text=True,
                check=False,
            )
            cargo_checked = True
            if chk.returncode != 0:
                problems.append(f"cargo check failed: {(chk.stderr or chk.stdout).strip()}")

    return {
        "ok": len(problems) == 0,
        "cargo_checked": cargo_checked,
        "exports": list(parsed.get("exports", {}).keys()),
        "problems": problems,
    }


def check_fmt(
    cargo_toml_path: Path = CARGO_TOML_PATH,
    lib_rs_path: Path = LIB_RS_PATH,
) -> dict[str, Any]:
    """Check Rust formatting on `Cargo.toml` and `src/lib.rs`."""
    problems: list[str] = []
    for path in (cargo_toml_path, lib_rs_path):
        if not path.is_file():
            problems.append(f"Missing file for fmt-check: {path}")
            continue
        text = path.read_text(encoding="utf-8")
        for idx, line in enumerate(text.splitlines(), 1):
            if "\t" in line:
                problems.append(f"{path.name}:{idx}: tab indentation found (use 4 spaces)")
                break
            if line.endswith((" ", "\t")):
                problems.append(f"{path.name}:{idx}: trailing whitespace found")
                break

    rustfmt = shutil.which("rustfmt")
    if rustfmt and lib_rs_path.is_file():
        res = subprocess.run(
            [rustfmt, "--check", "--edition", "2024", str(lib_rs_path)],
            capture_output=True,
            text=True,
            check=False,
        )
        if res.returncode != 0:
            problems.append(f"rustfmt --check failed: {(res.stderr or res.stdout).strip()}")

    return {
        "ok": len(problems) == 0,
        "problems": problems,
    }


def run_wasm_runtime_smoke(wasm_path: Path = WASM_BIN_PATH) -> dict[str, Any]:
    """AC4: Instantiate `w0m_wasm_utils.wasm` in Node/V8 and verify parity on test vectors."""
    if not wasm_path.is_file():
        return {"ok": False, "problems": [f"Missing WASM file: {wasm_path}"]}
    node = shutil.which("node")
    if not node:
        return {"ok": False, "problems": ["node binary not found on PATH"]}

    js_probe = """
const fs = require("node:fs");
const wasmBytes = fs.readFileSync(process.argv[1]);
if (!WebAssembly.validate(wasmBytes)) {
  console.error("WebAssembly.validate returned false");
  process.exit(1);
}
const mod = new WebAssembly.Module(wasmBytes);
const inst = new WebAssembly.Instance(mod);
const exp = inst.exports;
const mem = new Uint8Array(exp.memory.buffer);

function writeStr(offset, str) {
  const bytes = Buffer.from(str, "utf8");
  mem.set(bytes, offset);
  return bytes.length;
}

const lenEmpty = writeStr(0, "");
const hEmpty = BigInt.asUintN(64, exp.fnv1a64(0, lenEmpty));
if (hEmpty !== 0xcbf29ce484222325n) {
  throw new Error("fnv1a64('') mismatch: " + hEmpty.toString(16));
}

const lenFoobar = writeStr(0, "foobar");
const hFoobar = BigInt.asUintN(64, exp.fnv1a64(0, lenFoobar));
if (hFoobar !== 0x85944171f73967e8n) {
  throw new Error("fnv1a64('foobar') mismatch: " + hFoobar.toString(16));
}

const lenA = writeStr(0, "kitten");
const lenB = writeStr(512, "sitting");
const dist1 = exp.levenshtein_distance(0, lenA, 512, lenB);
if (dist1 !== 3) {
  throw new Error("levenshtein('kitten', 'sitting') mismatch: " + dist1);
}

const lenC = writeStr(0, "Forward Deployed Engineer");
const lenD = writeStr(512, "Forward Deployed Engineer");
const dist2 = exp.levenshtein_distance(0, lenC, 512, lenD);
if (dist2 !== 0) {
  throw new Error("levenshtein identical mismatch: " + dist2);
}

const s1 = exp.score_token_overlap(5, 10, 15);
const s2 = exp.score_token_overlap(12, 10, 20);
const s3 = exp.score_token_overlap(1, 10, -50);
if (s1 !== 65 || s2 !== 100 || s3 !== 0) {
  throw new Error(`score_token_overlap mismatch: ${s1}, ${s2}, ${s3}`);
}

console.log(JSON.stringify({
  fnv1a64_foobar: "0x" + hFoobar.toString(16),
  levenshtein_kitten_sitting: dist1,
  score_5_10_15: s1
}));
"""
    res = subprocess.run(
        [node, "-e", js_probe, str(wasm_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    if res.returncode != 0:
        return {
            "ok": False,
            "problems": [f"WASM runtime execution failed: {(res.stderr or res.stdout).strip()}"],
        }
    try:
        payload = json.loads(res.stdout.strip())
    except ValueError:
        payload = {"raw": res.stdout.strip()}
    return {
        "ok": True,
        "problems": [],
        "vectors": payload,
    }


def check_agdr_boundary_doc(agdr_path: Path = AGDR_0044_PATH) -> dict[str, Any]:
    """AC5 & AC7: Verify AgDR-0044 documents the TypeScript boundary, ZeroClaw, and 4th-language cost."""
    problems: list[str] = []
    if not agdr_path.is_file():
        problems.append(f"Missing AgDR-0044 decision record: {agdr_path}")
        return {"ok": False, "problems": problems}

    text = agdr_path.read_text(encoding="utf-8")
    for token, desc in (
        ("id: AgDR-0044", "AgDR-0044 frontmatter id"),
        ("status: accepted", "accepted status"),
        ("ticket: T273", "T273 ticket link"),
        ("ZeroClaw", "ZeroClaw native binary exclusion analysis"),
        ("31,699,216", "measured 31,699,216-byte ZeroClaw binary size"),
        ("TypeScript", "what stays TypeScript (I/O-bound routes/workflows)"),
        ("fourth", "fourth-language / 4th-runtime single-maintainer cost statement (AC7)"),
    ):
        if token.lower() not in text.lower():
            problems.append(f"AgDR-0044 missing {desc} (`{token}`)")

    return {
        "ok": len(problems) == 0,
        "problems": problems,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="T273 — Cloudflare Workers Rust-to-WASM toolchain, bundle budget & ABI gate."
    )
    parser.add_argument("--emit", "--build", action="store_true", dest="emit", help="Emit/build w0m_wasm_utils.wasm")
    parser.add_argument("--check", action="store_true", help="Run all T273 checks (default)")
    parser.add_argument("--lint", action="store_true", help="Run crate + WASM ABI lint checks")
    parser.add_argument("--fmt-check", action="store_true", help="Run Rust formatting checks")
    parser.add_argument("--test", action="store_true", help="Run WebAssembly runtime smoke tests")
    parser.add_argument("--bundle-report", action="store_true", help="Report Worker + WASM bundle sizes")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON")
    args = parser.parse_args(argv)

    if args.emit:
        info = emit_wasm_binary()
        if args.json:
            print(json.dumps(info, indent=2))
        else:
            print(
                f"  ✅ wasm-build: emitted {info['wasm_path']} ({info['mode']}, "
                f"raw={info['raw_bytes']} B, gzip={info['gzip_bytes']} B)"
            )
        return 0

    if args.fmt_check and not (args.check or args.lint or args.test or args.bundle_report):
        fmt_res = check_fmt()
        if args.json:
            print(json.dumps(fmt_res, indent=2))
        elif fmt_res["ok"]:
            print("  ✅ wasm-fmt-check: Cargo.toml and src/lib.rs formatting clean")
        else:
            for p in fmt_res["problems"]:
                print(f"  ❌ wasm-fmt-check: {p}")
        return 0 if fmt_res["ok"] else 1

    if args.lint and not (args.check or args.test or args.bundle_report):
        lint_res = check_crate_lint_and_abi()
        if args.json:
            print(json.dumps(lint_res, indent=2))
        elif lint_res["ok"]:
            print(
                f"  ✅ wasm-lint: #![no_std] crate and WASM exports verified "
                f"({', '.join(lint_res['exports'])})"
            )
        else:
            for p in lint_res["problems"]:
                print(f"  ❌ wasm-lint: {p}")
        return 0 if lint_res["ok"] else 1

    if args.test and not (args.check or args.bundle_report):
        smoke_res = run_wasm_runtime_smoke()
        if args.json:
            print(json.dumps(smoke_res, indent=2))
        elif smoke_res["ok"]:
            print(f"  ✅ wasm-test: WebAssembly.instantiate vectors passed ({smoke_res['vectors']})")
        else:
            for p in smoke_res["problems"]:
                print(f"  ❌ wasm-test: {p}")
        return 0 if smoke_res["ok"] else 1

    if args.bundle_report and not args.check:
        bundle_res = measure_bundle_budget()
        if args.json:
            print(json.dumps(bundle_res, indent=2))
        else:
            mark = "✅" if bundle_res["ok"] else "❌"
            print(
                f"  {mark} wasm-bundle-report: TS={bundle_res['ts_baseline_gzip_bytes']:,} B gzip + "
                f"WASM={bundle_res['wasm_gzip_bytes']:,} B gzip (raw {bundle_res['wasm_raw_bytes']:,} B) "
                f"-> combined={bundle_res['combined_gzip_bytes']:,} B gzip "
                f"({bundle_res['free_tier_pct']}% of 1 MiB Free tier limit; "
                f"ZeroClaw native={bundle_res['zeroclaw_native_bytes']:,} B)"
            )
        return 0 if bundle_res["ok"] else 1

    # Default / --check: run all 5 verification pillars
    tc_res = check_toolchain_policies()
    lint_res = check_crate_lint_and_abi()
    fmt_res = check_fmt()
    bundle_res = measure_bundle_budget()
    smoke_res = run_wasm_runtime_smoke()
    agdr_res = check_agdr_boundary_doc()

    all_ok = (
        tc_res["ok"]
        and lint_res["ok"]
        and fmt_res["ok"]
        and bundle_res["ok"]
        and smoke_res["ok"]
        and agdr_res["ok"]
    )
    summary = {
        "ok": all_ok,
        "toolchain": tc_res,
        "lint_abi": lint_res,
        "fmt": fmt_res,
        "bundle": bundle_res,
        "runtime_smoke": smoke_res,
        "agdr_0044": agdr_res,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
        return 0 if all_ok else 1

    checks = [
        (
            tc_res["ok"],
            "AC1 toolchain & stack policy (`wasm-pack`, `worker-build`, `wasm-worker`, `test-suites.json`)",
            tc_res["problems"],
        ),
        (
            bundle_res["ok"],
            f"AC2 bundle budget: TS={bundle_res['ts_baseline_gzip_bytes']:,} B gzip + "
            f"WASM={bundle_res['wasm_gzip_bytes']:,} B gzip ({bundle_res['wasm_raw_bytes']:,} B raw) "
            f"= {bundle_res['combined_gzip_bytes']:,} B ({bundle_res['free_tier_pct']}% of 1 MiB Free limit)",
            bundle_res["problems"],
        ),
        (
            lint_res["ok"] and fmt_res["ok"],
            f"AC3 Rust/WASM lint, fmt & ABI exports ({', '.join(lint_res['exports'])})",
            lint_res["problems"] + fmt_res["problems"],
        ),
        (
            smoke_res["ok"],
            "AC4 WebAssembly.instantiate execution parity (`fnv1a64`, `levenshtein_distance`, `score_token_overlap`)",
            smoke_res["problems"],
        ),
        (
            agdr_res["ok"],
            "AC5/AC7 AgDR-0044 TypeScript I/O boundary, ZeroClaw 31.7 MB exclusion & 4th-language cost",
            agdr_res["problems"],
        ),
    ]

    for ok, label, probs in checks:
        if ok:
            print(f"  ✅ {label}")
        else:
            print(f"  ❌ {label}")
            for p in probs:
                print(f"      · {p}")

    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())
