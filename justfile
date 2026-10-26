# ── w0m estate root forwarder ────────────────────────────────────────────────
# Root justfile for the workspace (@wom). Delegates queue queries, SDLC gates,
# state surface management, and skills orchestration to the canonical repos.

set dotenv-load := false

# Canonical @wom estate root exported to all child recipes and scripts (T427 / AgDR-0025).
export W0M_ROOT := env_var_or_default('W0M_ROOT', justfile_directory())

# Deployment Version & Parameters (T131 / T421)
project_ref := "pqbbjgeapylcengbuvee"
# Infisical project (workspace) id, the ONE source for every `infisical run` below (T429). It is an
# identifier, not a credential, and equals wom7api/.infisical.json `workspaceId`. Explicit, because
# these recipes run from @wom, which has no .infisical.json link (the T421 elevation broke that silently).
infisical_project_id := "87a1718d-17c6-4c5e-b0c1-f8bb2fd9d13c"
# ONE version per release, across nested `just` processes. A backtick runs once per `just` PROCESS, and
# the chain spawns several (`supabase-redeploy-all` → wom7api → back here for `deploy-functions`), so each
# re-ran `date`: run 7 (2026-09-24) stamped the edge functions 11 minutes after the apps, and the transcript
# was named after a version `deploy_log` never recorded. The outermost invocation mints it and EXPORTS it;
# every nested one inherits. Unset = a fresh standalone run, which correctly mints its own.
export W0M_DEPLOY_VERSION := env_var_or_default('W0M_DEPLOY_VERSION', `date +%Y.%m.%d-%s`)
export W0M_DEPLOY_AT := env_var_or_default('W0M_DEPLOY_AT', `date -u +%Y-%m-%dT%H:%M:%SZ`)
deploy_version := W0M_DEPLOY_VERSION
deploy_at := W0M_DEPLOY_AT
deploy_commit := `git rev-parse --short HEAD`
# wom7api/supabase/config.toml reads `env(W0M_DB_MIGRATIONS)`, which has no default: unset means
# EVERY `supabase` command fails with ProjectConfigParseError (T248). Recipes here that call the CLI
# directly (`deploy-function`, `deploy-functions`) need the same export wom7api/justfile carries;
# without it the first `just deploy-function` failed (T431).
export W0M_DB_MIGRATIONS := env_var_or_default('W0M_DB_MIGRATIONS', 'true')

default:
    @just --justfile wom7web/justfile default

# ── Queue & Triage (T146 / T232 / T412) ─────────────────────────────────────
# Hot list, SDLC rank, dynamic epic/ticket-set plan projections, and triage tools
tasks *args:
    @python3 scripts/tasks_query.py {{ args }}

[positional-arguments]
eli5 *args:
    @python3 scripts/ticket_eli5.py "$@"

eli5-test:
    @python3 wom7web/project/scripts/tests/test_ticket_eli5.py

system-one-test:
    @python3 wom7web/project/scripts/tests/test_system_one.py

hooks-llm-check:
    @python3 wom7web/project/scripts/hooks_llm_check.py

system-one-bench *args:
    @python3 wom7web/project/scripts/system_one_bench.py {{ args }}

tasks-render *args:
    @python3 scripts/tasks_render.py {{ args }}

agent-concurrency-test:
    @python3 scripts/tests/test_agent_concurrency.py

project-archetypes-test:
    @python3 wom7web/project/scripts/tests/test_project_archetypes.py

profile-resolve *args:
    @python3 wom7web/project/scripts/profile_resolver.py resolve {{ args }}

profile-env *args:
    @python3 wom7web/project/scripts/profile_resolver.py env {{ args }}

profile-run *args:
    @python3 wom7web/project/scripts/profile_resolver.py run {{ args }}

profile-infisical slug *args:
    @python3 wom7web/project/scripts/profile_resolver.py infisical {{ slug }} {{ args }}

profile-jam slug *args:
    @python3 wom7web/project/scripts/profile_resolver.py jam {{ slug }} {{ args }}

profile-inject-vm slug vm *args:
    @python3 wom7web/project/scripts/profile_resolver.py inject-vm {{ slug }} {{ vm }} {{ args }}

profile-resolver-test:
    @python3 wom7web/project/scripts/tests/test_profile_resolver.py

ticket-audit *args:
    @python3 scripts/ticket_audit.py {{ args }}

ticket-audit-test:
    @python3 wom7web/project/scripts/tests/test_ticket_audit.py

sync-tickets *args:
    @python3 scripts/sync_github.py {{ args }}

sync-tickets-test:
    @python3 wom7web/project/scripts/tests/test_ticket_sync.py

[positional-arguments]
diagram *args:
    @python3 scripts/diagram_view.py "$@"

diagram-test:
    @python3 scripts/tests/test_diagram_view.py

# ── Local Merge Queue & Committer (T425) ──────────────────────────────────────
[positional-arguments]
land *args:
    @python3 scripts/land.py "$@"

[positional-arguments]
land-root *args:
    @python3 scripts/land.py root "$@"

[positional-arguments]
land-check *args:
    @python3 scripts/land.py check "$@"

land-status *args:
    @python3 scripts/land.py status {{ args }}

land-test:
    @python3 scripts/tests/test_land.py

dod-check *args:
    @python3 scripts/dod_check.py {{ args }}

tasks-bounds *args:
    @python3 scripts/tasks_bounds.py {{ args }}

tasks-bounds-test:
    @python3 wom7web/project/scripts/tests/test_tasks_bounds.py

tasks-rotate *args:
    @python3 scripts/tasks_rotate.py {{ args }}

tasks-rotate-test:
    @python3 wom7web/project/scripts/tests/test_tasks_rotate.py

ticket-schema-check *args:
    @python3 scripts/ticket_schema_check.py {{ args }}

ticket-schema-check-test:
    @python3 wom7web/project/scripts/tests/test_ticket_schema_check.py

ticket-deps *args:
    @python3 scripts/ticket_deps.py {{ args }}

ticket-deps-test:
    @python3 scripts/ticket_deps.py --test

blocker-detection-test:
    @python3 wom7web/project/scripts/tests/test_blocker_detection.py

ticket-graph *args:
    @python3 scripts/ticket_graph.py {{ args }}

ac-recipe-check *args:
    @python3 scripts/ac_recipe_check.py {{ args }}

ac-recipe-check-test:
    @python3 wom7web/project/scripts/tests/test_ac_recipe_check.py

ac-trace-check *args:
    @python3 scripts/ac_trace_check.py {{ args }}

# ── Spec & SDLC Quality Gates (T23 / T33 / T72 / T110 / T419) ─────────────────
spec-drift *args:
    @python3 scripts/spec_drift_gate.py {{ args }}

spec-drift-ownership-test:
    @python3 wom7web/project/scripts/tests/test_spec_drift_ownership.py

spec-reality *args:
    @python3 scripts/spec_reality_check.py {{ args }}

spec-standard *args:
    @python3 scripts/spec_standard_check.py {{ args }}

spec-standard-test:
    @python3 wom7web/project/scripts/tests/test_spec_standard.py

spec-systems *args:
    @python3 scripts/spec_systems_gate.py {{ args }}

spec-systems-test:
    @python3 scripts/spec_systems_gate.py --selftest

sdlc-trace *args:
    @python3 scripts/sdlc_trace.py {{ args }}

sdlc-trace-test:
    @python3 wom7web/project/scripts/tests/test_sdlc_trace.py

# ── Design System & Shipping Code Reconciliation (T420) ──────────────────────
ds-check *args:
    @python3 scripts/ds_check.py {{ args }}

