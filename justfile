# ── w0m estate root forwarder ────────────────────────────────────────────────
# Root justfile for the workspace (@wom). Delegates queue queries, SDLC gates,
# state surface management, and skills orchestration to the canonical repos.

set dotenv-load := false

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

