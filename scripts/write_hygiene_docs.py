#!/usr/bin/env python3
"""T135 §4 — bootstrap the required human-facing files across the estate.

WHAT THIS IS. A one-shot generator for the three files whose *correct* form is
uniform across repos — LICENSE, SECURITY.md, CODE_OF_CONDUCT.md — plus
CONTRIBUTING.md, which is uniform in structure but carries each repo's REAL
gates and commands. It is committed rather than thrown away so that adding a
repo to `hygiene-policy.json` and re-running this is the whole bootstrap, and
so the estate-wide text has one source instead of eight drifting copies.

WHAT THIS IS NOT. It does not write README.md. The owner's decision (2026-07-25)
was that the README bar is REQUIRED SECTIONS carrying real content, and a
generated README is padding by construction — the exact vacuous pass the bar was
chosen to exclude. READMEs are hand-written per repo.

THE REPO LIST IS NOT HARDCODED. It is read from `project/hygiene-policy.json`,
the same file `repo_hygiene.py` gates against. T135 task 5.9's lesson applies
here too: a hardcoded list of repos is how 15 of 19 manifests got missed. If a
repo is in the policy and not on disk, that is a hard failure, not a skip —
silently shrinking scope is how a gate stops meaning anything.

IDEMPOTENT. Re-running overwrites the generated files with identical bytes.
Files not listed here are never touched.

Usage:
    python3 scripts/write_hygiene_docs.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Callable, cast

# ── Constants the owner decided, recorded here so they are greppable ──────────

# Owner decision (3), 2026-07-25: proprietary / UNLICENSED. These repos are not
# being opened. `hygiene-policy.json -> docs.required_files` gates the LICENSE on
# /(?i)all rights reserved/, so that phrase is load-bearing, not decoration.
COPYRIGHT_YEAR = "2026"

# ⚠️ NO LEGAL ENTITY IS ASSERTED HERE, DELIBERATELY.
# The estate contains no registered company: the site footer is an unattributed
# "© {year}. All rights reserved.", no manifest declares an `author`, and T137's
# open owner question explicitly asks whether "register" includes *legally
# registering an entity* — i.e. the answer is not yet known. Writing
# "Webomage LLC" or "Webomage Inc." into eight LICENSE files would be inventing
# a legal fact, and a copyright notice naming a non-existent entity is worse
# than one naming a person. The holder is therefore the natural person who
# authored the commits. ⇒ If an entity is later registered, change it HERE and
# re-run; that is a one-line change across all eight repos.
COPYRIGHT_HOLDER = "Aleksei Tcelishchev"
PROJECT_NAME = "Webomage (w0m)"

# Task 4.6: this must be a REAL reporting channel — a placeholder address is a
# vacuous pass and fails review. This is the owner's verified working address
# (it is the account email and the author address on the estate's commits), so
# it is provably deliverable. `security@webomage.com` is NOT used: nothing in
# this estate demonstrates that it routes anywhere, and an alias that silently
# blackholes a vulnerability report is precisely the vacuous pass task 4.6 warns
# about. Add it here once someone has actually received mail at it.
SECURITY_CONTACT = "aleksei@webomage.com"

BRANCH = "beta"


# ── Per-repo facts. Every value below was MEASURED, not assumed. ──────────────
# `gates` = the hook ids actually present in that repo's .pre-commit-config.yaml
# (read 2026-07-26). `commands` = recipes that actually exist. Where a repo has
# no build interface at all, that is stated rather than papered over.

REPO_FACTS: dict[str, dict] = {
    "w0m-web": {
        "what": "the canonical monorepo — five Astro apps plus the shared packages, "
        "and the home of the SDLC tracking surfaces (`TASKS.md`, `ROADMAP.md`, "
        "`TECH-DEBT.md`, `openspec/`, `project/tickets/`)",
        "gates": [
            "gitleaks",
            "osv-scanner",
            "semgrep",
            "oxlint",
            "prettier-astro",
            "oxfmt",
            "skills-drift",
            "guard-test-admin",
            "mmd-validate",
            "lexicon-lint",
            "status-dashboard",
            "conventional-commit",
        ],
        "commands": [
            ("just dev", "run the local dev server"),
            ("just typecheck", "type-check the workspace (also runs at pre-push)"),
            ("just test", "run the test suite"),
            ("just discovery", "report stacks-registry drift"),
            ("just sdlc-doctor", "check the SDLC tracking surfaces are coherent"),
        ],
        "notes": [
            "`core.hooksPath` is redirected to `.husky/_` here — and **only** here. "
            "`.git/hooks/pre-commit` in this repo is inert; do not read it and "
            "conclude anything about what runs.",
            "The `justfile` is a **symlink** to `w0m-api/justfile`, the canonical one. "
            "Edit it there.",
        ],
    },
    "w0m-api": {
        "what": "the API tier — the Cloudflare worker plus the Supabase edge functions, "
        "migrations and Drizzle schema. It owns the **canonical `justfile`** that "
        "`w0m-web` and `w0m-cf` symlink to",
        "gates": [
            "gitleaks",
            "osv-scanner",
            "semgrep",
            "mmd-validate",
            "oxlint",
            "oxfmt",
            "codegraph-sync",
            "conventional-commit",
            "deno-check",
            "typecheck-worker",
        ],
        "commands": [
            ("just deploy", "deploy — **the whole estate deploys from this repo**"),
            ("just deno-test", "run the edge-function tests"),
            ("just db-migrate", "apply migrations"),
            ("just typecheck-worker", "type-check the worker (Workers types, not Deno)"),
        ],
        "notes": [
            "**Deploy runs from here.** The recipes use bare `supabase/` paths, so "
            "`just deploy` from `@wom` is required — running it from another repo "
            "resolves the wrong tree.",
            "This is a hybrid repo: pnpm owns the worker, Deno owns the edge functions. "
            "Running `deno install` at the root clobbers the pnpm `node_modules`.",
        ],
    },
    "w0m-cf": {
        "what": "the Cloudflare Workflows worker — the durable, long-running half of the "
        "platform, deployed separately from the API worker",
        "gates": [
            "gitleaks",
            "osv-scanner",
            "semgrep",
            "tsc",
            "oxlint",
            "oxfmt",
            "codegraph-sync",
            "conventional-commit",
        ],
        "commands": [
            ("just typecheck", "type-check (also runs at pre-push)"),
            ("just deploy", "deploy via wrangler — outward-facing, confirm first"),
        ],
        "notes": [
            "The `justfile` is a **symlink** to `w0m-api/justfile`. Edit it there.",
            "Worker secrets are write-only: you can set one but never read it back, so "
            "the only way to verify a secret landed is a behavioural check.",
        ],
    },
    "w0m-skills": {
        "what": "the canonical agent-skills library and its TypeScript toolchain (T127). "
        "Skills are edited **here** and synced outward; the copies installed in "
        "other repos are generated",
        "gates": [
            "gitleaks",
            "osv-scanner",
            "semgrep",
            "conventional-commit",
            "skills-typecheck",
            "skill-test",
        ],
        "commands": [
            ("just skills-typecheck", "`tsc --noEmit` over the toolchain"),
            ("just skill-test", "the skill unit tests"),
            ("just skills-sync", "push canonical skills out to the consuming repos"),
            ("just skill check", "gate skills against `.w0m/skills.json` governance"),
        ],
        "notes": [
            "**Never edit an installed skill copy.** Edit the canonical one under "
            "`skills/`, then sync. An edit to a copy is overwritten without warning.",
            "The recipes live in the canonical `w0m-api/justfile` and `cd` back here "
            "themselves, which is why the hooks invoke them from `../w0m-api`.",
            "`ruff` was retired from this repo's hook stack in T135: `git ls-files "
            "'*.py'` returns **0**, so it could never fire. A wrong-stack linter reads "
            "as coverage while checking nothing.",
        ],
    },
    "w0m-ext": {
        "what": "the browser extension — LinkedIn and Upwork integration, AI-assisted. "
        "There are **two** extension surfaces: `extension/` (tracked, gated) and "
        "`extension-ff/` (gitignored, zero tracked files)",
        "gates": [
            "gitleaks",
            "osv-scanner",
            "semgrep",
            "conventional-commit",
            "ext-lint",
        ],
        "commands": [
            ("just lint", "advisory lint — reports the backlog, never fails"),
            ("just lint-gate", "the **gate**: `oxlint -D correctness`"),
            ("just typecheck", "type-check (currently **manual** — see below)"),
            ("just build-extension", "build the unpacked extension"),
        ],
        "notes": [
            "⚠️ **`just lint` and `just lint-gate` are two recipes on purpose. Do not "
            "collapse them.** Bare `oxlint` reports even duplicate object keys and "
            "`debugger` as *warnings* and exits **0** — hooking it would have been a gate "
            "that could never fail. `lint-gate` blocks the `correctness` category while "
            "holding two named backlog rules advisory, so the ratchet can tighten later.",
            "`extension/src/vendor/` is excluded from **lint** — it is third-party code "
            "the committer cannot act on. It is **not** excluded from the licence audit.",
            "`extension/package/` is vendored `@mcp-b/websocket-bridge`, correctly MIT "
            "with its own `LICENSE`. **Never rewrite it to `UNLICENSED`** — that would "
            "relicense someone else's MIT code as proprietary.",
            "`typecheck` is deferred to **manual**: it exits 2 on 5 pre-existing errors, "
            "and AC8 forbids installing a hook that starts red. Two of those five are "
            "dead message handlers, not annotation work — they have their own ticket.",
        ],
    },
    "w0m-sec": {
        "what": "the security / code-audit toolchain — a standalone scanner that audits "
        "*other* repos. **Early-stage**: `src/` and `specs/` are still empty",
        "gates": [
            "gitleaks",
            "osv-scanner",
            "semgrep",
            "conventional-commit",
            "ruff",
        ],
        "commands": [
            ("just setup", "install the toolchain"),
            ("just scan <target>", "scan a target repo"),
            ("just test", "pytest-bdd specs"),
            ("just diagrams", "render the architecture diagrams"),
        ],
        "notes": [
            "This repo is **Python**, and `ruff` is therefore the correct linter here. "
            "T135 retired `ruff` from the TypeScript repo only — do not generalise that "
            "into a blanket ban.",
            "⚠️ **`just test` currently has an empty input set** and so passes "
            "vacuously. That is tracked as a known AC7 trap, not a green signal. Treat a "
            "passing test run here as meaning nothing until `specs/` has content.",
            "It has no `.infisical.json` and no secret surface, which is why it is "
            "exempt in `.w0m/sdlc.json -> toolchain.exempt`. That exemption lapses the "
            "moment it grows one.",
        ],
    },
    "w0m-mlx/w0m-mlx": {
        "what": "`wom7-mlx-rs` — the Rust port of the MLX multimodal serving stack "
        "(Gemma 4 on Apple Silicon), built on `mlx-rs`",
        "gates": [
            "gitleaks",
            "osv-scanner",
            "semgrep",
            "conventional-commit",
            "ruff",
            "cargo-fmt-check",
        ],
        "commands": [
            ("just build", "`cargo build --release --features metal`"),
            ("just test", "`cargo test`"),
            ("just fmt-check", "the **gated** format check — read-only"),
            ("just serve-gpu", "serve the model on the GPU (port 1340)"),
        ],
        "notes": [
            "⚠️ **This repo is the INNER directory.** The outer `w0m-mlx/` is a workspace "
            "of upstream clones and is **not a git repo**. Measuring at the outer level "
            "is a mistake this estate has made repeatedly — it once reported *'this repo "
            "has zero hooks'* when it has six.",
            "⚠️ **The just file here is a hidden `.justfile`**, against the w0m "
            "convention that it is always a plain `justfile`. `ls justfile` therefore "
            "reports *absent* while the recipes work fine via `just`'s upward search. "
            "The rename is a known follow-up.",
            "**`just fmt` writes files; `just fmt-check` does not.** Only the read-only "
            "one is gated — a hook that reformats the tree changes what the committer is "
            "committing.",
            "Compile gates (`cargo check`, `clippy`) are **deferred**, not skipped: they "
            "exit 101 with ~29 errors that all resolve inside the vendored `../mlx-rs` "
            "clone, **zero in w0m source**. Re-measure when that clone lands.",
            "Methodology here is strict spec-driven development, and it differs from the "
            "rest of the estate: the source of truth is `specs/`, and tests must be "
            "written and seen to FAIL before any implementation.",
        ],
    },
}


# ── Templates ────────────────────────────────────────────────────────────────


def license_text(repo: str) -> str:
    return f"""Copyright (c) {COPYRIGHT_YEAR} {COPYRIGHT_HOLDER}