ds-check-test:
    @python3 wom7web/project/scripts/tests/test_ds_check.py

ds-react-free-test:
    @python3 -m unittest scripts/tests/test_design_system_react_free.py



# ── Estate Search (T406) ─────────────────────────────────────────────────────
# Bounded multi-repo search with LC_ALL=C and --no-pager. Never silently empty.
# Positional, not `{{ args }}`: interpolation re-splits the pattern through the shell, so
# `just search "a|b"` ran `b` as a command instead of searching for an alternation.
[positional-arguments]
search *args:
    @python3 scripts/estate_search.py "$@"

search-test:
    @python3 -m pytest scripts/tests/test_estate_search.py -q

# ── Coordinated Multi-Agent Worktrees (T411 AC5) ─────────────────────────────
worktree-agent id *args:
    @python3 scripts/worktree_agent.py create {{ id }} {{ args }}

worktree-agent-remove id *args:
    @python3 scripts/worktree_agent.py remove {{ id }} {{ args }}

worktree-agent-list:
    @python3 scripts/worktree_agent.py list

# ── Estate Health Audit (T96 / T414) ─────────────────────────────────────────
audit *args:
    @python3 scripts/w0m_audit.py {{ args }}

# ── GitHub PR Tool (T345 / T369 / T377 / T414) ───────────────────────────────
prs *args:
    @python3 scripts/w0m_prs.py {{ args }}

prs-open *args:
    @python3 scripts/w0m_prs.py table --preset wom7pr {{ args }}

forks *args:
    @python3 scripts/w0m_prs.py forks {{ args }}

forks-check:
    @python3 scripts/w0m_prs.py forks --strict

forks-fetch *args:
    @python3 scripts/w0m_prs.py fetch {{ args }}

forks-info repo *args:
    @python3 scripts/w0m_prs.py info {{ repo }} {{ args }}

forks-update *args:
    @python3 scripts/w0m_prs.py update {{ args }}

forks-sync *args:
    @python3 scripts/w0m_prs.py update {{ args }}

prs-test:
    @python3 wom7web/project/scripts/tests/test_w0m_prs.py

rename-audit *args:
    @just --justfile wom7web/justfile rename-audit {{ args }}

rename-audit-test:
    @just --justfile wom7web/justfile rename-audit-test

decommission-check *args:
    @just --justfile wom7web/justfile decommission-check {{ args }}

decommission-check-test:
    @just --justfile wom7web/justfile decommission-check-test

default-test:
    @just --justfile wom7web/justfile default-test

# ── Ticket Duplication Checks (T403 / T414) ──────────────────────────────────
ticket-dups *args:
    @python3 scripts/ticket_duplicate_check.py {{ args }}

ticket-dups-test:
    @python3 wom7web/project/scripts/tests/test_ticket_duplicate_check.py

# ── Automated Ticket Recycling (T397 / T414) ─────────────────────────────────
ticket-recycle *args:
    @python3 scripts/ticket_recycle.py {{ args }}

ticket-recycle-test:
    @python3 wom7web/project/scripts/tests/test_ticket_recycle.py

# ── Zero-NPX Invariant Audit (T398 / T414) ───────────────────────────────────
npx-audit *args:
    @python3 scripts/npx_audit.py {{ args }}

npx-audit-test:
    @python3 wom7web/project/scripts/tests/test_npx_audit.py

# ── Authorization Admin Client Ratchet (T202 / T327) ──────────────────────────
authz-admin-client *args:
    @just --justfile wom7web/justfile authz-admin-client {{ args }}

# T453 — live default-deny probe (read-only; run after the owner's deploy) and its offline red probes.
route-policy-live *args:
    @just --justfile wom7web/justfile route-policy-live {{ args }}

route-policy-live-test:
    @just --justfile wom7web/justfile route-policy-live-test

# T453 AC7 — cross-app route-policy check. Forwards to wom7api/justfile, where the recipe lives.
route-policy-check:
    @just --justfile wom7web/justfile route-policy-check

authz-admin-client-test:
    @just --justfile wom7web/justfile authz-admin-client-test

# ── macOS Host Security Posture (T233 / T414) ─────────────────────────────────
host-posture *args:
    @python3 scripts/host_posture.py {{ args }}

host-posture-check:
    @python3 scripts/host_posture.py --enforce

host-posture-test:
    @python3 wom7web/project/scripts/tests/test_host_posture.py

# ── Preflight & SDLC Doctor (T414) ───────────────────────────────────────────
preflight *args:
    @just --justfile wom7web/justfile preflight {{ args }}

sdlc-doctor *args:
    @python3 scripts/sdlc_doctor.py {{ args }}

# ── SDLC Machinery & Gates (T414) ────────────────────────────────────────────
gate ticket status note="":
    @python3 scripts/gate_advance.py {{ ticket }} --status {{ status }} {{ if note == "" { "" } else { "--note '" + note + "'" } }}

ticket-paths ticket:
    @python3 scripts/check_ticket_paths.py {{ ticket }}

ticket-paths-test:
    @python3 wom7api/scripts/tests/test_check_ticket_paths.py

# ── Tech Debt Register (T228 / T414) ─────────────────────────────────────────
debt-check *args:
    @python3 scripts/debt_register_check.py {{ args }}

debt-check-test:
    @python3 wom7web/project/scripts/tests/test_debt_register_check.py

lexicon-lint-test:
    @python3 wom7web/project/scripts/tests/test_lexicon_lint.py

schema-check *args:
    @python3 wom7web/project/scripts/schema_check.py {{ args }}

schema-check-test:
    @python3 wom7web/project/scripts/tests/test_schema_check.py

# Forwarding target for running any arbitrary wom7web recipe from workspace root
do recipe *args:
    @just --justfile wom7web/justfile {{ recipe }} {{ args }}

# ── Knowledge & Graph ────────────────────────────────────────────────────────
ask question repo="":
    @just --justfile wom7web/justfile ask "{{ question }}" "{{ repo }}"

graph-global *args:
    @just --justfile wom7web/justfile graph-global {{ args }}

graph-health *args:
    @just --justfile wom7web/justfile graph-health {{ args }}

crg-serve *args:
    @just --justfile wom7web/justfile crg-serve {{ args }}

crg-open *args:
    @just --justfile wom7web/justfile crg-open {{ args }}

crg-extract *args:
    @just --justfile wom7web/justfile crg-extract {{ args }}

graph-tree *args:
    @just --justfile wom7web/justfile graph-tree {{ args }}

graph-callflow *args:
    @just --justfile wom7web/justfile graph-callflow {{ args }}

graph-query *args:
    @just --justfile wom7web/justfile graph-query {{ args }}

graph-explain *args:
    @just --justfile wom7web/justfile graph-explain {{ args }}

graph-path *args:
    @just --justfile wom7web/justfile graph-path {{ args }}

graph-affected *args:
    @just --justfile wom7web/justfile graph-affected {{ args }}

graph-benchmark *args:
    @just --justfile wom7web/justfile graph-benchmark {{ args }}

# ── Deployment Machinery & Elevation (T131 / T161 / T421) ─────────────────────
# One producer for the estate's release-version schema (T131 AC1).
version:
    @echo "{{ deploy_version }}"

