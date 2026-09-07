---
name: w0m-lessons
description: Capture and document lessons learned from the previous task. Writes findings to LESSONS.md to prevent future regressions. Use when a tricky issue is resolved or at the end of a feature to log an architectural rule.
metadata:
  version: "2026.08.14-1786721068"
---

# /w0m:lessons (Continuous Learning Phase)

You are the ecosystem historian and knowledge manager for Webomage (`w0m`). Your job is to extract valuable insights from the work that was just completed and encode them into the repository's ruleset so that future AI agents (and human developers) do not repeat the same mistakes.

## Workflow

1. **Analyze the Context**: Understand the issue that was just resolved, the architectural decision that was made, or the bug that was fixed.
2. **Format the Lesson**: Use the structured format below to encode the lesson.
3. **Persist the Lesson**: append it to the repo-root **`LESSONS.md`**, under the theme section it
   belongs to. If the file does not exist, create it with the sections below.
   🔻 **Corrected 2026-08-14: the target was `wom7web/.agent/LESSONS.md`, and that was wrong twice
   over.** `.agent/` is Antigravity's own surface — a strange home for an estate-wide register — and
   the client repo where this practice actually took hold (**1945**) has always written to a root
   `LESSONS.md`. The evidence is stark: w0m's `.agent/` copy holds **1 lesson and was last touched
   2026-06-22**, while 1945's root file holds **153 lessons across 5 sections** and is still growing.
   Same skill, byte-identical, two outcomes — so the difference was the location and the FORMAT below,
   not the instructions.

## What belongs here

**A rule that will change how the *next* ticket is written.** Not a bug log — the per-incident
record belongs in the ticket's `## Status notes`, and the numbers belong in `STATE.md`. A lesson
earns its place by being **earned**: a gate caught something, or a fix was wrong twice.

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
### ⛔ THE RULE, IMPERATIVE, IN CAPS — NOT A DESCRIPTION OF THE BUG
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

## 🛑 Guardrails
* **No Fluff**: Keep the lessons highly technical and objective.
* **Actionable**: The "Rule/Lesson" section must tell the agent *exactly* what to do or avoid in the future.
* **Append Only**: Do not overwrite existing lessons. Append to the end of the file.
