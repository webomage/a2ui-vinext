# ── w0m estate root forwarder ────────────────────────────────────────────────
# Root justfile for the workspace (@wom). Delegates queue queries, SDLC gates,
# state surface management, and skills orchestration to the canonical repos.

set dotenv-load := false

# Canonical @wom estate root exported to all child recipes and scripts (T427 / AgDR-0025).
export W0M_ROOT := env_var_or_default('W0M_ROOT', justfile_directory())

# Deployment Version & Parameters (T131 / T421)
project_ref := "pqbbjgeapylcengbuvee"
# Infisical project (workspace) id, the ONE source for every `infisical run` below (T429). It is an
# identifier, not a credential, and equals w0m-api/.infisical.json `workspaceId`. Explicit, because
# these recipes run from @wom, which has no .infisical.json link (the T421 elevation broke that silently).
infisical_project_id := "87a1718d-17c6-4c5e-b0c1-f8bb2fd9d13c"
# ONE version per release, across nested `just` processes. A backtick runs once per `just` PROCESS, and
# the chain spawns several (`supabase-redeploy-all` → w0m-api → back here for `deploy-functions`), so each
# re-ran `date`: run 7 (2026-09-24) stamped the edge functions 11 minutes after the apps, and the transcript
# was named after a version `deploy_log` never recorded. The outermost invocation mints it and EXPORTS it;
# every nested one inherits. Unset = a fresh standalone run, which correctly mints its own.
export W0M_DEPLOY_VERSION := env_var_or_default('W0M_DEPLOY_VERSION', `date +%Y.%m.%d-%s`)
export W0M_DEPLOY_AT := env_var_or_default('W0M_DEPLOY_AT', `date -u +%Y-%m-%dT%H:%M:%SZ`)
deploy_version := W0M_DEPLOY_VERSION
deploy_at := W0M_DEPLOY_AT
deploy_commit := `git rev-parse --short HEAD`

export GH_CONFIG_DIR := env_var_or_default("GH_CONFIG_DIR", env_var("HOME") + "/.config/gh-w0m")
OMLX_URL := env_var_or_default("OMLX_URL", "http://127.0.0.1:8888/v1")
OMLX_MODEL := env_var_or_default("OMLX_MODEL", "gemma-4-e4b-it-4bit")
quartz_port := "8099"
quartz_tag := "v5.0.0"

import 'just/estate.just'
# w0m-api/supabase/config.toml reads `env(W0M_DB_MIGRATIONS)`, which has no default: unset means
# EVERY `supabase` command fails with ProjectConfigParseError (T248). Recipes here that call the CLI
# directly (`deploy-function`, `deploy-functions`) need the same export w0m-api/justfile carries;
# without it the first `just deploy-function` failed (T431).
export W0M_DB_MIGRATIONS := env_var_or_default('W0M_DB_MIGRATIONS', 'true')

default:
    @echo "================================================================================"
    @echo "w0m — Webomage Estate Command Runner"
    @echo "================================================================================"
    @echo ""
    @echo "Primary Workflows:"
    @echo "  just tasks             Ranked task queue & triage (hot list, SDLC rank)"
    @echo "  just prs-open          Fresh status table of open PRs in w0m-pr"
    @echo "  just forks             Status table of all upstream forks in w0m-pr"
    @echo "  just ask \"<symbol>\"    Query codebase knowledge graph (graph before grep)"
    @echo "  just test              Run project test suites"
    @echo "  just dev               Start local development server"
    @echo "  just status-dashboard  Show current estate & roadmap status dashboard"
    @echo "  just preflight         Verify environment, MCP, and estate reachability"
    @echo ""
    @echo "Command Discovery:"
    @echo "  just --list            List all available recipes with docstrings"
    @echo "  just <recipe> --help   Inspect arguments/flags for a specific recipe"
    @echo "  just do <recipe>       Run any w0m-web recipe from workspace root"
    @echo ""

# ── Queue & Triage (T146 / T232 / T412) ─────────────────────────────────────
# Hot list, SDLC rank, dynamic epic/ticket-set plan projections, and triage tools
tasks *args:
    @python3 scripts/tasks_query.py {{ args }}

[positional-arguments]
eli5 *args:
    @python3 scripts/ticket_eli5.py "$@"

eli5-test:
    @python3 scripts/tests/test_ticket_eli5.py

system-one-test:
    @python3 w0m-web/project/scripts/tests/test_system_one.py

hooks-llm-check:
    @python3 w0m-web/project/scripts/hooks_llm_check.py

system-one-bench *args:
    @python3 w0m-web/project/scripts/system_one_bench.py {{ args }}

tasks-render *args:
    @python3 scripts/tasks_render.py {{ args }}

agent-concurrency-test:
    @python3 scripts/tests/test_agent_concurrency.py

project-archetypes-test:
    @python3 w0m-web/project/scripts/tests/test_project_archetypes.py

profile-resolve *args:
    @python3 w0m-web/project/scripts/profile_resolver.py resolve {{ args }}

profile-env *args:
    @python3 w0m-web/project/scripts/profile_resolver.py env {{ args }}

profile-run *args:
    @python3 w0m-web/project/scripts/profile_resolver.py run {{ args }}

profile-infisical slug *args:
    @python3 w0m-web/project/scripts/profile_resolver.py infisical {{ slug }} {{ args }}

profile-jam slug *args:
    @python3 w0m-web/project/scripts/profile_resolver.py jam {{ slug }} {{ args }}

profile-inject-vm slug vm *args:
    @python3 w0m-web/project/scripts/profile_resolver.py inject-vm {{ slug }} {{ vm }} {{ args }}

profile-resolver-test:
    @python3 w0m-web/project/scripts/tests/test_profile_resolver.py

ticket-audit *args:
    @python3 scripts/ticket_audit.py {{ args }}

reality-verify *args:
    @python3 scripts/ticket_audit.py --completed --specs --strict --offline {{ args }}

ticket-audit-test:
    @python3 scripts/tests/test_ticket_audit.py

dod-check-test:
    @python3 scripts/tests/test_dod_check.py

sync-tickets *args:
    @python3 scripts/sync_github.py {{ args }}

sync-tickets-test:
    @python3 scripts/tests/test_ticket_sync.py

[positional-arguments]
diagram *args:
    @python3 scripts/diagram_view.py "$@"

diagram-test:
    @python3 scripts/tests/test_diagram_view.py

# ── Structural AST Guardrails (T589) ─────────────────────────────────────────
ast-grep-check *args:
    @python3 scripts/ast_grep_check.py {{ args }}

ast-grep-test:
    @python3 scripts/tests/test_ast_grep_check.py

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
    @python3 scripts/tests/test_tasks_bounds.py

tasks-rotate *args:
    @python3 scripts/tasks_rotate.py {{ args }}

tasks-rotate-test:
    @python3 scripts/tests/test_tasks_rotate.py

ticket-schema-check *args:
    @python3 scripts/ticket_schema_check.py {{ args }}

ticket-schema-check-test:
    @python3 scripts/tests/test_ticket_schema_check.py

ticket-deps *args:
    @python3 scripts/ticket_deps.py {{ args }}

ticket-deps-test:
    @python3 scripts/ticket_deps.py --test

blocker-detection-test:
    @python3 scripts/tests/test_blocker_detection.py

ticket-graph *args:
    @python3 scripts/ticket_graph.py {{ args }}

ac-recipe-check *args:
    @python3 scripts/ac_recipe_check.py {{ args }}

ac-recipe-check-test:
    @python3 scripts/tests/test_ac_recipe_check.py

ac-trace-check *args:
    @python3 scripts/ac_trace_check.py {{ args }}

# ── Spec & SDLC Quality Gates (T23 / T33 / T72 / T110 / T419) ─────────────────
spec-drift *args:
    @python3 scripts/spec_drift_gate.py {{ args }}

spec-drift-ownership-test:
    @python3 scripts/tests/test_spec_drift_ownership.py

spec-reality *args:
    @python3 scripts/spec_reality_check.py {{ args }}

spec-standard *args:
    @python3 scripts/spec_standard_check.py {{ args }}

spec-standard-test:
    @python3 scripts/tests/test_spec_standard.py

spec-systems *args:
    @python3 scripts/spec_systems_gate.py {{ args }}

spec-systems-test:
    @python3 scripts/spec_systems_gate.py --selftest

sdlc-trace *args:
    @python3 scripts/sdlc_trace.py {{ args }}

sdlc-trace-test:
    @python3 scripts/tests/test_sdlc_trace.py

# ── Design System & Shipping Code Reconciliation (T420) ──────────────────────
ds-check *args:
    @python3 scripts/ds_check.py {{ args }}

ds-check-test:
    @python3 scripts/tests/test_ds_check.py

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
    @python3 scripts/w0m_prs.py table --preset w0m-pr {{ args }}

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

tap-sync *args:
    @python3 scripts/w0m_prs.py tap-sync {{ args }}

prs-digest *args:
    @python3 scripts/w0m_prs.py digest {{ args }}

prs-rising *args:
    @python3 scripts/w0m_prs.py rising {{ args }}

prs-features *args:
    @python3 scripts/w0m_prs.py features {{ args }}

prs-vote *args:
    @python3 scripts/w0m_prs.py vote {{ args }}

prs-discover *args:
    @python3 scripts/w0m_prs.py discover {{ args }}

prs-check-delta *args:
    @python3 scripts/w0m_prs.py check-delta {{ args }}

prs-orca-sync *args:
    @python3 scripts/w0m_prs.py orca-sync {{ args }}

prs-proposals *args:
    @python3 scripts/w0m_prs.py proposals {{ args }}

prs-submit-dry *args:
    @python3 scripts/w0m_prs.py submit --dry-run {{ args }}

pr-dry *args:
    @python3 scripts/w0m_prs.py submit --dry-run {{ args }}

prs-submit *args:
    @python3 scripts/w0m_prs.py submit --no-dry-run {{ args }}

pr-open *args:
    @python3 scripts/w0m_prs.py submit --no-dry-run {{ args }}

pr-auto *args:
    @python3 scripts/w0m_prs.py auto {{ args }}

pr-compliance *args:
    @python3 scripts/w0m_prs.py compliance {{ args }}

prs-reconcile *args:
    @python3 scripts/w0m_prs.py reconcile {{ args }}

prs-obsolete *args:
    @python3 scripts/w0m_prs.py obsolete {{ args }}

prs-obsolete-close *args:
    @python3 scripts/w0m_prs.py obsolete --close {{ args }}

prs-launch-reports *args:
    @python3 scripts/w0m_prs.py launch-reports {{ args }}

prs-test:
    @python3 scripts/tests/test_w0m_prs.py

