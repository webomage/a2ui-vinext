---
name: w0m-lessons
description: Capture and document lessons learned from the previous task. Writes findings to LESSONS.md to prevent future regressions. Use when a tricky issue is resolved or at the end of a feature to log an architectural rule.
metadata:
  version: "2026.10.21-1792643707"
---

# /w0m:lessons (Continuous Learning Phase)

You are the ecosystem historian and knowledge manager for Webomage (`w0m`). Your job is to extract valuable insights from the work that was just completed and encode them into the repository's ruleset so that future AI agents (and human developers) do not repeat the same mistakes.

## Config Resolution

Before reading or writing a lesson, resolve the project's canonical lessons path from `.w0m/sdlc.json`:
1. `.w0m/sdlc.json -> lessons.path` (or `.w0m/sdlc.json -> lessons_surface.file`), defaulting to `LESSONS.md` at the repository root when unset.
2. Query existing lessons first via `.w0m/sdlc.json -> lessons.query_recipe` (or `lessons_surface.query`, defaulting to `just lessons <topic>`).
3. Retention bounds are governed by `.w0m/sdlc.json -> lessons_surface.retention` (or `state_surface.retention.surfaces["LESSONS.md"]`); when over budget, rotate older entries verbatim via `just state-rotate`.

## Workflow

1. **Analyze the Context**: Understand the issue that was just resolved, the architectural decision that was made, or the bug that was fixed.
2. **Check the 4-Home Knowledge Split**: Verify the finding belongs in `LESSONS.md` rather than one of the other three knowledge homes (see table below).
3. **Format the Lesson**: Use the structured format below to encode the lesson.
4. **Persist the Lesson**: Append it to the resolved lessons file (default: repo-root **`LESSONS.md`**), under the theme section it belongs to. If the file does not exist, create it with the sections below.
   *(Historical note: an early legacy `.agent/LESSONS.md` path held only 1 entry from 2026-06-22 and was retired in favor of the config-driven root `LESSONS.md`, where consuming projects and the canonical estate maintain their live lessons register.)*

## The 4-Home Knowledge Split (T178 AC3)

Every piece of operational or engineering knowledge has exactly ONE canonical home:

| Knowledge Home | Surface | What Belongs Here | What Does NOT Belong Here |
|---|---|---|---|
| **1. Standing Rules** | `CLAUDE.md` / `AGENTS.md` | Non-negotiable architectural invariants, safety gates, and session workflow rules enforced on every turn | Per-ticket progress, one-off bug narratives, machine-local paths |
| **2. Auto-Memory** | `MEMORY.md` (agent memory) | Durable cross-session user preferences and environment/machine facts | Ticket handoffs, task queues, or transferable code-review lessons |
| **3. Ticket Body** | `.tasks/T##.md` (`## Status`) | Per-ticket acceptance criteria evidence, verification outputs, and session handoff notes (`w0m-state-save`) | Reusable cross-ticket engineering rules that future tickets must query |
| **4. Lessons Register** | `LESSONS.md` (`lessons.path`) | Transferable engineering rules, failure modes, and post-mortem patterns (`⇒` generalisation + `⭐` tell) queried via `just lessons <topic>` | Routine delivery logs or ticket-specific status updates |

## What belongs here

**A rule that will change how the *next* ticket is written.** Not a bug log — the per-incident
record belongs in the ticket's `## Status` notes, and current pickup state belongs in `STATE.md`. A lesson
earns its place by being **earned**: a gate caught something, or a fix was wrong twice.

**Non-backfill decision (T178 AC5):** Historical closed tickets (`T1`–`T176`+) are deliberately **not** retroactively backfilled into `LESSONS.md`. Their per-ticket evidence and post-mortems are preserved in `.tasks/T##.md` and `project/state-archive/`, whereas synthetic backfill would dilute `LESSONS.md` with reconstructed boilerplate and degrade `just lessons <topic>` signal-to-noise.

## Sections, not chronology

Append under a theme heading, creating it if absent. Chronological append is what let the old file
die at one entry: nothing could be found, so nothing was read, so nothing was added.

```
## 1. Assertions          — how a check can pass while measuring nothing
## 2. Instruments         — the tools and gates themselves being wrong
## 3. Deploys and platforms
## 4. Dependencies and config
## 5. Records             — tickets, specs, registers drifting from reality
```

## The Lesson Format

```markdown
### THE RULE, IMPERATIVE, IN CAPS — NOT A DESCRIPTION OF THE BUG
**YYYY-MM-DD, T##. How many times it bit, if more than once.**

What actually happened, concretely, with the code or the measurement. Enough that a reader who was
not there can tell it is real.

⇒ **The generalisation** — the rule this becomes, beyond the instance.
⭐ **The tell** — how to recognise the shape NEXT time, before it bites.
⚠️ Any caveat that stops the rule being over-applied.
```

🔑 **The title carries the rule.** *"Cloudflare Pages SVG Optimization Bug"* describes an incident;
*"⛔ SERVE .SVG WITH `<img>`, NEVER ASTRO'S `<Image>`"* is a thing an agent can obey while skimming.
A register is read by skimming headings, so a heading that only names a symptom is unreadable.

🔑 **`⇒` and `⭐` are different moves and both are needed.** `⇒` states the rule; `⭐` says how to
*spot* it — the tell is what makes a lesson preventive rather than merely explanatory.

## Example

```markdown
### 2026-06-11 Cloudflare Pages SVG Optimization Bug

* **Context:** Rendering `.svg` logo files in Astro components using the `@astrojs/cloudflare` adapter.
* **Symptom:** The SVGs failed to render in the browser, showing broken image links.
* **Root Cause:** The Astro `<Image>` component attempts to optimize images using Cloudflare's image service (`compile`), which does not support or correctly parse vector SVG formats.
* **Rule/Lesson:** Always use standard HTML `<img>` tags (not Astro's `<Image>`) when serving `.svg` files in this ecosystem.
```

## Guardrails
* **Read-First, Write-Last**: `LESSONS.md` is read-first during grounding (`just lessons <query>`) and write-last upon completion (`w0m-sdlc-archive`).
* **Confidence & Promotion (T232 AC11)**: High confidence is earned when a rule is backed by an automated regression probe or observed across multiple tickets. Medium confidence applies to single confirmed incidents.
* **Bounded Retention**: `LESSONS.md` retention limit is 1,000 lines / 90 KiB (declared in `.w0m/sdlc.json`). When approaching the ceiling, superseded lessons are pruned or rotated.
* **No Fluff**: Keep the lessons highly technical, objective, and free of decorative emoji in headings.
* **Actionable**: The "Rule/Lesson" section must tell the agent *exactly* what to do or avoid in the future.
* **Append Only**: Do not overwrite existing active lessons. Append under the appropriate theme section.

