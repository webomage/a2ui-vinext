---
id: AgDR-0021
title: "Install-or-exclude verdicts for the 7 undecided canonical skills"
timestamp: 2026-09-15T00:00:00Z
agent: claude-code
model: claude-sonnet-5
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T190
---

# AgDR-0021 — Install-or-exclude verdicts for the 7 undecided canonical skills

## Y-statement

> In the context of **T190 AC3** (every canonical skill in `wom7skills/skills/` must be decided,
> not merely inventoried), facing **7 skills `w0m skill gaps` reports as installed nowhere**, we
> decided **to install 5 into specific repos and exclude 2 as superseded by already-installed,
> more comprehensive skills**, to achieve **a fully-accounted canonical library with no
> undecided residue**, accepting **that two skills now sit in `wom7skills/skills/` permanently
> unreachable by any project — dead weight in the canonical tree, not a gap in governance**.

## Context

Measured 2026-09-15 via `w0m skill gaps` (live) and `wom7skills/skills-registry.json`
(origin/evidence per skill):

- **`mmd-validate`** — registry evidence names `wom7web`'s own `doc-format-check` pre-commit hook
  as the concrete consumer.
- **`observability-and-instrumentation`** (origin: imported, `addyosmani/agent-skills`) — generic
  logging/tracing/metrics guidance; `wom7web` and `wom7api` are the two repos with live production
  runtime code (Astro SSR + Hono worker respectively); the other 5 estate repos
  (`wom7cfworkers`/`wom7ext`/`wom7sec`/`wom7mlx`/`wom7skills`) have **no `.claude/skills` directory
  at all** as of 2026-09-15 (confirmed live via `w0m skill estate`) — bootstrapping skills
  governance there from nothing is a separate, larger initiative, out of scope for this decision.
- **`playwright-testing`** (w0m-native, short) vs. `wom7web`'s already-installed
  `playwright-best-practices` (`skills.sh`, `currents-dev/playwright-best-practices-skill`,
  v1.1, MIT) — content-diffed directly (not matched by name, per the standing rule that a shared
  or similar name can denote genuinely different skills): the vendored skill is far more
  comprehensive (64 lines vs. a short native stub) and already governs Playwright usage in the
  one repo that runs Playwright.
- **`sourcing-integration`** — registry evidence cites the live ATS surface
  `apps/cp/src/pages/business/ats/index.astro` plus the recruitment-domain `join`/`job` apps, all
  in `wom7web`.
- **`steve-jobs`** (persona skill) — `wom7web` is the design-system/product-building repo; the
  workspace root already carries a more general-purpose persona set (`feynman`, `socrates`,
  `torvalds`, `doubt-driven-development`) rather than a product-design-specific one.
- **`supabase-postgres`** (w0m-native, 20 lines) vs. `supabase-postgres-best-practices`
  (`skills.sh`, `supabase/agent-skills`, already installed in both `wom7web` and `wom7api`,
  64 lines) — content-diffed directly: overlapping domain (DB/RLS best practices), the vendored
  skill materially more comprehensive.
- **`w0m-prs`** — the workspace-root `justfile` already wires a `prs` recipe (line 16, landed
  under T345, commit `06a5a89`), and no other root has an equivalent recipe.

T190's own "Out of scope" note (`.tasks/T190.md`) confirms: *"AC3 requires each be
decided, not that any be added — several are persona skills whose value is a judgement call."*
Deliberately-excluded-with-a-reason is therefore a fully valid AC3 outcome, not a fallback.

`w0m skill gaps` (`w0m_skill.ts:1771-1812`) computes "present" purely from manifest-declared ∪
on-disk-installed, per known root; it never reads a manifest's `exclude` map. That map exists only
to suppress `check`'s unmanaged-skill warning for something already installed — it cannot record
"deliberately not installed anywhere," which is why this decision is recorded here rather than in
an `exclude` entry.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| Install all 7 everywhere (blanket enrollment) | Simple, no judgement calls | Reintroduces exactly the `name.startsWith("w0m")`-style auto-enrollment T149 deliberately narrowed away from; ships two skills that duplicate a better-maintained vendored equivalent | Rejected |
| Leave all 7 undecided, close T190 on Phase 1+2 only | No further work | Fails AC3 outright — the ticket explicitly requires a decision, not silence | Rejected |
| Record "exclude" via each project's manifest `exclude` map | Reuses an existing mechanism | `exclude` is not consulted by `gaps` at all (confirmed by reading `cmdGaps`'s source) — would not actually suppress the gap and misrepresents what the field means | Rejected |
| Per-skill install-or-exclude verdict, recorded in an AgDR, manifests edited only for the 5 installs | Matches AC3's literal requirement; durable, reviewable, evidenced; excluded skills get a citable reason without abusing `exclude` | Two skills remain permanently unreachable in the canonical tree | **Accepted** |

## Decision

| Skill | Verdict | Install target(s) | Reason |
|---|---|---|---|
| `mmd-validate` | Install | `wom7web` | Consumer named directly in registry evidence (doc-format-check hook) |
| `observability-and-instrumentation` | Install | `wom7web`, `wom7api` | Only two repos with live production runtime code and an existing skills surface |
| `playwright-testing` | **Exclude** | — | Superseded by `wom7web`'s already-installed `playwright-best-practices` (content-diffed, materially more comprehensive) |
| `sourcing-integration` | Install | `wom7web` | Live ATS/recruitment-domain surface (`apps/cp/.../ats`, `join`, `job`) |
| `steve-jobs` | Install | `wom7web` | UI/product-design persona fits the design-system-owning repo; root's persona set is general-purpose |
| `supabase-postgres` | **Exclude** | — | Superseded by `supabase-postgres-best-practices` (content-diffed, already installed in `wom7web` + `wom7api`) |
| `w0m-prs` | Install | workspace root (`@wom`) | Its CLI (`just prs`) is wired at the workspace-root justfile (T345) |

## Consequences

**Positive:** All 7 canonical skills named by T190 AC3 now carry a recorded, evidenced decision;
`w0m skill gaps` will report zero canonical skills undecided once the 5 installs land; the two
exclusions are traceable to a content diff rather than a name-based guess.

**Negative:** `playwright-testing` and `supabase-postgres` remain in `wom7skills/skills/`
permanently uninstalled anywhere — dead weight in the canonical tree that a future skill-count
audit will need to remember is intentional (this record is that memory). Installing
`observability-and-instrumentation` into only 2 of 8 estate roots means the other 5 stay
unobserved by this skill until they separately gain a skills-governance surface — a known,
accepted gap, not a silent one.

## What this does NOT decide

- Whether `playwright-testing` or `supabase-postgres` should ever be **deleted** from
  `wom7skills/skills/` — this record only decides installation, not canonical-tree pruning.
- Whether `wom7cfworkers`/`wom7ext`/`wom7sec`/`wom7mlx`/`wom7skills` should be adopted into skills
  governance at all — that is a separate, larger initiative than this ticket's scope.
- Anything about the "wrong-root class" writeup, T190's other remaining Phase 3 item — tracked
  separately in `wom7web/AGENTS.md`.