# ── Unified Estate Resource Governance (T343) ──────────────────────────────
resources *args:
    @python3 scripts/resource_monitor.py {{ args }}

resources-prune *args:
    @python3 scripts/resource_monitor.py --prune {{ args }}

rename-audit *args:
    @python3 scripts/rename_audit.py {{ args }}

rename-audit-test:
    @python3 scripts/tests/test_rename_audit.py

decommission-check *args:
    @python3 scripts/decommission_check.py {{ args }}

decommission-check-test:
    @python3 scripts/tests/test_decommission_check.py

default-test:
    @cd w0m-web && python3 project/scripts/tests/test_just_default.py

# ── Ticket Duplication Checks (T403 / T414) ──────────────────────────────────
ticket-dups *args:
    @python3 scripts/ticket_duplicate_check.py {{ args }}

ticket-dups-test:
    @python3 scripts/tests/test_ticket_duplicate_check.py

# ── Automated Ticket Recycling (T397 / T414) ─────────────────────────────────
ticket-recycle *args:
    @python3 scripts/ticket_recycle.py {{ args }}

ticket-recycle-test:
    @python3 scripts/tests/test_ticket_recycle.py

# ── Zero-NPX Invariant Audit (T398 / T414) ───────────────────────────────────
npx-audit *args:
    @python3 scripts/npx_audit.py {{ args }}

npx-audit-test:
    @python3 scripts/tests/test_npx_audit.py

# ── Authorization Admin Client Ratchet (T202 / T327) ──────────────────────────
authz-admin-client *args:
    @cd w0m-web && python3 project/scripts/authz_admin_client_triage.py {{args}}

# T453 — live default-deny probe (read-only; run after the owner's deploy) and its offline red probes.
route-policy-live *args:
    @cd w0m-web && python3 project/scripts/live_route_probe.py {{ args }}

route-policy-live-test:
    @cd w0m-web && python3 project/scripts/tests/test_live_route_probe.py

# T453 AC7 — cross-app route-policy check. Forwards to w0m-api/justfile, where the recipe lives.
route-policy-check:
    @cd w0m-web && ASTRO_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1 pnpm exec vitest run packages/lib/src/auth/route-inventory.spec.ts packages/lib/src/auth/api-default-deny.spec.ts

authz-admin-client-test:
    @cd w0m-web && python3 project/scripts/authz_admin_client_triage.py --test

# ── macOS Host Security Posture (T233 / T414) ─────────────────────────────────
host-posture *args:
    @python3 scripts/host_posture.py {{ args }}

host-posture-check:
    @python3 scripts/host_posture.py --enforce

host-posture-test:
    @python3 scripts/tests/test_host_posture.py

# ── Preflight & SDLC Doctor (T414) ───────────────────────────────────────────
preflight *args:
    @python3 scripts/preflight.py {{ args }}

sdlc-doctor *args:
    @python3 scripts/sdlc_doctor.py {{ args }}

# ── SDLC Machinery & Gates (T414) ────────────────────────────────────────────
gate ticket status note="":
    @python3 scripts/gate_advance.py {{ ticket }} --status {{ status }} {{ if note == "" { "" } else { "--note '" + note + "'" } }}

ticket-paths ticket:
    @python3 scripts/check_ticket_paths.py {{ ticket }}

ticket-paths-test:
    @python3 scripts/tests/test_check_ticket_paths.py

# ── Tech Debt Register (T228 / T414) ─────────────────────────────────────────
debt-check *args:
    @python3 scripts/debt_register_check.py {{ args }}

debt-check-test:
    @python3 scripts/tests/test_debt_register_check.py

lexicon-lint-test:
    @python3 w0m-web/project/scripts/tests/test_lexicon_lint.py

schema-check *args:
    @python3 scripts/schema_check.py {{ args }}

schema-check-test:
    @python3 scripts/tests/test_schema_check.py

# Forwarding target for running any arbitrary w0m-web recipe from workspace root
do recipe *args:
    @just {{ recipe }} {{ args }}

# Unified w0m CLI entrypoint (skill, project, agent, tree, session, tasks, status, vm, k8s, cloud, llm, spec, notify) (T567 AC6 / T598 / AgDR-0012)
w0m *args:
    @python3 scripts/w0m_cli.py --project "{{ justfile_directory() }}" {{ args }}

w0m-cli-test:
    @python3 scripts/tests/test_w0m_cli.py

# ── Knowledge & Graph ────────────────────────────────────────────────────────
ask question repo="":
    #!/usr/bin/env bash
    set -uo pipefail
    q="{{ question }}"; only="{{ repo }}"
    [ -z "$q" ] && { echo "usage: just ask \"<question>\" [repo]"; exit 1; }
    if [ "${W0M_SKIP_GRAPH_FRESH:-0}" != "1" ]; then
        python3 scripts/graph_fresh.py --quiet || {
            echo "❌ refusing to answer from a graph that may be stale — see the error above"; exit 1; }
    fi
    if command -v codegraph >/dev/null 2>&1; then
        for r in root w0m-web w0m-api w0m-cf; do
            [ -n "$only" ] && [ "$r" != "$only" ] && continue
            if [ "$r" = "root" ]; then d="."; else d="$r"; fi
            [ -d "$d/.codegraph" ] || continue
            echo "───────── codegraph: $r ─────────"
            (cd "$d" && codegraph explore "$q" 2>/dev/null | head -60) || echo "  (no result)"
        done
    fi
    if [ -z "$only" ] || [ "$only" = "root" ]; then
        echo "───────── root symbols (estate_search --repo root) ─────────"
        python3 scripts/estate_search.py "$q" --repo root --cap 20 || true
    fi
    if [ "$only" = "root" ]; then
        if [ -f "scripts/graphify-out/graph.json" ]; then
            echo "───────── graphify (root) ─────────"
            (graphify query "$q" --graph "scripts/graphify-out/graph.json" --budget 800 2>/dev/null | head -40) || true
        fi
    elif [ -n "$only" ]; then
        if [ -f "$only/graphify-out/graph.json" ]; then
            echo "───────── graphify ($only) ─────────"
            (graphify query "$q" --graph "$only/graphify-out/graph.json" --budget 800 2>/dev/null | head -40) || true
        fi
    elif [ -f "$HOME/.graphify/global-graph.json" ]; then
        echo "───────── graphify (united 7-repo graph) ─────────"
        (graphify query "$q" --graph "$HOME/.graphify/global-graph.json" --budget 800 2>/dev/null | head -40) || true
    elif [ -f "w0m-web/graphify-out/graph.json" ]; then
        echo "───────── graphify (semantic/community view, w0m-web) ─────────"
        (graphify query "$q" --graph "w0m-web/graphify-out/graph.json" --budget 800 2>/dev/null | head -40) || true
    fi

graph-global *args:
    @python3 scripts/graph_global.py {{ args }}

graph-health *args:
    @python3 scripts/graph_health.py {{ args }}

crg-serve repo="w0m-web":
    #!/usr/bin/env bash
    set -euo pipefail
    REPO_DIR="{{ repo }}"
    DATA_DIR="$HOME/.cache/code-review-graph/{{ repo }}"
    if [ ! -d "$REPO_DIR" ]; then
        echo "❌ Repo directory $REPO_DIR does not exist."
        exit 1
    fi
    echo "🌐 Starting Code-Review-Graph live visualizer for {{ repo }} on http://localhost:8765 ..."
    (xdg-open "http://localhost:8765" 2>/dev/null || open "http://localhost:8765" 2>/dev/null || true)
    code-review-graph visualize --repo "$REPO_DIR" --data-dir "$DATA_DIR" --serve

crg-open repo="w0m-web":
    #!/usr/bin/env bash
    set -euo pipefail
    REPO_DIR="{{ repo }}"
    DATA_DIR="$HOME/.cache/code-review-graph/{{ repo }}"
    if [ ! -d "$REPO_DIR" ]; then
        echo "❌ Repo directory $REPO_DIR does not exist."
        exit 1
    fi
    code-review-graph visualize --repo "$REPO_DIR" --data-dir "$DATA_DIR" --format html
    (xdg-open "$DATA_DIR/graph.html" 2>/dev/null || open "$DATA_DIR/graph.html" 2>/dev/null || true)

crg-extract repo="w0m-web":
    #!/usr/bin/env bash
    set -euo pipefail
    REPO_DIR="{{ repo }}"
    DATA_DIR="$HOME/.cache/code-review-graph/{{ repo }}"
    echo "🔍 Extracting code-review-graph for {{ repo }} into $DATA_DIR ..."
    code-review-graph extract --repo "$REPO_DIR" --data-dir "$DATA_DIR"

graph-tree repo="w0m-web":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "{{ repo }}" = "global" ]; then
        graphify tree --graph "$HOME/.graphify/global-graph.json" --output "$HOME/.graphify/GLOBAL_TREE.html" --label "w0m-global"
        (xdg-open "$HOME/.graphify/GLOBAL_TREE.html" 2>/dev/null || open "$HOME/.graphify/GLOBAL_TREE.html" 2>/dev/null || true)
    else
        REPO_DIR="{{ repo }}"
        GRAPH_PATH="$REPO_DIR/graphify-out/graph.json"
        OUT_PATH="$REPO_DIR/graphify-out/GRAPH_TREE.html"
        graphify tree --graph "$GRAPH_PATH" --output "$OUT_PATH" --label "{{ repo }}"
        (xdg-open "$OUT_PATH" 2>/dev/null || open "$OUT_PATH" 2>/dev/null || true)
    fi

graph-callflow repo="w0m-web":
    #!/usr/bin/env bash
    set -euo pipefail
    REPO_DIR="{{ repo }}"
    graphify export callflow-html "$REPO_DIR"
    OUT_PATH="$REPO_DIR/graphify-out/{{ repo }}-callflow.html"
    (xdg-open "$OUT_PATH" 2>/dev/null || open "$OUT_PATH" 2>/dev/null || true)

graph-query query repo="w0m-web":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "{{ repo }}" = "global" ]; then
        graphify query "{{ query }}" --graph "$HOME/.graphify/global-graph.json"
    else
        graphify query "{{ query }}" --graph "{{ repo }}/graphify-out/graph.json"
    fi

graph-explain concept repo="w0m-web":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "{{ repo }}" = "global" ]; then
        graphify explain "{{ concept }}" --graph "$HOME/.graphify/global-graph.json"
    else
        graphify explain "{{ concept }}" --graph "{{ repo }}/graphify-out/graph.json"
    fi

graph-path a b repo="w0m-web":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "{{ repo }}" = "global" ]; then
        graphify path "{{ a }}" "{{ b }}" --graph "$HOME/.graphify/global-graph.json"
    else
        graphify path "{{ a }}" "{{ b }}" --graph "{{ repo }}/graphify-out/graph.json"
    fi