# `_confirm <step>` asks a human and ABORTS the recipe on anything but a confirmed yes.
#
# 🔑 Why here and not in the harness `ask` permission tier: `ask` DOES NOT GATE. Probed
# 2026-08-02 (T161 AC3) and re-probed 2026-08-10 — both times a rule in `ask` ran with no
# prompt, while the same shape in `deny` was withheld instantly. Shipping `ask` rules would
# be a gate that reads as protection and withholds nothing.
#
# What makes this one real — three layers (T435, 2026-09-24): (1) an agent session is refused
# outright, by process ancestry (`claude`, `agy`, `codex`, IDE language servers …) or agent env
# markers, before any prompt or consent; (2) the `yes` is read only from a real terminal, never a
# pipe; (3) macOS then verifies the device owner (Touch ID / password / Watch). A terminal alone
# was NOT enough: agy held a pty, saw the db-migrate prompt and answered it itself on 2026-09-17.
# No override env var exists, deliberately; an escape hatch is the hole.
#
# Consent: confirming a ROOT (`deploy`, `deploy-all`) covers the steps it chains for 45 min
# (`ttl_seconds: 2700`), bound to the git HEAD it was granted at. Steps in `always_confirm`
# (`db-reset`, `db-backup`, `storage-backup`, `db-psql`, `rotate`, `sync-env`,
# `sync-wom7api-secrets`, `crawler-deploy`) re-prompt ANYWAY.
# 🔴 `db-migrate` is NOT among them — it rides the `deploy-all` consent. That was an owner
# decision on 2026-08-16, recorded in `confirm-policy.json -> _notes.one_yes_is_the_decision`:
# the owner was offered the chance to put it back and declined. Re-adding it reverses a decision
# rather than fixing a bug, and `test_confirm_step.py` fails and says so. This comment claimed the
# opposite for 34 days (T407, [[AgDR-0024]]) — every behavioural probe stayed green throughout,
# because what had rotted was the description, not the gate.
# Policy is DATA: project/confirm-policy.json. Unrecognised step => confirm (fail closed).
_confirm step:
    @python3 wom7web/project/scripts/confirm_step.py {{ step }}

# Red probes for the confirmation gate (T161 AC3, extended by T407, T435, T471, and T541). 66 cases: it must
# withhold from an automated caller, refuse a piped "yes", refuse an agent session even with a pty
# and a live consent, refuse when the Touch ID dialog is not confirmed, find every deploy-shaped
# recipe without `_confirm`, fail CLOSED on an unrecognised step, honour a granted root for chained
# steps, and — since T407 — assert that every surface DESCRIBING this
# gate still matches `confirm-policy.json`, in both directions, with an unreadable surface failing
# as UNMEASURABLE rather than passing on zero bytes.
confirm-test:
    @python3 wom7web/project/scripts/tests/test_confirm_step.py

# Which confirmation channels does THIS shell expose?
confirm-doctor:
    @python3 wom7web/project/scripts/confirm_step.py --doctor

# Enroll or rotate a 6-digit TOTP secret for cross-device confirmation
confirm-enroll-totp:
    @python3 wom7web/project/scripts/confirm_step.py --enroll-totp

# Every `pnpm --filter <app> build` below runs from `wom7web`, never from @wom. @wom's package.json
# has no `packageManager` pin and is not the pnpm workspace, so from here PATH's pnpm (12.x) ran the
# build without the workspace root's node_modules/.bin, and the first root `deploy-web` failed with
# `astro: command not found` (T431, 2026-09-23). Guarded by `just deploy-elevation-test`.
# Build all web workspaces and stamp release metadata
build:
    @cd wom7web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter web --filter cp --filter join --filter job --filter demo build
    @python3 wom7web/project/scripts/stamp_build.py \
        --version "{{ deploy_version }}" --at "{{ deploy_at }}" --commit "{{ deploy_commit }}"

_assert-provisioned app:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 wom7web/project/scripts/build_provisioning_gate.py --app {{ app }}

# Deploy apps/web (webomage.com)
deploy-web: (_confirm "deploy-web")
    @echo "Building and deploying apps/web to Cloudflare Workers (Version: {{ deploy_version }})..."
    @echo "📸 Updating static snapshots..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- node wom7web/apps/web/scripts/snapshot-settings.mjs || true
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- node wom7web/apps/web/scripts/snapshot-blueprints.mjs || true
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- node wom7web/apps/web/scripts/snapshot-knowledge.mjs || true
    @cd wom7web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter web build
    @just _assert-provisioned web
    @echo "🔍 Building pagefind search index..."
    @cd wom7web/apps/web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm run build:search
    @cd wom7web/apps/web/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var APP_VERSION:${W0M_APP_VERSION_WEB:-{{ deploy_version }}} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py web "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Deploy apps/join (join.webomage.com)
deploy-join: (_confirm "deploy-join")
    @echo "Building and deploying apps/join to Cloudflare Workers (Version: {{ deploy_version }})..."
    @cd wom7web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter join build
    @just _assert-provisioned join
    @cd wom7web/apps/join/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var APP_VERSION:${W0M_APP_VERSION_JOIN:-{{ deploy_version }}} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py join "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Deploy apps/job (job.webomage.com)
deploy-job: (_confirm "deploy-job")
    @echo "Building and deploying apps/job to Cloudflare Workers (Version: {{ deploy_version }})..."
    @cd wom7web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter job build
    @just _assert-provisioned job
    @cd wom7web/apps/job/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var APP_VERSION:${W0M_APP_VERSION_JOB:-{{ deploy_version }}} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py job "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Deploy apps/demo (demo.webomage.com — T79 demo showcase) to Cloudflare Workers
deploy-demo: (_confirm "deploy-demo")
    @echo "Building and deploying apps/demo to Cloudflare Workers (Version: {{ deploy_version }})..."
    @cd wom7web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter demo build
    @cd wom7web/apps/demo/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var APP_VERSION:${W0M_APP_VERSION_DEMO:-{{ deploy_version }}} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py demo "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Deploy apps/cp (cp.w0m.xyz)
deploy-cp: (_confirm "deploy-cp")
    @echo "Building and deploying apps/cp to Cloudflare Workers (Version: {{ deploy_version }})..."
    @cd wom7web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter cp build
    @just _assert-provisioned cp
    @cd wom7web/apps/cp/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var APP_VERSION:${W0M_APP_VERSION_CP:-{{ deploy_version }}} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py cp "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Deploy wom7func to Cloudflare
deploy-workers: (_confirm "deploy-workers")
    @echo "Deploying wom7func to Cloudflare Workflows (Version: {{ deploy_version }})..."
    @cd wom7func && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm exec wrangler deploy --var DEPLOY_VERSION:{{ deploy_version }} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py wom7func "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Deploy all functions in parallel using Supabase CLI
