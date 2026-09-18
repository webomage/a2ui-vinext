# ── w0m estate root forwarder ────────────────────────────────────────────────
# Root justfile for the workspace (@wom). Delegates queue queries, SDLC gates,
# state surface management, and skills orchestration to the canonical repos.

set dotenv-load := false

default:
    @just --justfile wom7web/justfile default

# ── Queue & Triage (T146 / T232) ─────────────────────────────────────────────
# Hot list, SDLC rank, dynamic epic/ticket-set plan projections, and triage tools
tasks *args:
    @just --justfile wom7web/justfile tasks {{ args }}

# ── GitHub PR Tool (T345 / T369 / T377) ─────────────────────────────────────────
prs *args:
    @just --justfile wom7web/justfile prs {{ args }}

prs-open *args:
    @just --justfile wom7web/justfile prs-open {{ args }}

forks *args:
    @just --justfile wom7web/justfile forks {{ args }}

forks-check:
    @just --justfile wom7web/justfile forks-check

forks-fetch *args:
    @just --justfile wom7web/justfile forks-fetch {{ args }}

forks-info repo *args:
    @just --justfile wom7web/justfile forks-info {{ repo }} {{ args }}

forks-update *args:
    @just --justfile wom7web/justfile forks-update {{ args }}

forks-sync *args:
    @just --justfile wom7web/justfile forks-sync {{ args }}

prs-test:
    @just --justfile wom7web/justfile prs-test

default-test:
    @just --justfile wom7web/justfile default-test


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

# ── State Surface ────────────────────────────────────────────────────────────
state-check *args:
    @just --justfile wom7web/justfile state-check {{ args }}

state-save *args:
    @just --justfile wom7web/justfile state-save {{ args }}

state-rotate *args:
    @just --justfile wom7web/justfile state-rotate {{ args }}

lessons *args:
    @just --justfile wom7web/justfile lessons {{ args }}

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
    @just --justfile wom7web/justfile tasks-render-test

# ── oMLX Service Lifecycle (T374) ────────────────────────────────────────────
omlx-status:
    @just --justfile wom7web/justfile omlx-status

omlx-start:
    @just --justfile wom7web/justfile omlx-start

omlx-stop:
    @just --justfile wom7web/justfile omlx-stop

omlx-restart:
    @just --justfile wom7web/justfile omlx-restart

