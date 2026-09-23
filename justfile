# ── w0m estate root forwarder ────────────────────────────────────────────────
# Root justfile for the workspace (@wom). Delegates queue queries, SDLC gates,
# state surface management, and skills orchestration to the canonical repos.

set dotenv-load := false

# Deployment Version & Parameters (T131 / T421)
project_ref := "pqbbjgeapylcengbuvee"
# Infisical project (workspace) id, the ONE source for every `infisical run` below (T429). It is an
# identifier, not a credential, and equals wom7api/.infisical.json `workspaceId`. Explicit, because
# these recipes run from @wom, which has no .infisical.json link (the T421 elevation broke that silently).
infisical_project_id := "87a1718d-17c6-4c5e-b0c1-f8bb2fd9d13c"
deploy_version := `date +%Y.%m.%d-%s`
deploy_at := `date -u +%Y-%m-%dT%H:%M:%SZ`
deploy_commit := `git rev-parse --short HEAD`

default:
    @just --justfile wom7web/justfile default

# ── Queue & Triage (T146 / T232 / T412) ─────────────────────────────────────
# Hot list, SDLC rank, dynamic epic/ticket-set plan projections, and triage tools
tasks *args:
    @python3 scripts/tasks_query.py {{ args }}

tasks-render *args:
    @python3 scripts/tasks_render.py {{ args }}

agent-concurrency-test:
    @python3 wom7web/project/scripts/tests/test_agent_concurrency.py

ticket-audit *args:
    @python3 scripts/ticket_audit.py {{ args }}

ticket-audit-test:
    @python3 wom7web/project/scripts/tests/test_ticket_audit.py

sync-tickets *args:
    @python3 scripts/sync_github.py {{ args }}

sync-tickets-test:
    @python3 wom7web/project/scripts/tests/test_ticket_sync.py

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
search *args:
    @python3 scripts/estate_search.py {{ args }}

search-test:
    @python3 -m pytest wom7web/project/scripts/tests/test_estate_search.py -q

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

# Forwarding target for running any arbitrary wom7web recipe from workspace root
do recipe *args:
    @just --justfile wom7web/justfile {{ recipe }} {{ args }}

# ── Knowledge & Graph ────────────────────────────────────────────────────────
ask *args:
    @just --justfile wom7web/justfile ask {{ args }}

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

# ── SDLC Lifecycle Gates ─────────────────────────────────────────────────────
sdlc-start *args:
    @just --justfile wom7web/justfile sdlc-start {{ args }}

sdlc-spec *args:
    @just --justfile wom7web/justfile sdlc-spec {{ args }}

sdlc-build *args:
    @just --justfile wom7web/justfile sdlc-build {{ args }}

sdlc-review *args:
    @just --justfile wom7web/justfile sdlc-review {{ args }}

sdlc-security *args:
    @just --justfile wom7web/justfile sdlc-security {{ args }}

sdlc-verify *args:
    @just --justfile wom7web/justfile sdlc-verify {{ args }}

sdlc-deploy *args:
    @just --justfile wom7web/justfile sdlc-deploy {{ args }}

sdlc-archive *args:
    @just --justfile wom7web/justfile sdlc-archive {{ args }}

# ── Deployment Machinery & Elevation (T131 / T161 / T421) ─────────────────────
# One producer for the estate's release-version schema (T131 AC1).
version:
    @echo "{{ deploy_version }}"

# `_confirm <step>` prompts on /dev/tty and ABORTS the recipe on anything but "yes".
#
# 🔑 Why here and not in the harness `ask` permission tier: `ask` DOES NOT GATE. Probed
# 2026-08-02 (T161 AC3) and re-probed 2026-08-10 — both times a rule in `ask` ran with no
# prompt, while the same shape in `deny` was withheld instantly. Shipping `ask` rules would
# be a gate that reads as protection and withholds nothing.
#
# What makes this one real: it reads /dev/tty, which an agent shell here cannot even OPEN
# ("device not configured", measured 2026-08-10) while a human terminal always can. So it is
# not a rule an agent is trusted to respect — it is one an agent cannot answer. No override
# env var exists, deliberately; an escape hatch is the hole.
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

# Red probes for the confirmation gate (T161 AC3, extended by T407). 30 cases: it must withhold
# from an automated caller, refuse a piped "yes", fail CLOSED on an unrecognised step, honour a
# granted root for chained steps, and — since T407 — assert that every surface DESCRIBING this
# gate still matches `confirm-policy.json`, in both directions, with an unreadable surface failing
# as UNMEASURABLE rather than passing on zero bytes.
confirm-test:
    @python3 wom7web/project/scripts/tests/test_confirm_step.py

# Build all web workspaces and stamp release metadata
build:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter web --filter cp --filter join --filter job --filter demo build
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
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter web build
    @just _assert-provisioned web
    @echo "🔍 Building pagefind search index..."
    @cd wom7web/apps/web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm run build:search
    @cd wom7web/apps/web/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}

