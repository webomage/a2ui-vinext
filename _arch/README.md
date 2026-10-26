# _arch — soft-delete bin

The recycle bin for the w0m estate workspace. When something looks safe to delete but
you'd rather not lose it outright, `mv` it here instead of `rm`. Gitignored (this
README is the one tracked exception, same pattern as `_in/` and `_msg/`), so nothing
landing here touches any of the seven repos or estate history.

Not a permanent archive — periodically empty it once its contents are confirmed dead.
Give each moved item its own subfolder named for what it was, so provenance survives
the move without needing this file to enumerate contents.

## Current contents

- `ds_arc/` — extracted copies of five divergent "Webomage Design System" Claude
  Design canvas exports (2026-07-11 to 2026-07-14). Superseded: diffed file-by-file
  against `w0m-web/design-system/` (2026-09-08) and confirmed fully absorbed except
  two tech icons and a `templates/cv/` template, which were pulled into the repo.
- `ds_arc_pack/` — the zip form of the same five exports.
- **T519 (Group D — 8 retired one-off scripts, 2026-10-25):**
  - `update-system-status/` (`w0m-api/scripts/update_system_status.py` + `apps/{web,cp}/src/data/status.json`)
  - `env-rename-migrate/` (`w0m-web/project/scripts/env_rename_migrate.py`)
  - `fix-diagrams/` (`w0m-api/scripts/fix_diagrams.mjs`, `w0m-web/scripts/fix_diagrams.mjs`)
  - `fix-missing-prompts/` (`w0m-api/scripts/fix_missing_prompts.py`)
  - `check-upwork-proposal/` (`w0m-api/scripts/check_upwork_proposal.py`)
  - `gen-codemap-mmd/` (`w0m-web/project/scripts/gen_codemap_mmd.py`)
  - `gen-tracks-artifacts/` (`w0m-api/scripts/gen_tracks_artifacts.py`)
  - `validate-rust-vs-python/` (`w0m-web/project/scripts/validate_rust_vs_python.py`)
- **T517 (Group B — 9 scripts folded into existing tools, 2026-10-25):**
  - `verify-t440-live/` (`w0m-web/project/scripts/verify_t440_live.py` -> `scripts/live_verify_helper.py t440`)
  - `verify-t443-founder-units/` (`w0m-web/project/scripts/verify_t443_founder_units.py` -> `scripts/live_verify_helper.py t443`)
  - `verify-t444-site-settings/` (`w0m-web/project/scripts/verify_t444_site_settings.py` -> `scripts/live_verify_helper.py t444`)
  - `t352-fallback-hat-probe/` (`w0m-web/project/scripts/t352_fallback_hat_probe.py` -> `w0m-web/project/scripts/authz_probe_suite.py` `X43`–`X46`)
  - `verify-siri-shortcuts-contract/` (`w0m-web/project/scripts/verify_siri_shortcuts_contract.py` -> `scripts/zeroclaw_manage.py health`)
  - `verify-cf-ai/` (`w0m-api/scripts/verify_cf_ai.py` -> `w0m-api/scripts/healthcheck.py` `w0m-llm-personnel`)
  - `fetch-upwork/` (`w0m-api/scripts/fetch-upwork.js` -> `scripts/upwork_poller_status.py` / `just upwork-poller-status`)
  - `test-obsidian-mcp/` (`w0m-web/project/scripts/test_obsidian_mcp.py` -> `scripts/tests/test_obsidian_mcp.py` / `just obsidian-mcp-bridge-test`)
  - `security-audit/` (`w0m-api/scripts/security_audit.py` -> `w0m-web/scripts/pre-commit` + `.pre-commit-config.yaml`)
- **T518 (Group C — 2 retired/folded scripts per owner decisions 2026-10-25):**
  - `smoke-test/` (`w0m-api/scripts/smoke_test.py` -> `scripts/live_verify_helper.py crawler-smoke` / `just smoke-live`)
  - `index-internal-docs/` (`wom7api/scripts/index_internal_docs.py` — retired per owner decision 2026-10-25)