All rights reserved.

This repository ({repo}) is part of {PROJECT_NAME} and is proprietary and
confidential. It is not open-source software and no open-source licence is
granted, offered or implied.

No permission is granted to any person to use, copy, modify, merge, publish,
distribute, sublicense, sell, or create derivative works from this software or
its documentation, in whole or in part, except under a separate written
agreement signed by the copyright holder.

Unauthorised copying, distribution or disclosure of this software, via any
medium, is strictly prohibited.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.

THIRD-PARTY COMPONENTS
This repository may vendor or depend on third-party code that is licensed
separately. Nothing above overrides those licences: vendored trees retain their
own upstream notice files, and those notices govern that code. Where you find a
`LICENSE` file inside a vendored subdirectory, it — not this file — applies to
that subdirectory.
"""


def security_text(repo: str, facts: dict[str, Any]) -> str:
    return f"""# Security policy — `{repo}`

## Reporting a vulnerability

**Email {SECURITY_CONTACT}.** Put `SECURITY` in the subject line.

This is a monitored personal address, not an alias — it is deliberately chosen
over a `security@` alias that nobody has proven receives mail. A reporting
channel that silently blackholes a report is worse than no channel at all.

Please include:

- what the issue is, and which repo and file or endpoint it affects;
- how to reproduce it, ideally minimally;
- what an attacker gets out of it;
- whether you have disclosed it anywhere else.