graph-affected x depth="2" repo="w0m-web":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "{{ repo }}" = "global" ]; then
        graphify affected "{{ x }}" --depth {{ depth }} --graph "$HOME/.graphify/global-graph.json"
    else
        graphify affected "{{ x }}" --depth {{ depth }} --graph "{{ repo }}/graphify-out/graph.json"
    fi

graph-benchmark repo="w0m-web":
    #!/usr/bin/env bash
    set -euo pipefail
    if [ "{{ repo }}" = "global" ]; then
        graphify benchmark "$HOME/.graphify/global-graph.json"
    else
        graphify benchmark "{{ repo }}/graphify-out/graph.json"
    fi

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
# `sync-w0m-api-secrets`, `crawler-deploy`) re-prompt ANYWAY.
# 🔴 `db-migrate` is NOT among them — it rides the `deploy-all` consent. That was an owner
# decision on 2026-08-16, recorded in `confirm-policy.json -> _notes.one_yes_is_the_decision`:
# the owner was offered the chance to put it back and declined. Re-adding it reverses a decision
# rather than fixing a bug, and `test_confirm_step.py` fails and says so. This comment claimed the
# opposite for 34 days (T407, [[AgDR-0024]]) — every behavioural probe stayed green throughout,
# because what had rotted was the description, not the gate.
# Policy is DATA: project/confirm-policy.json. Unrecognised step => confirm (fail closed).
_confirm step:
    @python3 scripts/confirm_step.py {{ step }}

# Red probes for the confirmation gate (T161 AC3, extended by T407, T435, T471, and T541). 91 cases: it must
# withhold from an automated caller, refuse a piped "yes", refuse an agent session even with a pty
# and a live consent, refuse when the Touch ID dialog is not confirmed, find every deploy-shaped
# recipe without `_confirm`, fail CLOSED on an unrecognised step, honour a granted root for chained
# steps, and — since T407 — assert that every surface DESCRIBING this
# gate still matches `confirm-policy.json`, in both directions, with an unreadable surface failing
# as UNMEASURABLE rather than passing on zero bytes.
confirm-test:
    @python3 scripts/tests/test_confirm_step.py

# Which confirmation channels does THIS shell expose?
confirm-doctor:
    @python3 scripts/confirm_step.py --doctor

# Enroll or rotate a 6-digit TOTP secret for cross-device confirmation
confirm-enroll-totp:
    @python3 scripts/confirm_step.py --enroll-totp

# Every `pnpm --filter <app> build` below runs from `w0m-web`, never from @wom. @wom's package.json
# has no `packageManager` pin and is not the pnpm workspace, so from here PATH's pnpm (12.x) ran the
# build without the workspace root's node_modules/.bin, and the first root `deploy-web` failed with
# `astro: command not found` (T431, 2026-09-23). Guarded by `just deploy-elevation-test`.
# Build all web workspaces and stamp release metadata
build:
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter web --filter cp --filter me --filter demo build
    @python3 w0m-web/project/scripts/stamp_build.py \
        --version "{{ deploy_version }}" --at "{{ deploy_at }}" --commit "{{ deploy_commit }}"

_assert-provisioned app:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-web/project/scripts/build_provisioning_gate.py --app {{ app }}

# Deploy apps/web (webomage.com)
deploy-web: (_confirm "deploy-web")
    @echo "Building and deploying apps/web to Cloudflare Workers (Version: {{ deploy_version }})..."
    @echo "📸 Updating static snapshots..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- node w0m-web/apps/web/scripts/snapshot-settings.mjs
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- node w0m-web/apps/web/scripts/snapshot-blueprints.mjs
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- node w0m-web/apps/web/scripts/snapshot-knowledge.mjs
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter web build
    @just _assert-provisioned web
    @echo "🔍 Building pagefind search index..."
    @cd w0m-web/apps/web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm run build:search
    @cd w0m-web/apps/web/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 "{{ justfile_directory() }}/scripts/wrangler_deploy.py" -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var APP_VERSION:${W0M_APP_VERSION_WEB:-{{ deploy_version }}} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py web "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Deploy apps/me (me.webomage.com)
deploy-me: (_confirm "deploy-me")
    @echo "Building and deploying apps/me to Cloudflare Workers (Version: {{ deploy_version }})..."
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter me build
    @just _assert-provisioned me
    @cd w0m-web/apps/me/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 "{{ justfile_directory() }}/scripts/wrangler_deploy.py" -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var APP_VERSION:${W0M_APP_VERSION_ME:-{{ deploy_version }}} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- sh -c ' \
      if ! pnpm exec wrangler secret list --name webomage-me --format json 2>/dev/null | grep -q "\"PUBLIC_SUPABASE_URL\""; then \
        echo "🔐 First-deploy bootstrap: provisioning production secrets on webomage-me..." && \
        echo "$PUBLIC_SUPABASE_URL" | pnpm exec wrangler secret put PUBLIC_SUPABASE_URL --name webomage-me && \
        echo "$PUBLIC_SUPABASE_ANON_KEY" | pnpm exec wrangler secret put PUBLIC_SUPABASE_ANON_KEY --name webomage-me && \
        echo "$SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SERVICE_ROLE_KEY --name webomage-me && \
        echo "$SUPABASE_SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SUPABASE_SERVICE_ROLE_KEY --name webomage-me && \
        echo "$WORKERS_WEBHOOK_URL" | pnpm exec wrangler secret put WORKERS_WEBHOOK_URL --name webomage-me && \
        echo "$WORKERS_WEBHOOK_SECRET" | pnpm exec wrangler secret put WORKERS_WEBHOOK_SECRET --name webomage-me; \
      fi'
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py me "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Deploy apps/demo (demo.webomage.com — T79 demo showcase) to Cloudflare Workers
deploy-demo: (_confirm "deploy-demo")
    @echo "Building and deploying apps/demo to Cloudflare Workers (Version: {{ deploy_version }})..."
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter demo build
    @cd w0m-web/apps/demo/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 "{{ justfile_directory() }}/scripts/wrangler_deploy.py" -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var APP_VERSION:${W0M_APP_VERSION_DEMO:-{{ deploy_version }}} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py demo "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Deploy apps/cp (cp.w0m.xyz)
deploy-cp: (_confirm "deploy-cp")
    @echo "Building and deploying apps/cp to Cloudflare Workers (Version: {{ deploy_version }})..."
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter cp build
    @just _assert-provisioned cp
    @cd w0m-web/apps/cp/dist/server && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 "{{ justfile_directory() }}/scripts/wrangler_deploy.py" -- pnpm exec wrangler deploy --config wrangler.json --var DEPLOY_VERSION:{{ deploy_version }} --var APP_VERSION:${W0M_APP_VERSION_CP:-{{ deploy_version }}} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py cp "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Deploy w0m-cf to Cloudflare
