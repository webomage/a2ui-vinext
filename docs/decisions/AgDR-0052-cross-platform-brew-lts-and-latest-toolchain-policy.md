---
id: AgDR-0052
title: "Cross-platform toolchain & dependency currency governance: Homebrew primary manager, LTS floor, and latest comparison"
timestamp: 2026-11-01T03:29:00-05:00
agent: antigravity
model: gemini-4-argon
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T595
---

# AgDR-0052 — Cross-platform toolchain & dependency currency governance: Homebrew primary manager, LTS floor, and latest comparison

## Y-statement

> In the context of **operating the `@wom` estate and client workspaces (`bridgeroad-w0m`) across heterogeneous developer and agent hosts (`darwin-arm64` MacBook Pro and `linux-x86_64` Ubuntu `HP`) under [[T595]]**, facing **(1) restrictive upper-bound runtime pins (`engines.node: ">=22.23.3 <23"`) that reject current Homebrew `node` (`26.13.0`) and force deprecated keg-only `node@22` workarounds, and (2) fragmented per-language version managers (`nvs`, `fnm`, `pyenv`, `tfenv`) whose shims disappear across non-interactive agent shells**, we decided **to (1) mandate that all tools and packages maintain a minimum version (`min`) at or above active LTS while tracking and comparing against `latest` stable (`known_good`), lifting artificial major upper-bound caps (`<23`) once verified against the latest release, and (2) standardize on Homebrew (`brew` on both macOS `/opt/homebrew` and Linux `/home/linuxbrew/.linuxbrew`) as the preferred cross-platform package manager with cross-host version comparison**, to achieve **a unified, predictable, cross-platform toolchain where both macOS and Linux hosts run current stable/LTS tooling without shim drift or false-red preflight gates**, accepting **that major Homebrew formula upgrades (e.g. Node 22 → 26, Python 3.12 → 3.15) arrive rolling with `brew upgrade` and must be validated against `known_good` and `just tools-check` / `just deps-check` across connected hosts**.

## Context

Measured on 2026-11-01 while provisioning the reset macOS host (`proto@MacBook-Pro-de-Aleksei.local`, `darwin-arm64`) alongside the active Linux host (`aleksei@HP` / `192.168.0.95`, Ubuntu `linux-x86_64`):

1. **Restrictive `<23` Node cap vs Homebrew Latest (`26.13.0`)**:
   - `project/policies/deps-policy.json` (`runtime.engines.node`) and `w0m-web`, `w0m-api`, `w0m-cf` `package.json` pinned `"node": ">=22.23.3 <23"`, while `project/policies/tools-policy.json` already recorded `known_good: "24.17.0"` and `source: "nvs"`.
   - On macOS, default `brew install node` installs `26.13.0`, whereas `brew install node@22` (`22.23.4`) is keg-only and emits a Homebrew deprecation warning (`node@22 has been deprecated because it is in maintenance and will be end-of-life on 2027-04-30`).
   - Meanwhile, on the Linux host (`HP`), Node `22.23.3` was installed via `fnm` (`~/.local/share/fnm`), while `tools-policy.json` still claimed `source: "nvs"`.
2. **Shim fragmentation across macOS and Linux**:
   - `tools-policy.json` previously split 37 tools across 9 different sources (`brew`, `nvs`, `pyenv`, `tfenv`, `rustup`, `uv`, `uv-tool`, `pnpm`, `npm`). Several entries (`ast-grep`, `mypy`) already documented incidents where `pyenv` or language-manager shims vanished when switching interpreters or running inside non-interactive agent subshells.
   - Homebrew (`brew`) runs natively on both macOS (`/opt/homebrew`) and Linux (`/home/linuxbrew/.linuxbrew`, already installed on `HP`) and provides a single cross-platform CLI and bottle ecosystem.
3. **Measured Cross-Host Baseline (2026-11-01)**:

| Tool | Required | Policy `min` (LTS Floor) | Previous `known_good` | Mac (`brew` Latest) | Linux (`HP` Installed) | Target `source` |
|---|---|---|---|---|---|---|
| `node` | Yes | `22.23.3` (LTS) | `24.17.0` | `26.13.0` | `22.23.3` | `brew` |
| `python3` | Yes | `3.12.0` (LTS) | `3.12.9` | `3.15.2` | `3.15.0` | `brew` |
| `deno` | Yes | `2.0.0` | `2.9.3` | `2.9.8` | `2.9.7` | `brew` |
| `just` | Yes | `1.40.0` | `1.58.0` | `1.59.0` | `1.58.0` | `brew` |
| `uv` | Yes | `0.5.0` | `0.13.4` | `0.13.6` | `0.13.4` | `brew` |
| `gh` | Yes | `2.60.0` | `2.103.0` | `2.103.3` | `2.103.0` | `brew` |
| `infisical` | Yes | `0.40.0` | `0.44.6` | `0.44.11` | `0.44.6` | `brew` |
| `supabase` | Yes | `2.100.0` | `2.113.0` | `2.122.0` | `2.121.0` | `brew` |
| `semgrep` | Yes | `1.100.0` | `1.182.0` | `1.183.0` | `1.182.0` | `brew` |
| `gitleaks` | Yes | `8.20.0` | `8.30.1` | `8.30.1` | `8.30.1` | `brew` |
| `osv-scanner` | Yes | `2.0.0` | `2.7.0` | `2.7.0` | `2.7.0` | `brew` |
| `jq` | Yes | `1.6` | `1.8.2` | `1.8.2` | `1.6` | `brew` |
| `ast-grep` | No | `0.38.0` | `0.51.0` | `0.51.0` | `0.51.0` | `brew` |
| `cargo` / `rustc` | No | `1.95.0` | `1.98.1` | `1.99.1` | — | `brew` / `rustup` |
| `graphify` | No | `0.9.30` | `0.9.92` | `0.9.100` | `0.9.92` | `uv` |

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **O1 — Keep per-language managers (`nvs`, `fnm`, `pyenv`, `tfenv`) and strict `<23` major upper bounds** | Isolates exact point releases per language. | Breaks non-interactive shells when shims are missing; forces deprecated keg-only `node@22` on macOS; creates 3-way drift (`nvs` in policy vs `fnm` on Linux vs `brew` on Mac). | **Rejected** |
| **O2 — Pin strictly to `latest` only (`>=26.13.0`), rejecting LTS hosts** | Forces every machine onto the newest release immediately. | Breaks valid LTS environments (`HP` on `22.23.3`) until manually upgraded; conflates minimum compatibility floor with latest upstream target. | **Rejected** |
| **O3 — Standardize on Homebrew (`brew`) across macOS & Linux, enforce `min >= LTS`, and track/compare against `latest` (`known_good`)** | Works identically on macOS (`/opt/homebrew`) and Linux (`/home/linuxbrew/.linuxbrew`); guarantees every host is at least on active LTS (`>=22.23.3`) while comparing against `latest` (`26.13.0`) via `just tools-check` and `just tools-outdated`. | Rolling `brew` updates can introduce new major versions, requiring `known_good` promotion and smoke verification (`just tools-weekly` / `just tools-promote`). | **Accepted ([[T595]])** |