**Do not open a public issue for a security problem**, and do not include a
live credential in the report — describe it instead.

## What to expect

| | |
|---|---|
| Acknowledgement | within 3 business days |
| Initial assessment | within 10 business days |
| Fix or documented mitigation | tracked as a ticket, severity-ordered |

These repositories are proprietary and are maintained by a very small team, so
timelines are best-effort rather than contractual. You will get a straight
answer either way — including *"this is intended behaviour"* with the reasoning.

## Scope

In scope: `{repo}` — {facts['what']}.

Also in scope: anything that leaks a credential, bypasses authentication or
authorisation, or lets one tenant reach another tenant's data.

Out of scope:

- Findings that require a already-compromised host or an already-stolen
  credential to exploit.
- Automated-scanner output with no demonstrated impact.
- Missing hardening headers on endpoints that serve no authenticated content.
- Denial of service through sheer volume.

## Rules of engagement

- **Do not test against production.** Do not attempt to access, modify or
  destroy data that is not yours.
- **Never authenticate with a credential you found leaked.** Report the leak;
  confirming it by logging in is itself an intrusion. This estate has had a real
  leaked-superuser incident, and the correct response to the next one is a
  report, not a login attempt.
- Do not run automated scanners against live hosts without asking first.

## How this project handles secrets

