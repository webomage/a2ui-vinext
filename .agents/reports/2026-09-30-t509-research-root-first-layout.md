> Preserved copy of read-only deep research (2026-09-30). Ticket: [[T509]]; the 37 no-caller scripts were split to [[T516]], [[T517]], [[T518]], [[T519]]; the token finding is [[T515]] (closed). Verbatim except one neutralised fragment.

# Root-first migration research (read-only, 2026-09-30)

Scope: should more helper scripts, recipes, tests and data move from `wom7web` and `wom7api` UP to the workspace root `@wom`?
Method: everything measured from the root with `just search`, `just --dump --dump-format json`, `git -C <repo> ls-files`, and small throwaway Python scanners that live ONLY in the session scratchpad (nothing was written to any repo). Classification of scripts is name-independent (based on what each file reads, writes and assumes about cwd), but it is a one-pass human+heuristic classification, so treat per-class counts as +-5 files and recipe counts as +-10%.

---------------------------------------------------------------------------------------------------

## 1. Summary

1. The estate is half-moved. T414 (2026-09-21) elevated 64 scripts to `@wom/scripts/` and ~19 policy files to `@wom/project/policies/`, but left (a) 76 further estate-wide scripts in `wom7web/project/scripts` (72) and `wom7api/scripts` (4), (b) 26 test modules for root scripts still in `wom7web/project/scripts/tests/`, (c) one justfile that really lives in `wom7api` and is shadowed by symlinks in three repos, and (d) 24 shadow symlinks of estate files in `wom7web` (19 policies, 2 templates, `.w0m/sdlc.json`, `TASKS.md`, untracked `.tasks`) that AgDR-0025 (written for T414 itself) forbids.
2. Classification of the 232 top-level script files: **A (estate-wide, belongs at root) = 76 (33%)**, **B (genuinely repo-specific) = 142 (61%)**, **C (ambiguous) = 14 (6%)**. Tests: 120 modules, of which 68 test class-A/root scripts, 43 test B, 9 are C/infra. The A set has ~294 external reference sites (recipes, hooks, JSON registries, other scripts, tests).
3. Recipes: of 614 recipes in `wom7api/justfile` ~290 are estate-level (A), 295 repo-specific (B), 29 ambiguous (C). **414 have no root entry; 121 of those are class A.** 143 recipe names are defined in BOTH justfiles with different bodies (a dual SSOT: 132 of them are A). 17 `wom7api` recipes forward back to the root (reverse forwarders).
4. Root has 65 pure forwarders: 35 point at class-A targets (would vanish on a clean cutover), 17 at B targets (stay), 4 at C, and **8 are dangling today** (`just sdlc-start` ... `sdlc-archive` forward to recipes that do not exist in `wom7web/justfile`; confirmed by running one). `justfile-calls-check` is blind to this because it skips every call that carries `--justfile`.
5. A stale-path probe is feasible and would have caught T414. A prototype scan (scratchpad only) found **8 stale script paths in recipes, ~20 in JSON policy/profile files (after resolving the 19 symlinks; 3 are false positives from skill-shipped scripts), 50+ stale `python3 project/scripts/x.py` usage lines in root script docstrings**. No existing gate checks script-file existence (they all check recipe existence).
6. Biggest hidden risks of going root-first: (i) the root repo is invisible to `just search` (`--repo root` -> BLOCKED) and to `just ask` / the graphify union (no `.codegraph/`, `graphify-out` empty, `graph_global.REPOS` lists 7 repos but not the root), so every script moved to root leaves the code graph; (ii) the root has no mypy gate and the only pre-push hook lives in `wom7web/.husky`, so a root or wom7api push runs none of the 25 pre-push gates; (iii) 5 launchd agents on the host embed `cd .../wom7api && just X` / `cd .../wom7web && just audit`; (iv) 50 prose/hook references to `cd wom7api && just` in 4 repos plus the `/w0m-*` slash commands.
7. Recommendation: **staged by area (O2), preceded by the stale-path probe (O3 is simply its unit U0)**, in 9 one-session units; each unit a clean cutover (callers updated atomically, no shim, no symlink), executed in an isolated worktree because the shared tree is dirty. Do NOT use `just` modules or forwarders as a facade (that is the shim AgDR-0025 rejects).

---------------------------------------------------------------------------------------------------

## 2. Evidence

### 2.1 Layout facts (measured)

| fact | value | source |
|---|---|---|
| root `justfile` | 1064 lines, 252 recipe heads (263 incl. private/aliases via `--dump`) | `justfile`, `just --dump` |
| `wom7api/justfile` | 4820 lines, 571 heads (614 via `--dump`) | |
| symlinked justfiles | `wom7web/justfile`, `wom7func/justfile`, `wom7authz/justfile` -> `../wom7api/justfile` (git mode 120000 in wom7web and wom7func) | `ls -l`, `git ls-files -s` |
| repos with own justfile | wom7ext (176 lines), wom7sec (39), wom7mlx/wom7mlx (163); wom7skills, wom7pr: none | |
| scripts (top-level files) | root 64 .py (+18 tests); wom7web/project/scripts 172 files (+111 test modules, conftest, fixtures); wom7api/scripts 60 files (+10 in `archive/`, +9 tests) | `ls`, `find` |
| root-script references to web | 63 lines in root `justfile` name `wom7web/project/scripts/...` (mostly `tests/test_*.py`), 1 names `wom7api/scripts/` | `grep -oE` on `justfile` |
| `wom7api/justfile` coupling | 324 lines `cd ../wom7web`; 79 `../scripts/`; 73 bare `scripts/`; 292 lines mention `project/scripts/`; `justfile_directory()` used 3 times total | grep |
| recipe cwd classes (api justfile) | 318 recipes `cd ../wom7web`, 76 run root scripts via `../scripts/`, 93 are wom7api-cwd-dependent (bare `supabase/`, `src/`, `pnpm`, `deno`, `wrangler`), 127 no filesystem path | scanner |
| pre-push hook | exists ONLY at `wom7web/.husky/pre-push` (524 lines, 25 registered steps in `scripts/prepush_runner.py`). wom7api, wom7func, wom7ext, wom7sec, wom7skills, wom7mlx and the root have commit-msg/pre-commit/post-* but no pre-push | `ls .git/hooks`, `core.hooksPath` |
| host launchd | 5 agents (`com.w0m.{audit-daily,backup-daily,backup-weekly,schema-weekly,tools-weekly}`) each `cd .../wom7api && just <r>` (audit-daily: `cd .../wom7web && just audit`); declared in `wom7web/project/launchd/schedules.jsonc` (`"cwd"` keys) | `~/Library/LaunchAgents`, `schedules.jsonc` |
| SessionStart hook | `.claude/settings.local.json` runs `wom7web/project/scripts/preflight.py --fast --hook` and `scripts/state_doctor.py --brief` (file is globally gitignored, unversioned) | `.claude/settings.local.json` |
| `.mcp.json` | server `obsidian-wom7web` -> `wom7web/project/scripts/obsidian_mcp_bridge.py` | `.mcp.json:14` |

### 2.2 T414 residue (what the stale-path probe would have caught)

* 20 policy JSON hits (unique after symlink resolution), e.g. `project/policies/emoji-policy.json:213-222` six `discovery_exempt` keys (`project/scripts/tasks_query.py:1120`, `tools_check.py:329`, ...) that now point at files living in `scripts/` — a probable **functional** stale reference: the keys no longer match the sites' current paths (`scripts/...`), yet `just emoji-check` still reports OK, so either those lines no longer trigger or the exemptions are dead (not measured further). Also `.w0m/sdlc.json:25` (`"sync": "project/scripts/sync_github.py"`), `:530-541` (versioning exemptions keyed by old paths `project/scripts/w0m_audit.py`, `wom7web/project/scripts/prepush_runner.py`, `.../sync_manifest_versions.py`), `_comment` prose in stacks/ide/tools/hygiene/deps policies. 3 more hits are skill-shipped scripts (`scripts/idea-refine.sh`, ...) = false positives.
* 8 stale recipes in `wom7api/justfile`: `check-post-images`, `check-titles`, `infra-jumphost-dns`, `migrate-ext-data`, `model-serve`, `oci-env-sync`, `oci-vm-apply` (script files do not exist anywhere), and `project-vault-init` (runs bare `python3 project/scripts/init_project_vault.py`, which resolves only when invoked from `wom7web`).
* 8 dangling root forwarders (`sdlc-{start,spec,build,review,security,verify,deploy,archive}`), plus `do` forwards dynamically.
* 50+ usage lines in moved scripts' docstrings still say `python3 project/scripts/<name>.py` (`discovery.py`, `host_posture.py`, `ide_trace.py`, `mcp_health.py`, `repo_hygiene.py`, `sync_github.py`, `ticket_audit.py`, `ticket_duplicate_check.py`, `ticket_recycle.py`, `tools_check.py`, `tools_upgrade.py`, `w0m_audit.py`, ...), plus lockstep comments `wom7api/scripts/sdlc_doctor.py` in `state_doctor.py:82,151`.
* A duplicated, **divergent** test: `scripts/tests/test_agent_concurrency.py` and `wom7web/project/scripts/tests/test_agent_concurrency.py` (differ in the SCRIPTS path). Root recipe `agent-concurrency-test` runs the web copy; the api recipe runs the same web copy via `cd ../wom7web`; the root copy has no caller.
* 24 shadow symlinks of estate files in wom7web (19 `project/*-policy*` -> `../../project/policies/`, `project/templates/{ticket,decision}.md`, `TASKS.md`, `.w0m/sdlc.json`, untracked `.tasks`; 25 tracked symlinks in total incl. `justfile` and `apps/web/specs`) and the wom7api/root `.agent/.codex/.gemini/.kilocode/.claude/commands` symlinks. AgDR-0025 (accepted, ticket T414) says "Zero Shadow Symlinks".
* Root scripts still read estate data from `wom7web/project/`: `tickets.json` (4 root readers), `tickets-sync-index.json` (2), `tickets-schema.jsonc` (2), `test-suites.json` (`run_suites.py:43` `WEB/project/test-suites.json`), `tasks-rotation.json`, `dod-baseline.json`, `spec-standard-baseline.json`, `suite-uncounted-baseline.json`, `security-state.json`, `paused/` (8 root readers), `templates/`, `launchd/`, `.tools-*.json`. 20 root scripts hardcode `WEB = ROOT / "wom7web"`.

