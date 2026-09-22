<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-08-23 (LATEST) — **the client thread: Artemio's REPO is governed and CONFORMS, Artemio the CLIE -->

## ⭐ PICK UP HERE — 2026-08-23 (LATEST) — **the client thread: Artemio's REPO is governed and CONFORMS, Artemio the CLIENT does not exist in the database at all, and the registry could not describe a workspace until tonight.**

**Owner direction that reframed the queue:** *"we will be working more on content formatting and
layouts and Design System re-sync and deeper adoption — for now we have to complete our mechanics
and power up Artemio as first registered and managed client."*

**Shipped:** [[T268]] ✅ **DONE / ARCHIVED 2026-08-24** — the client registry now speaks **simple** and **workspace**, 10 probes + a control; finished by
REMOVING a subject (BridgeRoad) rather than by more work. [[T267]] ✅ **BUILT 8/8** — both gates scoped to the change, and its new pre-push emoji ratchet ran
on its own first push. [[T261]] ✅ **DONE / ARCHIVED 2026-08-24** — measured, fixed, deployed and verified **in production** (22 rows, every
figure matching local; 4 violations, all recorded debt [[D60]]). [[T182]] split — Artemio's import
CLOSED, `just client-check artemio` = **CONFORMS 6/6**. [[T268]] built — the registry now speaks
**simple** and **workspace**.

**Filed today (7):** [[T264]] 1945's divergence · [[T265]] BridgeRoad · [[T266]] the Artemio join ·
[[T267]] the deploy-hook false positive · [[T268]] two project shapes · [[T269]] `.mcpb`/`.dxt`
research · [[T270]] the `eli5` skill. [[T183]] **unpaused** at P1 (owner confirmed).

**THE ONE THING TO CARRY FORWARD**

🔑 **Four times today a measurement contradicted a written record, and every time the record was the
confident one.** This is not a run of bad luck; it is what the estate's own notes are for.

| the record said | the measurement said |
|---|---|
| [[T182]] AC4: the retired `.agent/skills` tree was *"found and fixed"* | 33 real dirs still there — Artemio's own `7ded876` reverted it, and **a probe naming that exact tree has been RED since 2026-08-13**, parked as `blocking: false` |
| [[T204]]: *"1 `direct` contract with a `client_id`"*, which I read as possibly Artemio | it is the **DEMO** client. Artemio has **zero** rows anywhere in the product DB |
| [[T182]] AC3: 1945 has **5** divergent keys | **4** |
| the deploy hook: *"committing would break the running deploy"* | the deploy was **1945's**, in another repo, which has no `confirm_step.py` at all |

⇒ **Re-run the measurement before acting on the note.** Every one of these was cheap to check and
none of them would have been caught by reading.

⚠️ **And the sharpest version, worth more than the four above:** a red probe that is red *for a stale
reason* is worse than no probe. Three assertions in `client-inventory-test` have been failing since
2026-08-13 with a recorded reason — and two of them now expect numbers that are simply wrong (*"23
declared"* against Artemio's **55**). The `.agent/skills` regression hid for 14 days **inside a suite
that names it**, because nobody could tell which of its reds still meant anything. **A parked red is
a decision that looks like a queue.**

**NEXT, in order**

1. **[[T266]]** (`queue: now`) — AC1 is DONE and it says *create, not prove*. Artemio needs a
   `clients` row, a `client_users` link and an account. 🔴 The blocker found while grounding it: the
   admin CRM (`ClientManager.svelte`) writes the `clients` row **only**, so an admin-created client
   has no user, no role and no link — and the portal correctly fails closed to an **empty page**.
   `client-register` wires all four but is keyed to a `lead_id`, and Artemio is not a lead.
2. **[[T198]] AC6 + AC7** — the last two live authz defects on that exact surface. AC6 is
   owner-decided and merely unbuilt.
3. **[[T268]] AC5 → [[T265]]** — declare BridgeRoad as a workspace; the capability now exists.
4. **[[T183]]** — unpaused, gates the DS re-sync arc the owner named as what comes next.

**OPEN DECISIONS FOR THE OWNER**

- ~~**[[T261]] archive** — blocked on the `layout-matrix` promotion trigger.~~
  🟢 **RESOLVED AND ARCHIVED 2026-08-24 (owner).** The suite stays **warning-only** and its trigger
  now names **D60/D61** instead of the ticket — a promotion condition must be a state of the
  **product**, not the paperwork, so archiving no longer arms a gate that cannot pass. The remainder
  is [[T275]] (P2), whose end state is a **value ratchet** (baseline 55/57/16, fail on regression,
  60% kept as the goal). Two stale claims in the old registration were corrected in the same edit.
- **T105** — Hono worker (`wom7api/src`) now type-checked + pre-commit gated (was zero coverage).
- **T79** — demo showcase app verified live + archived.
- **T41** — demo accounts **C+D live**: admin CP "Provision demo" button + nightly pg_cron reset.
- **T34** — flows library complete (22 `.mmd` + multi-role stories + README index).
- **T115** — Zod-v4 deprecation migration (~446 astro-check hints cleared). *Remaining: ts6133 unused
  sweep (~398) + the ratchet decision — deferred, T115 still 🟡.*
- **T116** — the "duplicated schemas" turned out to be dead/drifted orphaned Zod models → archived to
  `docs/archive/zod-models-snapshot-2026-02.md`, live copies deleted. *Remaining: per-app `supabase.ts`
  copies (minor).*
- **Tooling:** ticket-sync drift fixed + **pre-push auto-sync** to GitHub; **openspec narrowed to
  Claude+Antigravity**; **oxfmt auto-writes on commit**; **tech-debt pre-push advisory**.