Secrets reach a process by injection through **Infisical** — `infisical run
--env=<env> --silent -- <cmd>`. There is no `.env` file in this estate, and
adding one is a regression rather than a migration. Commands that *print* secret
values (`infisical export`, `infisical secrets --plain`) are treated as defects,
because a printed value ends up in a log, a buffer or a transcript. If you find
tracked automation doing it, that is a valid report.

Every repository here runs `gitleaks` at pre-commit, and history has been
scanned. If you find a live credential in the tree or in history, report it as a
vulnerability — and please do not test it.
"""


def code_of_conduct_text(repo: str) -> str:
    return f"""# Code of conduct — `{repo}`

## The short version

Be straight with people and assume they are doing the same. Argue about the work
rather than about each other. This is a small proprietary project, not a large
public community, so this document is short on purpose — it states the standard
and who enforces it, and does not pretend to be a governance structure that does
not exist.

## Expected

- **Technical honesty above all.** Say what you measured and how. If you are not
  sure, say you are not sure. A confident wrong answer costs more than an
  admitted gap, and this project has the scars to prove it.
- **Critique the work, not the person.** *"This gate can never fail"* is useful.
  *"You do not know how gates work"* is not.
- **Own mistakes plainly and move on.** Correcting your own record is normal
  practice here, not an embarrassment. Several files in this estate carry their
  own corrections in place, deliberately, so the lesson survives.
- **Respect other people's in-flight work.** Do not reformat, "fix" or
  opportunistically clean up a tree someone else is working in.