deploy-functions: (_confirm "deploy-functions")
    @echo "Deploying all functions to project {{ project_ref }} in parallel (Version: {{ deploy_version }})..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'supabase secrets set DEPLOY_VERSION="{{ deploy_version }}" DEPLOY_AT="{{ deploy_at }}" DEPLOY_COMMIT="{{ deploy_commit }}" --project-ref {{ project_ref }} > /dev/null 2>&1'
    # Bulk deploy, then VERIFY each function updated and retry only the stale ones (scripts/deploy_functions.py).
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/deploy_functions.py --project-ref {{ project_ref }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py api "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Offline probes for the deploy-functions staleness/retry logic.
deploy-functions-test:
    @python3 scripts/deploy_functions.py --self-test

# Deploy API capability layer
# T431: deploy NAMED edge function(s): the per-function top-level helper, replacing 25 copies in
# wom7api/justfile. Validates every name against wom7api/supabase/functions/ before deploying anything;
# JWT posture comes from supabase/config.toml, as for the bulk deploy. `just deploy-function-list`
# prints the names. It does not restamp DEPLOY_VERSION: a partial redeploy is not a release.
deploy-function +names: (_confirm "deploy-function")
    @python3 scripts/deploy_function.py {{ names }} --project-ref {{ project_ref }} --infisical-project-id {{ infisical_project_id }}

# Names `deploy-function` accepts (read-only, no confirmation).
deploy-function-list:
    @python3 scripts/deploy_function.py --list --project-ref {{ project_ref }} --infisical-project-id {{ infisical_project_id }}

deploy-api: (_confirm "deploy-api") check-auth check-warp supabase-redeploy-all check-supabase _log-deploy

# Pre-deploy security gate & infrastructure checks
check-infisical:
    @python3 scripts/check_infisical.py --project-id {{ infisical_project_id }}

check-guardrails:
    @echo "🛡  Pre-deploy security gate (secrets + test-admin + connection-strings)..."
    @cd wom7api && pre-commit run gitleaks --all-files
    @cd wom7web && pre-commit run gitleaks --all-files
    @cd wom7web && pre-commit run guard-test-admin --all-files
    @echo "🔑 Inline-credential connection-string scan (gitleaks gap — T32)..."
    @cd wom7api && if git --no-pager grep -nEI '(postgres|postgresql|mysql|mongodb|redis|amqp)://[A-Za-z0-9._%+-]+:[A-Za-z0-9._%+~!-]{6,}@' -- ':!*.md'; then echo "❌ inline credential in tracked files — remove + rotate (see T32)"; exit 1; fi
    @cd wom7web && if git --no-pager grep -nEI '(postgres|postgresql|mysql|mongodb|redis|amqp)://[A-Za-z0-9._%+-]+:[A-Za-z0-9._%+~!-]{6,}@' -- ':!*.md'; then echo "❌ inline credential in tracked files — remove + rotate (see T32)"; exit 1; fi
    @echo "✅ security gate passed"

check-warp:
    @just --justfile wom7api/justfile check-warp

check-auth:
    @just --justfile wom7api/justfile check-auth

check-supabase:
    @just --justfile wom7api/justfile check-supabase

supabase-redeploy-all:
    @just --justfile wom7api/justfile supabase-redeploy-all

db-migrate *args:
    @just --justfile wom7api/justfile db-migrate {{ args }}

# T551 AC4 — allocate the next free 14-digit migration version from origin/beta + local migrations and create wom7api/supabase/migrations/<version>_<name>.sql.
migration-new name:
    @python3 wom7web/project/scripts/db_drift_check.py --new "{{ name }}"

# T529 — clients & client_users retirement verification and offline tests
clients-retirement-verify *args:
    @just --justfile wom7api/justfile clients-retirement-verify {{ args }}

clients-retirement-verify-test:
    @just --justfile wom7api/justfile clients-retirement-verify-test

goldens *args:
    @just --justfile wom7api/justfile goldens {{ args }}

smoke-live *args:
    @just --justfile wom7api/justfile smoke-live {{ args }}

_assert-clean-tree:
    @pnpm --dir wom7api exec tsx dagger/pipeline.ts assert-clean-tree

_log-deploy:
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py release "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

changelog:
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/gen_changelog.py

changelog-drift *args:
    @python3 wom7web/project/scripts/changelog_drift.py {{ args }}

changelog-drift-test:
    @python3 wom7web/project/scripts/tests/test_changelog_drift.py

changelog-check *args:
    @python3 scripts/changelog_check.py {{ args }}

changelog-test:
    @python3 scripts/tests/test_changelog_check.py
    @python3 scripts/tests/test_gen_changelog.py

# Where does a NAME live? Inventory by surface class across every estate repo; `--gate` fails while a LIVE reference
# remains (history/records may keep it). Run before AND after renaming a repo, worker, service or env var.
name-refs *args:
    @python3 scripts/name_refs.py {{ args }}

name-refs-test:
    @python3 scripts/tests/test_name_refs.py

# CP feature index (see wom7api/justfile).
cp-feature-index *args:
    @just --justfile wom7web/justfile cp-feature-index {{ args }}

cp-feature-index-test:
    @just --justfile wom7web/justfile cp-feature-index-test

cp-feature-index-check:
    @just --justfile wom7web/justfile cp-feature-index-check

# T244 — secret flow gate (see wom7api/justfile).
secret-flow-check *args:
    @just --justfile wom7web/justfile secret-flow-check {{ args }}

secret-flow-check-test:
    @just --justfile wom7web/justfile secret-flow-check-test

secret-flow-check-enforce:
    @just --justfile wom7web/justfile secret-flow-check-enforce

# T335 — validated setter for `.w0m/sdlc.json -> current_plan` (see wom7api/justfile).
plan-set *args:
    @python3 scripts/plan_set.py {{ args }}

plan-set-test:
    @python3 scripts/tests/test_plan_set.py

plan-set-check:
    @python3 scripts/plan_set.py --check

# T473 (owner, 2026-09-27): the DEFAULT deploy ships a release, never a working tree. It tags origin/beta of every
# estate repo as release/<version>, checks that out detached under ~/.w0m/releases/<version>/w0m, deploys FROM there
# and publishes the tags only if the deploy succeeds. The main checkouts may be dirty at any moment (people and agents
# work in them at once); a release cannot see that. Inside the release worktree W0M_RELEASE_WORKTREE=1 is set and this
# recipe runs the chain itself. Forcing a deploy of the local working tree is explicit: `just deploy-local`.
deploy:
    @pnpm --dir wom7api exec tsx dagger/pipeline.ts entrypoint --mode deploy

# T473 — FORCE: deploy the local working tree as it is (uncommitted edits of anyone included). Not the default.
deploy-local:
    @python3 wom7web/project/scripts/release.py local-warning
    @env W0M_DEPLOY_LOCAL=1 just deploy

# T503 (2026-09-30). The chain used to be `check-warp check-infisical db-migrate deploy`, and the test gate sat INSIDE `deploy`: the schema was written to
# the live database BEFORE any test ran, so a red gate arrived after an irreversible change (two migrations applied, then five blocking suites failed, on
# 2026-09-30; the same shape on 2026-09-29). Now the chain is three parts, in this order, for both `deploy` and `deploy-all`:
#   _deploy-preflight  the cheap deterministic ratchets, BEFORE the confirmation prompt (a red one costs no Touch ID, no release cut, no 8-minute suite)
#   _deploy-gates      every check that can fail: infisical, guardrails, the whole offline suite tier. Writes NOTHING live.
#   _deploy-ship       what changes live state: db-migrate (deploy-all only), the app deploys, the smoke test, the clean-tree assertion, the deploy log
# `scripts/tests/test_deploy_chain_order.py` pins the order from the real recipe graph and red-probes the old one.
_deploy-chain: _deploy-preflight (_confirm "deploy") _deploy-gates _deploy-ship

# The fast tier of the suite registry (`"prepush": true`) plus the STATE.md drift gate: everything that is deterministic, offline and takes seconds.
# Pre-push runs the same set (wom7web/.husky/pre-push), so a red ratchet is normally found where the change is made, not at deploy time.
_deploy-preflight:
    @python3 scripts/run_suites.py --prepush
    @just state-check

# Note: `goldens` is excluded from `_deploy-gates` because booting the local Astro dev server + Playwright browser matrix inside a deploy run halts memory-constrained hosts. Run `just goldens` standalone when needed.
_deploy-gates: check-infisical check-guardrails test

_deploy-ship:
    @just _deploy-apps
    @just smoke-live
    @just _assert-clean-tree
    @just _log-deploy

# T473 D2 & T64 AC1/AC3: deploy each app via the TypeScript Dagger pipeline module (`wom7api/dagger/pipeline.ts`).
# W0M_RELEASE_APPS (set by a release deploy) lists the apps whose fingerprint changed since the last deployed release;
# the others are skipped and keep serving their previous version. Unset (a local deploy) = every app.
_deploy-apps:
    @pnpm --dir wom7api exec tsx dagger/pipeline.ts deploy-apps

deploy-all:
    @pnpm --dir wom7api exec tsx dagger/pipeline.ts entrypoint --mode deploy-all

# T64 AC1 & AC3 — Dagger TypeScript pipeline plan preview & unit/typecheck suite (`wom7api/dagger/`).
dagger-plan:
    @pnpm --dir wom7api exec tsx dagger/pipeline.ts plan

dagger-test:
    @cd wom7api && pnpm exec tsc --noEmit -p dagger/tsconfig.json && pnpm exec vitest run dagger/__tests__/pipeline.test.ts

# T473 — FORCE: deploy-all from the local working tree. Not the default.
deploy-all-local:
    @python3 wom7web/project/scripts/release.py local-warning
    @env W0M_DEPLOY_LOCAL=1 just deploy-all

# T473 — release helpers. `release-cut` + `release-worktree` + `release-deploy` is what `just deploy` does in one go;
# use them to inspect a release before deploying it, or to retry a failed one without cutting a new version.
release-cut *args:
    @python3 wom7web/project/scripts/release.py cut {{ args }}

release-worktree version:
    @python3 wom7web/project/scripts/release.py worktree {{ version }}

release-verify version:
    @python3 wom7web/project/scripts/release.py verify {{ version }}

release-deploy version mode="deploy":
    @python3 wom7web/project/scripts/release.py deploy {{ version }} {{ mode }}

release-publish version:
    @python3 wom7web/project/scripts/release.py publish {{ version }}

release-list:
    @python3 wom7web/project/scripts/release.py list

release-prune keep="":
    @python3 wom7web/project/scripts/release.py prune {{ keep }}

release-test:
    @python3 wom7web/project/scripts/release.py --test

# T554 — land (or re-land) a release's record on origin/beta without touching this checkout: a parked one first, else built from the release manifest. Run it when a deploy
# printed "release record is NOT on origin/beta".
release-record *args:
    @python3 wom7web/project/scripts/release.py record {{ args }}

# T554 — offline proof (27 checks, throwaway git repositories: a lost race is retried, a record never strands on the live checkout, records are read from origin/beta).
release-record-test:
    @python3 wom7web/project/scripts/tests/test_release_record.py

# T531 AC6 — agent trees: one COMPLETE, private copy of the estate per agent (the umbrella with every member repo nested inside), on local branch agent/<name> cut from origin/beta.
# No pull requests and no remote branch: commit in your tree, then `agent-tree-land` fetches, rebases onto origin/beta, checks ticket ids (a collision or a gap is refused) and pushes
# HEAD:beta, members first and the umbrella last. Never forces. See wom7web/project/scripts/agent_tree.py.
agent-tree name:
    @python3 wom7web/project/scripts/agent_tree.py new {{ name }}

agent-tree-list:
    @python3 wom7web/project/scripts/agent_tree.py list

agent-tree-land *args:
    @python3 wom7web/project/scripts/agent_tree.py land {{ args }}

agent-tree-remove name *args:
    @python3 wom7web/project/scripts/agent_tree.py remove {{ name }} {{ args }}

agent-tree-prune:
    @python3 wom7web/project/scripts/agent_tree.py prune

agent-tree-test:
    @python3 -m pytest wom7web/project/scripts/tests/test_agent_tree.py -q -p no:cacheprovider

t531-layers-test:
    @python3 -m pytest wom7web/project/scripts/tests/test_t531_layers.py -q -p no:cacheprovider

[no-cd]
[positional-arguments]
commit *args:
    @python3 "{{justfile_directory()}}/scripts/commit_by_path.py" "$@"

[positional-arguments]
ticket-new *args:
    @python3 "{{justfile_directory()}}/scripts/ticket_new.py" "$@"

# T564 — virtual agent identity (`agent_id`) and cross-worktree ticket claim/tagging system.
agent-id *args:
    @python3 wom7web/project/scripts/agent_identity.py whoami {{ args }}

agent-id-set agent_id *args:
    @python3 wom7web/project/scripts/agent_identity.py set {{ agent_id }} {{ args }}

ticket-claim ticket *args:
    @python3 wom7web/project/scripts/agent_identity.py claim {{ ticket }} {{ args }}

ticket-release ticket *args:
    @python3 wom7web/project/scripts/agent_identity.py release {{ ticket }} {{ args }}

ticket-tag ticket *args:
    @python3 wom7web/project/scripts/agent_identity.py tag {{ ticket }} {{ args }}

agent-claims *args:
    @python3 wom7web/project/scripts/agent_identity.py claims {{ args }}

agent-identity-test:
    @python3 -m pytest wom7web/project/scripts/tests/test_agent_identity.py -q -p no:cacheprovider

# T481 — Persistent isolated STABLE and CONFIRMED worktrees: full local regression runs in stable, stable-promote advances confirmed
stable-sync *args:
    @python3 wom7web/project/scripts/release.py stable-sync {{ args }}

stable-promote *args:
    @python3 wom7web/project/scripts/release.py stable-promote {{ args }}

e2e-stable *args:
    @python3 wom7web/project/scripts/release.py e2e-stable {{ args }}

# T532 — Run E2E tests against local sandbox environment
e2e-local *specs:
    @cd wom7web && just e2e-local {{ specs }}

# T532 — Run live-guard proof test
live-guard-test:
    @cd wom7web && just live-guard-test

# T532 — unit tests for the E2E sandbox isolation guard
e2e-sandbox-guard-test:
    @cd wom7web && just e2e-sandbox-guard-test

_deploy-all-chain: _deploy-preflight (_confirm "deploy-all") check-warp check-infisical _deploy-gates db-migrate _deploy-ship _post-deploy-knowledge

_post-deploy-knowledge:
    #!/usr/bin/env bash
    # A release worktree is a throwaway snapshot: indexing it would register its paths in the code graphs. The
    # main estate refreshes its own knowledge (`just --justfile wom7api/justfile knowledge-light`).
    if [ -n "${W0M_RELEASE_WORKTREE:-}" ]; then echo "knowledge refresh skipped in a release worktree (T473)"; exit 0; fi
    just --justfile wom7api/justfile knowledge-light || true

# Every bare `just <recipe>` in a recipe body must name a recipe that justfile defines — the
# `-`-prefixed call above named one that only wom7api has, silently, from T421 to T431 run 7.
justfile-calls-check *args:
    @python3 scripts/justfile_calls_check.py {{ args }}

justfile-calls-check-test:
    @python3 -m pytest scripts/tests/test_justfile_calls_check.py -q -p no:cacheprovider

# Every `.agents/reports/` file cites an existing ticket — the ticket is the one source of work state (T428).
reports-ticket-check *args:
    @python3 scripts/reports_ticket_check.py {{ args }}

reports-ticket-check-test:
    @python3 -m pytest scripts/tests/test_reports_ticket_check.py -q -p no:cacheprovider

deploy-logged *args:
    @python3 wom7web/project/scripts/deploy_logged.py {{ args }}

deploy-logged-test:
    @python3 wom7web/project/scripts/tests/test_deploy_logged.py

deploy-logs-rotate *args:
    @python3 wom7web/project/scripts/deploy_logs_rotate.py {{ args }}

deploy-logs-rotate-test:
    @python3 wom7web/project/scripts/tests/test_deploy_logs_rotate.py

deploy-in-flight-test:
    @python3 wom7web/project/scripts/tests/test_deploy_in_flight.py

deploy-elevation-test:
    @python3 scripts/tests/test_deploy_elevation.py


# ── State Surface (T145 / T412) ──────────────────────────────────────────────
state-check *args:
    @python3 scripts/state_doctor.py --check {{ args }}

state-save *args:
    @python3 scripts/state_doctor.py --write {{ args }}

state-rotate *args:
    @python3 scripts/state_doctor.py --rotate {{ args }}

# Session-start read: the current ⭐ PICK UP HERE block only (recorded intent, not measured facts).
state-brief:
    @python3 scripts/state_doctor.py --brief

state-doctor-test:
    @python3 wom7web/project/scripts/tests/test_state_doctor.py

# ── Lessons Register (T232 / T414) ───────────────────────────────────────────
lessons *args:
    @python3 scripts/lessons_query.py {{ args }}

lessons-test:
    @python3 scripts/tests/test_lessons_query.py

# ── Decisions Register (T232 / T392 / T414) ──────────────────────────────────
decisions *args:
    @python3 scripts/decisions_index.py {{ args }}

decisions-check:
    @python3 scripts/decisions_index.py --check

decisions-test:
    @python3 scripts/tests/test_decisions_index.py

# ── Skills Platform (Level 1 & Level 2) ──────────────────────────────────────
skills-sync *args:
    @cd wom7skills && pnpm run skills:sync {{ args }}

skills-test *args:
    @cd wom7skills && pnpm run skill-test {{ args }}

skills-update *args:
    @cd wom7skills && pnpm run skill --project "{{ invocation_directory() }}" update --canonical {{ args }}

skills-diff *args:
    @cd wom7skills && pnpm run skill --project "{{ invocation_directory() }}" diff {{ args }}

skills-backport *args:
    @cd wom7skills && pnpm run skill --project "{{ invocation_directory() }}" backport {{ args }}

skills-audit-tools *args:
    @cd wom7skills && pnpm run skill --project "{{ invocation_directory() }}" audit-tools {{ args }}

skills-chips *args:
    @cd wom7skills && pnpm run skill --project "{{ invocation_directory() }}" chips {{ args }}

skills-catalog *args:
    @python3 wom7web/project/scripts/skills_catalog_gen.py --write {{ args }}

skills-catalog-check *args:
    @python3 wom7web/project/scripts/skills_catalog_gen.py --check {{ args }}

skills-catalog-test:
    @PYTHONPATH=wom7web python3 -m pytest wom7web/project/scripts/tests/test_t24_skills_expansion.py -q -p no:cacheprovider

# ── SkillOpt Self-Evolution & Nightly Sleep Loop (T482) ──────────────────────
sleep *args:
    @python3 scripts/sleep_harness.py {{ args }}

sleep-test *args:
    @python3 -m pytest scripts/tests/test_sleep_cli.py -q {{ args }}


# ── Tart Virtual Machine Sandboxes ──────────────────────────────────────────
# VM management shortcuts for local sandboxes (macOS, Ubuntu, BridgeRoad)
vm command="list" name="macos-mini-sandbox":
    @case "{{ command }}" in \
        list) tart list ;; \
        run) tart run {{ name }} ;; \
        isolated) tart run --net-softnet {{ name }} ;; \
        headless) tart run --no-graphics {{ name }} ;; \
        ip) tart ip {{ name }} ;; \
        stop) tart stop {{ name }} ;; \
        reset) \
            tart stop {{ name }} 2>/dev/null || true; \
            tart delete {{ name }} 2>/dev/null || true; \
            tart clone ghcr.io/cirruslabs/macos-tahoe-vanilla:latest {{ name }}; \
            tart set {{ name }} --cpu 4 --memory 6144 --display 1440x900pt; \
            echo "[OK] {{ name }} cleanly reset to mint state" ;; \
        prune) tart prune ;; \
        doctor) just --justfile wom7web/justfile vm-doctor ;; \
        install-guest) wom7pr/tart-guest-agent/packaging/install-darwin.sh {{ name }} ;; \
        *) \
            echo "Unknown VM command: '{{ command }}'"; \
            echo "Usage: just vm [list|run|isolated|headless|ip|stop|reset|prune|doctor|install-guest] [name]"; \
            exit 1 ;; \
    esac