deploy-workers: (_confirm "deploy-workers")
    @echo "Deploying w0m-cf to Cloudflare Workflows (Version: {{ deploy_version }})..."
    @cd w0m-cf && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 "{{ justfile_directory() }}/scripts/wrangler_deploy.py" -- pnpm exec wrangler deploy --var DEPLOY_VERSION:{{ deploy_version }} --var DEPLOY_AT:{{ deploy_at }} --var DEPLOY_COMMIT:{{ deploy_commit }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py w0m-cf "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Deploy all functions in parallel using Supabase CLI (bulk deploy, then verify each function updated and retry stale ones via scripts/deploy_functions.py).
deploy-functions: (_confirm "deploy-functions")
    @echo "Deploying all functions to project {{ project_ref }} in parallel (Version: {{ deploy_version }})..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'supabase secrets set DEPLOY_VERSION="{{ deploy_version }}" DEPLOY_AT="{{ deploy_at }}" DEPLOY_COMMIT="{{ deploy_commit }}" --project-ref {{ project_ref }} > /dev/null 2>&1'
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/deploy_functions.py --project-ref {{ project_ref }}
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py api "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

# Offline probes for the deploy-functions staleness/retry logic.
deploy-functions-test:
    @python3 scripts/deploy_functions.py --self-test

# Deploy API capability layer
# T431: deploy NAMED edge function(s): the per-function top-level helper, replacing 25 copies in
# w0m-api/justfile. Validates every name against w0m-api/supabase/functions/ before deploying anything;
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
    @python3 scripts/deploy_cert.py guardrails

check-warp:
    @echo "Checking Cloudflare WARP and deploy-host reachability..."
    @if ! command -v warp-cli >/dev/null 2>&1; then \
    	echo "❌ warp-cli is not installed on PATH — required by 'just check-warp' for deploy-all / deploy-api."; \
    	echo "   Install Cloudflare WARP (`brew install --cask cloudflare-warp`) and retry."; \
    	exit 1; \
    fi
    @status=$(warp-cli --accept-tos status 2>/dev/null | head -1); \
    if ! echo "$status" | grep -q "Connected"; then \
    	echo "  WARP not connected ($status) — connecting..."; \
    	warp-cli --accept-tos connect >/dev/null 2>&1 || true; \
    	for i in $(seq 1 45); do \
    		sleep 1; \
    		status=$(warp-cli --accept-tos status 2>/dev/null | head -1); \
    		if echo "$status" | grep -q "Connected"; then break; fi; \
    	done; \
    fi; \
    if ! echo "$status" | grep -q "Connected"; then \
    	echo "❌ WARP never reached Connected (last: $status)."; \
    	echo "   A half-connected WARP intercepts traffic without routing it — deploying through it"; \
    	echo "   fails at the first network call. Wait for it, or 'warp-cli disconnect' and retry."; \
    	exit 1; \
    fi; \
    echo "  ✅ WARP $status"
    @for host in app.infisical.com {{ project_ref }}.supabase.co; do \
    	code=$(curl -s -o /dev/null -w "%{http_code}" --max-time 12 "https://$host"); rc=$?; \
    	if [ "$rc" -ne 0 ] || [ "$code" = "000" ] || [ -z "$code" ]; then \
    		echo "❌ $host unreachable (curl timed out). Deploy would fail at the first call."; \
    		echo "   Usually a half-up WARP or a dropped link. Check 'warp-cli status', then retry."; \
    		exit 1; \
    	fi; \
    	echo "  ✅ $host reachable (HTTP $code)"; \
    done
    @python3 scripts/check_db_host.py --host db.{{ project_ref }}.supabase.co

check-auth:
    @echo "Verifying Supabase project access for {{ project_ref }}..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'supabase functions list --project-ref {{ project_ref }} -o json > /dev/null || (echo "❌ Error: Project {{ project_ref }} not accessible." && exit 1)'
    @echo "✅ Authorized for project {{ project_ref }}"

check-supabase:
    @echo "Supabase functions for project {{ project_ref }}"
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- supabase functions list --project-ref {{ project_ref }} || true

supabase-redeploy-all: (_confirm "supabase-redeploy-all") sync-secrets ensure-cv-bucket deploy-functions

db-migrate: (_confirm "db-migrate") db-drift-check
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 ../w0m-web/project/scripts/db_migrate.py

# T551 AC4 — allocate the next free 14-digit migration version from origin/beta + local migrations and create w0m-api/supabase/migrations/<version>_<name>.sql.
migration-new name:
    @python3 w0m-web/project/scripts/db_drift_check.py --new "{{ name }}"

# T529 — clients & client_users retirement verification and offline tests
clients-retirement-verify *args:
    @cd w0m-web && python3 project/scripts/clients_retirement_verify.py {{args}}

clients-retirement-verify-test:
    @cd w0m-web && python3 -m pytest -q -p no:cacheprovider project/scripts/tests/test_clients_retirement_verify.py

goldens:
    #!/usr/bin/env bash
    set -euo pipefail
    cd w0m-web
    # ALWAYS kill whatever is on :4321 first, then boot our own known-good server. Reusing a
    # server left over from an interactive `redev` session (T222 original design) seemed cheaper,
    # but a leftover server can be hung — mid-recompile, HMR-wedged — and `curl -sf` against it
    # fails just like a real absence. This recipe then tries to boot a second instance, Astro's own
    # single-instance lock correctly refuses it, the 60s wait against the still-hung original never
    # gets a healthy response, and the EXIT trap (which must kill by PORT — see below) takes down
    # that original server as a side effect (2026-09-06: killed the owner's own `just redev`).
    # Killing it up front makes that outcome the deliberate, visible first line instead of an
    # accidental side effect discovered 60s later.
    lsof -ti tcp:4321 -sTCP:LISTEN 2>/dev/null | xargs -r kill 2>/dev/null || true
    echo "🎨 Visual goldens — booting a dev server..."
    ASTRO_DEV_BACKGROUND=1 infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter web dev > /tmp/w0m-web-goldens-dev.log 2>&1 &
    DEV_PID=$!
    # Kill it on ANY exit path, including the gauge failure this gate exists to produce.
    # ⚠️ Kill by PORT, not by the PID we spawned. `infisical run -- pnpm dev` puts astro two
    # levels down, so neither `kill $DEV_PID` nor `pkill -P $DEV_PID` reaches it — both were
    # tried and both leaked, leaving a dev server holding :4321 (one orphan was still listening
    # 2h43m later, reparented to launchd).
    trap 'lsof -ti tcp:4321 -sTCP:LISTEN 2>/dev/null | xargs -r kill 2>/dev/null || true; kill $DEV_PID 2>/dev/null || true' EXIT
    for i in $(seq 1 60); do
      if curl -sf -o /dev/null http://localhost:4321/; then echo "✅ server ready after ${i}s"; break; fi
      if [ "$i" -eq 60 ]; then echo "❌ dev server did not start in 60s"; tail -20 /tmp/w0m-web-goldens-dev.log; exit 1; fi
      sleep 1
    done
    # ⚠️ WARM UP UNTIL STABLE — a 200 is not readiness.
    #
    # A cold Astro dev server answers, then RE-OPTIMIZES dependencies and reloads, which aborts
    # any navigation in flight. Measured on the owner's deploy 2026-08-16: the first two golden
    # rows died with `net::ERR_ABORTED at http://localhost:4321/` and the remaining five passed —
    # a gate failing for a reason that has nothing to do with the page, which is the "cries wolf"
    # outcome this whole ticket exists to avoid. Two throwaway curls were not enough, because
    # each of them can itself be the request that triggers the reload.
    #
    # So: require THREE consecutive successful loads spaced 2s apart. A restart in between resets
    # the streak, so the loop only exits once the server has stopped reloading.
    echo "🔥 warming the server until it stops reloading (a 200 is not readiness)..."
    streak=0
    for i in $(seq 1 45); do
      if curl -sf -o /dev/null --max-time 10 http://localhost:4321/; then
        streak=$((streak + 1))
      else
        streak=0
      fi
      if [ "$streak" -ge 3 ]; then echo "✅ stable after ${i} probe(s)"; break; fi
      if [ "$i" -eq 45 ]; then echo "❌ server never stabilised"; exit 1; fi
      sleep 2
    done
    env -u npm_config_verify_deps_before_run -u npm_config_enable_pre_post_scripts E2E_BASE_URL=http://localhost:4321 gauge run specs/web/goldens.spec:40

# T227 (AC2, AC3, AC5, AC6) — On-demand built-artifact server & golden gate (`wrangler dev --local` with
# sanitized `wrangler.local-gate.json` and ephemeral `--persist-to`, never `--remote` against live bindings).
# Kept on-demand rather than in blocking `_deploy-gates` per T224 AC4 and `justfile` host memory constraints.
serve-built-web *args:
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 project/scripts/serve_built_artifact.py --app web {{ args }}

goldens-built port="4329":
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 project/scripts/serve_built_artifact.py --app web --port {{ port }} --check-assets --exec "gauge run specs/web/goldens.spec:40"

# T487 AC2/AC3 (AgDR-0053) — Verify every golden baseline referenced across specs exists, and regenerate with a mandatory diff summary.
goldens-check *args:
    @python3 scripts/regen_goldens.py --check {{ args }}

goldens-regen spec="":
    @python3 scripts/regen_goldens.py --regen {{ spec }}

goldens-check-test:
    @python3 scripts/tests/test_regen_goldens.py


smoke-live url="https://webomage.com":
    @echo "🔎 Live smoke against {{ url }} (non-blocking — reports, does not gate)..."
    -@cd w0m-web && env -u npm_config_verify_deps_before_run -u npm_config_enable_pre_post_scripts E2E_BASE_URL={{ url }} gauge run specs/web/live-smoke.spec
    -@python3 scripts/live_verify_helper.py crawler-smoke

_assert-clean-tree:
    @[ -x w0m-api/node_modules/.bin/tsx ] || pnpm --dir w0m-api install --frozen-lockfile --prefer-offline
    @pnpm --dir w0m-api exec tsx dagger/pipeline.ts assert-clean-tree

_log-deploy:
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/log_deploy.py release "{{ deploy_version }}" "{{ deploy_commit }}" "$(git config user.email || echo unknown)" --outcome "${W0M_DEPLOY_OUTCOME:-success}" --trigger "${W0M_DEPLOY_TRIGGER:-planned}" --incident-ref "${W0M_DEPLOY_INCIDENT_REF:-}"

changelog:
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/gen_changelog.py

changelog-drift *args:
    @python3 scripts/changelog_drift.py {{ args }}

changelog-drift-test:
    @python3 scripts/tests/test_changelog_drift.py

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

# CP feature index (see w0m-api/justfile).
cp-feature-index *args:
    @cd w0m-web && python3 project/scripts/cp_feature_index.py {{ args }}

cp-feature-index-test:
    @cd w0m-web && python3 project/scripts/tests/test_cp_feature_index.py

cp-feature-index-check:
    @cd w0m-web && python3 project/scripts/cp_feature_index.py --check

# T244 — secret flow gate (see w0m-api/justfile).
secret-flow-check *args:
    @python3 scripts/secret_flow_check.py {{ args }}

secret-flow-check-test:
    @python3 scripts/secret_flow_check.py --test

secret-flow-check-enforce:
    @python3 scripts/secret_flow_check.py --enforce

# T335 — validated setter for `.w0m/sdlc.json -> current_plan` (see w0m-api/justfile).
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
    @[ -x w0m-api/node_modules/.bin/tsx ] || pnpm --dir w0m-api install --frozen-lockfile --prefer-offline
    @pnpm --dir w0m-api exec tsx dagger/pipeline.ts entrypoint --mode deploy

# T473 — FORCE: deploy the local working tree as it is (uncommitted edits of anyone included). Not the default.
deploy-local:
    @python3 scripts/release.py local-warning
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
# Pre-push runs the same set (w0m-web/.husky/pre-push), so a red ratchet is normally found where the change is made, not at deploy time.
_deploy-preflight:
    @python3 scripts/deploy_cert.py preflight
    @just state-check

# Note: `goldens` is excluded from `_deploy-gates` because booting the local Astro dev server + Playwright browser matrix inside a deploy run halts memory-constrained hosts. Run `just goldens` standalone when needed.
_deploy-gates: check-infisical check-guardrails test

_deploy-ship:
    @just _deploy-apps
    @just smoke-live
    @just _assert-clean-tree
    @just _log-deploy

# T473 D2 & T64 AC1/AC3: deploy each app via the TypeScript Dagger pipeline module (`w0m-api/dagger/pipeline.ts`).
# W0M_RELEASE_APPS (set by a release deploy) lists the apps whose fingerprint changed since the last deployed release;
# the others are skipped and keep serving their previous version. Unset (a local deploy) = every app.
_deploy-apps:
    @[ -x w0m-api/node_modules/.bin/tsx ] || pnpm --dir w0m-api install --frozen-lockfile --prefer-offline
    @pnpm --dir w0m-api exec tsx dagger/pipeline.ts deploy-apps

deploy-all:
    @[ -x w0m-api/node_modules/.bin/tsx ] || pnpm --dir w0m-api install --frozen-lockfile --prefer-offline
    @pnpm --dir w0m-api exec tsx dagger/pipeline.ts entrypoint --mode deploy-all

# T64 AC1 & AC3 — Dagger TypeScript pipeline plan preview & unit/typecheck suite (`w0m-api/dagger/`).
dagger-plan:
    @[ -x w0m-api/node_modules/.bin/tsx ] || pnpm --dir w0m-api install --frozen-lockfile --prefer-offline
    @pnpm --dir w0m-api exec tsx dagger/pipeline.ts plan

dagger-test:
    @cd w0m-api && pnpm exec tsc --noEmit -p dagger/tsconfig.json && pnpm exec vitest run dagger/__tests__/pipeline.test.ts

# T473 — FORCE: deploy-all from the local working tree. Not the default.
deploy-all-local:
    @python3 scripts/release.py local-warning
    @env W0M_DEPLOY_LOCAL=1 just deploy-all

# T473 — release helpers. `release-cut` + `release-worktree` + `release-deploy` is what `just deploy` does in one go;
# use them to inspect a release before deploying it, or to retry a failed one without cutting a new version.
release-cut *args:
    @python3 scripts/release.py cut {{ args }}

release-worktree version:
    @python3 scripts/release.py worktree {{ version }}

release-verify version:
    @python3 scripts/release.py verify {{ version }}

release-deploy version mode="deploy":
    @python3 scripts/release.py deploy {{ version }} {{ mode }}

release-publish version:
    @python3 scripts/release.py publish {{ version }}

release-list:
    @python3 scripts/release.py list

release-prune keep="":
    @python3 scripts/release.py prune {{ keep }}

release-test:
    @python3 scripts/release.py --test

# T554 — land (or re-land) a release's record on origin/beta without touching this checkout: a parked one first, else built from the release manifest. Run it when a deploy
# printed "release record is NOT on origin/beta".
release-record *args:
    @python3 scripts/release.py record {{ args }}

# T554 — offline proof (27 checks, throwaway git repositories: a lost race is retried, a record never strands on the live checkout, records are read from origin/beta).
release-record-test:
    @python3 scripts/tests/test_release_record.py

# T531 AC6 — agent trees: one COMPLETE, private copy of the estate per agent (the umbrella with every member repo nested inside), on local branch agent/<name> cut from origin/beta.
# No pull requests and no remote branch: commit in your tree, then `agent-tree-land` fetches, rebases onto origin/beta, checks ticket ids (a collision or a gap is refused) and pushes
# HEAD:beta, members first and the umbrella last. Never forces. See w0m-web/project/scripts/agent_tree.py.
agent-tree name:
    @python3 w0m-web/project/scripts/agent_tree.py new {{ name }}

agent-tree-list:
    @python3 w0m-web/project/scripts/agent_tree.py list

agent-tree-land *args:
    @python3 w0m-web/project/scripts/agent_tree.py land {{ args }}

agent-tree-remove name *args:
    @python3 w0m-web/project/scripts/agent_tree.py remove {{ name }} {{ args }}

agent-tree-prune:
    @python3 w0m-web/project/scripts/agent_tree.py prune

agent-tree-test:
    @python3 -m pytest w0m-web/project/scripts/tests/test_agent_tree.py -q -p no:cacheprovider

t531-layers-test:
    @python3 -m pytest w0m-web/project/scripts/tests/test_t531_layers.py -q -p no:cacheprovider

# T640 — single-command in-session SDLC wrap-up (`session_wrapup`), gates, landing, live sync, and transcript archive.
[no-cd]
[positional-arguments]
session-complete *args:
    @python3 "{{justfile_directory()}}/scripts/session_complete.py" "$@"

session-complete-test:
    @python3 -m pytest scripts/tests/test_session_complete.py -q -p no:cacheprovider

[no-cd]
[positional-arguments]
commit *args:
    @python3 "{{justfile_directory()}}/scripts/commit_by_path.py" "$@"

[positional-arguments]
ticket-new *args:
    @python3 "{{justfile_directory()}}/scripts/ticket_new.py" "$@"

# T564 — virtual agent identity (`agent_id`) and cross-worktree ticket claim/tagging system.
agent-id *args:
    @python3 w0m-web/project/scripts/agent_identity.py whoami {{ args }}

agent-id-set agent_id *args:
    @python3 w0m-web/project/scripts/agent_identity.py set {{ agent_id }} {{ args }}

ticket-claim ticket *args:
    @python3 w0m-web/project/scripts/agent_identity.py claim {{ ticket }} {{ args }}

ticket-release ticket *args:
    @python3 w0m-web/project/scripts/agent_identity.py release {{ ticket }} {{ args }}

ticket-tag ticket *args:
    @python3 w0m-web/project/scripts/agent_identity.py tag {{ ticket }} {{ args }}

agent-claims *args:
    @python3 w0m-web/project/scripts/agent_identity.py claims {{ args }}

agent-identity-test:
    @python3 -m pytest w0m-web/project/scripts/tests/test_agent_identity.py -q -p no:cacheprovider

# T481 — Persistent isolated STABLE and CONFIRMED worktrees: full local regression runs in stable, stable-promote advances confirmed
stable-sync *args:
    @python3 scripts/release.py stable-sync {{ args }}

stable-promote *args:
    @python3 scripts/release.py stable-promote {{ args }}

e2e-stable *args:
    @python3 scripts/release.py e2e-stable {{ args }}

# T532 & T480 — Run E2E tests against local sandbox environment (fail-fast precondition gates + parallel execution)
e2e-local *specs:
    #!/usr/bin/env bash
    set -uo pipefail
    # T480 AC5b — refuse to start when a concurrent astro check / vite build is holding .vite caches.
    if pgrep -f "astro check|vite build" >/dev/null 2>&1; then
      echo "  ❌ concurrent astro check or vite build detected — wait for it to finish so .vite/deps_ssr is not corrupted (T480 AC5b)."
      exit 2
    fi
    if ! curl -s -o /dev/null "http://127.0.0.1:54321/rest/v1/"; then
      echo "  ❌ local Supabase is not up. Run: just db-local-up && just db-local-env && just db-local-seed"
      exit 2
    fi
    gen=w0m-web/env/local/generated.properties
    [ -f "$gen" ] || { echo "  ❌ no $gen — run \`just db-local-env\`"; exit 2; }
    team=w0m-web/env/local/test-team.properties
    [ -f "$team" ] || { echo "  ❌ no $team — run \`just test-team-local\`"; exit 2; }
    # T478 — without the functions, every AI/API spec fails on a refused connection and reads as a product
    # defect. Refuse to run instead; `just edge-local` in another terminal.
    if [ "$(curl -s -o /dev/null -w '%{http_code}' -X OPTIONS http://127.0.0.1:54321/functions/v1/w0m-consultant)" = "000" ] \
       || ! lsof -nP -iTCP:8791 -sTCP:LISTEN >/dev/null 2>&1; then
      echo "  ❌ edge functions are not served locally — run \`just edge-local\` in another terminal first."; exit 2
    fi
    # T478 — sign in as the LOCAL test team, never beta's ADMIN_EMAIL (a Google-only login that 17 specs
    # could not use). Only *_EMAIL / *_PASSWORD / *_TOTP_SECRET keys; token_urlsafe and base32 carry no shell metacharacters.
    creds=$(grep -E '^[A-Z_]+_(EMAIL|PASSWORD|TOTP_SECRET) = ' "$team" | sed 's/ = /=/')
    anon=$(grep '^PUBLIC_SUPABASE_ANON_KEY' "$gen" | cut -d= -f2- | tr -d ' ')
    svc=$(grep '^SERVICE_ROLE_KEY' "$gen" | cut -d= -f2- | tr -d ' ')
    db=$(grep '^DATABASE_URL' "$gen" | cut -d= -f2- | tr -d ' ')
    # T480 AC5 — prove the test team can actually sign in BEFORE launching 148 specs.
    admin_email=$(grep '^ADMIN_EMAIL = ' "$team" | cut -d= -f2- | tr -d ' ')
    admin_pass=$(grep '^ADMIN_PASSWORD = ' "$team" | cut -d= -f2- | tr -d ' ')
    auth_rc=$(curl -s -o /dev/null -w '%{http_code}' \
      -H "apikey: $anon" -H "Content-Type: application/json" \
      -d "{\"email\":\"$admin_email\",\"password\":\"$admin_pass\"}" \
      "http://127.0.0.1:54321/auth/v1/token?grant_type=password")
    if [ "$auth_rc" != "200" ]; then
      echo "  ❌ test-team sign-in failed against 127.0.0.1:54321 (HTTP $auth_rc) — run \`just test-team-local\` first (T480 AC5)."
      exit 2
    fi
    # T478 — measured 2026-09-28, beta injects FIVE values that point at live: PUBLIC_SUPABASE_URL,
    # SUPABASE_URL, PUBLIC_CP_URL, UPWORK_CALLBACK_URL, WORKERS_WEBHOOK_URL — and DATABASE_URL is the live
    # superuser. The first two were overridden; the rest reached live (ats.steps.ts connects with
    # DATABASE_URL; the dev server dispatches to the live worker). All are pinned to loopback below, in BOTH
    # env blocks. The worker URL points at a port nothing listens on: a dispatch fails loudly, not live.
    local_urls="DATABASE_URL=$db PUBLIC_CP_URL=http://localhost:4325 PUBLIC_WEB_URL=http://localhost:4321 PUBLIC_ME_URL=http://localhost:4323 WORKERS_WEBHOOK_URL=http://127.0.0.1:1 UPWORK_CALLBACK_URL=http://127.0.0.1:1"
    # T478 — every app port must be FREE, or the run is not local. Measured 2026-09-28: `pnpm run dev`
    # SKIPS an app whose port is taken, so dev servers left running against the LIVE
    # project answered this suite's requests. A server we did not start is refused, not reused.
    for p in 4321 4323 4324 4325; do
      if lsof -nP -iTCP:$p -sTCP:LISTEN >/dev/null 2>&1; then
        echo "  ❌ port $p is already in use (pid $(lsof -nP -tiTCP:$p -sTCP:LISTEN | head -1)) — this run would not be local."
        echo "     Stop it first (\`just stop-dev\`), then rerun."; exit 2
      fi
    done
    for p in 9229 9230 9231 9232 9233 9234; do
      lsof -nP -tiTCP:$p -sTCP:LISTEN 2>/dev/null | xargs kill -9 2>/dev/null || true
    done
    # T478 — the corpus once wrote 12 rows into LIVE contact_messages from a local run: ~25 steps hardcoded live
    # URLs. tests/support/liveGuard.ts now refuses live hosts in-process; prove it works before any spec runs.
    ( cd w0m-web && PUBLIC_SUPABASE_URL=http://127.0.0.1:54321 node tests/support/liveGuard.probe.mts ) \
      || { echo "  ❌ the live guard is not holding — refusing to run a local suite that could reach live."; exit 2; }
    expected_ver="${W0M_DEPLOY_VERSION:-local-$(git -C w0m-web rev-parse --short HEAD 2>/dev/null || echo dev)}"
    echo "  ▶ starting Astro against LOCAL Supabase (expected version: $expected_ver)…"
    cd w0m-web
    infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- env \
      W0M_E2E_LOCAL=1 \
      E2E_LOCAL=true \
      SUBDOMAIN_DEV=1 \
      DEPLOY_VERSION="$expected_ver" \
      W0M_DEPLOY_VERSION="$expected_ver" \
      PUBLIC_SUPABASE_URL=http://127.0.0.1:54321 \
      PUBLIC_SUPABASE_ANON_KEY="$anon" \
      SUPABASE_SERVICE_ROLE_KEY="$svc" \
      SERVICE_ROLE_KEY="$svc" \
      $local_urls \
      pnpm run dev > /tmp/w0m-e2e-local-dev.log 2>&1 &
    DEV=$!
    # Kill by PORT, not only the parent pid: `pnpm -r --parallel` children outlive $DEV, and the first T478 run
    # left web listening on :4321 after the recipe exited.
    trap 'kill $DEV 2>/dev/null || true; for p in 4321 4323 4324 4325 9229 9230 9231 9232 9233 9234; do lsof -nP -tiTCP:$p -sTCP:LISTEN 2>/dev/null | xargs kill 2>/dev/null || true; done' EXIT
    if ! python3 ../scripts/host_service_probe.py --expect-version "$expected_ver" --wait 60; then
      echo "  ❌ dev servers failed service+version verification:"; tail -20 /tmp/w0m-e2e-local-dev.log; exit 1
    fi
    echo "  ✅ all 4 Astro dev servers + Supabase GoTrue verified (service identity + version $expected_ver)"
    parallel_flags=""
    if [ "${W0M_E2E_PARALLEL:-1}" != "0" ]; then
      parallel_flags="--parallel -n ${W0M_E2E_WORKERS:-4}"
    fi
    # 🔴 gauge needs ADMIN_EMAIL / ADMIN_PASSWORD (tests/helpers/auth.ts) or 99 scenarios fail on
    # "ADMIN_EMAIL and ADMIN_PASSWORD must be set" — 36% of the first full run, and none of it a
    # product defect. But injecting the estate's secrets wholesale is DANGEROUS: the teardown in
    # tests/support/hooks.ts runs pattern-matched DELETEs against PUBLIC_SUPABASE_URL /
    # SERVICE_ROLE_KEY, so beta's values would point that purge at PRODUCTION.
    # ⇒ take the two credentials, then OVERRIDE every Supabase pointer back to loopback. The
    # override comes AFTER the injection deliberately: last writer wins, so a new Supabase-shaped
    # secret appearing in beta cannot silently redirect the purge.
    infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- env \
      W0M_E2E_LOCAL=1 \
      E2E_LOCAL=true \
      PUBLIC_SUPABASE_URL=http://127.0.0.1:54321 \
      SUPABASE_URL=http://127.0.0.1:54321 \
      PUBLIC_SUPABASE_ANON_KEY="$anon" \
      SUPABASE_SERVICE_ROLE_KEY="$svc" \
      SERVICE_ROLE_KEY="$svc" \
      $local_urls \
      $creds \
      gauge run --env local $parallel_flags {{ if specs == "" { "specs" } else { specs } }}

# T579 — Multi-role RBAC, throwaway Postgres hat write-path, CP shell context, and Gauge spec verification
roles-verify:
    @just cp-nav-check-test
    @just t553-hat-write-path-test
    @cd w0m-web && pnpm --filter cp exec vitest run --project dom src/components/shell/__tests__/CpShell.test.ts src/lib/context/__tests__/nav.test.ts
    @cd w0m-web && gauge validate specs/personas/class_reach.spec specs/web/multi_role_hats_and_guild.spec specs/web/admin_cp_personas.spec

# T579 — Self-contained 7-persona local browser E2E runner (provisions test-team-local + edge-local + runs persona specs)
e2e-roles-local *specs:
    #!/usr/bin/env bash
    set -euo pipefail
    if ! curl -s -o /dev/null "http://127.0.0.1:54321/rest/v1/"; then
      echo "  ❌ local Supabase is not up on 127.0.0.1:54321. Start Docker and run: just db-local-up && just db-local-seed"
      exit 2
    fi
    [ -f w0m-web/env/local/generated.properties ] || just db-local-env
    just test-team-local
    EDGE_PID=""
    if ! lsof -nP -iTCP:8791 -sTCP:LISTEN >/dev/null 2>&1; then
      echo "  ▶ starting edge-local in background…"
      just edge-local > /tmp/w0m-edge-local.log 2>&1 &
      EDGE_PID=$!
      trap '[ -n "$EDGE_PID" ] && kill "$EDGE_PID" 2>/dev/null || true' EXIT
      for i in $(seq 1 30); do
        lsof -nP -iTCP:8791 -sTCP:LISTEN >/dev/null 2>&1 && break
        sleep 1
      done
    fi
    just e2e-local {{ if specs == "" { "specs/personas/class_reach.spec specs/web/multi_role_hats_and_guild.spec" } else { specs } }}

# T532 — Run live-guard proof test
live-guard-test:
    @cd w0m-web && PUBLIC_SUPABASE_URL=http://127.0.0.1:54321 node tests/support/liveGuard.probe.mts

# T532 — unit tests for the E2E sandbox isolation guard
e2e-sandbox-guard-test:
    @cd w0m-web && python3 project/scripts/tests/test_e2e_sandbox_guard.py

# T480 — Multi-engine local and remote OCI/VM sandbox status (Colima, Apple container, Docker, Podman, Tart, DevPod, remote SSH)
oci-status *args:
    @python3 scripts/oci_sandbox.py status {{ args }}

# T480 — Ensure an OCI/VM sandbox engine is up and print its DOCKER_HOST
oci-up provider="auto":
    @python3 scripts/oci_sandbox.py up --provider={{ provider }}

# T480 — Print the active DOCKER_HOST for the running OCI sandbox engine
oci-env:
    @python3 scripts/oci_sandbox.py env

# T480 — Unit tests for the multi-engine OCI/VM sandbox orchestrator
oci-sandbox-test:
    @python3 -m pytest scripts/tests/test_oci_sandbox.py -q -p no:cacheprovider

# T480 — Verify host/service identity and expected version across local/remote endpoints
host-probe *args:
    @python3 scripts/host_service_probe.py {{ args }}

# T480 — Unit tests for Gauge fail-fast, stage-aware timeouts, watchdog, and parallel execution
t480-gauge-test:
    @python3 -m pytest scripts/tests/test_t480_gauge_fail_fast.py -q -p no:cacheprovider

_deploy-all-chain: _deploy-preflight (_confirm "deploy-all") check-warp _deploy-gates db-migrate tinybird-apply _deploy-ship _post-deploy-knowledge

_post-deploy-knowledge:
    #!/usr/bin/env bash
    set -euo pipefail
    # T473 / T652: A release worktree is a throwaway snapshot, so never index its worktree path; instead resolve
    # the canonical estate checkout from `--git-common-dir` and refresh canonical knowledge + graph union cleanly
    # (never skip forever under W0M_RELEASE_WORKTREE and never swallow failures with `|| true`).
    if [ -n "${W0M_RELEASE_WORKTREE:-}" ]; then
        CANONICAL_ROOT="$(cd "$(git rev-parse --path-format=absolute --git-common-dir)/.." && pwd)"
        if [ -d "$CANONICAL_ROOT/w0m-web" ] && command -v graphify >/dev/null 2>&1; then
            python3 "$CANONICAL_ROOT/scripts/graph_global.py" --root "$CANONICAL_ROOT" --auto-rebuild-stale
        fi
        exit 0
    fi
    just knowledge-light
    if command -v graphify >/dev/null 2>&1; then
        python3 scripts/graph_global.py --auto-rebuild-stale
    fi

# Every bare `just <recipe>` in a recipe body must name a recipe that justfile defines — the
# `-`-prefixed call above named one that only w0m-api has, silently, from T421 to T431 run 7.
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
    @python3 scripts/deploy_logged.py {{ args }}

deploy-logged-test:
    @python3 scripts/tests/test_deploy_logged.py

deploy-logs-rotate *args:
    @python3 scripts/deploy_logs_rotate.py {{ args }}

deploy-logs-rotate-test:
    @python3 scripts/tests/test_deploy_logs_rotate.py

deploy-in-flight-test:
    @python3 scripts/tests/test_deploy_in_flight.py

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
    @python3 scripts/tests/test_state_doctor.py

# ── Lessons Register (T232 / T414 / T602) ────────────────────────────────────
lessons *args:
    @python3 scripts/lessons_query.py {{ args }}

lessons-harvest *args:
    @python3 scripts/lessons_query.py --harvest-friction {{ args }}

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
skills-sync mode="":
    @[ -x w0m-skills/node_modules/.bin/tsx ] || pnpm --dir w0m-skills install --frozen-lockfile --prefer-offline
    @cd w0m-skills && pnpm exec tsx skills.ts {{ if mode == "check" { "--check" } else { mode } }}
    @if [ "{{mode}}" != "check" ] && [ "{{mode}}" != "--check" ]; then python3 "{{justfile_directory()}}/w0m-web/project/scripts/catalog_sync.py" --write && python3 "{{justfile_directory()}}/w0m-web/project/scripts/skills_catalog_gen.py" --write; fi

skills-test *args:
    @cd w0m-skills && pnpm run skill-test {{ args }}

skills-update *args:
    @cd w0m-skills && pnpm run skill --project "{{ invocation_directory() }}" update --canonical {{ args }}

skills-diff *args:
    @cd w0m-skills && pnpm run skill --project "{{ invocation_directory() }}" diff {{ args }}

skills-backport *args:
    @cd w0m-skills && pnpm run skill --project "{{ invocation_directory() }}" backport {{ args }}

skills-audit-tools *args:
    @cd w0m-skills && pnpm run skill --project "{{ invocation_directory() }}" audit-tools {{ args }}

skills-chips *args:
    @cd w0m-skills && pnpm run skill --project "{{ invocation_directory() }}" chips {{ args }}

skills-catalog *args:
    @python3 w0m-web/project/scripts/skills_catalog_gen.py --write {{ args }}

skills-catalog-check *args:
    @python3 w0m-web/project/scripts/skills_catalog_gen.py --check {{ args }}

skills-catalog-test:
    @PYTHONPATH=w0m-web python3 -m pytest w0m-web/project/scripts/tests/test_t24_skills_expansion.py -q -p no:cacheprovider

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
        doctor) just vm-doctor ;; \
        install-guest) w0m-pr/tart-guest-agent/packaging/install-darwin.sh {{ name }} ;; \
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
    @python3 scripts/vm_supervisor.py doctor {{ args }}

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
    @w0m-pr/tart-guest-agent/packaging/install-darwin.sh {{ name }}