### 2.3 Existing gates (read, do not duplicate)

| gate | what it checks | covers script-path existence? |
|---|---|---|
| `scripts/justfile_calls_check.py` (117 lines, `just justfile-calls-check`) | every bare `just <recipe>` in a recipe body resolves in that justfile | No. Skips `--justfile/-f/-d` and anything after `cd X &&` (lines 24-26, `DELEGATING_FLAGS`), which is exactly why the 8 dangling forwarders pass. Runs on root + wom7api justfiles, green today (13 + 12 calls) |
| `scripts/ac_recipe_check.py` (198 lines; root pre-commit hook `ac-recipe-check`, `files: ^\.tasks/T\d+\.md$`) | a TICKED AC may not cite a missing recipe; acknowledged exceptions printed each run | No (recipes only, tickets only) |
| `scripts/discovery.py --enforce` (invoked by `sdlc_doctor.check_stacks`) | every declared command role binds a real recipe | No |
| `wom7web/project/scripts/decommission_check.py` (+ `DECOMMISSIONED.md`) | tombstoned symbols/paths must stay GONE (reverse direction) | No (asserts absence, not presence) |
| `wom7web/project/scripts/rename_audit.py` | one-shot 5-surface search for an OLD NAME | Partially: only if you know the old name; not a standing gate |
| `scripts/hooks_check.py`-equivalent in web (`hooks_check.py`) | declared hooks are wired | No |
| `scripts/emoji_policy_check.py` | `discovery_exempt` keyed by `file:line` | No - and its keys went stale (2.2) |
| `suites-drift` (`scripts/run_suites.py --drift`) | every `*-test`/`*-check` recipe is in `test-suites.json` | recipe level only |

Conclusion: five gates check "recipe exists"; none checks "the file this recipe/hook/profile runs exists".

### 2.4 Classification method

