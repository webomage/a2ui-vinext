---
id: T00
title: "Short imperative phrase"
status: queued          # queued | in-progress | blocked | done | paused
area: product           # product · sdlc · security · tools · ai · knowledge · schemas · data ·
                        # mcp · infra · skills · tickets — 13 values in use. THIS LINE WAS MISSING
                        # from the template until 2026-08-04 while 156 of 159 tickets carried it,
                        # so the three authored from the template most recently (T161-T163) all
                        # dropped the field. A stale template propagates its gap into every new
                        # ticket; `just ticket-schema-check` now reports the divergence.
queue: backlog-platform # now | next | p1 | backlog-ai | backlog-platform | security
                        # ⚠️ VESTIGIAL: `tasks_query.py` never reads this. Nothing downstream
                        # interprets it, so an odd value breaks nothing — retire it or wire it up.
priority: P1            # P0 | P1 | P2 | P3 | (blank) — P3 has always been scored by the ranker
                        # (PRIORITY_WEIGHT["P3"] = 10); this comment claimed otherwise until 2026-08-04.
repos: [web]            # api | web | cf | ext | infra | tooling | research | mlx | …
epic: ""                # e.g. "platform-health-tooling" — canonical kebab-case slug from ROADMAP.md
                        # (closed vocabulary defined in project/tickets-schema.jsonc; see also ROADMAP.md).
spec: ""                # e.g. "openspec/changes/2026-07-12-multi-hat"  (blank if none)
# OPTIONAL milestone: audit-2026-07-17  # temporal phase or origin event, T239 AC3b. Orthogonal to functional `epic`.
                        # Declared in .w0m/sdlc.json -> milestones. Optional for ticket-side origin milestones.
# OPTIONAL blocked_by: [T8]   # ticket ids this one waits on.
                        # 🔴 Declared as an OPTIONAL key, commented out on purpose. The field is
                        # ALREADY LIVE — tasks_query.py renders the sdlc board's "Blocked by" column
                        # from it and ticket_deps.py builds the dependency graph — but the template
                        # omitted it, so `ticket-schema-check` reported the two tickets USING it
                        # (T20, T22) as "key not in the template". The gate's wording was right:
                        # TEMPLATE drift, not ticket drift.
# OPTIONAL type: task            # bug | feature | task — the NATURE of the work, T242 AC5b.
                        # Adopted 2026-08-21: GitHub org issue types, names taken DIRECTLY because
                        # there was no pre-existing local spelling to preserve (unlike priority).
                        # Orthogonal to `area` (a domain) and `tags` (keywords): this says defect vs
                        # capability vs chore, which nothing else here captures.
                        # 🔑 Unlike issue FIELDS, types are SEARCHABLE — `type:Task` matches in the
                        # issue list where `priority:High` returns 0. The only new filterable axis.
                        # 🔴 OPTIONAL, and deliberately NOT backfilled. Measured over 240 titles:
                        # 18 defect-ish, 9 feature-ish, 213 (89%) neither; only 2 tickets tagged
                        # `bug`. There is no signal to derive from, so assigning a type to 213
                        # tickets would be inventing a classification. Assign going forward.
                        # ⚠️ Required is not an option: template_keys() makes every key here
                        # mandatory, and adding one turned 227 tickets red in one commit (T228).
# OPTIONAL closed_as: completed   # completed | not-planned | duplicate — HOW this closed, T239 AC7.
                        # Only meaningful once `status: done`. 🔴 It exists because we were already
                        # publishing the answer and getting it wrong: `sync_github.py` never set
                        # `stateReason`, so GitHub DEFAULTED every close to COMPLETED and all 76
                        # closed issues read COMPLETED. A false PRESENT is worse than an empty field.
                        # ⚠️ OPTIONAL deliberately — requiring it would redden 74 historical closes
                        # that cannot be dispositioned without reading each one, and a keyword sweep
                        # was measured at ~1-in-5 precision. Declare it on new closures; the gap on
                        # old ones is REPORTED, not guessed.
                        # ⚠️ It must NOT be an active line: `template_keys()` treats every frontmatter
                        # key as REQUIRED, so adding it live turned 227 tickets red in one edit
                        # (measured 2026-08-18). An `# OPTIONAL ` prefix declares the field without
                        # demanding it.
# OPTIONAL x_ac_done: 0           # derived by tasks_query.py / tickets_frontmatter_sync.py
# OPTIONAL x_ac_total: 0          # derived by tasks_query.py / tickets_frontmatter_sync.py
# OPTIONAL x_ac_pct: 0            # derived by tasks_query.py / tickets_frontmatter_sync.py
# OPTIONAL x_hot_score: 0.0       # derived by tasks_query.py / tickets_frontmatter_sync.py
# OPTIONAL x_blocked_by: []       # derived by tasks_query.py / tickets_frontmatter_sync.py
# OPTIONAL x_synced: "2026-09-18" # synced by scripts/sync_github.py
# OPTIONAL agent_id: ""           # virtual agent id (<harness>:<handle>, e.g. agy:ant-ci, claude:main) — T564
# OPTIONAL pending_closure: ""    # declared external condition holding a 100%-AC ticket open (e.g. awaiting deploy) — T245 AC1b
# OPTIONAL spec_exempt: ""        # exemption class from .w0m/sdlc.json -> spec_policy.exempt_classes — T185 AC1/AC2
gh_issue:               # filled by scripts/sync_github.py
tags: []                # e.g. [ai, security]
                        # OPTIONAL namespaced form (T353): `_`-delimited, most-general segment
                        # first — `sdlc`, `sdlc_design`, `sdlc_design_gate` are 3 depths of one
                        # family. `just tasks overview`'s "by TAG FAMILY" block rolls these up
                        # automatically from the string alone (`tasks_query.tag_family()`), no
                        # roadmap-section lookup table to maintain. A flat tag (no `_`) is fine —
                        # this is additive to `epic:`, not a replacement; use it going forward,
                        # not a mass-retag of existing tickets.
created: 2026-07-13
---

# T00 — Short imperative phrase

## Summary

What this ticket delivers and why, in a few sentences. Carry over the prose from the
TASKS.md row; expand where the board view had to stay terse.

## Acceptance criteria

<!-- Each criterion MUST carry an `AC<n>` id — the sdlc ranking counts `- [state] AC<n> …` and
     nothing else. This template used to show id-less bullets, and 64 tickets followed it and were
     silently excluded from the ranking as "unmeasurable". `just ac-trace-check` now fails on it.
     Four states: [x] done · [ ] open · [~] half-done · [N/A] conditional whose branch was not
     taken (excluded from BOTH counts, so it cannot cap a finished ticket below 100%).
     Sub-criteria nest with a letter: AC3a, AC3b. -->

- [ ] AC1 — Observable, testable outcome
- [ ] AC2 — Observable, testable outcome

## Definition of Done

Per [`../../openspec/SPEC-AUTHORING-STANDARD.md`](../../openspec/SPEC-AUTHORING-STANDARD.md):
- Spec verified (`openspec-verify-change`) when required by `.w0m/sdlc.json → spec_policy`, or exemption class noted.
- Acceptance criteria verified with tests/quality gates.
- Quality gates clean (`just test`, `just lint`, `just typecheck`, `just debt-check`).
- Committed referencing ticket ID; TASKS.md row + ticket + GH issue in sync.

## Links

- **Epic:** [[ROADMAP]] §13.6 — `platform-health-tooling`
- **Spec:** —
- **Related:** [[T00]]

## Status notes

Running log of state — mirror the nuance from the TASKS.md status cell here.