# ── Core Plan & Queue Tests ──────────────────────────────────────────────────
plan-verdict-test:
    @cd w0m-web && python3 project/scripts/tests/test_plan_verdict.py

tasks-render-test:
    @python3 scripts/tests/test_tasks_render.py

# ── oMLX Service Lifecycle (T374) ────────────────────────────────────────────
omlx-status:
    @python3 scripts/omlx_service.py status

omlx-start:
    @python3 scripts/omlx_service.py start

omlx-stop:
    @python3 scripts/omlx_service.py stop

omlx-restart:
    @python3 scripts/omlx_service.py restart

# ── Headroom Proxy Service Lifecycle (T456) ──────────────────────────────────
headroom-status *args:
    @python3 scripts/headroom_service.py status {{ args }}


headroom-start:
    @python3 scripts/headroom_service.py start

headroom-stop:
    @python3 scripts/headroom_service.py stop

headroom-restart:
    @python3 scripts/headroom_service.py restart

headroom-logs *args:
    @python3 scripts/headroom_service.py logs {{ args }}

headroom-service-test:
    @python3 scripts/tests/test_headroom_service.py

headroom-bootstrap-status *args:
    @python3 scripts/headroom_bootstrap.py {{ args }}



# ── Version Management (T391 / T414) ─────────────────────────────────────────
version-sync *args:
    @python3 scripts/sync_manifest_versions.py {{ args }}