A script is **A** when its inputs/outputs are estate-level (tickets, TASKS/STATE/ROADMAP, `.w0m/sdlc.json`, policy JSON, every repo's git state, host tooling, MCP/graph/headroom/launchd, GitHub board, deploy/confirm machinery) and it names no single repo's app code, migrations, edge functions, worker or Astro apps. **B** when it reads or writes `apps/**`, `packages/**`, `supabase/migrations|functions`, `src/` of the worker, a live-database probe (BEGIN READ ONLY ... ROLLBACK), CV/Upwork data, Quartz/Obsidian vault of wom7web, design-system tokens. **C** when it straddles (estate input, repo-specific output, or one-off/retire-candidate).

---------------------------------------------------------------------------------------------------

## 3. Classification tables

### 3.1 Counts

| set | A | B | C | total |
|---|---:|---:|---:|---:|
| wom7web/project/scripts (top-level files) | 72 | 90 | 10 | 172 |
| wom7api/scripts (top-level files) | 4 | 52 | 4 | 60 |
| **scripts total** | **76** | **142** | **14** | **232** |
| wom7api/scripts/archive/ (dead) | - | 10 | - | 10 |
| web tests (111 modules) | 41 + 26 (tests of scripts ALREADY at root) = 67 | 37 | 6 + 1 infra (`conftest.py`) | 111 |
| api tests (9 modules) | 1 (`test_check_ticket_paths.py`, subject already at root) | 6 | 2 | 9 |
| recipes in wom7api/justfile (614) | ~290 | ~295 | ~29 | 614 |
| ... of which no root entry (414) | ~121 | ~271 | ~22 | 414 |
| ... of which defined in both justfiles with different bodies (143) | ~132 | ~8 | ~3 | 143 |

Sub-split of class B (to show most "B" is not web or api internals but a DB-probe pile in the wrong repo): 58 wom7web scripts are live-database/authz/RLS probes (`authz_*` x18, `org_*`, `s3_delete`, `s5_merge`, `profile_*`, `t210/t254/t349/t352`, `verify_t4*`, `anon_*`, `db_drift_check`, `db_migrate`, `drop_caller_gate`, `lookup_index_gate`, `schema_drizzle_drift`, ...) whose natural home is wom7api (or `wom7authz`), 32 are wom7web app/docs/CV/Upwork/Quartz/DS tooling, 17 wom7api scripts are DB/backup/ops, 35 wom7api scripts are legacy content/Upwork/Cloudflare helpers. Moving the 58 to wom7api is a **separate** concern from root migration (they are B, not A), but it is the same `cd ../wom7web` hack in reverse and should be a later unit.

Dead weight: 37 top-level scripts have **zero** references from any recipe, hook, JSON registry or other script (candidates for deletion, not migration): web `backfill_upwork_proposals`, `ds_inventory`, `env_rename_migrate` (one-shot, finished), `graph_callsites`, `status_truth`, `t352_fallback_hat_probe`, `test_obsidian_mcp`, `verify_siri_shortcuts_contract`, `verify_t440_live`, `verify_t443_founder_units`, `verify_t444_site_settings`, `write_hygiene_docs`, `zc_compression_measure`, `zeroclaw_manage`; api `__init__`, `ai-eval.ts`, `backfill_news`, `backfill_post_images`, `check-upwork-proposal.js`, `fetch-upwork.js`, `fix_diagrams.mjs`, `fix_missing_prompts`, `gen_codemap_mmd`, `gen_tracks_artifacts`, `get_keys`, `get_upwork_auth.ts`, `index_internal_docs`, `infisical_set_prod`, `init_tinybird_schemas`, `resume-assist-eval.ts`, `security_audit`, `smoke_test`, `update_system_status`, `validate_content`, `validate_rust_vs_python`, `validate_tracks`, `verify_cf_ai` (+ `codesignal.html`, `rsc.json`, `t251_purge_test_chats.sql`: junk/one-off). Also, **security finding**: `wom7api/scripts/init_tinybird_schemas.py` (tracked) contains a hardcoded bearer-style token literal (a bearer-style token assignment; value not reproduced). Value deliberately not reproduced; owner should rotate the Tinybird token and delete or rewrite the script.

### 3.2 Class A scripts (76) by area, with why

Why A for all rows: they read only estate-level files (root registers, `.w0m/`, policies, every repo's git/host state), or they are the estate's own gate/host machinery; none touches one repo's app code. Marker `[root-ready]` = already referenced only from root recipes/hooks, so moving is cheapest; `[orphan]` = zero references (delete or move with a decision).

**SDLC / tickets / GitHub board (17):** `tickets_frontmatter_sync` (already a ROOT pre-commit hook, script still in web), `populate_project_fields`, `sync_project_fields`, `sync_subissues`, `sync_epic_vocabulary`, `epic_completeness`, `type_backfill`, `ticket_id_align_check`, `backfill_tickets`, `status_truth [orphan]`, `state_bounds`, `board_identity`, `close_legacy_tracker_issues`, `stage_guard`, `decisions_index` (already a ROOT pre-commit hook), `changelog_drift`, `push_report`.
**Governance / hygiene / policy gates (27):** `annotations_doctor`, `command_namespace_check`, `hooks_check`, `ignore_audit`, `hygiene_preflight`, `write_hygiene_docs [orphan, one-shot]`, `deps_sync` (+ `deps_sync_test`), `schema_check` (shared by 6 policy gates), `decommission_check`, `rename_audit`, `coverage_scan` (+ test), `client_check`, `client_inventory`, `client_profile_check`, `init_project_vault`, `project_identity_check`, `push_cadence_check`, `estate_config_versioned`, `skills_catalogue`, `secret_flow_check`, `tool_usage_probe`, `toolset_status`, `ade_rules_parity`, `auto_memory_check`, `ai_memory_pin_check`, `_credential_hasher.py`, `_infisical_token_probe.sh`.
**Deploy / release / confirm / git identity (10):** `confirm_step` (908 lines, the mutating-recipe gate; 18 external refs), `deploy_in_flight_check`, `deploy_logged`, `deploy_logs_rotate`, `release`, `health_check`, and from wom7api: `check_git_identity` (used by wom7web pre-push step 1), `hook_log`, `install_hooks` (installs hooks into every repo incl. root), `security_audit [orphan]`.
**Host / graph / MCP / local AI (22):** `graph_global`, `graph_fresh`, `graph_health`, `graph_callsites [orphan]`, `headroom_bootstrap`, `headroom_service`, `omlx_service`, `zeroclaw_manage [orphan]`, `zc_compression_measure [orphan]`, `vm_supervisor`, `launchd_schedule`, `mcp_exposure`, `mcp_ratchet`, `obsidian_mcp_bridge` (named by absolute path in `.mcp.json:14`), `test_obsidian_mcp [orphan]`, `host_surface_check`, `human_presence.swift`, `link_probe`, `preflight` (+ `preflight_test`; root `preflight` is a forwarder to it).

(Full per-file coupling + reference counts: Appendix A.)

### 3.3 Class C scripts (14) and why ambiguous

| file | what it does | why C | suggested home |
|---|---|---|---|
| `credential_snapshot.py` (web) | snapshot credential STATE across Infisical/Supabase/CF, never values | estate-wide concept, but reads `apps/cp` and `wom7api` layout and writes `project/credential-snapshot.json` (71 KB) | root once its two path assumptions are parametrised |
| `backup_watchdog_drift.py` (web) | does offsite watchdog still match config and ride an existing cron slot | estate gate, reads `wom7func` cron + `.w0m/sdlc.json` | root (A-leaning) |
| `version_doctor.py` (web) | one version format, one producer | estate rule, but names `wom7api/scripts/bump_version.js` as a producer | root (A-leaning) after producer path is declared in sdlc.json |
| `stamp_build.py` (web) | writes build stamp into every built artifact; called by `just build` | shared helper, but only meaningful inside an app build | stay with the build recipes (B-leaning) |
| `gen_status_dashboard.py` (web) | regenerates regions of `wom7web/docs/STATUS-DASHBOARD.html` from root TASKS.md | estate INPUT, web-repo OUTPUT (and a wom7web pre-commit hook `git add`s the output) | decide where the dashboard lives |
| `ast_grep_test.py` (web) | proves ast-grep rules fire | rules in `wom7web/project/ast-grep`, scans Astro code | stay web (B-leaning) |
| `env_rename_migrate.py` (web, orphan) | `--env=dev` -> `beta` one-shot over all repos | finished one-shot | delete |
| `org_migrate_plan.py`, `org_migrate_execute.py` (web) | T242 GitHub org migration dry-run / execute | one-shot, estate scope (GitHub) | retire or archive |
| `verify_siri_shortcuts_contract.py` (web, orphan) | T367 Siri/Shortcuts contract | host-level, no callers | delete or A |
| `open_vault.py` (api) | opens an Obsidian vault, registers it | generic, but only used for the wom7web vault | A-leaning |
| `healthcheck.py` (api) | colourised probe of services | estate services, but wired as `health` alias in api justfile only | A-leaning |
| `bake_pdfs.py` (api) | WeasyPrint PDF bake of wom7web docs/CVs | reads `../../wom7web/...`, writes into web docs | B (web), misplaced in api |
| `resumes_upload.py` (api) | uploads resume docs to the `resumes` bucket | spans web assets + api bucket | B (api), name wom7web for inputs |

### 3.4 The 65 root forwarders

* **Would disappear on a clean cutover (target is class A, 35):** `ask`, `crg-extract`, `crg-open`, `crg-serve`, `decommission-check(-test)`, `default`, `default-test`, `graph-{affected,benchmark,callflow,explain,global,path,query,tree}`, `headroom-{bootstrap-status,logs,restart,service-test,start,status,stop}`, `omlx-{restart,start,status,stop}`, `plan-verdict-test`, `preflight`, `rename-audit(-test)`, `secret-flow-check`, `-enforce`, `-test`, `vm-doctor`. (`default` is a special case: root `default` forwards to wom7web `default`.)
* **Stay (target is B, 17):** `authz-admin-client(-test)`, `check-auth`, `check-supabase`, `cp-feature-index(-check,-test)`, `db-migrate` (gated), `dev-stack`, `goldens`, `route-policy-{check,live,live-test}`, `smoke-live`, `stop-dev`, `supabase-redeploy-all`, `typecheck`. Under a clean layout these should become explicit per-repo entries (see 4), not forwarders.
* **C (4):** `check-warp`, `resumes-upload`, `resumes-upload-live`, `resumes-upload-test`.
* **Broken today (8):** `sdlc-{start,spec,build,review,security,verify,deploy,archive}` -> recipes do not exist (`just sdlc-start` exits 1 at justfile:350). Fix is independent of any migration.
* **Mixed (2):** `_post-deploy-knowledge` (calls `just --justfile wom7api/justfile knowledge-light || true`), `vm` (21-line dispatcher into wom7web `vm-doctor`).

### 3.5 Estate-level recipes with no root entry (121; selection by area)

SDLC/board: `tickets-frontmatter-{check,sync}`, `sync-project-fields`, `sync-subissues`, `populate-project-fields`, `ticket-id-align`, `type-backfill`, `epic-vocab-{check,sync}`, `state-bounds`, `decisions(-check)`, `close-legacy-tracker-issues`, `stage-guard`.
Governance: `annotations-doctor`, `command-namespace-check`, `hooks-check`, `hooks-install`, `ignore-audit`, `deps-{check,apply}`, `dep-licenses-check`, `overrides-check`, `client-{check,inventory,profile-check}`, `project-identity-check`, `push-cadence`, `skills-catalogue`, `spec-standard-check`, `estate-config-check`, `coverage-scan`, `health-check`, `host-check`, `mcp-exposure`, `mcp-ratchet`, `tools-{outdated,reconcile,schedule,usage}`, `toolset-status`, `hook-log`, `gh-w0m`, `knowledge`, `knowledge-light`, `confirm-log`.
Host/AI: `graph`, `graph-docs(-inc)`, `graph-health`, `codegraph-sync`, `headroom-{audit,bootstrap,doctor,learn,learn-apply,task}`, `zc`, `zeroclaw-{cp,restart,start,status,stop}`, `vm-{retention,staleness,status}`, `ask-{affected,path}`.
Quality: `py-test`, `py-test-{cov,fast,file}`, `py-typecheck(-api,-web)`, `check`, `spec`, `verify`, `tech-debt`, plus ~45 `*-test` recipes of the above.

Note `spec`/`verify`/`check` are aliases for Gauge E2E / sitemap generation / typecheck (SDLC contract names) and are B-leaning despite the name; counted A only because they are contract aliases. `tech-debt` hardcodes `base=/Users/proto/Projects/@self/@wom`.

---------------------------------------------------------------------------------------------------

## 4. cwd / path coupling, edit surface, hooks, deploy

### 4.1 Class A coupling (76 scripts)

* 57 of 76 compute the repo root from `Path(__file__).parents[n]` / `.parent...` (n=1..3): moving a script one level up changes every one of those indices. Typical: `parents[2]` (from `wom7web/project/scripts/x.py` that is `wom7web/`), `parents[3]` (the estate) in `graph_*`, `release.py`, `secret_flow_check.py`, `hygiene_preflight.py`, `push_cadence_check.py`, `tool_usage_probe.py`, `env_rename_migrate.py`, `db_migrate.py`.
* 34 read `wom7web/project/*` data files (see 4.3). 37 hardcode the strings `wom7web` / `wom7api`. 18 use `cwd=`/`Path.cwd()`. 6 use `../` literals (`ade_rules_parity`, `client_check` -> `../scripts/discovery.py`, `decisions_index`, `install_hooks`, `release`, `write_hygiene_docs`).
* External reference sites (recipes root 29 / recipes api 112 / hooks 17 / JSON 40 / other scripts 50 / tests 46 = **294**). Hottest: `confirm_step` 18, `release` 17, `deploy_logged` 13, `schema_check` 12, `preflight` 11, `decisions_index` 10, `install_hooks` 9, `headroom_service` 9, `graph_health` 7, `skills_catalogue` 7, `sync_project_fields` 7.
* Edit surface estimate per area unit: ~15-30 files (scripts + their tests + recipe lines + JSON). Mechanical rewrite classes: (a) `parents[n]` -> `parents[n-1]`/`ROOT`, (b) `WEB / "project" / X` -> `ROOT / "project" / X`, (c) recipe lines `cd ../wom7web && python3 project/scripts/X` or `python3 ../scripts/X` -> `python3 scripts/X`, (d) test `sys.path` and `parents[3]` (67 web tests use `parents[3]`, 23 `parents[4]`, 62 `sys.path.insert`, 19 `importlib` loaders).

### 4.2 Test infrastructure coupling (often forgotten)

* `wom7web/pyproject.toml`: `testpaths = ["project/scripts/tests"]`, `pythonpath = [".", "project/scripts"]`; `wom7web/uv.lock`, `.venv` live in wom7web; `conftest.py` computes `ROOT = parents[3]` (wom7web) and reads `ROOT/project/test-suites.json`. `just py-test*` = `cd ../wom7web && uv run pytest`. The root has **no** pyproject/pytest config, and root `scripts/tests` (18 modules) run only through individual `just <x>-test` recipes.
* `mypy`: `wom7web/mypy.ini` (`files = project/scripts`, `mypy_path = ../scripts`) and `wom7api/mypy.ini` (`files = scripts`); the root's 64 scripts are in **no** mypy gate today; wom7web's pre-commit hook `py-typecheck` fires on `^(project/scripts/[^/]+\.py|mypy\.ini)$`. Moving A scripts to root without a root `mypy.ini` + hook silently drops them from the typecheck gate (zero-silent-failure violation).
* `test-suites.json` (254 suites, 1 registry, in wom7web/project/) is read by root `run_suites.py:43`; the suite runner runs recipes with `cwd=API` (`run_suites.py:111,151`).

### 4.3 Data files the A scripts read from `wom7web/project/`

Must move with (or before) their readers, else each moved script grows a `WEB/"project"` path or a fallback ladder (both forbidden): `tickets.json`, `tickets-schema.jsonc`, `tickets-sync-index.json`, `test-suites.json`, `tasks-rotation.json`, `paused/`, `templates/`, `launchd/`, `dod-baseline.json`, `spec-standard-baseline.json`, `suite-uncounted-baseline.json`, `security-state.json`, `.tools-outdated.json`, `.tools-weekly-status.json`, `client-profile*.json`, `clients/`, `credential-snapshot.json`, `co-tenancy.json`, `command-namespace-baseline.json`, `mcp-exposure-baseline.json`, `secret-flow-baseline.json`, `typecheck-baseline.json`, `ai-memory-pin.json`, `zeroclaw/`, `permissions-deny.json`. Left in wom7web (B): `authz-*` (10 files + `authz-probe/`, 74 entries), `anon-execute-baseline`, `db-drift-baseline`, `ds-conformance-baseline`, `cv-*`, `data/` (23 B-script readers).

### 4.4 Hooks and deploy/release scripts that name script paths

* `wom7web/.pre-commit-config.yaml`: `python3 project/scripts/deploy_in_flight_check.py`, `lexicon_lint.py`, `gen_status_dashboard.py`, `cp_feature_index.py`, `decisions_index.py` (inline `sh -c`), mypy `files:` regex; `scripts/guard-test-admin.sh`.
* `wom7web/.husky/pre-push`: `python3 ../wom7api/scripts/check_git_identity.py` (A script in api), `python3 ../scripts/w0m_audit.py`, `python3 ../scripts/prepush_runner.py`, and **14 `( cd ../wom7api && just <recipe> )` blocks** (authz-probe, docs-check, license-check, dep-licenses-check, cv-leak-check, dod-check, client-page-tenancy-test, suites-drift, test-prepush, debt-check, drop-callers, emoji-check, version-check, graph-global). 25 steps registered in `scripts/prepush_runner.py:REGISTERED_STEPS`.
* root `.pre-commit-config.yaml`: `python3 wom7web/project/scripts/tickets_frontmatter_sync.py` (line 63) and `python3 wom7web/project/scripts/decisions_index.py --check` (line 78): root hooks calling into web scripts; `files:` filters mirror `decisions_index.py SOURCES` (a test asserts that).
* wom7api `.pre-commit-config.yaml`: `just py-typecheck-api`, `just discovery`; wom7skills `.pre-commit-config.yaml`: 3 hooks `bash -c 'cd ../wom7api && just skill-test|skills-typecheck|skills-version-check'` (lines 52,60,75).
* `scripts/install_hooks.py` (in wom7api, A) installs the hook stack in every repo incl. root (`EXPLICIT = [wom7mlx/wom7mlx, ROOT]`) but installs **pre-commit + commit-msg only**, never pre-push.
* Deploy/release: root `justfile` holds the deploy machinery since T421 (`_deploy-chain`, `deploy-*`, `release-*`); `wom7api/justfile` has 17 reverse forwarders (`--justfile ../justfile`) so `cd wom7api && just deploy` still works; `deploy_logged.py`, `release.py`, `confirm_step.py`, `deploy_in_flight_check.py` live in wom7web but are run from the root recipes (`python3 wom7web/project/scripts/...`). `release.py` computes `parents[3]` and names 14 repo paths.
* Host: 5 launchd agents (2.1) and `.claude/settings.local.json` SessionStart (`preflight.py`), `.mcp.json` (`obsidian_mcp_bridge.py`) name absolute `wom7web/project/scripts/...` paths.

---------------------------------------------------------------------------------------------------

## 5. The `wom7web/justfile` -> `wom7api/justfile` symlink (Q4)

**Purpose (reconstructed from the repos' own prose, not from a commit message):** one recipe surface shared by the repos, created before the estate root existed (`.justfile` renamed `justfile` 2026-07-04, `e48f6efef`; symlink mode 120000 already in that rename). It lets `just <recipe>` work when you are standing in `wom7web` or `wom7api` (and `wom7func`, `wom7authz`, formerly `wom7cfworkers`). It only works because ~394 of 614 recipes carry `cd ../wom7web` or `../scripts/` prefixes that are valid from either sibling directory, and 93 recipes assume cwd = wom7api (bare `supabase/`, `src/`, `wrangler`), which is why docs say "deploy runs from wom7api". From the root it does not work at all (root has its own justfile; so 65 forwarders exist).

**Who depends on it:**
* wom7web `.husky/pre-push` (`just typecheck` ...), `.husky/pre-commit` (`just secrets-check`, `just emoji-check --staged`), `.pre-commit-config.yaml` (`just py-typecheck-web`, `just stage-guard`, `just mmd-validate`).
* wom7func and wom7authz (symlinks; most recipes cannot work there).
* `/w0m-just`, `/w0m-tasks`, `/w0m-headroom`, `/w0m-local-dev` commands and `.agent/workflows/*` ("From wom7api/ ... wom7web's is a symlink to it") - 7 command files + 3 workflows + `.agents/rules/w0m.md:74` + wom7web `CLAUDE.md:100`/`README.md:47`/`CONTRIBUTING.md:97`, wom7api `CLAUDE.md:16`/`README.md:13`/`CONTRIBUTING.md:95`.
* The 17 api->root reverse forwarders and `just --justfile wom7web/justfile ...` in 33 root recipes.

**What `just` does (verified in the scratchpad, just 1.58.0):** (1) `just` walks upward to the nearest `justfile`; recipes run with cwd = the directory of that file; (2) a symlinked justfile runs with cwd = the symlink's directory; (3) in a directory that has NO justfile, `just x` finds the parent's (root's) and runs with cwd = root; (4) `import` merges into one flat namespace with cwd = importing justfile's dir (and `source_directory()` = the imported file's dir); duplicate recipe names are an error; (5) `mod` creates `api::recipe` names and runs module recipes with cwd = the module dir (`[no-cd]` = caller's).

**Root-first options for the layout:**
| layout | mechanics | verdict |
|---|---|---|
| L1. ONE justfile at root; delete all three symlinks; repo-specific recipes move into it with root-relative paths (`cd wom7api && ...`) | upward search makes `just <recipe>` work from any subdirectory of any repo (cwd = root); needs the 143 duplicates deleted first (else collision), 93 api-cwd recipes rewritten to `cd wom7api &&`, 318 `cd ../wom7web` -> `cd wom7web`, 76 `../scripts/` -> `scripts/` | cleanest for "operate from the root by default"; 4800 lines + 1064 in one file is large but `import` can split by area WITHOUT changing names or cwd |
| L2. Root justfile = estate recipes (A) + `import 'wom7api/api.just'` style files per area; per-repo justfiles deleted | same flat names, cwd always root, split files per area (e.g. `just/estate.just`, `just/api.just`, `just/web.just`) | recommended refinement of L1: file size and review ownership solved with `import`, still one namespace, no forwarders |
| L3. per-repo justfiles remain, root `mod api`/`mod web` | names change to `api::db-migrate`; all 200+ docs/hooks/skills/allowlists change; nearest-justfile-wins shadows root inside repos | rejected: blast radius, creates a second naming scheme |
| L4. keep symlink, add root forwarders for everything | = today | rejected: it is the shim/fallback AgDR-0025 forbids and is the source of the 8 dangling forwarders |

**Consequence to design for:** once `wom7web/justfile` is deleted, a hook or launchd job that does `cd wom7web && just audit` silently starts running ROOT's `audit` (cwd root) or, if the recipe has not moved yet, fails "no recipe". Fail-loud is right, but the sequencing in section 8 puts recipe moves BEFORE deleting the symlink and updates the 5 launchd agents in the same unit.

---------------------------------------------------------------------------------------------------

## 6. Stale-path probe design (Q5)

Name: `just stale-path-check` (script `scripts/stale_path_check.py`), registered in `wom7web/project/test-suites.json` (-> root-owned after unit 3) as `tier: offline, blocking: true, prepush: true`. Exit 0 clean, 1 stale reference, 2 could not measure (same convention as `justfile_calls_check.py` and `ac_recipe_check.py`: cannot-measure never prints as pass).

**What to scan (the five reference carriers):**
1. Recipe bodies of every justfile/import (use `just --dump --dump-format json`, as `justfile_calls_check.py` does; handle `\` continuation and shebang recipes).
2. JSON/JSONC: `project/policies/*.json*`, `.w0m/*.json`, `project/*.json*` incl. `test-suites.json`, `schedules.jsonc`, `.mcp.json`, `.claude/launch.json`; keys `command|entry|script|path|sync|recipe` plus any string value that looks like a repo-relative script path. Scan KEYS too (emoji `discovery_exempt` is keyed by `file:line`).
3. Hook configs: every repo's `.pre-commit-config.yaml` `entry:`/`files:`, `.husky/*` (shell: only non-comment lines), `.git/hooks` shims installed by `install_hooks.py` (compare to expected).
4. Test runners/config: `pyproject.toml` `testpaths/pythonpath`, `mypy.ini` `files/mypy_path/exclude`, `conftest.py` `ROOT =` assertions (exec: assert the computed ROOT contains `justfile`+`.git`).
5. Host-level: `~/Library/LaunchAgents/com.w0m.*.plist` ProgramArguments (resolve `cd X && just R` -> X exists and R resolves in the justfile found upward from X), `.claude/settings.local.json` hook commands (local-only mode, skipped but REPORTED if absent).

**Resolution rules (to avoid false positives):**
* Resolve each reference against the base the carrier actually executes from: recipe -> justfile dir, adjusted by `cd X &&` on the same line and by `cd` in shebang bodies; subshell `( cd X && ... )` must not leak the cd to later lines (the prototype got this wrong once, flagging `quartz`; fixed by treating a parenthesised cd as scoped). Hook -> repo root of the repo that owns the config. JSON -> declared base per file (policy files: estate root; `.w0m/sdlc.json`: estate root).
* Candidate extraction regex: `(?<![\w/.~-])((?:\.\./)*(?:wom7[a-z]+/)?(?:project/scripts/|scripts/)[A-Za-z0-9_.-]+\.(py|sh|ts|mjs|js|swift))` plus bare filenames in the second token of `python3|node|deno run|bash|sh|uv run`. Ignore: comments (`#`, `//`), anything inside quoted echo/print text, `.agents/skills/**` and vendored trees (skill-shipped `scripts/idea-refine.sh` etc. are not estate scripts: this removed 3 false positives), `node_modules`, `archive/`, and files in an explicit `stale-path-exempt` list that REQUIRES a `why` (same discipline as `decommission_check` `except`), with STALE exemptions reported (an exemption whose path now exists or whose reference vanished is itself drift).
* Dynamic references (`{{ ... }}`, `$VAR`) are counted and reported, never guessed (same as `justfile_calls_check` "dynamic").
* Second direction, cheap and high value: (a) every recipe forward target (`just --justfile X recipe`) exists - closes the blind spot of `justfile_calls_check` (it explicitly skips delegating flags; extend that script rather than writing a second one: SSOT); (b) every recipe name defined in more than one justfile/import = FAIL (dual SSOT; `just` already errors on duplicates only inside one namespace); (c) docstring "Usage:" lines naming `project/scripts/x.py` for a file that is somewhere else (advisory tier, 50+ today).
* Placement rule (separate small check, same script): a script under `wom7*/` may not contain `../scripts` or `parents[n]` landing outside its repo, and a script under `scripts/` may not name `WEB / "project"` (after unit 3) - this turns the A/B classification into a standing invariant.

**Where it runs:** (1) offline suite -> `just test`, `just test-prepush` and the deploy pre-flight (T503), therefore pre-push of wom7web; (2) root pre-commit hook when staged files match `^(justfile|.*\.just|project/.*\.jsonc?|\.w0m/.*|\.pre-commit-config\.yaml|scripts/.*|\.mcp\.json)$`, `pass_filenames: false`, well under 1 s (same shape as the `ac-recipe-check` hook); (3) wire into `hooks_check` so a repo whose hook config references a missing path is reported by `just hooks-check` (pre-push step 24). Because only wom7web has a pre-push, item (2) is the only gate for a root-only push until the pre-push question (open question Q2) is settled.

**Prototype result (scratchpad, not committed, 2026-09-30):** 9 recipe findings (8 true after the subshell fix) + 40 JSON hits (20 unique after resolving the 19 policy symlinks, 3 false positives) + 80 "nowhere" hits in script text (mostly docstrings; ~10 functional or lockstep comments). A real implementation must be tested with red fixtures first (estate rule: a gate nobody watched fail is not a gate): one fixture per carrier, one per false-positive rule, one cannot-measure case.

**Existing gates it should reuse, not duplicate:** `justfile_calls_check.py` (dump + body parsing + exit-2 convention; extend it with `--justfile` target resolution and duplicate detection), `ac_recipe_check.py` (acknowledged-exception reporting pattern), `decommission_check.py` (`except` requires `why`; stale-exception reporting), `hooks_check.py` (hook layer). `rename_audit.py` stays a one-shot tool for renames; it is not a standing gate.

---------------------------------------------------------------------------------------------------

## 7. Options and weighted decision matrix

Options:
* **O1 Full atomic cutover.** One change moves all 76 class-A scripts, 68 tests, ~25 data files/dirs, 121 recipes, dedupes 143 recipes, deletes the three justfile symlinks and the 24 shadow symlinks, updates hooks/launchd/skills/docs.
* **O2 Staged by area (recommended).** Probe first; then dedupe/layout; then tests+data; then 4 script areas (SDLC/board, governance/gates, deploy/release/hooks, host/graph/AI); then hooks+launchd; then docs/skills/slash-commands. Each unit is a clean cutover of one area (100% of that area's callers in the same commit pair), never a shim.
* **O3 Leave split + probe only.** Add `stale-path-check` (+ forwarder and duplicate checks), fix the T414 leftovers, stop.
* **O4 Facade.** Root recipes and `just mod` forward to repo justfiles; scripts stay.

Weights: meets the owner direction / unblocks 30, risk 25, blast radius 20, cost 15, SSOT compliance (AgDR-0025) 10. Scores 1 (bad) - 5 (good).

| option | cost (15) | risk (25) | blast radius (20) | unblocks/direction (30) | SSOT/AgDR-0025 (10) | weighted |
|---|---:|---:|---:|---:|---:|---:|
| O1 full cutover | 1 | 1 | 1 | 5 | 5 | **2.60** |
| O2 staged by area | 3 | 4 | 4 | 4 | 5 | **3.95** |
| O3 probe only | 5 | 5 | 5 | 1 | 2 | **3.50** |
| O4 facade | 4 | 3 | 3 | 3 | 1 | **2.95** |

Notes: O3 scores high on safety but does not move anything, so it fails the owner direction; it is also strictly contained in O2 as unit 0 (so choosing O2 forfeits nothing). O1's blast radius: ~294 reference sites + 120 tests + 5 launchd agents + 50 doc/hook references in one change on a shared dirty tree, with 2-3 independent git repos (not truly atomic across repos). O4 re-creates exactly the forwarder layer that rotted (8 dangling today) and keeps `wom7web/justfile` shadowing.
Sensitivity: if blast radius is weighted at 10 and unblocks at 40, O2 still wins (3.95 -> 4.05; O3 3.5 -> 3.0); O1 only wins if risk and blast are weighted at 0.

---------------------------------------------------------------------------------------------------

## 8. Recommendation and migration units (each sized for one session)

Recommendation: **O2**, layout **L2** (one flat namespace at the root, split into `import`ed files by area, per-repo justfiles deleted, no forwarders, no modules), executed with these rules: every unit runs in an isolated worktree (`just worktree-agent <id>`, T411 AC5 - verify it handles the nested repos before relying on it), commits per repo with `git mv` (history preserved), a ticket per unit with `Split from:` links, probe green before and after, `just test` check-count conserved, push only via the human gate for anything deploy-adjacent.

| unit | content | repos touched | est. sites | exit proof |
|---|---|---|---:|---|
| U0 probe + repair | build `stale-path-check` red-first; extend `justfile-calls-check` for `--justfile` targets + duplicate names; repair the 8 dangling `sdlc-*` forwarders (point at real recipes or delete), 8 dead api recipes, 20 JSON refs (emoji `discovery_exempt` keys re-keyed), fix 50 usage docstrings; delete the 37 orphan scripts and the duplicate `test_agent_concurrency.py` (after owner OK) | root, wom7api, wom7web | ~100 | probe exit 0 on tree; red fixtures pass; `just justfile-calls-check` green |
| U1 recipes + layout | delete the 17 reverse forwarders and 143 api-side duplicates (root copy wins), move the 121 remaining class-A api recipes to root `just/estate.just` (import), rewrite `../scripts/`->`scripts/`; keep B recipes in `wom7api/justfile`/`wom7web` area files but root-relative; delete `wom7web/justfile`, `wom7func/justfile`, `wom7authz/justfile` symlinks; remove the 35 A-target forwarders | root, wom7api, wom7web, wom7func (authz is not in the 7-repo list, verify) | ~450 recipe lines (mechanical) | `just --dump` name set unique; `cd wom7web && just tasks` resolves to root; `suites-drift` green |
| U2 tests + data | move the 26 root-script tests + 41 A tests + their fixtures/conftest from `wom7web/project/scripts/tests` to `scripts/tests`; root `pyproject.toml` (uv, pytest) and `mypy.ini`; `py-test*` recipes point at root; move the estate data files in 4.3 to `project/` (root); delete the 19 policy symlinks and `templates/` symlinks | root, wom7web | ~120 files | `just test` total check count equal before/after; root mypy gate at 0; no `WEB/"project"` read for moved files |
| U3 scripts: SDLC/board | 17 scripts (3.2) | root, wom7web | ~60 | per-area `git grep project/scripts/<name>` = 0 via `just search`; stale-path-check green |
| U4 scripts: governance/gates | 27 scripts incl. `schema_check`, `deps_sync`, `secret_flow_check`, `hooks_check` | root, wom7web, wom7api | ~100 | same |
| U5 scripts: deploy/release/hooks | `confirm_step`, `deploy_*`, `release`, `health_check`, `check_git_identity`, `install_hooks`, `hook_log`; 5 launchd plists regenerated (`just tools-schedule`) | root, wom7web, wom7api, host | ~70 + 5 plists | confirm-test (64 probes) green; deploy dry-run chain order test green; `launchd_schedule` status clean |
| U6 scripts: host/graph/AI | 22 scripts incl. `graph_*`, `headroom_*`, `omlx_service`, `mcp_*`, `launchd_schedule`, `preflight`, `obsidian_mcp_bridge` + `.mcp.json` + `.claude/settings.local.json` SessionStart | root, wom7web, host | ~60 | `just preflight --fast`, MCP connect, `just graph-health` green |
| U7 hooks + indexes | move/adapt the wom7web pre-commit script hooks to recipe calls; decide pre-push for root/api (Q2); add root to `estate_search` (`--repo root`), `graph_global.REPOS`, codegraph/graphify indexing (needs owner OK: indexing is the user's decision) | root, wom7web, wom7api, wom7skills | ~40 | `just search tasks_bounds --repo root` finds `scripts/tasks_bounds.py`; `just ask` returns root symbols |
| U8 docs/skills/commands | replace `cd wom7api && just` in 50 places (wom7web 38, wom7api 7, wom7func 1, wom7skills 4), `/w0m-*` slash commands, `w0m-state-load`, `.agents/rules/w0m.md`, AGENTS/CLAUDE/README/CONTRIBUTING; canonical skills edited in `wom7skills` first (stamp BEFORE sync, `relock` not `update`, hand-copy to @wom root) | wom7skills, wom7web, wom7api, root | ~60 | `just search "cd wom7api && just"` -> 0 for estate recipes; skills lock verified |
| U9 (later, separate) | 58 DB/authz probes from wom7web to wom7api (B, wrong repo) and 20+ legacy api scripts to archive/delete | wom7web, wom7api | ~120 | placement check green |

Rollback strategy: (1) each unit = one commit per repo, tagged `unit/Un` locally; rollback = `git revert` of those commits in reverse repo order (never reset/checkout blanket - AGENTS.md), then re-run the probe; (2) because root and wom7web are separate repos, a unit is not atomic across them: land both commits locally, run `just test` + probe, push root and the sibling in one `just land` session; if anything fails before push, revert locally; (3) U1 and U5 touch host-visible state (symlinks, launchd): take `~/Library/LaunchAgents/com.w0m.*.plist` backup before, and U1 keeps the old symlink deletion as the LAST commit of the unit so a revert restores the shadow instantly; (4) no unit leaves a shim: if a caller is missed, the probe (U0) fails loudly, which is the point.

---------------------------------------------------------------------------------------------------

## 9. Draft acceptance criteria and Definition of Done

Each AC has a probe. "Before" numbers are measured 2026-09-30.

| # | acceptance criterion | verifying probe | before |
|---|---|---|---|
| AC1 | `just stale-path-check` exists, has red fixtures for each carrier (recipe, JSON, hook, test runner, launchd) and false-positive rule, exits 2 on cannot-measure, is in `test-suites.json` with `prepush: true` | `just stale-path-check-test` + `just suites-drift` | no such gate |
| AC2 | 0 stale script-path references across recipes/JSON/hooks/runners | `just stale-path-check` exit 0 | 8 recipes, ~17 JSON, 8 dangling forwarders |
| AC3 | `just --dump` recipe names unique across all justfiles/imports; 0 reverse forwarders | duplicate-name check in `justfile-calls-check` | 143 duplicates, 17 reverse forwarders |
| AC4 | 0 dangling forwarders (`--justfile X recipe` targets all exist) | `just justfile-calls-check` (extended) | 8 dangling |
| AC5 | class-A scripts: 0 remain in `wom7web/project/scripts` and `wom7api/scripts`; manifest of moved files recorded in the ticket | placement check + `git -C wom7web ls-files project/scripts` vs manifest | 76 |
| AC6 | the 68 tests of A/root scripts live under `scripts/tests`; no test of a root script remains in a repo | placement check; `ls wom7web/project/scripts/tests` | 26 root-script tests in web, 1 duplicate |
| AC7 | `just test` aggregate check count after == before (no suite silently dropped) | `just test` output total vs recorded baseline | baseline to record at U0 |
| AC8 | root has `mypy.ini` + pre-commit hook covering `scripts/` at 0 errors; root pytest config collects `scripts/tests` | `just py-typecheck` incl. root; `uv run pytest --collect-only` count | root: no gate |
| AC9 | `wom7web/justfile`, `wom7func/justfile` symlinks absent; from any repo directory `just tasks` resolves to the root justfile | `test -L wom7web/justfile` false; scripted `cd wom7web && just --show tasks` | 3 symlinks |
| AC10 | 0 shadow symlinks of estate files in wom7web (policies, templates, `.tasks`, `TASKS.md`, `.w0m/sdlc.json`) | `git ls-files -s` filtered to mode 120000 (estate targets) | 24 |
| AC11 | 5 launchd agents run from the new layout; one forced run each succeeds (or the intended recipe prints its usual output) | `just tools-schedule` status + `launchctl print` + log mtime | 5 agents `cd wom7api/web && just` |
| AC12 | `just search --repo root` works; root is in the graph union; `just ask "tasks_bounds"` returns `scripts/tasks_bounds.py` symbols | the two commands | root BLOCKED / invisible |
| AC13 | 0 occurrences of `cd wom7api && just` / `cd ../wom7api && just` for estate recipes in hooks, skills, slash commands, docs | `just search "cd (\.\./)?wom7api && just"` | 50 |
| AC14 | pre-push (or an agreed equivalent) runs on pushes from root and wom7api | push dry-run log lists the gate steps | only wom7web |
| AC15 | `.mcp.json`, SessionStart hook and `wom7skills` canonical skills reference only existing paths; skills lock verified | `just mcp-health`, `just preflight --fast`, `just skills-diff` | 3 carriers name web paths |
| AC16 | each moved script's own docstring usage line names its new path | `stale-path-check` advisory tier = 0 | 50+ |
| AC17 | zero use of `--no-verify`, no repo-wide formatter run, no blanket git discard (audit of the unit commits) | reviewer checklist + `git log` | n/a |

Definition of Done (whole initiative): AC1-AC17 green; `just tasks`, `just preflight --fast`, `just state-brief`, `just test-prepush` all run from the root AND from inside a repo subdirectory with identical results; STATE.md/TASKS.md updated; AgDR recorded for the layout decision (L2) referencing AgDR-0025; each unit's leftover questions closed by weighted decision per the estate rule; `TECH-DEBT.md` rows for deferred items (U9, dead-script purge).

---------------------------------------------------------------------------------------------------

## 10. Risks

1. **Concurrent agents on a shared tree.** The root tree is dirty at the start (`project/policies/clients-policy.json`, `scripts/sync_github.py` modified by someone else). Moving 76 files and rewriting 294 reference sites while another agent edits the same scripts loses work. Mitigation: worktree per unit; `git status --short` before and after (memory: background sessions do invisible ticket work); known traps: pre-commit stash drops unstaged work when a dashboard regenerates mid-commit (`gen_status_dashboard`/`decisions_index` hooks do `git add`), and `git mv` + failed commit + reset can drop the new tree. Stage only your own paths.
2. **Indexes keyed to paths.** graphify union and codegraph are per-repo; `graph_global.REPOS` has 7 entries and no root; root has no `.codegraph/` and an empty `graphify-out`; `just ask "tasks_bounds"` returns web symbols and zero hits in `scripts/tasks_bounds.py`. Today's 64 root scripts are already invisible; the migration would make 76 more invisible. Moves also change `file:line` anchors that `decisions_index`, `emoji-policy.json` (`discovery_exempt`) and `.w0m/sdlc.json` key on; `decisions_index --check` is a root pre-commit hook with a `files:` filter that must stay mirrored. Re-index (`just graph-global --rebuild`, `codegraph sync`) is a required step of each unit; creating a root index needs owner approval.
3. **Headroom / skills / slash commands that hardcode `cd wom7api`.** `.claude/commands/{w0m-just,w0m-tasks,w0m-headroom,w0m-local-dev}.md`, `.agent/workflows/*`, `wom7skills/skills/w0m-state-load/SKILL.md:88`, `wom7skills .pre-commit-config.yaml` (3 hooks). The `/w0m-tasks` command tells agents `cd wom7api && just tasks` although root has `tasks`. Root's `.claude/commands` is itself a symlink into wom7web. The w0m-* skills are not in the `Skill` tool (they live in `wom7web/.agents/skills`); canonical edits must go through `wom7skills` (stamp -> sync -> relock; 3 repos incl. hand-copy to @wom).
4. **Host-level references outside git:** 5 launchd plists, `.claude/settings.local.json` (globally gitignored), `~/.claude` allowlist entries (2 allow `python3 project/scripts/...`): they can only be found by the probe's host mode, never by `git grep`.
5. **No pre-push at root/wom7api.** Root-first operation means more pushes originate from root; today those run no pre-push gate (25 steps live only in `wom7web/.husky/pre-push`, which also contains 14 `cd ../wom7api && just` calls).
6. **Gate coverage regressions:** root has no mypy, wom7web's mypy hook only matches `project/scripts/...`, `suites-drift` matches recipe names only, `just search` excludes root. A gate that quietly looks at nothing is worse than no gate (root `.pre-commit-config.yaml` header says it).
7. **Duplicate-name hazard when merging justfiles:** 200 names exist in both; 57 are identical-or-forwarding, 143 differ. `import` errors on duplicates (good), but resolving each needs a human read; do it in U1 with the diff list from this report.
8. **Secrets handling during moves:** recipes use `infisical run --env=beta`; the root justfile pins `--projectId`, wom7api uses `.infisical.json` in its cwd (121 `infisical run` in api vs 22 in root). Moving a recipe to root without `--projectId` breaks it silently (the T421 elevation did this once, per the root justfile comment at lines 9-12). Probe candidate: every root `infisical run` carries `--projectId`.
9. **Two hardcoded absolute paths** (`tech-debt` recipe `base=/Users/proto/...`, `.mcp.json`, launchd) break on any other checkout.
10. **Gated operations stay human:** `db-migrate`, `deploy*`, PR creation, are never to be executed by the migrating agent (AGENTS.md); units that touch them prepare and ask.

---------------------------------------------------------------------------------------------------

## 11. Open owner questions (with recommended answer and weight)

| # | question | recommended answer | weight (cost / risk / unblocks) |
|---|---|---|---|
| Q1 | Layout: one root namespace split by `import` (L2), vs per-repo justfiles with `mod` (L3)? | L2 | low / low / high (everything depends on it) |
| Q2 | Install a pre-push (the 25-step runner) on root and wom7api too, via `install_hooks.py`? | Yes, root first (same runner, repo-aware); otherwise "operate from root" weakens the gate | medium / low / high |
| Q3 | Index the root repo (`codegraph init`, add to `graph_global.REPOS`, add root to `estate_search`)? Indexing is your decision | Yes; without it every moved script becomes invisible to `just ask`/`search` | low / low / high |
| Q4 | Where do the 58 DB/authz probes in wom7web belong - wom7api or `wom7authz`? | wom7api now (own unit U9); wom7authz is not one of the seven repos | medium / medium / medium |
| Q5 | Delete the 37 zero-reference scripts (incl. one-shots `env_rename_migrate`, `org_migrate_*`, `write_hygiene_docs`)? | Yes, list in U0 for a yes/no per file; git history keeps them | low / low / medium |
| Q6 | `init_tinybird_schemas.py` has a hardcoded token literal in a tracked file: rotate the Tinybird token and remove? | Yes (owner action: rotate); script removal in U0 | low / medium / n/a (security) |
| Q7 | Class C decisions: `gen_status_dashboard` (output lives in wom7web docs), `stamp_build`, `credential_snapshot`, `version_doctor`, `open_vault`, `healthcheck` | A for `credential_snapshot`, `version_doctor`, `backup_watchdog_drift`, `open_vault`, `healthcheck`; B for `stamp_build`, `ast_grep_test`, `bake_pdfs`, `resumes_upload`; dashboard output moves to root `docs/`? (needs your call) | low / low / medium |
| Q8 | Estate data in `wom7web/project/` (tickets.json, test-suites.json, launchd/, ...): move to root `project/` in U2 (clean cutover), or leave until their readers move? | U2, before the script units; leaving them forces `WEB/"project"` paths into every moved script | medium / medium / high |
| Q9 | Agent surface (`.claude/commands`, `.agent`, `.codex`, `.gemini`, `.kilocode` symlinks into wom7web) moves to the root too? | Yes, as a follow-up ticket after U8 (same AgDR-0025 argument); out of this scope | medium / medium / medium |
| Q10 | The 8 dangling `sdlc-*` root recipes: implement against `.w0m/sdlc.json` commands, or delete? | Check `w0m-sdlc-*` skills for callers in U0; delete if none (they have never worked) | low / low / low |

---------------------------------------------------------------------------------------------------

## Appendix A: class A and C edit surface (generated, scratchpad scanner)

Columns: coupling flags, then external reference counts in the order recipes-in-root / recipes-in-api / hooks / JSON registries / other scripts / tests (letters r a h j s t). Counts are occurrences of the file name outside the file itself (+ `import <stem>` for scripts/tests); they overcount mentions in comments and undercount names built dynamically.

| file | repo | path/cwd coupling | external references (recipes root / recipes api / hooks / JSON / other scripts / tests) |
|---|---|---|---|
| check_git_identity.py (A) | wom7api | names wom7api | r0 / a3 / h2 / j0 / s0 / t0 |
| hook_log.py (A) | wom7api | - | r0 / a1 / h0 / j0 / s0 / t0 |
| install_hooks.py (A) | wom7api | parents[2], ../, cwd, names wom7web, names wom7api | r0 / a1 / h7 / j0 / s1 / t0 |
| security_audit.py (A) | wom7api | - | r0 / a0 / h0 / j0 / s0 / t0 |
| _credential_hasher.py (A) | wom7web | - | r0 / a0 / h0 / j0 / s1 / t0 |
| _infisical_token_probe.sh (A) | wom7web | - | r0 / a1 / h0 / j0 / s0 / t0 |
| ade_rules_parity.py (A) | wom7web | parents[2], reads 1 wom7web/project/* items, names wom7web, names wom7api | r0 / a2 / h0 / j1 / s0 / t1 |
| ai_memory_pin_check.py (A) | wom7web | parents[2], reads 1 wom7web/project/* items | r0 / a1 / h0 / j0 / s0 / t0 |
| annotations_doctor.py (A) | wom7web | parents[2], cwd, reads 1 wom7web/project/* items, names wom7web | r0 / a3 / h0 / j1 / s1 / t1 |
| auto_memory_check.py (A) | wom7web | - | r0 / a1 / h0 / j0 / s0 / t0 |
| backfill_tickets.py (A) | wom7web | parents[3], ../, reads 1 wom7web/project/* items | r0 / a0 / h0 / j0 / s3 / t0 |
| board_identity.py (A) | wom7web | parents[2] | r0 / a1 / h0 / j1 / s3 / t1 |
| changelog_drift.py (A) | wom7web | parents[2] | r2 / a2 / h0 / j0 / s0 / t1 |
| client_check.py (A) | wom7web | parents[2], ../, cwd, reads 2 wom7web/project/* items, names wom7web | r0 / a1 / h0 / j1 / s0 / t0 |
| client_inventory.py (A) | wom7web | parents[2], reads 2 wom7web/project/* items, names wom7web | r0 / a2 / h0 / j1 / s0 / t2 |
| client_profile_check.py (A) | wom7web | parents[2], reads 4 wom7web/project/* items, names wom7web, names wom7api | r0 / a1 / h0 / j0 / s1 / t1 |
| close_legacy_tracker_issues.py (A) | wom7web | - | r0 / a2 / h0 / j0 / s0 / t1 |
| command_namespace_check.py (A) | wom7web | parents[2], reads 1 wom7web/project/* items | r0 / a1 / h0 / j0 / s0 / t0 |
| confirm_step.py (A) | wom7web | parents[2], cwd, reads 1 wom7web/project/* items, names wom7api | r5 / a5 / h0 / j3 / s3 / t2 |
| coverage_scan.py (A) | wom7web | parents[2,3], reads 1 wom7web/project/* items, names wom7web | r0 / a1 / h0 / j1 / s0 / t1 |
| coverage_scan_test.py (A) | wom7web | .parent, cwd, reads 1 wom7web/project/* items, names wom7web | r0 / a1 / h0 / j0 / s0 / t0 |
| decisions_index.py (A) | wom7web | parents[2], ../, reads 2 wom7web/project/* items, names wom7web | r0 / a3 / h5 / j1 / s0 / t1 |
| decommission_check.py (A) | wom7web | parents[2], cwd, names wom7web, names wom7api | r0 / a2 / h0 / j0 / s1 / t1 |
| deploy_in_flight_check.py (A) | wom7web | parents[2], cwd, names wom7api | r0 / a0 / h1 / j0 / s0 / t1 |
| deploy_logged.py (A) | wom7web | parents[2], cwd, names wom7web, names wom7api | r4 / a4 / h0 / j2 / s1 / t2 |
| deploy_logs_rotate.py (A) | wom7web | parents[2] | r2 / a2 / h0 / j0 / s1 / t1 |
| deps_sync.py (A) | wom7web | parents[1,3], reads 1 wom7web/project/* items, names wom7web | r0 / a2 / h1 / j1 / s1 / t1 |
| deps_sync_test.py (A) | wom7web | .parent | r0 / a1 / h0 / j0 / s0 / t0 |
| epic_completeness.py (A) | wom7web | parents[2,3], reads 1 wom7web/project/* items | r0 / a0 / h0 / j1 / s1 / t0 |
| estate_config_versioned.py (A) | wom7web | parents[3] | r0 / a1 / h0 / j0 / s1 / t0 |
| graph_callsites.py (A) | wom7web | parents[3], names wom7web, names wom7api | r0 / a0 / h0 / j0 / s0 / t0 |
| graph_fresh.py (A) | wom7web | .parent, cwd | r0 / a1 / h0 / j0 / s1 / t1 |
| graph_global.py (A) | wom7web | parents[3], cwd, names wom7web, names wom7api | r0 / a1 / h0 / j0 / s2 / t0 |
| graph_health.py (A) | wom7web | parents[3], cwd, names wom7web, names wom7api | r0 / a1 / h0 / j0 / s4 / t2 |
| headroom_bootstrap.py (A) | wom7web | - | r0 / a2 / h0 / j1 / s0 / t0 |
| headroom_service.py (A) | wom7web | - | r0 / a6 / h0 / j2 / s0 / t1 |
| health_check.py (A) | wom7web | names wom7api | r0 / a1 / h0 / j0 / s2 / t0 |
| hooks_check.py (A) | wom7web | parents[2], reads 1 wom7web/project/* items, names wom7web, names wom7api | r0 / a2 / h0 / j2 / s0 / t1 |
| host_surface_check.py (A) | wom7web | - | r0 / a1 / h0 / j0 / s0 / t1 |
| human_presence.swift (A) | wom7web | - | r0 / a0 / h0 / j0 / s1 / t1 |
| hygiene_preflight.py (A) | wom7web | parents[3], ../, names wom7web, names wom7api | r0 / a0 / h0 / j0 / s1 / t0 |
| ignore_audit.py (A) | wom7web | parents[2], cwd, reads 1 wom7web/project/* items | r0 / a2 / h0 / j0 / s0 / t1 |
| init_project_vault.py (A) | wom7web | .parent, reads 1 wom7web/project/* items, names wom7web | r0 / a1 / h0 / j0 / s0 / t1 |
| launchd_schedule.py (A) | wom7web | parents[2], reads 1 wom7web/project/* items | r0 / a1 / h0 / j0 / s0 / t0 |
| link_probe.py (A) | wom7web | names wom7web | r0 / a0 / h0 / j1 / s1 / t1 |
| mcp_exposure.py (A) | wom7web | parents[2,3] | r0 / a1 / h0 / j0 / s2 / t0 |
| mcp_ratchet.py (A) | wom7web | parents[2], reads 1 wom7web/project/* items | r0 / a2 / h0 / j0 / s2 / t2 |
| obsidian_mcp_bridge.py (A) | wom7web | - | r0 / a0 / h0 / j1 / s0 / t1 |
| omlx_service.py (A) | wom7web | - | r0 / a4 / h0 / j0 / s0 / t0 |
| populate_project_fields.py (A) | wom7web | parents[2,3] | r0 / a1 / h0 / j2 / s1 / t1 |
| preflight.py (A) | wom7web | parents[2], cwd, reads 1 wom7web/project/* items, names wom7web | r0 / a5 / h0 / j1 / s3 / t2 |
| preflight_test.py (A) | wom7web | .parent, reads 1 wom7web/project/* items | r0 / a1 / h0 / j0 / s0 / t0 |
| project_identity_check.py (A) | wom7web | parents[2], reads 1 wom7web/project/* items, names wom7web | r0 / a1 / h0 / j0 / s0 / t1 |
| push_cadence_check.py (A) | wom7web | parents[3], names wom7web, names wom7api | r0 / a1 / h0 / j0 / s0 / t0 |
| push_report.py (A) | wom7web | names wom7web | r0 / a2 / h0 / j1 / s0 / t1 |
| release.py (A) | wom7web | parents[3], ../, cwd, reads 1 wom7web/project/* items, names wom7web, names wom7api | r14 / a0 / h0 / j3 / s0 / t0 |
| rename_audit.py (A) | wom7web | parents[2], reads 2 wom7web/project/* items | r0 / a2 / h0 / j2 / s0 / t1 |
| schema_check.py (A) | wom7web | .parent | r2 / a3 / h0 / j1 / s5 / t1 |
| secret_flow_check.py (A) | wom7web | parents[3], cwd, reads 1 wom7web/project/* items, names wom7web, names wom7api | r0 / a3 / h0 / j0 / s0 / t0 |
| skills_catalogue.py (A) | wom7web | parents[2], reads 1 wom7web/project/* items, names wom7web | r0 / a2 / h0 / j3 / s1 / t1 |
| stage_guard.py (A) | wom7web | .parent, reads 1 wom7web/project/* items | r0 / a4 / h0 / j0 / s0 / t0 |
| state_bounds.py (A) | wom7web | parents[2], reads 1 wom7web/project/* items, names wom7web | r0 / a2 / h0 / j1 / s1 / t1 |
| status_truth.py (A) | wom7web | parents[3], cwd, names wom7web | r0 / a0 / h0 / j0 / s0 / t0 |
| sync_epic_vocabulary.py (A) | wom7web | .parent, reads 1 wom7web/project/* items | r0 / a2 / h0 / j0 / s2 / t1 |
| sync_project_fields.py (A) | wom7web | parents[2,3], reads 1 wom7web/project/* items | r0 / a1 / h0 / j2 / s2 / t2 |
| sync_subissues.py (A) | wom7web | parents[2] | r0 / a2 / h0 / j0 / s0 / t1 |
| test_obsidian_mcp.py (A) | wom7web | names wom7web | r0 / a0 / h0 / j0 / s0 / t0 |
| ticket_id_align_check.py (A) | wom7web | parents[2,3] | r0 / a1 / h0 / j0 / s0 / t1 |
| tickets_frontmatter_sync.py (A) | wom7web | parents[3], names wom7web | r0 / a2 / h1 / j2 / s0 / t0 |
| tool_usage_probe.py (A) | wom7web | parents[3], reads 1 wom7web/project/* items, names wom7web, names wom7api | r0 / a1 / h0 / j0 / s0 / t0 |
| toolset_status.py (A) | wom7web | parents[2], cwd, names wom7web | r0 / a1 / h0 / j0 / s0 / t0 |
| type_backfill.py (A) | wom7web | parents[2,3] | r0 / a1 / h0 / j0 / s0 / t0 |
| vm_supervisor.py (A) | wom7web | - | r0 / a3 / h0 / j1 / s0 / t1 |
| write_hygiene_docs.py (A) | wom7web | .parent, reads 1 wom7web/project/* items, names wom7web, names wom7api | r0 / a0 / h0 / j0 / s0 / t0 |
| zc_compression_measure.py (A) | wom7web | cwd, reads 1 wom7web/project/* items | r0 / a0 / h0 / j0 / s0 / t0 |
| zeroclaw_manage.py (A) | wom7web | parents[2], reads 1 wom7web/project/* items | r0 / a0 / h0 / j0 / s0 / t0 |
| bake_pdfs.py (C) | wom7api | ../, names wom7web | r0 / a5 / h0 / j0 / s1 / t0 |
| healthcheck.py (C) | wom7api | - | r0 / a3 / h0 / j1 / s0 / t1 |
| open_vault.py (C) | wom7api | parents[2], reads 1 wom7web/project/* items, names wom7web | r0 / a3 / h0 / j0 / s0 / t1 |
| resumes_upload.py (C) | wom7api | .parent, names wom7web | r0 / a3 / h0 / j1 / s0 / t1 |
| ast_grep_test.py (C) | wom7web | parents[1], cwd, reads 1 wom7web/project/* items | r0 / a1 / h0 / j0 / s1 / t0 |
| backup_watchdog_drift.py (C) | wom7web | parents[2] | r0 / a2 / h0 / j0 / s0 / t1 |
| credential_snapshot.py (C) | wom7web | parents[2], cwd, reads 1 wom7web/project/* items, names wom7api | r0 / a1 / h0 / j0 / s0 / t0 |
| env_rename_migrate.py (C) | wom7web | parents[3], cwd, names wom7web, names wom7api | r0 / a0 / h0 / j0 / s0 / t0 |
| gen_status_dashboard.py (C) | wom7web | parents[2], reads 3 wom7web/project/* items, names wom7web | r0 / a1 / h1 / j0 / s0 / t0 |
| org_migrate_execute.py (C) | wom7web | parents[2,3] | r0 / a2 / h0 / j0 / s0 / t1 |
| org_migrate_plan.py (C) | wom7web | parents[2], reads 1 wom7web/project/* items | r0 / a2 / h1 / j0 / s1 / t1 |
| stamp_build.py (C) | wom7web | parents[2], names wom7api | r1 / a2 / h0 / j0 / s0 / t0 |
| verify_siri_shortcuts_contract.py (C) | wom7web | parents[2], names wom7web | r0 / a0 / h0 / j0 / s0 / t0 |
| version_doctor.py (C) | wom7web | parents[2], cwd, names wom7web, names wom7api | r0 / a2 / h0 / j1 / s1 / t2 |
