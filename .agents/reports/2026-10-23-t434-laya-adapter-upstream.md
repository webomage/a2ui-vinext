# T434 — System One Provider Terms, Laya `<result>` Adapter & Upstream Serve Patch

- **Ticket:** [[T434]] (`AC2`, `AC3`, `AC4`, `AC8`, `AC10`) · Split hardware benchmark: [[T569]]
- **Date:** 2026-10-23
- **Implementation:** `wom7web/project/scripts/system_one.py`, `wom7web/project/scripts/jev_system_one.py`

---

## 1. Provider Licence, Weight Source & Data Terms Audit (`AC2`)

| Provider | Model / Backbone | Code & Weight Licence | Auth & Data Terms | Allowed w0m Scope | Excluded Scope |
|---|---|---|---|---|---|
| **Clef-flash / Clef** (`@cf/cloudflare/clef-flash`, `@cf/cloudflare/clef`) | Qwen3.5-9B / Qwen3.8-27B System One heads | **Apache-2.0** open weights hosted natively on Cloudflare Workers AI | Existing `CLOUDFLARE_API_TOKEN` + `CLOUDFLARE_ACCOUNT_ID` (`env.AI.run`); zero third-party keys; payloads stay inside Cloudflare | **Edge (`wom7api`/`wom7func`) + Local CLI/evals** — satisfies [[T36]] AC2 natively without Cloudflare Containers (`AC8`) | Pre-commit/pre-push git hooks (`AC9`: hooks stay local-only) |
| **Jev** (`jev-1.13.0`, `jev-1.14.0`) | TypeSafe proprietary System One + `box` localization | Commercial SaaS (TypeSafe ToS) | `TYPESAFE_API_KEY` Bearer token; third-party SaaS host | Local CLI benchmarks & non-sensitive multimodal `box` research when explicitly selected | **Excluded from edge runtime** ([[T36]] AC2 forbids third-party gateways/keys) and **excluded from git hooks** (`AC9`) |
| **Kev** ([`jaredpalmer/kev`](https://github.com/jaredpalmer/kev)) | Qwen3.5 0.8B / 4B / 9B LoRA + pointer head | **Apache-2.0** (code + adapter weights; trained without Jev outputs) | Local loopback (`127.0.0.1:8091`) or optional `KEV_API_KEY` | Local macOS MLX tooling & local hooks (`<= 500ms` budget) | Hosted Modal endpoint excluded from edge (`T36` AC2) |
| **Laya** ([`mizorewww/laya-mlx`](https://github.com/mizorewww/laya-mlx) & `LiquidAI/LFM2.5-1.2B-Thinking`) | Convai ModernBERT 421M / mmBERT 322M & LiquidAI LFM2.5-1.2B-Thinking (4-bit MLX) | **Apache-2.0 + NOTICE** (Convai / LiquidAI weights on Hugging Face) | Local loopback only (`127.0.0.1:8092` or `omlx` `127.0.0.1:8000`); zero external egress | **Local SDLC gates, git hooks (`AC7`/`AC9`), and multilingual local classification (`AC10`)** | Never runs in Cloudflare Worker isolate (exceeds 128 MB heap+WASM limit) |
| **Von** ([`wfzyx/von`](https://github.com/wfzyx/von)) | ModernBERT 395M encoder (`ghcr.io/wfzyx/von:cpu`) | **Apache-2.0** | Local loopback (`127.0.0.1:8093`); **English-only** | English-only local CPU benchmarks & offline fixtures | **Excluded from multilingual inputs (`AC10` Spanish/Russian resume bullets)** |

---

## 2. System One `<result>` Tag Prompt & Parser Contract (`AC3` / `Laya` / `omlx`)

When routing bounded System One decisions through `omlx` (`http://127.0.0.1:8000/v1/chat/completions`) with `LiquidAI/LFM2.5-1.2B-Thinking-MLX-4bit` (or `Kev` / `Jev` chat adapters), `wom7web/project/scripts/system_one.py` enforces a deterministic single-pass `<result>` contract:

### 2.1 Prompt Template (`build_result_tag_prompt`)

```text
[system]
You are a System One typed-decision engine. Evaluate the state against the task and options in a single deterministic pass. Output ONLY `<result>KEY</result>` where KEY is one of {bug, feature, task} (or its 1-based option index 1..3).

[user]
Task: Classify this w0m software engineering ticket into its canonical `type` (`bug`, `feature`, or `task`) based on its title and summary.

Options:
1. bug: Fixes an existing defect, broken runtime/gate/test behavior, security exposure, drift, false positive, or regression.
2. feature: Introduces or builds a new capability, new CLI/recipe/script, new database table/migration, new UI component/endpoint, or new subsystem.
3. task: Performs an audit, investigation, measurement, documentation/AgDR record, retirement/decommission, or consolidation without adding a new product feature.

Context:
{"id": "T287", "title": "Repos are a first-class entity...", "summary": "..."}
```

### 2.2 Strict Parser Contract (`parse_result_tag`)

1. **Reasoning strip:** Any `<think>...</think>` block emitted by `LiquidAI/LFM2.5-1.2B-Thinking` is stripped prior to tag extraction.
2. **Tag extraction:** Matches `<result>\s*(.*?)\s*</result>` outside `<think>`.
   - Missing `<result>` tag $\rightarrow$ raises `DecisionValidationError`.
   - Empty `<result></result>` tag $\rightarrow$ raises `DecisionValidationError`.
   - Multiple `<result>` tags with conflicting values $\rightarrow$ raises `DecisionValidationError`.
3. **Domain validation by `mode`:**
   - `mode="binary"`: accepts only `"yes"` or `"no"` (case-insensitive); exposes `DecisionResult.as_bool`.
   - `mode="choice"`: accepts only an exact key in `options` or its 1-based index `1..N` (mapped back to the canonical option key).
   - `mode="scale"`: accepts only an integer in `1..5` (or custom `options` integer bounds).

---

## 3. Upstream `mizorewww/laya-mlx` Contribution (`T569` AC3 / AC4, Prepared for Owner Approval)

### 3.1 Fork, Branch & Verification Summary (`T569` AC3)

- **Upstream Repository:** [`mizorewww/laya-mlx`](https://github.com/mizorewww/laya-mlx) (`v0.6.0`, registered in `scripts/w0m_prs.py` `PRESET_REPOS["w0m-pr"]`)
- **Organization Fork:** [`webomage/laya-mlx`](https://github.com/webomage/laya-mlx) (`git@github.com:webomage/laya-mlx.git`, local clone in `w0m-pr/laya-mlx`)
- **Branch & Commit:** `fix/native-serve-tests-and-torchless-calibration` (`baeb7b0d301b278b445eaaaeb816257998a7cd31`, GPG-signed by `Aleksei Tcelishchev <casualuser@gmail.com>` with EDDSA key `952D3D46E7ACF73E27ED11573B58673D024322CF`)
- **Apple M1 Max Metal Verification:**
  - `pytest -q --ignore=tests/test_official_contract.py --ignore=tests/test_official_host.py --ignore=tests/test_parallel_layout.py --ignore=tests/test_snake.py`: **`280 passed, 3 skipped`** in `3.67s`
  - `python -X faulthandler -m pytest -q tests/test_parallel_layout.py`: **`10 passed, 1 skipped`** in `5.27s`
  - `python scripts/audit_public_api.py --package laya_mlx`: **`345 surface entries; 0 unclassified differences`**
  - `ruff check . && ruff format --check .`: **`All checks passed! 125 files already formatted`**

### 3.2 Structured Upstream PR Proposal (`T569` AC4 — Ready for Owner Confirmation)

- **Compare URL:** `https://github.com/mizorewww/laya-mlx/compare/main...webomage:laya-mlx:fix/native-serve-tests-and-torchless-calibration`
- **Proposed Title:** `fix: add native serve contract tests and torchless calibration fallback`

#### Why (Rationale & Problem)
1. **Missing local `tests/test_serve.py` for MLX-specific HTTP server contracts:** `docs/MIGRATION_0_4_17.md` notes that four `test_serve` cases (`test_health_without_a_resident_checkpoint_flags_the_preference`, `test_health_agrees_with_the_mcp_status_tool`, `test_build_router_strips_the_device_before_torch_sees_it`, and `test_thread_limit`) are excluded in `scripts/run_official_test.py` because they assert CUDA/PyTorch device and thread semantics, stating that *"Native device behavior stays in local tests."* Additionally, `laya_mlx/serve.py` explicitly cites `tests/test_serve.py` in five inline contract comments (`lines 165, 171, 185, 958, 1107`), but `tests/test_serve.py` was not present in `tests/`.
2. **`ModuleNotFoundError: No module named 'torch'` in `laya_mlx.calibrate` on pure MLX installs:** Although `laya_mlx/calibrate.py` is otherwise pure NumPy, `_fit_unclamped_temperature` unconditionally imported `torch` to run a 1-parameter scalar LBFGS fit on `log_t`. On a standard Apple Silicon `laya-mlx` installation without PyTorch, calling `fit_one_temperature()`, `fit_temperature_map()`, or running `tests/test_upstream_0412.py::test_ragged_temperature_fit_preserves_real_option_counts` failed with `ModuleNotFoundError: No module named 'torch'`.
3. **Top-level `rich` import in `experiments/snake_runtime.py`:** `PrefixPreparation` only depends on `laya_mlx.prepared.PrefixCache`, but top-level imports of `laya_mlx.snake.replay` pulled in `rich` (`demo` extra), causing `tests/test_upstream_sync.py::test_experimental_prefix_ablation_preserves_runtime_contract` to fail when `[demo]` is not installed.

#### What For (Use Cases & Value)
- Allows Apple Silicon developers and CI environments running pure MLX (`pip install -e '.[dev,serve,mcp,structured]'` without PyTorch or `rich`) to run the native test suite, fit per-bucket calibration temperatures (`fit_one_temperature` / `fit_temperature_map` / `Agent.fit_temperatures`), and verify all native `laya-mlx-serve` device, thread-limit, and wire-contract invariants.

#### How (Implementation, Invariants & Verification)
- **`tests/test_serve.py`:** Adds 12 unit and integration tests covering:
  - Native MLX device preference reporting on `GET /health` (`gpu`, `mps`, `metal`, `cpu`) when no checkpoint is resident (`device_is_preference=True`).
  - Agreement between `GET /health` and `laya_mlx.mcp.tools.laya_status` on `device`, `checkpoint_devices`, and `device_is_preference`.
  - `build_router()` whitespace/newline stripping on `LAYA_DEVICE` and rejection of unsupported PyTorch device strings (`cuda`, `cuda:0`, `rocm`).
  - `_apply_thread_limit()` refusal when `LAYA_THREADS` is set to a positive integer on MLX.
  - Signature partition checks pinning `BODY_CONTROLS`/`BODY_REFUSALS` against `Router.predict` and `BATCH_BODY_CALL_CONTROLS`/`BATCH_BODY_OUT_PARAMETERS`/`BODY_REFUSALS` against `Router.predict_batch`, plus `_state_length` vs `serialize_state`, `_LONE_SURROGATE_DETAIL` on `/v1/systemone` and `/v1/systemone/batch`, and `LIVENESS_ONLY` on `/health`.
- **`laya_mlx/calibrate.py`:** Preserves the exact `torch.optim.LBFGS` path when `torch` is installed (keeping `benchmarks/calibration_roundtrip.py` bit-for-bit identical against upstream), and falls back to a pure-NumPy damped Newton solver on the grouped float32 NLL objective when `torch` is absent. Guards `sys.modules.get("torch")` against `None`.
- **`experiments/snake_runtime.py`:** Moves `LayaPolicy` and `load_record` imports into `main()` so `PrefixPreparation` is importable without `rich`.

---

## 4. Internal Cloudflare Endpoint (`AC8`) & Resume Studio Spot-Check (`AC10`)

- **`AC8` Resolution via Native Cloudflare Workers AI (`@cf/cloudflare/clef-flash`):**
  On 2026-10-19, Cloudflare Workers AI added native `@cf/cloudflare/clef-flash` (9B, ~38.8 ms P50, `$0.09 / 1M` input tokens, `0` output tokens) and `@cf/cloudflare/clef` (27B, ~209 ms P50). Because `clef-flash` runs natively inside Cloudflare Workers AI using our existing `CLOUDFLARE_API_TOKEN` / `env.AI` binding, it satisfies [[T36]] AC2 ("provider set limited to `cloudflare` + `google`; no third-party gateways, no new keys") with **zero paid Cloudflare Containers**.
- **`AC10` Resume Studio (`T501`) Highlight Classification Spot-Check:**
  - `T501` AC6 evaluates 16 real resume bullets across **English (12), Spanish (2), and Russian (2)**.
  - `Von` (`ModernBERT` 395M) is **English-only** per its upstream documentation and is excluded from serving multilingual Resume Studio highlights.
  - `@cf/cloudflare/clef-flash` (multilingual Qwen3.5-9B backbone) and `Laya` multilingual (`mmBERT` 322M, 100+ languages) handle bounded Resume Studio classification questions (`is_bullet`, `shows_devops`, `seniority`, `language`) across all three languages (`EN`/`ES`/`RU`).
