---
name: eli5
description: Explain complex technical concepts, architectures, and workflows through progressive audience-adaptive simplification (5-year-old, junior developer, product manager, executive) and self-contained interactive visual HTML explainers with SVG diagrams, guided walkthroughs, and click-to-reveal details. Trigger when asked to "ELI5", "explain like I'm 5", "make this simple", or build a visual architecture explainer.
metadata:
  version: "2026.11.13-1794579916"
---

# ELI5 — Progressive Simplification & Interactive Visual Explainer

Adopted and adapted from `anthropics/claude-plugins-community` (`plugins/eli5/skills/eli5/SKILL.md` @ `f4c9452f5ca091f1be7064d9faab1b001ea21645`, MIT License, authored by `busse`), combined with audience-adaptive progressive simplification patterns evaluated against `DreambigOu/ELI5` (`a766623b062331fdde53467001379b4ddf3acc2f`).

## When to Activate

Trigger this skill when the user asks to:
- **"ELI5"**, **"Explain like I'm 5"**, **"Explain this simply"**, or **"Break this down in plain English"**
- Explain an unfamiliar architecture, protocol, algorithm, database policy, or workflow to a specific audience (child/novice, junior developer, non-technical product manager, or executive)
- Generate an **interactive visual HTML explainer** for a system, data flow, state machine, or codebase subsystem

---

## Boundary with Design System & Production UI (`[[T183]]`)

> **Strict Separation of Surfaces (`[[T183]]`):**
> `eli5`'s standalone HTML output and self-contained CSS palettes apply **exclusively** to throwaway explanatory artifacts (such as `/tmp/eli5-*.html` or scratch architectural walkthroughs) and designated standalone visual documentation folders (`docs/visuals/`).
> - **Never** use `eli5` ad-hoc HTML, inline styles, or standalone color palettes inside production application routes (`apps/*`), `.astro` pages, `.svelte` components, shared UI libraries (`packages/ui/*`), or public documentation walkthrough hubs (`docs/walkthroughs/`).
> - Production interfaces and control-plane views are strictly governed by the canonical Design System (`@webomage/ui` in `packages/ui`, `[[T183]]`) and must use semantic CSS custom properties (`var(--...)`) and Design System primitives (`Button`, `Input`, `Select`, `Badge`, `Card`, `PageHeader`).
> - Complementarity with `feynman`: Use `feynman` to interrogate a convoluted bug or expose hidden gaps in your own understanding via the four-step Feynman Technique; use `eli5` to **communicate** a verified architecture or concept outward through calibrated prose ladders or interactive visual HTML explainers.

---

## Mode Selection

Choose the output mode that matches the user's request:

1. **Prose Ladder Mode (Default for quick conversational questions):**
   Deliver a structured, jargon-free explanation calibrated to the requested audience, progressing from a concrete everyday analogy to the real technical mechanism.
2. **Interactive Visual HTML Explainer Mode (Default when asked to "visualize", "show me how X works", or "build an explainer page"):**
   Generate a self-contained single-file HTML document (`/tmp/eli5-<topic>.html`) combining an interactive SVG architecture diagram, a numbered step-by-step walkthrough, and expandable deep-dive cards.

---

## Mode 1: Audience-Adaptive Progressive Simplification

Every prose explanation follows a 4-stage progressive disclosure ladder:

### 1. The One-Sentence Core Truth
State what the system or concept *actually does* in one plain sentence without acronyms or buzzwords.

### 2. Audience-Calibrated Analogy
Anchor the unfamiliar mechanism to a concrete physical-world system the audience already knows:
- **Level 1 — 5-Year-Old / Complete Novice:** Everyday physical objects (locked toy boxes, post office sorting rooms, restaurant kitchen tickets, traffic lights). Zero code or jargon.
- **Level 2 — Junior Developer:** Familiar programming primitives (hash maps, function queues, check-in desks, library hold shelves) mapped directly onto the target system's files and functions.
- **Level 3 — Product Manager / Stakeholder:** User journey, failure modes, latency/cost tradeoffs, and operational guarantees without implementation syntax.
- **Level 4 — Executive / Decision Maker:** System invariant, blast radius, risk reduction, and unit-economics or delivery impact in three crisp bullets.

### 3. Mapping the Analogy to Reality
Provide a compact mapping table connecting each element of the analogy to the exact code symbol, table, route, or protocol step:

| Analogy Element | Real System Component | What It Actually Does |
|---|---|---|
| Restaurant ticket rail | Job queue table | Holds pending tasks in strict order until a worker claims one |
| Kitchen pass check | Schema validator | Rejects malformed outputs before they reach the customer |

### 4. Where the Analogy Breaks Down
Every analogy has an edge where it stops being true. Name that boundary explicitly so the reader never forms a false mental model.

---

## Mode 2: Self-Contained Interactive Visual HTML Explainer

When building a visual explainer, research the actual code paths first (trace real files, schemas, and call flows — never invent placeholder boxes), then generate a **single self-contained `.html` file** with zero external network dependencies.

### Required Interactive Structure

1. **Header Banner:**
   - Clear title, one-sentence plain-English subtitle, and an audience-level toggle or summary badge.
2. **Interactive SVG Architecture Diagram:**
   - Clean SVG viewBox with distinct node groups (`<g class="node" data-step="1">`) for each component.
   - Directional connectors (`<path>` with `<marker>` arrowheads) showing data or control flow.
   - Clicking a node highlights its active step and scrolls/switches the walkthrough panel.
3. **Step-by-Step Guided Walkthrough:**
   - Numbered sequence (`Step 1 of N`) with **Previous** and **Next** controls (plus keyboard left/right arrow support).
   - Stepping forward highlights the active SVG node and connector path while dimming inactive nodes, updating the plain-English explanation and real file/symbol reference for that step.
4. **Click-to-Reveal Deep Dives:**
   - Collapsible `<details>` sections for edge cases, security invariants, and "Under the Hood" code references so the primary view stays uncluttered.
5. **Self-Contained Styling & Accessibility:**
   - Zero CDN links, zero external scripts or fonts (use system UI and monospace font stacks).
   - High-contrast semantic colors supporting `prefers-color-scheme: dark` and `light`.
   - Semantic keyboard-accessible controls (`<button type="button">`, `aria-current="step"`).