# Explicit recipes for tab-completion
vm-list:
    @tart list

# Run VM doctor: inspect host hypervisor, VM states, runaway CPU, and guest agents
vm-doctor *args:
    @just --justfile wom7web/justfile vm-doctor {{ args }}

vm-run name="macos-mini-sandbox":
    @tart run {{ name }}

vm-run-isolated name="macos-mini-sandbox":
    @tart run --net-softnet {{ name }}

vm-run-headless name="macos-mini-sandbox":
    @tart run --no-graphics {{ name }}

vm-ip name="macos-mini-sandbox":
    @tart ip {{ name }}

vm-stop name="macos-mini-sandbox":
    @tart stop {{ name }}

vm-reset-macos name="macos-mini-sandbox":
    @tart stop {{ name }} 2>/dev/null || true
    @tart delete {{ name }} 2>/dev/null || true
    @tart clone ghcr.io/cirruslabs/macos-tahoe-vanilla:latest {{ name }}
    @tart set {{ name }} --cpu 4 --memory 6144 --display 1440x900pt
    @echo "[OK] {{ name }} cleanly reset to mint state"

vm-prune:
    @tart prune

# Install and verify enhanced w0m tart-guest-agent inside guest VM (T296)
vm-install-guest name="macos-mini-sandbox":
    @wom7pr/tart-guest-agent/packaging/install-darwin.sh {{ name }}