## Decision

1. **LTS Floor + Latest Comparison Rule (All Tools & Packages)**:
   - Every tool in `project/policies/tools-policy.json` and package/runtime in `project/policies/deps-policy.json` MUST set its minimum floor (`min` / `floors`) to **at least the active LTS release** (e.g. Node `>=22.23.3`, Python `>=3.12.0`).
   - Upper-bound major caps (`<23`) on `engines.node` are removed (`>=22.23.3`) so both LTS (`22.x` / `24.x`) and current stable (`26.x`) satisfy the runtime range, while `.nvmrc` and `known_good` track the latest verified release (`26.13.0`).
   - `just tools-check` and `just tools-outdated` compare the installed version against both `min` (LTS floor) and upstream `latest` / `known_good`.
2. **Homebrew (`brew`) as Preferred Cross-Platform Package Manager**:
   - Homebrew (`/opt/homebrew` on macOS, `/home/linuxbrew/.linuxbrew` on Linux) is the canonical package manager for host CLI tools and runtimes (`node`, `python3`, `deno`, `just`, `uv`, `gh`, `infisical`, `supabase`, `semgrep`, `gitleaks`, `osv-scanner`, `jq`, `ast-grep`, `pnpm`, `ruff`, `mypy`, `terraform`).
   - Legacy `source` declarations (`nvs`, `pyenv`, `tfenv`, `pip`) in `project/policies/tools-policy.json` are migrated to `brew`.
   - Isolated ecosystem tools that do not publish core Homebrew bottles (`openspec` via `pnpm`) remain on their respective cross-platform tool runners and are compared alongside `brew` formulae.
3. **Patched First-Party Forks (`webomage/<repo>@beta`) & Canonical Homebrew Tap (`webomage/tap`)**:
   - For every open-source tool where `@wom` maintains custom features, fixes, or upstream PRs (`headroom`, `omlx`, `orca`, `graphify`, `serena`, `mlx-vlm`, `laya-mlx`, `tart-guest-agent`, `virtual-fido` under `github.com/webomage/<repo>` in `w0m-pr/`), the fork MUST maintain a **`beta` integration branch** that is continuously aligned to the **latest official upstream release / default branch** with all open `webomage` PR branches rebased/merged on top (authored and GPG-signed `-S` by `casualuser` with zero `Co-Authored-By` trailers).
   - All patched tools are published to and installed from the canonical organization Homebrew tap **`webomage/tap`** (`github.com/webomage/homebrew-tap`, never personal `casualuser/tap` or third-party taps like `jundot/omlx`) using `<latest_upstream_version>-w0m` versioning, `url "https://github.com/webomage/<repo>.git", branch: "beta"`, `skip_clean "libexec"`, and ad-hoc Mach-O code signing (`codesign --force --sign -`) in `post_install` so local macOS 27 (`arm64_golden_gate`) installations run natively without requiring Apple Developer certificate resigning or notarization.
   - `just tap-sync` (`scripts/w0m_prs.py tap-sync`) audits and synchronizes the `w0m-pr/*` `beta` branches against upstream releases and updates `webomage/homebrew-tap` formulae.

## Consequences

- **Positive:** Fresh macOS and Linux hosts provisioned via `brew install` work out of the box with `node` (`26.13.0`), `python3` (`3.15.2`), and all 12 required preflight tools without shim configuration or keg-only formula workarounds.
- **Positive:** Both LTS (`>=22.23.3`) and Latest (`26.13.0`) hosts pass `just preflight --fast` and `just deps-check`, while `just tools-check` surfaces exact version drift between hosts and latest Homebrew releases.
- **Negative / Trade-off:** Because `brew` tracks latest stable releases by default, `known_good` in `tools-policy.json` must be promoted when Homebrew updates formulae (`just tools-check --update-known-good` / `just tools-promote`).

## What this does NOT decide

- Does not change Cloudflare Workers production `compatibility_date` (`2026-05-06`) or `nodejs_compat` flags in `wrangler.jsonc` (which govern the remote edge `workerd` runtime rather than the local host CLI).
