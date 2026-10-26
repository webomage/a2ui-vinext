---
id: AgDR-0044
title: "Rust-to-WASM Cloudflare Workers Boundary, #![no_std] Bundle Budget Ceiling, ZeroClaw Exclusion, and Fourth-Language Maintenance Cost"
timestamp: 2026-10-25T23:45:00Z
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T273
---

# AgDR-0044 — Rust-to-WASM Cloudflare Workers Boundary, `#![no_std]` Bundle Budget Ceiling, and Fourth-Language Cost

## Y-statement

> In the context of **adopting Rust compiled to WebAssembly (`wasm32-unknown-unknown`) for Cloudflare Workers utilities in `wom7func` (`[[T273]]`)**, facing **the `1,048,576`-byte (`1 MiB`) compressed bundle ceiling on Cloudflare Workers Free (`[[AgDR-0003]]`), the risk that unconstrained Rust `std` / `workers-rs` crates silently consume the free bundle budget and force an unbudgeted upgrade to Workers Paid (`[[T271]]`, `[[T272]]`, `[[AgDR-0043]]`), the temptation to over-read *"use Rust for Workers tools and utils"* as a mandate to rewrite I/O-bound routes or port local native daemons (`ZeroClaw`), and single-maintainer review burden across four runtimes**, we decided **to scope Rust-on-Workers strictly to `#![no_std]` CPU-bound pure functions (`wom7func/crates/w0m-wasm-utils`: 64-bit FNV-1a hashing, bounded Wagner–Fischer Levenshtein edit distance, and token-overlap scoring at `550` B raw / `389` B gzip = `0.037%` of the Free limit), keep all I/O-bound HTTP/Supabase/AI routes, remote Puppeteer rendering, and cron orchestration 100% in TypeScript, exclude `ZeroClaw` (`31,699,216` B native binary) from WASM porting in favour of HTTP A2A, and enforce a fail-closed `85%` (`891,289` B) compressed bundle gate (`scripts/wasm_worker_check.py`)**, to achieve **a `14.8×` speedup on 64-bit FNV-1a fingerprinting (`2.22 ms` vs `32.76 ms` / 1k ops) and `1.77×` speedup on Levenshtein deduplication (`35.33 ms` vs `62.63 ms` / 1k ops) while staying at `5.66%` (`59,318` B) of the Free tier ceiling**, accepting **the explicit fourth-language maintenance cost (TypeScript + Python + Deno + Rust) borne by a single maintainer**.

## Context

1. **Measured Bundle Budget vs Cloudflare Tier Limits (`[[T273]]` AC2, `scripts/wasm_worker_check.py --bundle-report`):**
   - Cloudflare Workers Free caps compressed worker bundles at **`1,048,576` bytes (`1 MiB`)**; Cloudflare Workers Paid raises this to **`10,485,760` bytes (`10 MiB`)** (`$5/mo`, governed by `[[AgDR-0043]]` / `[[T271]]` / `[[T272]]`).
   - `wom7func` TypeScript baseline (`26` production `.ts` files): **`205,494` B raw / `58,967` B gzip** (`5.62%` of Free tier limit).
   - `wom7func/crates/w0m-wasm-utils/pkg/w0m_wasm_utils.wasm` (`#![no_std]`, `opt-level = "z"`, `lto = true`, `panic = "abort"`, `strip = "symbols"`): **`550` B raw / `389` B gzip** (`+0.0371%` of Free tier limit).
   - Combined `wom7func` Worker + WASM: **`206,044` B raw / `59,318` B gzip** (**`5.66%`** of the `1 MiB` Free tier limit, leaving `94.34%` headroom and staying far below the `85%` = `891,289` B gate ceiling).
   - **Finding reported to `[[T271]]`:** Rust-to-WASM in `#![no_std]` utility form does **not** push the estate toward Cloudflare Workers Paid.
2. **Measured CPU-Bound Benchmark (`[[T273]]` AC4, 1,000 iterations in V8/Workers):**
   - `fnv1a64` (149-byte UTF-8 ATS job description): **`2.215 ms` (WASM) vs `32.764 ms` (TS `BigInt`)** — **`14.8×` faster** (native 64-bit `i64.xor`/`i64.mul` vs heap-boxed JS `BigInt` allocations per byte).
   - `levenshtein_distance` (72×73-byte job titles): **`35.326 ms` (WASM) vs `62.626 ms` (TS)** — **`1.77×` faster**.
3. **Why `ZeroClaw` (`31.7 MB`) is Structurally Excluded from Workers WASM (`[[T273]]` AC5):**
   - `~/.cargo/bin/zeroclaw` (v0.8.3) is **`31,699,216` bytes (`31.7 MB`)** — `30.2×` larger than the entire Cloudflare Workers Free tier ceiling and `3.0×` larger than the Paid tier ceiling before compression.
   - Its core subcommands depend on OS capabilities that do not exist in a stateless Worker isolate: `daemon` binds `127.0.0.1:42617` sockets, `acp` speaks JSON-RPC 2.0 over `stdio`, `service` manages `launchd`/`systemd`, its memory backend uses local filesystem SQLite + FTS5, and its primary route targets local `omlx` (`127.0.0.1:8888`) and macOS iMessage.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Option 1: `#![no_std]` C-ABI Rust→WASM crate (`w0m-wasm-utils`) for CPU-bound pure functions only; keep I/O routes in TypeScript** | `389` B gzip delta (`0.037%` of Free tier); `14.8×` 64-bit hashing speedup; zero `std` allocator bloat; clean TypeScript FFI over linear memory | Requires explicit C-ABI slice bounds (`ptr, len`) for new pure utilities | **ACCEPTED** |
