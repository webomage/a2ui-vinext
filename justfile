# ── w0m estate root forwarder ────────────────────────────────────────────────
# Root justfile for the workspace (@wom). Delegates queue queries, SDLC gates,
# state surface management, and skills orchestration to the canonical repos.

set dotenv-load := false

default:
    @just --justfile wom7web/justfile --list

# ── Queue & Triage (T146 / T232) ─────────────────────────────────────────────
# Hot list, SDLC rank, dynamic epic/ticket-set plan projections, and triage tools
tasks *args:
    @just --justfile wom7web/justfile tasks {{ args }}

# Forwarding target for running any arbitrary wom7web recipe from workspace root
do recipe *args:
    @just --justfile wom7web/justfile {{ recipe }} {{ args }}

# ── Knowledge & Graph ────────────────────────────────────────────────────────
ask *args:
    @just --justfile wom7web/justfile ask {{ args }}

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

# ── Skills Platform (Level 1 & Level 2) ──────────────────────────────────────
skills-sync *args:
    @cd wom7skills && pnpm run skills:sync {{ args }}

skills-test *args:
    @cd wom7skills && pnpm run skill-test {{ args }}

# ── Core Plan & Queue Tests ──────────────────────────────────────────────────
plan-verdict-test:
    @just --justfile wom7web/justfile plan-verdict-test

tasks-render-test:
    @just --justfile wom7web/justfile tasks-render-test