# ── Core Plan & Queue Tests ──────────────────────────────────────────────────
plan-verdict-test:
    @just --justfile wom7web/justfile plan-verdict-test

tasks-render-test:
    @python3 wom7web/project/scripts/tests/test_tasks_render.py

# ── oMLX Service Lifecycle (T374) ────────────────────────────────────────────
omlx-status:
    @just --justfile wom7web/justfile omlx-status

omlx-start:
    @just --justfile wom7web/justfile omlx-start

omlx-stop:
    @just --justfile wom7web/justfile omlx-stop

omlx-restart:
    @just --justfile wom7web/justfile omlx-restart

# ── Headroom Proxy Service Lifecycle (T456) ──────────────────────────────────
headroom-status *args:
    @just --justfile wom7web/justfile headroom-status {{ args }}


headroom-start:
    @just --justfile wom7web/justfile headroom-start

headroom-stop:
    @just --justfile wom7web/justfile headroom-stop

headroom-restart:
    @just --justfile wom7web/justfile headroom-restart

headroom-logs *args:
    @just --justfile wom7web/justfile headroom-logs {{ args }}

headroom-service-test:
    @just --justfile wom7web/justfile headroom-service-test

headroom-bootstrap-status *args:
    @just --justfile wom7web/justfile headroom-bootstrap-status {{ args }}



# ── Version Management (T391 / T414) ─────────────────────────────────────────
version-sync *args:
    @python3 scripts/sync_manifest_versions.py {{ args }}

version-check *args:
    @python3 scripts/sync_manifest_versions.py --check {{ args }}

sync-manifest-versions-test:
    @python3 wom7web/project/scripts/tests/test_sync_manifest_versions.py

# ── Estate Policies & Standards (T130 / T135 / T192 / T256 / T419) ───────────
emoji-check *args:
    @python3 scripts/emoji_policy_check.py {{ args }}

