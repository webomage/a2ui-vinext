<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0c. DONE & PUSHED 2026-07-24 — T64 SDLC/DevOps framework DECISION -->

### 0c. DONE & PUSHED 2026-07-24 — T64 SDLC/DevOps framework DECISION

Owner asked to review the SDLC/devops framework research (`wom7md/50-research/business/
open_source_sdlc_alternatives.md`, 30 platforms). **Decision recorded:** `wom7md/40-specs/
T64-sdlc-devops-framework-decision-2026-07-24.md` (wom7md `2dd37cf`; T64 ticket+board wom7web
`cde31739`). **Verdict: Model B stays the baseline interface** (hooks + `just`, no CI/CD server, no
Backstage framework, no self-hosted forge); **adopt Dagger** (TS pipelines) + a **Backstage-*style***
Svelte catalog ONLY as implementations *behind* `just`. **T64 re-scoped + ordered AFTER T130** (AC3
first = Dagger replaces fragile bash in `deploy-all`; AC2 = Svelte catalog over the T130 registry).
Rejected self-hosted forge/CI; deferred Gitpod. **T22's Model B is affirmed, not replaced.**
