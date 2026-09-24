# Research: DORA, SPACE & DevEx — How w0m Can Use Them (Internally and as a Client Offering)

**Date:** 2026-09-23
**Author:** Claude Code (Opus 5.5), web research + estate baseline
**Status:** Adopted 2026-09-23 as **T432** (`.tasks/T432.md`); §9 below is the original ticket draft
**Diagram:** [`2026-09-23-t432-research-dora-space-devex-for-w0m.mmd`](2026-09-23-t432-research-dora-space-devex-for-w0m.mmd)
**Related:** `public.deploy_log` (release-versioning change), `.tasks/` frontmatter, `deploy-logs/`,
T43 (Tinybird log/trace sink), `LESSONS.md`, measurement-trap lessons (T242/T261)

> Framework facts were checked against primary texts on 2026-09-23 (dora.dev, the 2025 DORA PDF, the SPACE
> and DevEx ACM Queue papers). Where only secondary sources exist, the entry says so.

---

## 1. Executive summary

1. **Use all three frameworks, each for a different job.** **DORA** measures the delivery pipeline (is shipping fast and
   safe?). **DevEx** measures the friction of doing the work (feedback loops, cognitive load, flow). **SPACE** is the
   rulebook that stops either being gamed: at least 3 dimensions, at least one perceptual, never a single metric. **DX Core 4**
   (2024/25) already packages all three into four counterbalanced dimensions. Use it as the reporting frame.
2. **w0m can produce a DORA baseline from data it already has, without buying tools.** `deploy_log` has deploy timestamps
   and commits, git has commit times, `.tasks/` has ticket dates, and `deploy-logs/` has run outcomes. The one real gap:
   **nothing records whether a deploy failed or was unplanned.** That gap makes change fail rate and the new
   **rework rate** unmeasurable today. One migration adds the columns.
3. **w0m is an extreme case, which makes it an interesting one.** It has roughly one human and many agents: 967 commits in 30 days
   in wom7web alone. Activity metrics are therefore useless (agents inflate them for free; see the T261 lesson that every metric
   has a degenerate solution). Surveys of one person are statistically meaningless. Adapt DevEx instead: measure
   **agent friction** (gate failures, permission prompts, hook time, rework loops) plus a **weekly one-minute owner pulse**.
4. **The DORA 2025 AI Capabilities Model reads like a description of w0m's practices.** Clear AI stance (AGENTS.md), AI-accessible
   internal data (codegraph/graphify), strong version control, small batches, quality internal platform (the justfile).
   A self-assessment against it is cheap, and "we score well on DORA's AI capabilities" is a credible sales line.
5. **This can become a client service, with a naming trap.** Consultancies sell 2–4 week DORA/DevEx baselines (Thoughtworks,
   Qualitest on G-Cloud, Clouditive). No firm publishes fixed prices, so w0m has room to productize one.
   **In the EU, "DORA" mostly means the Digital Operational Resilience Act** (fintech regulation): most "DORA audit" pricing online
   is for that. Market it as *"Delivery & Developer-Experience Baseline"* and keep "DORA metrics" in the body text.

---

## 2. The frameworks, briefly and accurately

### DORA (dora.dev, guide updated 2026-01-05)

| Group | Metric | Definition |
|---|---|---|
| **Throughput** | Change lead time | commit → running in production |
| | Deployment frequency | deploys per unit time |
| | Failed deployment recovery time | time to recover from a *change-caused* failure (renamed from MTTR in 2023; **counted as throughput**, not stability) |
| **Instability** | Change fail rate | share of deploys needing immediate intervention (rollback or hotfix) |
| | **Deployment rework rate** (new, 2024) | share of deploys that are *unplanned and caused by a production incident* |

- The **2025 report** was renamed *State of AI-assisted Software Development* (~5k respondents, 90% use AI). AI now correlates
  **positively with throughput but still negatively with stability**; thesis: AI is *"an amplifier"* of what the organisation already is.
- **The elite/high/medium/low tiers are gone.** The 2025 report uses **7 team profiles**: foundational challenges (10%), legacy bottleneck (11%),
  constrained by process (17%), high impact/low cadence (7%), stable & methodical (15%), pragmatic performers (20%), harmonious
  high-achievers (20%). The word "elite" does not appear in the 2025 PDF.