emoji-check-test:
    @python3 wom7web/project/scripts/tests/test_emoji_policy_check.py

emoji-text-dialects-test:
    @python3 wom7web/project/scripts/tests/test_emoji_text_dialects.py

doc-format-check *args:
    @python3 scripts/doc_format_check.py {{ args }}

doc-format-check-test:
    @python3 wom7web/project/scripts/tests/test_doc_format_check.py

hygiene *args:
    @python3 scripts/repo_hygiene.py all {{ args }}

hygiene-check *args:
    @python3 scripts/repo_hygiene.py all {{ args }}

repo-hygiene *args:
    @python3 scripts/repo_hygiene.py all {{ args }}

hygiene-check-test:
    @python3 wom7web/project/scripts/tests/test_repo_hygiene.py

docs-check *args:
    @python3 scripts/repo_hygiene.py docs {{ args }}

license-check *args:
    @python3 scripts/repo_hygiene.py license {{ args }}

secrets-check *args:
    @python3 scripts/repo_hygiene.py secrets {{ args }}

dep-licenses *args:
    @python3 scripts/repo_hygiene.py dep-licenses {{ args }}

ide-trace *args:
    @python3 scripts/ide_trace.py {{ args }}

ide-trace-test:
    @python3 wom7web/project/scripts/tests/test_ide_trace.py

discovery *args:
    @python3 scripts/discovery.py {{ args }}

discovery-test:
    @python3 wom7web/project/scripts/tests/test_discovery.py

# ── Tool & MCP Governance (T112 / T154 / T247 / T419) ────────────────────────
tools *args:
    @python3 scripts/tools_check.py {{ args }}

tools-check *args:
    @python3 scripts/tools_check.py {{ args }}

tools-upgrade *args:
    @python3 scripts/tools_upgrade.py {{ args }}

# T546 — the scheduled run upgrades and smoke-tests, then PROPOSES the bumps (a machine-level state file); it never writes tools-policy.json, so the live checkout stays clean.
tools-weekly *args:
    @python3 scripts/tools_check.py --outdated --cache && python3 scripts/tools_upgrade.py --apply {{ args }}

# T546 — list the proposed known_good bumps (dry run). `--apply`, run from an agent tree (`just agent-tree <name>`), re-verifies each one (installed == proposed, >= min, smoke
# passes) and writes known_good into that tree, ready to commit and `just agent-tree-land`. Refused outside an agent tree.
tools-promote *args:
    @python3 scripts/tools_upgrade.py --promote {{ args }}

tools-upgrade-test:
    @python3 scripts/tests/test_tools_upgrade.py

toolchain-chain-test:
    @python3 wom7web/project/scripts/tests/test_toolchain_chain.py

mcp-declared-test:
    @python3 wom7web/project/scripts/tests/test_mcp_declared.py

mcp-health *args:
    @python3 scripts/mcp_health.py {{ args }}

# ── Estate Test Suites & Hook Runners (T160 / T375 / T419) ───────────────────
test:
    @python3 scripts/run_suites.py --tier offline --level {{ env_var_or_default("W0M_TEST_LEVEL", "critical") }}

# T503 — the fast tier only (`"prepush": true` suites): what pre-push and the deploy pre-flight run.
test-prepush:
    @python3 scripts/run_suites.py --prepush

test-critical:
    @python3 scripts/run_suites.py --prepush

test-medium:
    @python3 scripts/run_suites.py --tier offline --level medium

test-full:
    @python3 scripts/run_suites.py --tier offline --level full

test-all:
    @python3 scripts/run_suites.py --tier all --level full

typecheck *args:
    @just --justfile wom7web/justfile typecheck {{ args }}

svelte-typecheck-ratchet *args:
    @cd wom7web && python3 project/scripts/svelte_typecheck_ratchet.py {{ args }}

svelte-typecheck-ratchet-test:
    @cd wom7web && pytest -q project/scripts/tests/test_svelte_typecheck_ratchet.py

suites-drift *args:
    @python3 scripts/run_suites.py --drift {{ args }}

run-suites-test:
    @python3 wom7web/project/scripts/tests/test_run_suites.py

prepush-status *args:
    @python3 scripts/prepush_runner.py status {{ args }}

prepush-reset *args:
    @python3 scripts/prepush_runner.py reset {{ args }}

prepush-run *args:
    @python3 scripts/prepush_runner.py {{ args }}

prepush-test:
    @python3 wom7web/project/scripts/tests/test_prepush_runner.py

# ── Local Development Stack (T449) ──────────────────────────────────────────
# Check local /etc/hosts for *.w0m.local development domains
hosts-check:
    @python3 scripts/hosts_check.py

# Stop all local development servers (web, workers, and caddy reverse proxy)
stop-dev:
    @just --justfile wom7api/justfile stop-dev

# Start the full local estate stack with *.w0m.local SSL reverse proxy (T449)
dev-stack:
    @just --justfile wom7api/justfile dev-stack

# ── TypeSafe System One & Jev Image Processing (T558 / T556 / T434) ─────────
jev-image *args:
    @python3 wom7web/project/scripts/jev_system_one.py {{ args }}

jev-system-one-test:
    @python3 wom7web/project/scripts/tests/test_jev_system_one.py

# ── Google Research Harness² ContextTree & SurfaceSpec (T556) ───────────────
context-tree *args:
    @python3 wom7web/project/scripts/context_tree.py {{ args }}

context-tree-test:
    @python3 wom7web/project/scripts/tests/test_context_tree.py

harness2-surface-check *args:
    @python3 wom7web/project/scripts/harness2_surface.py {{ args }}

harness2-surface-test:
    @python3 wom7web/project/scripts/tests/test_harness2_surface.py

# ── Org Model S7, Secret History Audit & Resume Vault (T458 / T504 / T510) ──
engagements-hats-verify *args:
    @just --justfile wom7api/justfile engagements-hats-verify {{ args }}

engagements-hats-verify-test:
    @just --justfile wom7api/justfile engagements-hats-verify-test

secret-history-check *args:
    @just --justfile wom7api/justfile secret-history-check {{ args }}

secret-history-check-test:
    @just --justfile wom7api/justfile secret-history-check-test

resume-vault-verify *args:
    @just --justfile wom7api/justfile resume-vault-verify {{ args }}

resume-vault-verify-test:
    @just --justfile wom7api/justfile resume-vault-verify-test

# ── External Project Work Report Ingestion (T357) ────────────────────────────
project-report-ingest *args:
    @python3 wom7web/project/scripts/report_ingest.py {{ args }}

project-report-ingest-test:
    @python3 wom7web/project/scripts/tests/test_report_ingest.py -v

# ── Estate Port Governance & Interactive Status Dashboard (T402 / T394) ─────
ports-check *args:
    @python3 wom7web/project/scripts/ports_check.py {{ args }}

ports-check-test:
    @python3 wom7web/project/scripts/tests/test_ports_check.py

status-dashboard-test:
    @python3 wom7web/project/scripts/tests/test_gen_status_dashboard.py

# ── Estate File Hygiene & _in Tray Disposition (T446 / T447) ────────────────
layout-check *args:
    @python3 wom7web/project/scripts/layout_check.py {{ args }}

layout-check-test:
    @python3 wom7web/project/scripts/tests/test_layout_check.py

in-triage *args:
    @python3 wom7web/project/scripts/in_tray.py triage {{ args }}

in-check *args:
    @python3 wom7web/project/scripts/in_tray.py check {{ args }}

