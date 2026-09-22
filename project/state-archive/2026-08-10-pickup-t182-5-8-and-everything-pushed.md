<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### ⭐ (was) PICK UP HERE — 2026-08-10 — **[[T182]] 5/8 and everything PUSHED (4 repos). 🔴 I deleted a live IDE surface a -->

### ⭐ (was) PICK UP HERE — 2026-08-10 — **[[T182]] 5/8 and everything PUSHED (4 repos). 🔴 I deleted a live IDE surface and pushed it — read §A first. [[T192]] filed: a second IDE is autoloading rules that contradict `CLAUDE.md` and nothing detects it.**

> **Written for an agent with none of my context. Everything below is measured, 2026-08-10.**
>
> ### 🔴 A. The mistake to read before touching any `.agent/` directory
> I deleted **Artemio's `.agent/`**, called it *"the retired pre-[[T127]] w0m layout"*, committed and
> **pushed** it. **It is Antigravity's skills directory** — `openspec init --tools antigravity`
> generates it, exactly as `claude → .claude` and `opencode → .opencode` (read from the installed
> CLI's own registry, `dist/core/config.js`, which maps **31** tools). Restored in Artemio
> `7ded876`, 37 files, refreshed content intact.
> 🔑 **I had a reason to believe it, and that is the real finding:** `w0m skill check` prints
> *"the retired `.agent/skills` path has reappeared"*. That warning encodes `.agent` = retired w0m
> layout — true before openspec grew multi-IDE support, **false now**. **The estate's own gate
> taught an agent to break a client.** Fixing it is [[T192]] AC5. **Until then, never delete an
> IDE directory on that warning alone.**
>
> ### ✅ B. What shipped and is PUSHED
> - **All four repos pushed**: `wom7web` beta `498485c6`, `wom7api` beta `9ed2311`, Artemio main
>   `236867e`(+`7ded876`), servicios777 main `49e49e9`. Verified local == remote on each.
> - **[[T182]] 5/8** — client import path built, written (`docs/CLIENT-IMPORT-PATH.md`) and proven.
>   **8/8 required keys enforceable at a client**; **Artemio and servicios777 both CONFORM**.
>   New gates: `just client-inventory` · `client-profile-check` · `skills-catalogue` ·
>   `state-bounds` · `client-check <id>` (the one-command runner). All red-probed.
> - **[[T192]] filed** (P1, 7 ACs) — connected IDEs ungoverned. In `wom7web`, Claude Code loads
>   `CLAUDE.md` (16,320 B); **Antigravity loads `.agent/rules.md` (1,646 B) with 0 of 6
>   non-negotiables**, byte-identical to wom7api's, and it points at **`wom7web/.env`** — deleted
>   by [[T119]] AC2b — for admin credentials.
>
> ### ⏭️ C. Next, in priority order
> 1. **[[T192]]** — start at AC2 (trace all 31 tool dirs, local *and* global). Three sets of
>    "connected IDEs" exist and none match: owner's 3, `OPENSPEC-OWNERSHIP.md`'s 5, and the disk
>    (**`.opencode` NOWHERE**; **`.kilocode` in servicios777**, named by no one).
> 2. **[[T103]] Astro 6→7** (P1, 0/5, **13 GHSA suppressed as "Astro 6 unfixable"**).
>    🔑 **AC4 is HALF DONE and uncommitted — do not redo the fetch.** Measured against the v7
>    guide: **5 of 10 breaking changes DO NOT apply** (`src/fetch.ts`, `@astrojs/db`,
>    `astro:transitions` internals, `getContainerRenderer`, `experimental` flags — the only
>    `experimental:` hits are vendored `.obsidian` JS). **The real hits:** `markdown:` with
>    `remarkGfm`+`remarkBreaks` in **web + cp** (v7 switches the default markdown processor away
>    from remark → needs `@astrojs/markdown-remark`); **`compressHTML` default `true` → `'jsx'`**
>    and **CSS serialization changes** — 🔴 **both land on the VRT/pixel gates**, which is
>    cosmetic elsewhere and gate-breaking here; **Vite 8** (all 5 apps set `vite:`); the **Rust
>    compiler** now errors on unclosed tags across **210 `.astro` files**. Required bumps:
>    **`@astrojs/cloudflare` 13.3 → 14.2**, **`@astrojs/svelte` 8.1 → 9.0** (both peer `astro@^7`).
>    **servicios777 already runs Astro 7.0.4 on this exact stack — use it as the reference.**
>    ⛔ **AC5 needs deploy, which is DENIED to this agent** (`Bash(just deploy*)`).
> 3. **1945** — [[T182]] AC3 + AC5's half. ⛔ **BLOCKED: another agent works in that repo.** Its
>    `STATE.md` is **411,216 B** and still UNDECLARED, growing ~56 KB in two days.
>
> ### ⚠️ D. Gotchas earned today
> - **This file's rotation only works if you DEMOTE first.** `rotate_patterns` match
>   `### ⭐ (was) PICK UP HERE`; `never_rotate` protects `## ⭐ PICK UP HERE`. I wrote a new block
>   on 08-09 without demoting the old one, so `state-rotate` archived **0** sections and the file
>   sat at 83% of budget with two blocks both labelled **(LATEST)**. Demote, then rotate.
> - **`personaje0`** is a **fourth** project, partly imported, in no ticket until now: **1 of 8
>   required keys, 7 of 14 excluded ones.** Registered read-only in `clients-policy.json`.
> - **Artemio's `secrets_via` is `dotenv`**, servicios777's too — both diverge from infisical.
>   Recorded, not aligned: that is an owner architecture call.
