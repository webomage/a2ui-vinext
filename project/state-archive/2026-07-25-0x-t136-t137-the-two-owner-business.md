<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0x. 🆕 FILED 2026-07-25 (night) — T136 + T137, the two owner BUSINESS asks. New board section. -->

### 0x. 🆕 FILED 2026-07-25 (night) — T136 + T137, the two owner BUSINESS asks. New board section.

> *"write in business tasks 2 important new: research rewriting WP to vinext · register and provide fast
> audit service (for code in repo only) and full audit service (including parsing infra state and
> observability, etc)"*

Filed through `w0m-sdlc-new`. **`TASKS.md` gained a new section — `💼 BUSINESS / SERVICE OFFERINGS`** —
because both are revenue-side, and filing them under *"PLATFORM HEALTH, TOOLING & KNOWLEDGE INFRA"*
would have misfiled them. There was **no** pre-existing business-task surface: `TASKS.md` is the dev
queue and the vault's `50-research/business/` holds research documents, not tasks.

**[[T136]] — research migrating WordPress → vinext (Vite+React).** GH **#97**, P1, `queue: p1`.
- ✅ **Genuinely net-new**: `wordpress|\bWP\b` over `ROADMAP.md` + `TASKS.md` + all `project/tickets/*.md`
  → **zero hits**; the vault has no WordPress document. Duplicates nothing.
- 🔴 **Blocked on one owner question: the estate is unidentified.** The connected Hostinger account has
  **zero WordPress installations** (`listWordPressInstallations`, ownership `all` → `[]`) and exactly
  **one** website, `1945socialclub.com`. So the WP sites are not on our hosting — presumably client or
  prospect properties. **AC1 cannot start until they are named.**
- ℹ️ **`vinext` is not a w0m stack.** It is *1945's own* `conventions.framework: "vinext-vite-react"`
  (Vite+React on CF Pages) and is **absent from `project/stacks-policy.json`** — so adopting it as a
  delivery target costs a **[[T130]]** stack registration (`commands` roles → `just` recipes), which AC6
  makes explicit. **1945 stays in its own session.**
- ⚠️ The ticket deliberately keeps **"do not migrate" as a valid outcome**, and makes AC5 compare
  headless-WP and **Astro** — the w0m platform is already Astro, and Astro suits content/SEO sites better
  than a React SPA, which is what most WordPress sites are.

**[[T137]] — register and offer the two-tier audit service.** GH **#98**, P1, `queue: p1`.
- 🔎 **RIGHT-SIZED AT THE GATE, and this is the important part.** **ROADMAP §30 already specifies both
  depths almost verbatim** — *shallow* = "code-only audit, in a sandbox"; *deep/full* = "code +
  infrastructure + runtime" incl. IaC/cloud-config, TLS/exposure, IAM posture and observability of the
  live surface. Filing the ask as worded would have duplicated a P1 epic — the same trap [[T134]] was
  saved from. **T137 therefore owns the COMMERCIAL layer only:** SKU boundaries a buyer can check,
  pricing/packaging, the intake-and-"registration" path, the **signed scope-and-authorization artifact**
  deep mode legally requires, the report deliverable, the FinOps in-or-out call, and launch sequencing.
- ✅ **The commercial layer really is unwritten:** the prior art
  `../../docs/research/business/ai_native_security_auditing.md` (T45) is purely technical — SAST/SCA/AST
  in agent loops, "agentic slop" — with **zero** pricing/tier/packaging content.
- ⚠️ **The two tiers are NOT launchable as a pair.** §30's build order is shallow-CLI → service wrapper →
  **deep mode last**, so fast is sellable well before full. AC8 forces that to be stated rather than
  discovered by a customer.
- 🔴 **Surfaced dependency: [[T111]] — the toolchain this service sells — has NO ticket file**, only a
  board row. Same class as T99/T109, both of which had to be reconstructed before they could enter the
  SDLC. **A ticket that cannot be opened cannot be gated**, so **AC0 reconstructs it.** This makes
  **five** file-less rows (T111, T112, T87, T90, T94) — the cleanup pass §0v asks for is now overdue.
- ❓ **3 owner questions open**, the load-bearing one being what **"register"** means: build a
  signup/intake surface · list on an external marketplace · or legally register an entity to trade under.
  AC5 assumes the first two.
