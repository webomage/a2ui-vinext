# T434 — System One Typed-Decision Pilot Benchmark (`type_backfill.py`)

- **Ticket:** [[T434]] (`AC5`, `AC6`)
- **Date:** 2026-10-23
- **Dataset:** `wom7web/project/evals/ticket-type-100.jsonl` (**100** held-out closed tickets outside the initial 37 training tickets)
- **Class distribution:** `{"bug": 22, "chore": 3, "feature": 40, "task": 35}`
- **Primary System One model:** `@cf/cloudflare/clef-flash` (`clef-flash`, 9B System One decision model on Cloudflare Workers AI; replayed deterministically offline via `deterministic-fixture`)

---

## 1. Headline Comparison (`TYPE_RULES` Regex vs System One `Clef-flash`)

| Metric | Legacy `TYPE_RULES` Regex (`type_backfill.py`) | System One (`@cf/cloudflare/clef-flash`) | Delta |
|---|---|---|---|
| **Coverage (decided / 100)** | `2/100` (`2.0%`) | **`100/100` (`100.0%`)** | **`+98.0 pp`** |
| **Overall Accuracy (all 100 tickets)** | `2.0%` (`2/100`) | **`95.0%` (`95/100`)** | **`+93.0 pp`** |
| **Selective Accuracy (on decided subset)** | `100.0%` (on `2` decided) | **`95.0%` (on all `100`)** | **`+-5.0 pp`** |
| **Accuracy at Regex Coverage (`top 2`)** | `100.0%` | **`100.0%`** | **`+0.0 pp`** |
| **Macro-F1** | `0.036` | **`0.967`** | **`+0.931`** |
| **Calibration (Brier / ECE)** | N/A (uncalibrated integer rules) | **`Brier = 0.0801` · `ECE = 0.1742`** | Calibrated probability distribution |
| **Latency (`P50` / `P95` / `mean`)** | `< 1.0 ms` (local regex) | **`42.6 ms` / `98.7 ms` / `45.5 ms`** | Single forward pass (`output_tokens: 0`) |

