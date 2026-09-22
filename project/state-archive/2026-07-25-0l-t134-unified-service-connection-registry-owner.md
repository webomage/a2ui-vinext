<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0l. 🆕 FILED 2026-07-25 — T134: unified service & connection registry (owner ask) -->

### 0l. 🆕 FILED 2026-07-25 — T134: unified service & connection registry (owner ask)

`project/tickets/T134.md` (P1, `queue: next`, GH **#95**). Owner ask: connect services to w0m; show
in admin CP every connected/used service with **status, version, MCP, CLI, SDK, update-check**; and
let users manage their own connections (GitHub, external job/profile systems).

**RIGHT-SIZED at the `new` gate — read this before building it.** Research found the request is
largely already tracked, and filing it as asked would have duplicated a P1:
- The **user-facing half is [[T94]](b) almost verbatim** — that ticket already names
  *LinkedIn / Upwork / **GitHub** / CV / Credly* profile connectors plus job boards and ATS.
- The **admin catalog overlaps [[T64]]**'s Backstage-*style* catalog decision (2026-07-24).
- **Four disconnected service registries already exist:** `tools-policy.json` + `just tools-outdated`
  ([[T112]] — **already has versions, floors, known-good and update detection**, just no UI) ·
  `stacks-policy.json` + `just discovery` ([[T130]]) · `.w0m/sdlc.json → mcp` · `social_integrations`.

So T134 owns **only** the taxonomy, the status semantics, the version model and the two CP surfaces;
plumbing stays with T94 / T64 / T90, credentials with T99, reach with T117. **4 owner questions are
open in the ticket** (admin-first vs user-first · is third-party SaaS in scope · per-host vs single
version truth · does "check update" stay read-only). Not started, no spec.