| **Option 2: Full `workers-rs` (`worker` crate + `std`) rewrite of `wom7func` / `wom7api` routes** | Single language inside rewritten worker | Pulls `std` allocator + JS glue (`150–400 KB` gzip), zero latency win on network I/O (Supabase/AI fan-out), duplicates Hono/Zod/Supabase middleware | Rejected |
| **Option 3: Port `ZeroClaw` (`31,699,216` B) to Cloudflare Workers WASM** | Reuses Rust agent crate name | Exceeds Free tier limit by `30×`; no sockets, no `stdio`, no `launchd`/`systemd`, no local filesystem SQLite FTS5, cannot reach `127.0.0.1:8888` (`omlx`) | Rejected (use HTTP A2A counterpart instead) |

## Decision

1. **Strict Boundary — What Moves to Rust→WASM vs What Stays TypeScript (`[[T273]]` AC5):**
   - **Moves to `#![no_std]` Rust→WASM (`wom7func/crates/w0m-wasm-utils`):** CPU-bound, stateless, deterministic computations over byte slices and integers — 64-bit FNV-1a content fingerprinting (`fnv1a64`), bounded Wagner–Fischer edit distance (`levenshtein_distance`), token-overlap scoring (`score_token_overlap`), and future pure-compute kernels (diffing, cryptographic/checksum primitives, deterministic DAG evaluation).
   - **Stays 100% TypeScript:**
     - `wom7api` Hono HTTP routes, Supabase PostgREST/RPC queries, and AI provider fan-out (100% network I/O-bound; WASM adds bundle bytes and FFI copy overhead for zero latency reduction).
     - `wom7func` `/api/generate` (`@cloudflare/puppeteer` → remote headless browser rendering).
     - `wom7func` `scheduled()` cron orchestration, `/mcp` JSON-RPC 2.0 dispatch, `/health`, `/estate-health`, and `/backup-watchdog`.
   - **`ZeroClaw` Integration Boundary:** `ZeroClaw` remains a local workstation daemon; Worker-to-ZeroClaw interaction uses HTTP A2A, never a WASM port.
2. **Mechanical Governance & Bundle Ceiling (`[[T273]]` AC1/AC2/AC3):**
   - `wasm-pack` and `worker-build` (`source: rustup`, `required: false`) and the `wasm32-unknown-unknown` target are governed in `project/policies/tools-policy.json`.
   - The `wasm-worker` stack is governed separately from native `mlx` in `project/policies/stacks-policy.json` (`repo: wom7func`, `path: crates/w0m-wasm-utils`, `runtime: rust`, `justfile: wom7func/justfile`).
   - `scripts/wasm_worker_check.py` (`just wasm-worker-check`, registered in `wom7web/project/test-suites.json`) fails closed (`exit 1`) if the combined compressed Worker + WASM bundle exceeds **`85%` (`891,289` bytes)** of the `1,048,576`-byte Cloudflare Workers Free tier limit.
3. **Explicit Statement of Fourth-Language Maintenance Cost (`[[T273]]` AC7):**
   - This estate is maintained by **one maintainer** and now governs **four runtimes**: **TypeScript/Node (`5` stacks) · Python (`3` stacks) · Deno (`1` stack) · Rust (`2` stacks: native `mlx` + WASM `wasm-worker`)**.
   - Every Rust→WASM addition carries three concrete ongoing costs:
     1. **Dual-ABI review burden:** Every exported function requires reviewing both `#![no_std]` `unsafe extern "C"` pointer/length bounds in `src/lib.rs` and the TypeScript linear-memory wrapper in `wom7func/src/utils/wasm-utils.ts`.
     2. **Cross-host toolchain matrix:** Because `rustup`/`cargo` are optional (`required: false`) on Linux `x86_64` guest/agent hosts, the `.wasm` artefact (`pkg/w0m_wasm_utils.wasm`) and its parity test suite (`wasm-utils.test.ts` + `wasm_worker_check.py`) must remain deterministically verifiable offline without a local Rust compiler.
     3. **Onboarding & cognitive switching cost:** A fourth runtime is justified **only** when a pure CPU-bound loop demonstrates a measurable win (such as the `14.8×` 64-bit FNV-1a speedup) while staying under `#![no_std]` sub-kilobyte discipline.

## Consequences

- **Positive:**
  - `wom7func` job-board deduplication (`scrapeAll` in `src/lib/job-boards.ts`) and `/health` (`wasm_ready: true`, `wasm_fnv1a64: "0xc6e33ed7be4d5a51"`) execute real `#![no_std]` WASM in production with a `389`-byte compressed footprint.
  - Any future commit that pulls `std` into `w0m-wasm-utils` or bloats the compressed bundle past `891,289` bytes is blocked automatically at `pre-commit` (`just wasm-lint`) and in `just test` (`wasm-worker-check`).
- **Negative:**
  - Developers adding a new WASM function must maintain 100% parity between `src/lib.rs`, `pkg/w0m_wasm_utils.wasm`, and the TypeScript reference test in `src/utils/wasm-utils.test.ts`.

## What this does NOT decide

- Does not authorize porting any `wom7api` Hono route, Supabase edge function (`Deno`), or stateful workflow to Rust.
- Does not change `[[AgDR-0003]]` or `[[AgDR-0043]]` tier posture (`$0/mo` Cloudflare Workers Free remains active at `5.66%` bundle utilization).