## Not accepted

- Harassment, discrimination, or personal attacks — including on the basis of
  gender, gender identity, sexual orientation, disability, physical appearance,
  race, ethnicity, age, religion, or nationality.
- Sexualised language or imagery, and unwelcome sexual attention.
- Publishing anyone's private information without their explicit permission.
- Sustained disruption, or deliberately wasting other people's time.
- Retaliation against anyone who reports a concern in good faith.

## Scope

This applies anywhere work on this project happens: commits, commit messages,
code review, issues, tickets, chat, and any channel where you are recognisably
acting as a contributor.

## Enforcement

Report a concern to **{SECURITY_CONTACT}**. Reports are read by the project
owner and handled privately. Where a report concerns the owner, say so plainly
in the message — it will still be read and answered.

Consequences are proportionate and are the owner's decision: a private word,
a required correction, having a change reverted, or losing access. There is no
appeals committee, because there is no committee — that is stated honestly
rather than implied otherwise.
"""


def contributing_text(repo: str, facts: dict[str, Any]) -> str:
    gates = " · ".join(f"`{g}`" for g in facts["gates"])
    commands = "\n".join(f"| `{c}` | {d} |" for c, d in facts["commands"])
    notes = "\n".join(f"- {n}" for n in facts["notes"])

    return f"""# Contributing — `{repo}`

{facts['what'].capitalize()}.

Everything below is enforced by a hook or a gate, not by convention alone. If a
rule here is not mechanically checkable, that is a gap worth reporting.

## Before you start

Work on **`{BRANCH}`**. ⚠️ More than one agent commits to this branch, so
**`git pull` before you start and before you push** — a stale local branch is
the most common source of avoidable conflict here.

If the work maps to a ticket (`T##` in `w0m-web/TASKS.md`), run it through the
**w0m SDLC gates** rather than editing ad hoc:

```
new → start → spec → build → review → security → verify → deploy → archive
```

Entry point is the `w0m` skill or `w0m-sdlc-start <id>`. Ad-hoc edits to tracked
work are how the queue, the specs and the debt register drift away from the
code. Update the tracking surfaces **in the same commit as the work** — a stale
row misleads whoever picks it up next.

*(Client and non-w0m projects do not use these gates — see
`w0m-skills/GENERIC-SDLC-SET.md`.)*

## Commands

Run work through a `just` recipe rather than a raw `pnpm` / `npx` / `tsc` /
`deno` / `wrangler` call. The recipe is the declared interface; a raw call is
invisible to the registry and to `just discovery`.

| Command | What it does |
|---|---|
{commands}

## Gates that run on your commit

{gates}

**Never use `--no-verify`.** There are no exceptions, and it has been called out
in this project before. If a hook fails, fix the finding — or, if the hook is
wrong, fix the hook and say so in the commit. Bypassing it silently means the
next person inherits both the defect and a gate nobody trusts.

## Commit messages

**Conventional Commits**, referencing the ticket:

```
fix(auth): stop the hat-switch dropping the active role (T39)
```

Types: `feat` `fix` `docs` `style` `refactor` `test` `chore` `perf` `ci` `build`
`revert`. The `commit-msg` hook rejects anything else.

**Do not add `Co-Authored-By` or other attribution trailers.**

## Secrets

Secrets are injected, never read from a file:

```
infisical run --env=beta --silent -- <command>
```

There is **no `.env`** in this estate and adding one is a regression, not a
migration. To check whether a secret exists, presence-check it *through*
`infisical run` — never `infisical secrets --plain` or `infisical export`, both
of which materialise the value into a buffer that ends up somewhere you did not
intend.

## When you add a check

This project has shipped a gate that could not fail more than once, so the bar
is explicit: **a new check must be proven in both directions before it lands.**

1. Show it **fails** on a deliberately broken input — and make the breakage
   violate *the thing the check checks*. A type error will not prove a lint gate.
2. Show it **passes** on the unmodified tree. A check that starts red walls off
   pre-existing debt and trains people to bypass the stack.
3. Check what it did **not** flag. A gate's first output is a hypothesis.
4. Verify it fails, rather than passes, when its input set is **empty**. A check
   over zero files reporting success is the most common way to ship nothing.

