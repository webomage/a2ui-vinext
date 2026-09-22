<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0f. 1945 (separate project) — DONE there, **continues in its OWN session** -->

### 0f. 1945 (separate project) — DONE there, **continues in its OWN session**

**Do not pick this up from here.** `/Users/proto/Projects/_self/1945` — the 1945 Social Club site
(ViNext = Vite+React, Cloudflare Pages). Branch `t05-deploy-menu`, clean, **2 unpushed commits**, its
own remote. Owner will give feedback in that session. It has its own `STATE.md`/`BOARD.md`/tickets.

Landed there (its **T11**, `.w0m/tickets/T11-automated-release-versioning.md`):
- **Automated release versioning** in the w0m schema — one producer (`justfile` → `app_version`, the
  same `date +%Y.%m.%d-%s` expression as `wom7api`), `just build`/`deploy` stamp,
  `dist/version.json` in the w0m health shape ships to Pages → live surface `/version.json`. Schema
  declared in `.w0m/sdlc.json → versioning`; enforced by `just version-check`, **proven red on all 5
  violation classes** then reverted.
- **The w0m skills installed + governed there**: 11 canonical gates, `11 installed — 11 managed ·
  0 excluded · 0 unmanaged`, tamper proven caught. `just skills-check` / `just skills-sync` wired in.
- **Terminology decoded** (it cost this session real time): **"vinext"** is *1945's own*
  `conventions.framework: "vinext-vite-react"` — it is **not** a w0m stack and is absent from
  `stacks-policy.json`; **"1945"** is this project, not a ticket or a timestamp.

**Why it matters to w0m:** installing into a fresh project exposed a **real bug in our tooling**,
now fixed (`wom7skills` `53ede91`): `skills.ts` symlinked into `.claude/skills` **without creating
the directory**. wom7web already has it, so the bug was invisible — a fresh project failed ENOENT on
the first symlink *after* copying the canonical file, leaving a **partial install**. That is exactly
the **T127 AC10** install-bootstrap failure mode.