in-sync *args:
    @python3 wom7web/project/scripts/in_tray.py sync {{ args }}

in-check-test:
    @python3 wom7web/project/scripts/tests/test_in_tray.py

# ── Universal System Standards & SSOT Adherence (T214) ──────────────────────
standards-check *args:
    @python3 wom7web/project/scripts/standards_check.py {{ args }}

standards-check-test:
    @python3 wom7web/project/scripts/tests/test_standards_check.py

# ── Client Project Services, Cost Attribution & Scoped Settings (T272) ──────
client-services-check *args:
    @python3 wom7web/project/scripts/client_services_check.py {{ args }}

client-services-check-test:
    @python3 wom7web/project/scripts/tests/test_client_services_check.py

# ── Typed Python Ratchet, Backstage Catalog & DORA/DevEx Cockpit (T448 / T64 / T432) ──
py-typecheck-root *args:
    @mypy --config-file mypy.ini {{ args }}

py-typecheck *args:
    @just --justfile wom7api/justfile py-typecheck {{ args }}

py-typing-check *args:
    @python3 wom7web/project/scripts/py_typing_check.py {{ args }}

py-typing-check-test:
    @python3 wom7web/project/scripts/py_typing_check_test.py

catalog-sync *args:
    @python3 wom7web/project/scripts/catalog_sync.py --write {{ args }}

catalog-check:
    @python3 wom7web/project/scripts/catalog_sync.py --check

catalog-check-test:
    @python3 wom7web/project/scripts/catalog_sync_test.py

dora *args:
    @python3 scripts/dora_metrics.py {{ args }}

devex-pulse *args:
    @python3 scripts/dora_metrics.py --pulse {{ args }}

dora-test:
    @python3 scripts/dora_metrics_test.py

# ── SDLC Branch Hygiene & Stage-Branch Consolidation Monitor (T148) ──────────
branch-hygiene *args:
    @python3 scripts/branch_hygiene.py {{ args }}

branch-hygiene-test:
    @python3 wom7web/project/scripts/tests/test_branch_hygiene.py

# ── Codegraph Codemap Generator & Serena Config Reconciliation (T193 / T172) ─
codemap-gen *args:
    @python3 wom7web/project/scripts/codemap_gen.py --write {{ args }}

codemap-check *args:
    @python3 wom7web/project/scripts/codemap_gen.py --check {{ args }}

codemap-check-test:
    @python3 wom7web/project/scripts/tests/test_codemap_gen.py

serena-config-check *args:
    @python3 wom7web/project/scripts/serena_config_check.py {{ args }}

serena-config-check-test:
    @python3 wom7web/project/scripts/tests/test_serena_config_check.py

# ── Delivery Record, Spec Policy, Consumer Gate, Lessons & OpenCode (T245 / T185 / T177 / T178 / T270 / T152) ──
ac-trace-test:
    @python3 wom7web/project/scripts/tests/test_ac_trace_check.py

spec-policy-check *args:
    @python3 wom7web/project/scripts/spec_policy_check.py {{ args }}

spec-policy-test:
    @python3 wom7web/project/scripts/tests/test_spec_policy_check.py

consumer-skill-gate *args:
    @python3 wom7web/project/scripts/consumer_skill_gate.py {{ args }}

consumer-skill-gate-test:
    @python3 wom7web/project/scripts/tests/test_consumer_skill_gate.py

lessons-check *args:
    @python3 wom7web/project/scripts/lessons_check.py {{ args }}

lessons-check-test:
    @python3 wom7web/project/scripts/tests/test_lessons_check.py

eli5-governance-test:
    @python3 -m unittest wom7web/project/scripts/tests/test_t270_eli5_governance.py

opencode-health *args:
    @python3 scripts/opencode_config.py --check {{ args }}

opencode-sync *args:
    @python3 scripts/opencode_config.py --generate {{ args }}

opencode-config-test:
    @python3 -m unittest wom7web/project/scripts/tests/test_opencode_config.py

# ── Stripe Reconciliation, Cloud Compute & 4-Identity Selector (T290 / T305 / T306) ──
stripe-reconcile *args:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 wom7api/scripts/stripe_reconcile.py {{ args }}

stripe-reconcile-test:
    @python3 -m pytest wom7api/scripts/tests/test_stripe_reconcile.py -q

cloud-compute-check *args:
    @python3 scripts/cloud_compute_check.py {{ args }}

cloud-compute-check-test:
    @python3 -m pytest scripts/tests/test_cloud_compute_check.py -q

gh-identity *args:
    @python3 scripts/gh_identity_select.py {{ args }}

gh-identity-test:
    @python3 -m pytest scripts/tests/test_gh_identity_select.py -q

# ── Git Hook Recipes & Commit-Msg T## Gate (T129 / T386) ─────────────────────
[no-cd]
[positional-arguments]
commit-msg-check *args:
    @python3 "{{justfile_directory()}}/scripts/conventional_commit.py" "$@"

t129-t386-hooks-test:
    @python3 wom7web/project/scripts/tests/test_t129_t386_hooks.py

# ── Toolchain Governance, Deploy Drift, Suppression Ratchet, Remote CI, AI Memory & Stale-Path Probe (T164 / T259 / T384 / T387 / T234 / T509) ──
tools-check-test:
    @python3 scripts/tests/test_tools_check.py

deploy-drift *args:
    @python3 wom7web/project/scripts/deploy_drift_check.py {{ args }}

deploy-drift-test:
    @python3 wom7web/project/scripts/tests/test_deploy_drift_check.py

suppression-ratchet *args:
    @python3 wom7web/project/scripts/suppression_ratchet.py {{ args }}

suppression-ratchet-test:
    @python3 wom7web/project/scripts/tests/test_suppression_ratchet.py

ci-workflow-check *args:
    @python3 wom7web/project/scripts/ci_workflow_check.py {{ args }}

ci-workflow-check-test:
    @python3 wom7web/project/scripts/tests/test_ci_workflow_check.py

ai-memory-pin-check *args:
    @python3 wom7web/project/scripts/ai_memory_pin_check.py {{ args }}

ai-memory-pin-test:
    @python3 wom7web/project/scripts/tests/test_ai_memory_pin_check.py

stale-path-check *args:
    @python3 scripts/stale_path_check.py {{ args }}

stale-path-check-test:
    @python3 scripts/tests/test_stale_path_check.py

# ── Biometric Hardware Anchor for @wom/kyc & profile_identity (T475) ─────────
kyc-bio-probe *args:
    @python3 wom7api/scripts/kyc_bio_probe.py {{ args }}

kyc-bio-probe-test:
    @python3 -m pytest wom7api/scripts/tests/test_kyc_bio_probe.py -q

# ── Cloudflare Binding Inventory & Rust->WASM Worker Toolchain (T271 / T273) ──
cf-bindings-inventory *args:
    @python3 scripts/cf_bindings_inventory.py {{ args }}

cf-bindings-inventory-test:
    @python3 -m pytest scripts/tests/test_cf_bindings_inventory.py -q

wasm-worker-check *args:
    @python3 scripts/wasm_worker_check.py --check {{ args }}

wasm-worker-check-test:
    @python3 -m pytest scripts/tests/test_wasm_worker_check.py -q

wasm-build:
    @just --justfile wom7func/justfile wasm-build

wasm-test:
    @just --justfile wom7func/justfile wasm-test

wasm-lint:
    @just --justfile wom7func/justfile wasm-lint

wasm-fmt:
    @just --justfile wom7func/justfile wasm-fmt

wasm-fmt-check:
    @just --justfile wom7func/justfile wasm-fmt-check