Record both exit codes. A check with only a green run recorded does not ship.

## Repo-specific notes

{notes}

## Where the docs are

- `README.md` — what this repo is and how to run it
- `CLAUDE.md` / `AGENTS.md` — the agent-facing conventions (where present)
- `w0m-web/TASKS.md` — the live queue; the `T##` row is status-of-record
- `w0m-web/TECH-DEBT.md` — decided debt; delete the rows your ticket pays down
- `w0m-web/openspec/` — specs and in-flight changes
"""


# ── Driver ───────────────────────────────────────────────────────────────────


def _render_license(repo: str, _facts: dict[str, Any]) -> str:
    return license_text(repo)


def _render_coc(repo: str, _facts: dict[str, Any]) -> str:
    return code_of_conduct_text(repo)


GENERATED: dict[str, Callable[[str, dict[str, Any]], str]] = {
    "LICENSE": _render_license,
    "SECURITY.md": security_text,
    "CONTRIBUTING.md": contributing_text,
    "CODE_OF_CONDUCT.md": _render_coc,
}


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="write_hygiene_docs.py",
        description=__doc__,
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        default=True,
        help="report files that would be written without modifying disk (default)",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="write generated hygiene files to disk",
    )
    ap.add_argument(
        "--check",
        action="store_true",
        help="verify generated files on disk match rendered templates (exits 1 on drift)",
    )
    ap.add_argument(
        "--estate-root",
        type=Path,
        default=None,
        help="override estate root directory (for offline testing)",
    )
    ap.add_argument(
        "--policy",
        type=Path,
        default=None,
        help="override hygiene-policy.json path (for offline testing)",
    )
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    estate = Path(args.estate_root).resolve() if args.estate_root else Path(__file__).resolve().parent.parent
    policy_path = (
        Path(args.policy).resolve()
        if args.policy
        else (estate / "project" / "policies" / "hygiene-policy.json")
    )
    policy: dict[str, Any] = cast(dict[str, Any], json.loads(policy_path.read_text(encoding="utf-8")))

    repos = [str(r["path"]) for r in policy["repos"]]

    missing_on_disk = [r for r in repos if not (estate / r).is_dir()]
    if missing_on_disk:
        print(
            "[FAIL] declared repo(s) absent from disk: "
            + ", ".join(missing_on_disk)
            + "\n   A declared repo that is missing is a HARD FAILURE, not a skip —"
            "\n   silently shrinking scope is how a gate stops meaning anything.",
            file=sys.stderr,
        )
        return 1

    unknown = [r for r in repos if r not in REPO_FACTS]
    if unknown:
        print(
            "[FAIL] no measured facts recorded for: "
            + ", ".join(unknown)
            + "\n   Add an entry to REPO_FACTS. Do NOT let it fall back to a generic"
            "\n   template — boilerplate that says nothing about the repo is the"
            "\n   padding this change exists to reject.",
            file=sys.stderr,
        )
        return 1

    written = 0
    unchanged = 0
    drifted: list[str] = []
    for repo in repos:
        facts = REPO_FACTS[repo]
        for name, render in GENERATED.items():
            # T433 / T52 / AgDR-0047: w0m-sec/SECURITY.md is the canonical estate Vulnerability
            # Disclosure Policy + T52 password policy mirror and is authored directly.
            if repo == "w0m-sec" and name == "SECURITY.md":
                continue
            target = estate / repo / name
            body = render(repo, facts)
            if target.exists() and target.read_text(encoding="utf-8") == body:
                unchanged += 1
                continue
            drifted.append(f"{repo}/{name}")
            if args.apply and not args.check:
                target.write_text(body, encoding="utf-8")
            else:
                print(f"would write {repo}/{name}")
            written += 1

    if args.check:
        if drifted:
            print(f"[FAIL] {len(drifted)} hygiene doc(s) drifted: {', '.join(drifted)}")
            return 1
        print(f"[PASS] All {unchanged} generated hygiene doc(s) across {len(repos)} repos are in sync.")
        return 0

    verb = "wrote" if args.apply else "would write"
    print(
        f"[PASS] {verb} {written} file(s) across {len(repos)} repos "
        f"({unchanged} already identical)"
    )
    print("[INFO] README.md is NOT generated — it is hand-written per repo (see module docstring).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