- **AI Capabilities Model v2025.2**, seven capabilities that amplify AI's effect: clear AI stance · healthy data ecosystems · AI-accessible
  internal data · strong version control · small batches · user-centric focus · quality internal platforms.
- **2026 so far:** an *ROI of AI-assisted Software Development* report (J-curve dip, "verification tax", ROI calculator) and a
  *"tokenmaxxing"* post warning against using token spend as a performance signal. No 2026 annual report yet; past editions came out in late September.
- **[Quick Check](https://dora.dev/quickcheck/)** (updated 2026-04-22): free, includes rework rate, 0–10 scores. Useful as a
  client-facing hook.

Sources: [metrics guide](https://dora.dev/guides/dora-metrics/) · [history](https://dora.dev/insights/dora-metrics-history/) ·
[2025 announcement](https://cloud.google.com/blog/products/ai-machine-learning/announcing-the-2025-dora-report) ·
[2025 PDF](https://services.google.com/fh/files/misc/2025_state_of_ai_assisted_software_development.pdf) ·
[ROI report](https://www.infoq.com/news/2026/05/dora-roi-ai-assisted-dev-report/) · [insights](https://dora.dev/insights/).

### SPACE (Forsgren et al., ACM Queue 2021)

- **Five dimensions:** **S**atisfaction & well-being · **P**erformance · **A**ctivity · **C**ommunication & collaboration · **E**fficiency & flow.
- **Rules:** use *"a handful of metrics across at least three dimensions"*, at least one perceptual (survey), and pick metrics that pull
  against each other on purpose. Report at team level, anonymised; individual reporting is illegal in some countries.
- **Myths it rebuts:** productivity = activity; productivity = individual output; one metric tells all.
- Co-author Storey: *"three dimensions, three metrics, done"* is a misuse, though still better than one metric.

Sources: [MSR](https://www.microsoft.com/en-us/research/publication/the-space-of-developer-productivity-theres-more-to-it-than-you-think/) ·
[ACM Queue](https://queue.acm.org/detail.cfm?id=3454124) · [Storey interview](https://www.software-engineering-unlocked.com/measure-developer-productivity-space/).

### DevEx (Noda, Storey, Forsgren, Greiler, ACM Queue 2023)

| | Feedback loops | Cognitive load | Flow state |
|---|---|---|---|
| **Perceptions** | satisfaction with test speed, local validation, deploy time | perceived complexity; ease of debugging prod; doc clarity | ability to focus; goal clarity; on-call disruption |
| **Workflows** | time to CI result; review turnaround; deploy lead time | time to get answers; manual deploy steps; doc-improvement frequency | meeting-free blocks; unplanned-task frequency; incidents needing attention |

North-star KPIs: perceived ease of delivery, engagement, perceived productivity. Always compare perception with workflow data:
*"neither alone can tell the full picture."*
Sources: [ACM Queue](https://queue.acm.org/detail.cfm?id=3595878) · [free PDF](https://www.michaelagreiler.com/wp-content/uploads/2024/06/DevEx-WhatDrivesProductivity.pdf).

### DX Core 4 (2024/25), the unifier

**Speed** (diffs per engineer, never tracked per individual and never a target) · **Effectiveness** (DXI survey) · **Quality**
(change fail rate) · **Impact** (% of time on new capabilities). DX's June 2026 revisit leaves the framework unchanged and
treats AI telemetry (adoption, tokens, agent tasks) as **diagnostic context, not outcomes**. The companion **AI Measurement
Framework** is *utilization · impact · cost*, and counts agent-authored PRs as extensions of the supervising developer.
Sources: [Core 4](https://getdx.com/research/measuring-developer-productivity-with-the-dx-core-4/) ·
[2026 revisit](https://getdx.com/blog/revisiting-the-dx-core-4-in-the-age-of-ai/) ·
[AI framework](https://getdx.com/research/measuring-ai-code-assistants-and-agents/). DXI itself is proprietary.

### AI-productivity evidence (read with care)

- **METR RCT (Jul 2025):** 16 experienced OSS developers took **19% longer** with AI while *believing* they were ~20% faster.
  **Follow-up (Feb 2026):** −18% time for returning developers, but METR itself calls the new data unreliable (developers refused to work without AI). The study is being redesigned.
- Google enterprise RCT (2024): ~21% faster, wide CI. GitHub Copilot lab study (2023): 55.8% faster on a narrow task.
- **Lesson for w0m:** perception and measured time diverge badly with AI, so measure outcomes, not how productive it feels.
  Sources: [METR 2025](https://metr.org/blog/2025-07-10-early-2025-ai-experienced-os-dev-study/) ·
  [METR 2026](https://metr.org/blog/2026-02-24-uplift-update/) · [Google](https://arxiv.org/abs/2410.12944) · [GitHub](https://arxiv.org/abs/2302.06590).

---

## 3. w0m baseline: what exists today (measured 2026-09-23, read-only)

| Signal | Where | 30-day reading | Usable for |
|---|---|---|---|
| Commits (no merges) | git, per repo | wom7web **967** · wom7api 211 · root 114 · skills 45 · func 19 · ext 9 · sec 4 | context only. **Not a metric** (agent-inflated) |
| `fix:`/`revert:` commit share | git subjects | wom7web 14% · wom7api 22% · 1 revert total | ⚠️ weak rework proxy. Most `fix:` commits never reached prod |
| Deploy events | `public.deploy_log` (service, version, commit, actor, deployed_at, notes) | **not queried** (live DB; this research ran no DB reads) | deploy frequency, lead time (join `commit` → git time) |
| Deploy run outcomes | `deploy-logs/*.log` (local, gitignored) | ~6 deploy + 11 run logs in Sept | failure evidence, e.g. 2026-09-23 `deploy-all` had 3× Supabase 500 → T431 |
| Ticket lifecycle | `.tasks/*.md` frontmatter (`created`, `status`, `closed_as`, `x_ac_*`) | 240 done; 161 created since 2026-08-24 | ticket lead time (created → done; the done date must be derived from git history of the file) |
| Incidents / lessons | `LESSONS.md`, memory, tickets | narrative only | recovery time (needs structured start/end) |
| CI | GitHub Actions | **dead** (account-level startup_failure) | ❌. Local hooks are the only "CI", so hook duration *is* the feedback loop |

**Gaps that block the instability half of DORA:**
1. `deploy_log` has **no `outcome`** (success/failed/rolled_back) and **no `trigger`** (planned/incident), so neither change fail rate nor rework rate can be computed.
2. No structured **incident record** (start, detected, recovered, cause-deploy id), so recovery time cannot be computed.
3. **Agent attribution is invisible in git by design.** The no-`Co-Authored-By` rule means "% agent-authored" can't come from git.
   It would need session-side telemetry (Claude Code / Orca / Antigravity logs). Treat it as optional context.
4. It is unverified whether *every* deploy path (`deploy`, `deploy-all`, the new `deploy-function` from T431) writes `deploy_log`.
   **Check this first.** A deploy path that skips the log produces a false baseline (the measurement-trap pattern).

---

## 4. How w0m should use each framework

### 4.1 DORA → the delivery cockpit (internal)

| Metric | w0m computation | Change needed |
|---|---|---|
| Deployment frequency | `count(deploy_log)` per service per week | none (after the gap-4 check) |
| Change lead time | `deploy_log.deployed_at − git commit time(deploy_log.commit)`; median + p90 | none (git lookups are local) |
| Change fail rate | `outcome ∈ {failed, rolled_back, hotfixed}` ÷ deploys | **migration**: `outcome` column; deploy recipes write it (fail closed if missing) |
| Rework rate | `trigger = 'incident'` ÷ deploys | **migration**: `trigger` + `incident_ref` columns |
| Recovery time | incident `recovered_at − detected_at` for change-caused incidents | an `incidents` record (table or `.incidents/` md, matching the `.tasks/` pattern) |

Delivery: a `just dora [--since 30d] [--service X]` recipe (Python, reads `deploy_log` via the existing Infisical-injected
path plus local git) that emits JSONL. Optionally dual-write to Tinybird (fits **T43**) and a CP "Delivery" panel next to
"Services & Versions". **Don't adopt DevLake/Middleware**: both need Docker and GitHub CI data (Actions is dead here), and
DevLake is heavy for one team. **Four Keys is archived** (2024-01), Faros CE is gone (404), and LinearB has no free tier.

### 4.2 DevEx → "Agent DevEx" (w0m-specific adaptation)

In w0m, most of the "developers" are agents, and their friction is measurable directly. Owner friction still needs a short survey.

| DevEx dimension | Agent workflow signal (automatic) | Owner perception (weekly pulse, 1–5) |
|---|---|---|
| Feedback loops | pre-commit/pre-push hook duration; gate failures per commit; `just verify` time; hook re-runs before a green commit | "Getting a change verified felt fast" |
| Cognitive load | size of AGENTS.md/CLAUDE.md context loaded per session; `just ask` misses (had to grep); STATE.md drift blocks | "I understood what the agents were doing" |
| Flow state | permission prompts per session; session interruptions/restarts; tickets re-opened; parallel-agent collisions (T423/T425 domain) | "I had uninterrupted focus time" |

The pulse is three questions in one minute, logged to JSONL. It fulfils SPACE's perceptual requirement without pretending
n=1 is a survey. The existing tooling already touches these signals: Headroom audit, `just mcp-exposure`, the preflight hook,
`state-check`, and hook logs.

### 4.3 SPACE → the guardrail charter

Write a one-page **measurement charter** (AgDR) before any dashboard ships:
- ≥3 dimensions shown together (proposed: Efficiency & flow ← DevEx signals · Performance ← DORA · Satisfaction ← owner pulse).
- **Never target activity** (commits, PRs, lines, tokens, agent task counts); show it only as context. Echoes DORA's "tokenmaxxing" warning and w0m's T261 lesson.
- **"Could not measure" is its own state** (T242 lesson). A missing `outcome` must not read as "success".
- Team/system level only. When w0m measures a client team, results are anonymised and aggregated, never ranked per engineer.

### 4.4 DORA AI Capabilities → a self-assessment w0m would score well on

| Capability | w0m evidence | Self-score |
|---|---|---|
| Clear, communicated AI stance | AGENTS.md non-negotiables, AgDRs, deny-lists | strong |
| Healthy data ecosystems | Supabase migrations-only, schema_change_log, DDL audit | strong |
| AI-accessible internal data | codegraph, graphify, `just ask`, KB-INDEX | strong |
| Strong version control | hooks never skipped, Conventional Commits, ticket-in-commit | strong |
| Small batches | 1 ticket ↔ small commits; but `deploy-all` bundles many services | medium |
| User-centric focus | Gauge specs, UI-SPEC | medium, not measured |
| Quality internal platform | justfile, `just discovery`, preflight | strong, but CI is dead |

### 4.5 DX Core 4 → the one-page scorecard

Core 4 is how the pieces above get **reported**: four dimensions, each with one key metric, designed so that no
dimension can be pushed up without the others showing the cost. DORA feeds Speed and Quality, DevEx feeds
Effectiveness, SPACE's rules are built in, and Impact is the one dimension the other frameworks don't cover.

| Dimension | Core 4 key metric | Secondary metrics ⚠️ | w0m adaptation | Available now? |
|---|---|---|---|---|
| **Speed** | diffs (PRs) per engineer, never per individual, never a target | lead time, deploy frequency, perceived delivery rate | Raw diffs are degenerate here (967 agent commits in 30 days). Use **tickets reaching production per week** + DORA lead time. Diffs are shown only as context, counted per supervising human as DX's AI framework advises | ⚠️ partly: lead time yes, "ticket reached prod" needs a ticket↔deploy link |
| **Effectiveness** | DXI (proprietary 14-item survey) | time to 10th PR, ease of delivery, regretted attrition | DXI is paid and meaningless at n=1. Use the **Agent-DevEx signals** (§4.2) + **owner pulse**; "time to 10th PR" becomes *time for a fresh agent session to land its first green commit* (onboarding cost of AGENTS.md/STATE.md) | ❌ needs AC6 |
| **Quality** | change failure rate | recovery time, perceived quality, operational health | Same as DORA instability; add w0m-native health signals: `/health` checks, `state-check` blocks, security-gate findings | ❌ needs `deploy_log.outcome` (AC3) |
| **Impact** | % of time on new capabilities | initiative progress/ROI, revenue per engineer, R&D % of revenue | Proxy: **share of done tickets by `area`**, i.e. product/ai vs sdlc/tools/infra. Later, weight by time or AC count. For the agency: **billable client work vs internal platform work** | ✅ roughly, today |

⚠️ The secondary metrics come from memory of DX's published table and LeadDev/InfoQ coverage; DX's own table is an
image and was not re-verified. The four key metrics are verified.

**First Impact reading (2026-09-23, ticket counts from `.tasks/*.md` `area:`, 431 tickets):**

| Bucket | Areas | Tickets | Share |
|---|---|---|---|
| New capability (product) | product, ai | 103 | **~24%** |
| Delivery platform (w0m on itself) | sdlc, tools, knowledge, skills, mcp | 213 | **~49%** |
| Security | security, sec | 55 | ~13% |
| Infra & data | infra, schemas, data | 60 | ~14% |

Caveats: counts tickets, not time; **80 tickets carry an *inferred* area** (`⚠️ inferred … verify` comments); and
297 of 432 tickets have no `type:` field, so feature/bug/task can't be used instead yet. Still, it is the headline Core 4
would put in front of the owner: **about half of all ticketed work is w0m building its own delivery platform, and about a
quarter is product.** Whether that ratio is right is an owner decision. The point of Impact is to make it visible.

**2026 AI position (DX, June 2026):** framework unchanged; AI telemetry (adoption, tokens, agent task counts) is
*diagnostic context*, not an outcome. DX's own data: PR throughput +7.8% with AI; AI-generated code ~27.4% of production
code in Q1 2026. This matches the charter in §4.3.

**Why Core 4 is the client-facing frame:** four numbers fit on one slide, executives recognise "% time on new
capabilities", and it is the only framework of the four with an explicit business-impact dimension. Internally, DORA and
DevEx stay as the drill-down; Core 4 is the cover page.

---

## 5. Using it as an agency offering

**Product: "Delivery & Developer-Experience Baseline"** (name avoids the EU-regulation "DORA" collision)

| Phase | Weeks | Output |
|---|---|---|
| 0. Hook | free | Run the client through [DORA Quick Check](https://dora.dev/quickcheck/) + 10-question DevEx pulse |
| 1. Definition audit | 1 | Agree what "deploy", "failure", "incident" mean for them; written protocol (Clouditive-style) |
| 2. Baseline | 1–2 | 5 DORA metrics from their git + deploy + incident data; DevEx survey + workflow signals; Core 4 summary |
| 3. Diagnosis | 1 | 7-profile placement (DORA 2025), AI Capabilities gap map, top-3 bottlenecks |
| 4. Roadmap | — | ADRs + 90-day plan; optional retainer to re-measure quarterly |

- **Pricing signal:** no fixed public prices found. A UK specialist day rate is about £1,050, and baselines usually take 2–4 weeks,
  so roughly **£10–21k** is an extrapolation, not a market quote. A fixed-scope, fixed-price SKU is a gap w0m could fill.
- **Differentiator:** "AI-assisted delivery measured honestly." Most clients now ask whether AI is helping. DORA 2025 (throughput up,
  stability down) and METR (perceived ≠ actual) give w0m a research-backed pitch, and w0m's own cockpit is the live demo.
- **Reuse:** the same `just dora` extractor, pointed at a client's git + deploy source, is the delivery tool. It could live in
  a small package or in `wom7sec`'s audit toolchain alongside the security tiers (openspec 2026-09-11).
- Comparable offerings: [Thoughtworks Engineering Effectiveness](https://www.thoughtworks.com/en-us/about-us/news/2023/thoughtworks-launches-engineering-effectiveness-solution),
  [Qualitest on G-Cloud](https://www.applytosupply.digitalmarketplace.service.gov.uk/g-cloud/services/593381378129614),
  [Clouditive](https://dxclouditive.com/en/dora-metrics-consulting/).

---

## 6. Anti-patterns to avoid (w0m-specific)

1. **Celebrating commit volume.** 967 commits/month is agent output, not productivity. It must never appear as a headline number.
2. **Reading `fix:` share as change fail rate.** Most fixes never shipped a broken deploy; only `deploy_log.outcome` can say.
3. **Reporting a green baseline built on partial deploy logging** (gap 4). Verify coverage before the first number is published.
4. **Token/agent-task counts as output.** Cost belongs in the *cost* column of DX's AI framework, never in *impact*.
5. **Borrowing elite/high/medium/low tiers.** DORA dropped them in 2025; citing them to clients now looks out of date.

---

## 7. Tooling landscape (2026 status)

| Tool | Status | Verdict for w0m |
|---|---|---|
| Four Keys (Google) | **archived 2024-01-23**, GCP-bound | ❌ |
| Apache DevLake | active (v1.0.3-beta16, 2026-08) | ❌ internally (heavy, needs CI data); ⚪ possibly for large clients |
| Middleware OSS | slow (last release 2025-05), 4 classic metrics only | ❌ |
| Faros CE | repo 404, enterprise-only | ❌ |
| LinearB | no free plan; $29–59/user/month with minimums | ❌ |
| Sleuth | pivoted to AI-agent governance | ❌ |
| **Own `just dora` + Tinybird/CP** | fits existing stack | ✅ |

Sources: [fourkeys](https://github.com/dora-team/fourkeys) · [devlake](https://github.com/apache/devlake) ·
[middleware](https://github.com/middlewarehq/middleware) · [linearb pricing](https://linearb.io/pricing).

---

## 8. Could not verify

- Quick Check benchmark values or any 2025/2026 benchmark table (none published).
- Whether a 2026 annual DORA report is imminent (past editions came out in late September).
- 2024 tier shares and the −1.5% throughput / −7.2% stability AI effects: taken from summaries, not the 2024 PDF.
- DX Core 4 per-dimension metrics: confirmed via LeadDev/InfoQ only.
- A standard definition of "agent-authored PR share" beyond DX's guidance.
- Whether all w0m deploy paths write `deploy_log` (estate check, see §3 gap 4).

---

## 9. Proposed ticket (for intake)

**Title:** Delivery & DevEx measurement: DORA 5-metric cockpit, Agent-DevEx signals, and a SPACE measurement charter
**Prio:** P2 · **Repos:** api, web, tooling · **Type:** research → task

- **AC1:** A measurement charter AgDR (≥3 SPACE dimensions, no activity targets, "unmeasurable" as its own state, team-level only) is recorded in `docs/DECISIONS.md`.
- **AC2:** An audit confirms every deploy path (`deploy`, `deploy-all`, `deploy-function`) writes `deploy_log`, with the evidence recorded.
- **AC3:** A migration adds `deploy_log.outcome` + `trigger` + `incident_ref`, and deploy recipes write them (fail closed). The human runs `just db-migrate`.
- **AC4:** A structured incident record exists (location decided: table vs `.incidents/` md) with detected/recovered/cause-deploy fields.
- **AC5:** `just dora` emits the 5 DORA metrics as JSONL for a time window and marks each metric *unmeasurable* when its inputs are missing.
- **AC6:** The Agent-DevEx signals (hook duration, gate failures, permission prompts) and the weekly 3-question owner pulse log to JSONL.
- **AC7:** A DORA AI Capabilities self-assessment is committed to `docs/reports/`.
- **AC7b:** `just dora` also emits a Core 4 scorecard (Speed · Effectiveness · Quality · Impact); Impact starts as the done-ticket share by `area`, and the 80 inferred `area:` values are confirmed first.
- **AC8 (optional, owner decision):** a one-page outline of the "Delivery & DevEx Baseline" client offering (scope, phases, price hypothesis).

**Owner decisions needed:** incident-record location; whether the CP gets a Delivery panel now or later; whether to productize the client offering.