version-check *args:
    @python3 scripts/sync_manifest_versions.py --check {{ args }}

sync-manifest-versions-test:
    @python3 scripts/tests/test_sync_manifest_versions.py

# ── Estate Policies & Standards (T130 / T135 / T192 / T256 / T419) ───────────
emoji-check *args:
    @python3 scripts/emoji_policy_check.py {{ args }}

emoji-check-test:
    @python3 scripts/tests/test_emoji_policy_check.py

emoji-text-dialects-test:
    @python3 w0m-web/project/scripts/tests/test_emoji_text_dialects.py

doc-format-check *args:
    @python3 scripts/doc_format_check.py {{ args }}

doc-format-check-test:
    @python3 scripts/tests/test_doc_format_check.py

hygiene *args:
    @python3 scripts/repo_hygiene.py all {{ args }}

hygiene-check *args:
    @python3 scripts/repo_hygiene.py all {{ args }}

repo-hygiene *args:
    @python3 scripts/repo_hygiene.py all {{ args }}

hygiene-check-test:
    @python3 scripts/tests/test_repo_hygiene.py

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
    @python3 scripts/tests/test_ide_trace.py

discovery *args:
    @python3 scripts/discovery.py {{ args }}

discovery-test:
    @python3 scripts/tests/test_discovery.py