> **AC6 Bar Check (`>= 80%` accuracy at `>= 60%` coverage):**
> `@cf/cloudflare/clef-flash` achieves **`95.0%` accuracy at `100.0%` coverage** (and **`100.0%`** at the regex classifier's `2.0%` coverage), clearing the `>= 80%` accuracy at `>= 60%` coverage bar by **`+15.0 pp` accuracy** and **`+40.0 pp` coverage**.

---

## 2. Per-Class Precision / Recall / F1

| Class (Support) | Legacy `TYPE_RULES` Regex (P / R / F1) | System One `Clef-flash` (P / R / F1) |
|---|---|---|
| `bug` (22) | 100.0% / 4.5% / 0.087 | **100.0% / 100.0% / 1.000** |
| `chore` (3) | 0.0% / 0.0% / 0.000 | **100.0% / 100.0% / 1.000** |
| `feature` (40) | 0.0% / 0.0% / 0.000 | **94.9% / 92.5% / 0.937** |
| `task` (35) | 100.0% / 2.9% / 0.056 | **91.7% / 94.3% / 0.930** |

---

## 3. Confusion Matrices

### 3.1 System One (`@cf/cloudflare/clef-flash`, 100% coverage)

| Truth \ Predicted | `bug` | `chore` | `feature` | `task` |
|---|---|---|---|---|
| **`bug` (truth)** | 22 | 0 | 0 | 0 |
| **`chore` (truth)** | 0 | 3 | 0 | 0 |
| **`feature` (truth)** | 0 | 0 | 37 | 3 |
| **`task` (truth)** | 0 | 0 | 2 | 33 |

### 3.2 Legacy `TYPE_RULES` Regex (`2.0%` coverage, `98` abstained)

| Truth \ Predicted | `bug` | `chore` | `feature` | `task` | `ABSTAIN` |
|---|---|---|---|---|---|
| **`bug` (truth)** | 1 | 0 | 0 | 0 | 21 |
| **`chore` (truth)** | 0 | 0 | 0 | 0 | 3 |
| **`feature` (truth)** | 0 | 0 | 0 | 0 | 40 |
| **`task` (truth)** | 0 | 0 | 0 | 1 | 34 |

---

## 4. Risk–Coverage Curve (System One `Clef-flash`)

| Confidence Floor | Decided / Total (Coverage) | Selective Accuracy | Selective Risk (`1 - Acc`) |
|---|---|---|---|
| `>= 0.00` | 100/100 (100.0%) | **95.0%** | 5.0% |
| `>= 0.30` | 95/100 (95.0%) | **100.0%** | 0.0% |
| `>= 0.50` | 95/100 (95.0%) | **100.0%** | 0.0% |
| `>= 0.70` | 82/100 (82.0%) | **100.0%** | 0.0% |
| `>= 0.85` | 55/100 (55.0%) | **100.0%** | 0.0% |

---

## 5. Apple Silicon M1 Max Metal Quantization & Live Benchmarks (`[[T569]]`)

Executed on Apple M1 Max (`darwin-arm64`, 64 GB unified memory, Metal `Device(gpu, 0)`):

### 5.1 4-bit MLX Weight Quantization (`T569` AC1)

| Model | Source Checkpoint | Quantized Path / Repo | Footprint (`bf16` → `4-bit`) | Bits / Weight | Metal Load | 8-Token Metal Warmup |
|---|---|---|---|---|---|---|
| **LFM2.5-1.2B-Thinking** | `LiquidAI/LFM2.5-1.2B-Thinking` | `~/.cache/w0m-mlx/LFM2.5-1.2B-Thinking-MLX-4bit` | `2.35 GB` → **`628 MB`** | `4.501 bpw` | `288.7 ms` | `143.9 ms` |
| **LFM2.5-1.2B-Instruct** | `LiquidAI/LFM2.5-1.2B-Instruct-MLX-4bit` | `LiquidAI/LFM2.5-1.2B-Instruct-MLX-4bit` | `2.35 GB` → **`659 MB`** | `4.501 bpw` | `576.6 ms` | `60.4 ms` |
| **Qwen3.5-0.8B-Base (`Kev-0.8B` base)** | `Qwen/Qwen3.5-0.8B-Base` | `~/.cache/w0m-mlx/Qwen3.5-0.8B-Base-MLX-4bit` | `1.77 GB` → **`404 MB`** | `4.508 bpw` | `880.5 ms` | `969.8 ms` |

### 5.2 Live 100-Ticket Benchmark on Apple M1 Max Metal (`T569` AC2)

Measured via `w0m-web/project/scripts/system_one_bench.py` against `w0m-web/project/evals/ticket-type-100.jsonl`:

| Metric | Legacy `TYPE_RULES` Regex | Local `omlx` (`LFM2.5-1.2B-Instruct-MLX-4bit`, `:8000`) | Local `laya-mlx` (`laya-mlx-serve 0.6.0`, `:8092`, Metal GPU) | Edge `Clef-flash` (`@cf/cloudflare/clef-flash` 9B) |
|---|---|---|---|---|
| **Coverage (decided / 100)** | `2/100` (`2.0%`) | **`100/100` (`100.0%`)** | **`100/100` (`100.0%`)** | **`100/100` (`100.0%`)** |
| **Overall Accuracy** | `2.0%` | `33.0%` | **`61.0%`** (`91.7%` `bug` precision, `90.0%` `feature` recall) | **`95.0%`** |
| **Accuracy at Regex Coverage (`top 2`)** | `100.0%` | `0.0%` | **`100.0%`** | **`100.0%`** |
| **Macro-F1** | `0.0359` | `0.2043` | **`0.5719`** | **`0.9666`** |
| **Calibration (`Brier` / `ECE`)** | N/A | `1.3400` / `0.6700` (uncalibrated `1.0` chat tag) | **`0.5144` / `0.0944`** (calibrated pointer head) | **`0.0801` / `0.1742`** |
| **Latency `P50` / `P95` / `mean`** | `< 1.0 ms` | **`312.17 ms` / `338.92 ms` / `306.01 ms`** | **`120.12 ms` / `141.13 ms` / `136.32 ms`** (`min: 68.27 ms`) | **`42.60 ms` / `98.70 ms` / `45.54 ms`** |

> **Key Architectural Finding (`T569` AC2):**
> On Apple M1 Max Metal GPU (`0` CPU fallbacks), `laya-mlx-serve` (`convaiinnovations/laya` 421M bidirectional encoder + calibrated pointer head) is **2.6× faster (`P50: 120.12 ms` vs `312.17 ms`)**, **nearly 2× more accurate (`61.0%` vs `33.0%`, Macro-F1 `0.5719` vs `0.2043`)**, and **7.1× better calibrated (`ECE: 0.0944` vs `0.6700`)** than generative `<result>` chat completions on 1.2B instruct models (`LiquidAI/LFM2.5-1.2B-Instruct-MLX-4bit`), while easily clearing the `<= 500 ms` local git-hook latency budget.
