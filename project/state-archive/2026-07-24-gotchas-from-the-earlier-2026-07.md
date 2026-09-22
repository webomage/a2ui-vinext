<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 🔴 Gotchas from the earlier 2026-07-24 session (still true) -->

### 🔴 Gotchas from the earlier 2026-07-24 session (still true)

- **osv-scanner advisory-refresh blocks ALL commits.** The advisory DB updated and newly flagged
  `postcss@8.5.15` (GHSA-r28c-9q8g-f849) + `tar@7.5.19` (GHSA-r292-9mhp-454m). Fixed via the
  **`pnpm.overrides`** block in wom7api (`bc009f7`) + wom7web (`2afe9be3`) → clean. **Other repos
  (wom7cfworkers/ext/sec/mlx) will hit the same on their next commit** — bump via their overrides,
  and raise the **deps-policy floor (T112)** so it's ecosystem-wide, not per-repo whack-a-mole.
- **`wom7skills` now needs `pnpm install`** (TS toolchain) — a fresh clone must run it before the
  `skills-drift` hook / `just skills-sync` work. `.infisical.json` is gitignored per convention, so
  fresh clones recreate it (the re-clone gotcha — worth deciding to commit it; it holds no secret).
- **Still genuinely open (security, unticketed):** `get-upwork-status` (ungated Upwork read) +
  `get-admin-metrics` (`!==` non-constant-time key compare — reuse `_shared/auth.ts` `constantTimeEqual`).