# ── Tool & MCP Governance (T112 / T154 / T247 / T419) ────────────────────────
tools *args:
    @python3 scripts/tools_check.py {{ args }}

tools-check *args:
    @python3 scripts/tools_check.py {{ args }}

tools-upgrade *args:
    @python3 scripts/tools_upgrade.py {{ args }}

# T611 AC3 — bootstrap missing governed `source: "brew"` CLI tools (and optional `post_install` hooks such as `gauge install`).
tools-install *args:
    @python3 scripts/tools_upgrade.py --install-missing {{ args }}

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
    @python3 scripts/tests/test_toolchain_chain.py

mcp-declared-test:
    @python3 scripts/tests/test_mcp_declared.py

mcp-health *args:
    @python3 scripts/mcp_health.py {{ args }}

# ── Estate Test Suites & Hook Runners (T160 / T375 / T419 / T650) ────────────
test:
    @python3 scripts/deploy_cert.py test --level {{ env_var_or_default("W0M_TEST_LEVEL", "medium") }}

# T650 (AgDR-0057) — certify the clean 10-repo estate tree-set (`check-guardrails` + `offline/medium`) into `~/.cache/w0m/deploy-cert/`.
certify:
    @python3 scripts/deploy_cert.py certify

certify-status:
    @python3 scripts/deploy_cert.py status

certify-test:
    @python3 scripts/tests/test_deploy_cert.py

# T652 — bounded staleness ceilings & zero-swallowed-hook guard (`scripts/automation_health.py`).
automation-health *args:
    @python3 scripts/automation_health.py {{ args }}

automation-health-test:
    @python3 scripts/tests/test_automation_health.py

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

typecheck:
    @cd w0m-web && ASTRO_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1 python3 ../scripts/prepush_runner.py run-typecheck

svelte-typecheck-ratchet *args:
    @cd w0m-web && python3 project/scripts/svelte_typecheck_ratchet.py {{ args }}

svelte-typecheck-ratchet-test:
    @cd w0m-web && pytest -q project/scripts/tests/test_svelte_typecheck_ratchet.py

suites-drift *args:
    @python3 scripts/run_suites.py --drift {{ args }}

run-suites-test:
    @python3 scripts/tests/test_run_suites.py

prepush-status *args:
    @python3 scripts/prepush_runner.py status {{ args }}

prepush-reset *args:
    @python3 scripts/prepush_runner.py reset {{ args }}

prepush-run *args:
    @python3 scripts/prepush_runner.py {{ args }}

prepush-test:
    @python3 scripts/tests/test_prepush_runner.py

# ── Local Development Stack (T449) ──────────────────────────────────────────
# Check local /etc/hosts for *.w0m.local development domains
hosts-check:
    @python3 scripts/hosts_check.py

# Stop all local development servers (web, workers, and caddy reverse proxy)
stop-dev:
    - caddy stop 2>/dev/null || true
    - lsof -ti:443 -ti:80 -sTCP:LISTEN | xargs kill -9 2>/dev/null || true
    - lsof -ti:4321 -sTCP:LISTEN | xargs kill -9 2>/dev/null || true
    - lsof -ti:4323 -sTCP:LISTEN | xargs kill -9 2>/dev/null || true
    - lsof -ti:4324 -sTCP:LISTEN | xargs kill -9 2>/dev/null || true
    - lsof -ti:4325 -sTCP:LISTEN | xargs kill -9 2>/dev/null || true
    - lsof -ti:8790 -sTCP:LISTEN | xargs kill -9 2>/dev/null || true
    - lsof -ti:9229 -ti:9230 -ti:9231 -ti:9232 -sTCP:LISTEN | xargs kill -9 2>/dev/null || true
    - pkill -f "astro dev" || true
    - pkill -f "wrangler dev" || true
    - pkill -f "caddy run" || true
    - pkill -f "tsx watch src/index.ts" || true
    @echo "Local development servers stopped."

# Start the full local estate stack with *.w0m.local SSL reverse proxy (T449)
dev-stack: stop-dev
    @sh -c 'if [ ! -f "$HOME/.w0m/certs/w0m.local.pem" ]; then mkdir -p "$HOME/.w0m/certs" && mkcert -cert-file "$HOME/.w0m/certs/w0m.local.pem" -key-file "$HOME/.w0m/certs/w0m.local-key.pem" "*.w0m.local" "w0m.local" "web.localhost" "cp.localhost" "admin.localhost" "me.localhost" "demo.localhost" "func.localhost" "*.localhost" "localhost" "127.0.0.1"; fi'
    @python3 scripts/hosts_check.py || true
    @echo "Starting Caddy SSL reverse proxy on port 443..."
    @caddy start --config Caddyfile.local
    @echo "Starting w0m-cf worker on port 8790..."
    @sh -c 'cd w0m-cf && nohup infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm exec wrangler dev --port 8790 --show-interactive-dev-session=false > /tmp/w0m-cf-dev.log 2>&1 < /dev/null &'
    @echo "Starting 4 Astro apps with subdomain root bases..."
    cd w0m-web && SUBDOMAIN_DEV=1 infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm run dev

# ── TypeSafe System One & Jev Image Processing (T558 / T556 / T434) ─────────
jev-image *args:
    @python3 w0m-web/project/scripts/jev_system_one.py {{ args }}

jev-system-one-test:
    @python3 w0m-web/project/scripts/tests/test_jev_system_one.py

# ── Google Research Harness² ContextTree & SurfaceSpec (T556) ───────────────
context-tree *args:
    @python3 w0m-web/project/scripts/context_tree.py {{ args }}

context-tree-test:
    @python3 w0m-web/project/scripts/tests/test_context_tree.py

harness2-surface-check *args:
    @python3 w0m-web/project/scripts/harness2_surface.py {{ args }}

harness2-surface-test:
    @python3 w0m-web/project/scripts/tests/test_harness2_surface.py

# ── Org Model S7, Secret History Audit & Resume Vault (T458 / T504 / T510) ──
engagements-hats-verify *args:
    @cd w0m-web && python3 project/scripts/engagements_hats_verify.py {{args}}

engagements-hats-verify-test:
    @cd w0m-web && python3 -m pytest -q -p no:cacheprovider project/scripts/tests/test_engagements_hats_verify.py

secret-history-check *args:
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 project/scripts/secret_history_check.py {{args}}

secret-history-check-test:
    @cd w0m-web && python3 project/scripts/secret_history_check.py --test

resume-vault-verify *args:
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 project/scripts/resume_vault_verify.py {{args}}

resume-vault-verify-test:
    @cd w0m-web && python3 project/scripts/resume_vault_verify.py --test

# ── External Project Work Report Ingestion (T357) ────────────────────────────
project-report-ingest *args:
    @python3 w0m-web/project/scripts/report_ingest.py {{ args }}

project-report-ingest-test:
    @python3 w0m-web/project/scripts/tests/test_report_ingest.py -v

# ── Estate Port Governance & Interactive Status Dashboard (T402 / T394) ─────
ports-check *args:
    @python3 w0m-web/project/scripts/ports_check.py {{ args }}

ports-check-test:
    @python3 w0m-web/project/scripts/tests/test_ports_check.py

status-dashboard-test:
    @python3 w0m-web/project/scripts/tests/test_gen_status_dashboard.py

# ── Estate File Hygiene & _in Tray Disposition (T446 / T447) ────────────────
layout-check *args:
    @python3 w0m-web/project/scripts/layout_check.py {{ args }}

layout-check-test:
    @python3 w0m-web/project/scripts/tests/test_layout_check.py

in-triage *args:
    @python3 w0m-web/project/scripts/in_tray.py triage {{ args }}

in-check *args:
    @python3 w0m-web/project/scripts/in_tray.py check {{ args }}

in-sync *args:
    @python3 w0m-web/project/scripts/in_tray.py sync {{ args }}

in-check-test:
    @python3 w0m-web/project/scripts/tests/test_in_tray.py

# ── Universal System Standards & SSOT Adherence (T214) ──────────────────────
standards-check *args:
    @python3 w0m-web/project/scripts/standards_check.py {{ args }}

standards-check-test:
    @python3 w0m-web/project/scripts/tests/test_standards_check.py

# ── Client Project Services, Cost Attribution & Scoped Settings (T272) ──────
client-services-check *args:
    @python3 w0m-web/project/scripts/client_services_check.py {{ args }}

client-services-check-test:
    @python3 w0m-web/project/scripts/tests/test_client_services_check.py

# ── Typed Python Ratchet, Backstage Catalog & DORA/DevEx Cockpit (T448 / T64 / T432) ──
py-typecheck-root *args:
    @mypy --config-file mypy.ini {{ args }}

py-typecheck *args:
    @just py-typecheck-root {{ args }}
    @just py-typecheck-web {{ args }}
    @just py-typecheck-api {{ args }}

py-typing-check *args:
    @python3 w0m-web/project/scripts/py_typing_check.py {{ args }}