# Deploy apps/join (join.webomage.com)
deploy-join: (_confirm "deploy-join")
    @echo "Building and deploying apps/join to Cloudflare Workers (Version: {{ deploy_version }})..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter join build
    @just _assert-provisioned join
    @cd wom7web/apps/join/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}

# Deploy apps/job (job.webomage.com)
deploy-job: (_confirm "deploy-job")
    @echo "Building and deploying apps/job to Cloudflare Workers (Version: {{ deploy_version }})..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter job build
    @just _assert-provisioned job
    @cd wom7web/apps/job/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}

# Deploy apps/demo (demo.webomage.com — T79 demo showcase) to Cloudflare Workers
deploy-demo: (_confirm "deploy-demo")
    @echo "Building and deploying apps/demo to Cloudflare Workers (Version: {{ deploy_version }})..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter demo build
    @cd wom7web/apps/demo/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}

# Deploy apps/cp (cp.w0m.xyz)
deploy-cp: (_confirm "deploy-cp")
    @echo "Building and deploying apps/cp to Cloudflare Workers (Version: {{ deploy_version }})..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter cp build
    @just _assert-provisioned cp
    @cd wom7web/apps/cp/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}

# Deploy wom7func to Cloudflare
deploy-workers:
    @echo "Deploying wom7func to Cloudflare Workflows (Version: {{ deploy_version }})..."
    @cd wom7func && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm exec wrangler deploy --var DEPLOY_VERSION:{{ deploy_version }} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}

# Deploy all functions in parallel using Supabase CLI
deploy-functions:
    @echo "Deploying all functions to project {{ project_ref }} in parallel (Version: {{ deploy_version }})..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'supabase secrets set DEPLOY_VERSION="{{ deploy_version }}" DEPLOY_AT="{{ deploy_at }}" DEPLOY_COMMIT="{{ deploy_commit }}" --project-ref {{ project_ref }} > /dev/null 2>&1'
    @cd wom7api && infisical run --projectId={{ infisical_project_id }} --env=beta -- supabase functions deploy --use-api -j 5 --project-ref {{ project_ref }}

# Deploy API capability layer
deploy-api: (_confirm "deploy-api") check-auth check-warp supabase-redeploy-all check-supabase

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

goldens *args:
    @just --justfile wom7api/justfile goldens {{ args }}

smoke-live *args:
    @just --justfile wom7api/justfile smoke-live {{ args }}

_assert-clean-tree:
    @dirty="$(cd wom7web && git status --porcelain -- apps/web/src/config apps/web/.generated 2>/dev/null)"; \
        if [ -n "$dirty" ]; then echo "❌ Deploy dirtied tracked files:"; echo "$dirty"; exit 1; fi; \
        echo "✅ Deploy left no tracked snapshot/version files dirty."

_log-deploy:
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py release "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)"

changelog:
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/gen_changelog.py

changelog-drift *args:
    @python3 wom7web/project/scripts/changelog_drift.py {{ args }}

changelog-drift-test:
    @python3 wom7web/project/scripts/tests/test_changelog_drift.py

deploy:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "${W0M_DEPLOY_LOGGED:-}" ]; then
      exec just _deploy-chain
    fi
    exec env W0M_DEPLOY_LOGGED=1 python3 wom7web/project/scripts/deploy_logged.py _deploy-chain

_deploy-chain: (_confirm "deploy") check-infisical check-guardrails test goldens deploy-api deploy-web deploy-cp deploy-join deploy-job deploy-demo smoke-live _assert-clean-tree _log-deploy

deploy-all:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -n "${W0M_DEPLOY_LOGGED:-}" ]; then
      exec just _deploy-all-chain
    fi
    exec env W0M_DEPLOY_LOGGED=1 python3 wom7web/project/scripts/deploy_logged.py _deploy-all-chain

_deploy-all-chain: (_confirm "deploy-all") check-warp check-infisical db-migrate deploy _post-deploy-knowledge

_post-deploy-knowledge:
    -@just knowledge-light

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

state-doctor-test:
    @python3 wom7web/project/scripts/tests/test_state_doctor.py

# ── Lessons Register (T232 / T414) ───────────────────────────────────────────
lessons *args:
    @python3 scripts/lessons_query.py {{ args }}

lessons-test:
    @python3 wom7web/project/scripts/tests/test_lessons_query.py

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

tools-weekly *args:
    @python3 scripts/tools_check.py --outdated --cache && python3 scripts/tools_upgrade.py --apply {{ args }}

toolchain-chain-test:
    @python3 wom7web/project/scripts/tests/test_toolchain_chain.py

mcp-declared-test:
    @python3 wom7web/project/scripts/tests/test_mcp_declared.py

mcp-health *args:
    @python3 scripts/mcp_health.py {{ args }}

# ── Estate Test Suites & Hook Runners (T160 / T375 / T419) ───────────────────
test:
    @python3 scripts/run_suites.py --tier offline

test-all:
    @python3 scripts/run_suites.py --tier all

typecheck *args:
    @just --justfile wom7web/justfile typecheck {{ args }}

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