py-typing-check-test:
    @python3 w0m-web/project/scripts/py_typing_check_test.py

catalog-sync *args:
    @python3 w0m-web/project/scripts/catalog_sync.py --write {{ args }}

catalog-check:
    @python3 w0m-web/project/scripts/catalog_sync.py --check

catalog-check-test:
    @python3 w0m-web/project/scripts/catalog_sync_test.py

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
    @python3 scripts/tests/test_branch_hygiene.py

# ── Codegraph Codemap Generator & Serena Config Reconciliation (T193 / T172) ─
codemap-gen *args:
    @python3 w0m-web/project/scripts/codemap_gen.py --write {{ args }}

codemap-check *args:
    @python3 w0m-web/project/scripts/codemap_gen.py --check {{ args }}

codemap-check-test:
    @python3 w0m-web/project/scripts/tests/test_codemap_gen.py

serena-config-check *args:
    @python3 w0m-web/project/scripts/serena_config_check.py {{ args }}

serena-config-check-test:
    @python3 w0m-web/project/scripts/tests/test_serena_config_check.py

# ── Delivery Record, Spec Policy, Consumer Gate, Lessons & OpenCode (T245 / T185 / T177 / T178 / T270 / T152) ──
ac-trace-test:
    @python3 scripts/tests/test_ac_trace_check.py

spec-policy-check *args:
    @python3 w0m-web/project/scripts/spec_policy_check.py {{ args }}

spec-policy-test:
    @python3 w0m-web/project/scripts/tests/test_spec_policy_check.py

consumer-skill-gate *args:
    @python3 w0m-web/project/scripts/consumer_skill_gate.py {{ args }}

consumer-skill-gate-test:
    @cd w0m-web && uv run pytest -q project/scripts/tests/test_consumer_skill_gate.py

lessons-check *args:
    @python3 w0m-web/project/scripts/lessons_check.py {{ args }}

lessons-check-test:
    @python3 w0m-web/project/scripts/tests/test_lessons_check.py

supabase-surface-drift *args:
    @python3 w0m-web/project/scripts/supabase_surface_drift_check.py {{ args }}

supabase-surface-drift-test:
    @python3 w0m-web/project/scripts/tests/test_supabase_surface_drift_check.py

eli5-governance-test:
    @python3 -m unittest w0m-web/project/scripts/tests/test_t270_eli5_governance.py

opencode-health *args:
    @python3 scripts/opencode_config.py --check {{ args }}

opencode-sync *args:
    @python3 scripts/opencode_config.py --generate {{ args }}

opencode-config-test:
    @python3 scripts/tests/test_opencode_config.py

# ── Stripe Reconciliation, Cloud Compute & 4-Identity Selector (T290 / T305 / T306) ──
stripe-reconcile *args:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/stripe_reconcile.py {{ args }}

stripe-reconcile-test:
    @python3 -m pytest w0m-api/scripts/tests/test_stripe_reconcile.py -q

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
    @python3 scripts/tests/test_t129_t386_hooks.py

# ── Toolchain Governance, Deploy Drift, Suppression Ratchet, Remote CI, AI Memory & Stale-Path Probe (T164 / T259 / T384 / T387 / T234 / T509) ──
tools-check-test:
    @python3 scripts/tests/test_tools_check.py

deploy-drift *args:
    @python3 w0m-web/project/scripts/deploy_drift_check.py {{ args }}

deploy-drift-test:
    @python3 w0m-web/project/scripts/tests/test_deploy_drift_check.py

suppression-ratchet *args:
    @python3 w0m-web/project/scripts/suppression_ratchet.py {{ args }}

suppression-ratchet-test:
    @python3 w0m-web/project/scripts/tests/test_suppression_ratchet.py

ci-workflow-check *args:
    @python3 w0m-web/project/scripts/ci_workflow_check.py {{ args }}

ci-workflow-check-test:
    @python3 w0m-web/project/scripts/tests/test_ci_workflow_check.py

ai-memory-pin-check *args:
    @python3 scripts/ai_memory_pin_check.py {{ args }}

ai-memory-pin-test:
    @python3 scripts/tests/test_ai_memory_pin_check.py

stale-path-check *args:
    @python3 scripts/stale_path_check.py {{ args }}

stale-path-check-test:
    @python3 scripts/tests/test_stale_path_check.py

# ── Biometric Hardware Anchor for @wom/kyc & profile_identity (T475) ─────────
kyc-bio-probe *args:
    @python3 w0m-api/scripts/kyc_bio_probe.py {{ args }}

kyc-bio-probe-test:
    @python3 -m pytest w0m-api/scripts/tests/test_kyc_bio_probe.py -q

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
    @just --justfile w0m-cf/justfile wasm-build

wasm-test:
    @just --justfile w0m-cf/justfile wasm-test

wasm-lint:
    @just --justfile w0m-cf/justfile wasm-lint

wasm-fmt:
    @just --justfile w0m-cf/justfile wasm-fmt

wasm-fmt-check:
    @just --justfile w0m-cf/justfile wasm-fmt-check

# ── Script Consolidation & Regular CLI Tools (T516 / T517 / T518) ─────────────
zeroclaw *args:
    @python3 scripts/zeroclaw_manage.py {{ args }}

zeroclaw-manage-test:
    @python3 scripts/tests/test_zeroclaw_manage.py

ai-eval *args:
    @deno run --no-check --allow-env --allow-net --allow-read w0m-api/scripts/ai-eval.ts {{ args }}

hygiene-docs-sync *args:
    @python3 scripts/write_hygiene_docs.py {{ args }}

hygiene-docs *args:
    @python3 scripts/write_hygiene_docs.py {{ args }}

status-truth *args:
    @python3 scripts/status_truth.py {{ args }}

resume-assist-eval *args:
    @deno run --no-check --allow-env --allow-net --allow-read w0m-api/scripts/resume-assist-eval.ts {{ args }}

zc-compression-measure *args:
    @python3 scripts/zc_compression_measure.py {{ args }}

compression-measure *args:
    @python3 scripts/zc_compression_measure.py {{ args }}

ds-inventory *args:
    @python3 w0m-web/project/scripts/ds_inventory.py {{ args }}

infisical-set-prod *args:
    @python3 scripts/infisical_set_prod.py {{ args }}

secrets-push *args:
    @python3 scripts/infisical_set_prod.py {{ args }}

keys-verify *args:
    @python3 scripts/get_keys.py {{ args }}

upwork-auth-check *args:
    @deno run --no-check --allow-env --allow-read w0m-api/scripts/get_upwork_auth.ts {{ args }}

graph-callsites *args:
    @python3 scripts/graph_callsites.py {{ args }}

tinybird-schemas-init *args:
    @python3 w0m-api/scripts/init_tinybird_schemas.py {{ args }}

tinybird-init *args:
    @python3 w0m-api/scripts/init_tinybird_schemas.py {{ args }}

tinybird-check:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/init_tinybird_schemas.py --check

tinybird-apply: (_confirm "tinybird-apply")
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/init_tinybird_schemas.py --apply

tinybird-surface-test:
    @python3 scripts/tests/test_tinybird_surface_drift.py

t516-tools-test:
    @python3 scripts/tests/test_t516_tools.py

live-verify *args:
    @python3 scripts/live_verify_helper.py {{ args }}

live-verify-test:
    @python3 scripts/tests/test_live_verify_helper.py

upwork-poller-status *args:
    @python3 scripts/upwork_poller_status.py {{ args }}

upwork-poller-status-test:
    @python3 scripts/tests/test_upwork_poller_status.py

obsidian-mcp-bridge-test:
    @python3 scripts/tests/test_obsidian_mcp.py

news-backfill *args:
    @python3 scripts/backfill_news.py {{ args }}

news-backfill-images *args:
    @python3 scripts/backfill_post_images.py {{ args }}

content-validate *args:
    @python3 scripts/validate_content.py {{ args }}

tracks-validate *args:
    @python3 scripts/validate_tracks.py {{ args }}

tracks-check *args:
    @python3 scripts/validate_tracks.py {{ args }}

content-tools-test:
    @python3 scripts/tests/test_content_tools.py

# ── Per-Engagement Cloudflare R2 Obsidian Vault Sync (T580 / T653) ────────────
vault-push-r2 *args:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 scripts/vault_push_r2.py {{ args }}

vault-push-r2-test:
    @python3 scripts/tests/test_vault_push_r2.py

vault-guard *args:
    @python3 scripts/obsidian_vault_guard.py {{ args }}

vault-guard-test:
    @python3 scripts/tests/test_obsidian_vault_guard.py

# ── Multi-Host Orca Instance & Agent Session Orchestration (T596 / T599) ──────
orca-sessions *args:
    @python3 scripts/orca_sessions.py list {{ args }}

orca-attach *args:
    @python3 scripts/orca_sessions.py attach {{ args }}

orca-hosts *args:
    @python3 scripts/orca_sessions.py hosts {{ args }}

orca-state-save *args:
    @python3 scripts/orca_sessions.py save-state {{ args }}

orca-state-load *args:
    @python3 scripts/orca_sessions.py load-state {{ args }}

orca-archive *args:
    @python3 scripts/orca_sessions.py archive {{ args }}

orca-close-completed *args:
    @python3 scripts/orca_sessions.py close-completed {{ args }}

orca-sessions-test:
    @python3 scripts/tests/test_orca_sessions.py

orca-status:
    @python3 scripts/orca_overlay_update.py --status

orca-release:
    @python3 scripts/orca_overlay_update.py --trigger

orca-apply *args:
    @python3 scripts/orca_overlay_update.py --apply --wait {{ args }}

orca-repair-cli:
    @python3 scripts/orca_overlay_update.py --repair-cli

orca-overlay-test:
    @python3 scripts/tests/test_orca_overlay_update.py

moksha-apply:
    sudo dpkg -i "$HOME/.local/share/moksha-backport/moksha_0.4.2-4+w0m1_amd64.deb" && "$HOME/.local/bin/moksha-apply-native-snap"

# ── Multi-Platform Social & Developer Signal Tracing CLI (T624) ────────────────
social-trace *args:
    @python3 scripts/social_trace.py {{ args }}

social-search platform query *args:
    @python3 scripts/social_trace.py --platform {{ platform }} --query "{{ query }}" {{ args }}

social-trace-test:
    @python3 scripts/tests/test_social_trace.py

# ── User-Facing UI Ticket / AgDR / AC Copy Leak Gate (T667) ────────────────────
ui-ticket-leak-check *args:
    @python3 w0m-web/project/scripts/ui_ticket_leak_check.py {{ args }}

ui-ticket-leak-check-test:
    @python3 w0m-web/project/scripts/tests/test_ui_ticket_leak_check.py











