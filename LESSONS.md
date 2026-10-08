# LESSONS — w0m

Durable rules earned by a gate catching something, each with the instance that earned it.

**What belongs here:** a rule that will change how the *next* ticket is written. **Not a bug log** —
the per-incident record lives in each ticket's `## Status notes`, and the numbers live in
[`STATE.md`](STATE.md).

🔻 **Restarted 2026-08-14 at the repo root**, adopting the format proven in the **1945** client repo.
The previous file lived at `wom7web/.agent/LESSONS.md`, held **one lesson**, and had not been touched
since **2026-06-22**. 1945's root file holds **153 lessons across 5 sections** and is still growing —
with a **byte-identical** copy of the same `w0m-lessons` skill. Same instructions, two outcomes, so
the difference was the location and the format, not the discipline. The old entry is carried over
below, rewritten into this shape.

---

## 1. Assertions

### ⛔ A GREEN STATE MUST BE EARNED BY EVIDENCE, NEVER INHERITED AS A DEFAULT
**2026-08-13, T69.** The character sheet rendered `0 XP / 0 balance` as fact for a month.

`CharacterSheet.svelte` queried `player_xp_totals` without `.schema('gamification')`. PostgREST
resolved against `public`, found nothing, returned `PGRST205` — and the component discarded the
error and rendered the zero. A missing table and a brand-new player were **indistinguishable**.

⇒ **Where an empty result and a failure look the same, the code must distinguish them.** Use
`maybeSingle()` when "no rows yet" is expected, and throw on everything else.
⭐ **The tell:** a destructured query that takes `data` and not `error`. `const { data } = await …`
is a swallowed failure waiting for a schema to move.

### ⛔ WHEN AN ASSERTION COUNTS, ASK WHAT ELSE PRODUCES THAT NUMBER
**Carried from 1945, T54 — it bit three times inside one ticket.**

Three assertions read `sent.length === 1`; a feature added a second recipient and the obvious fix was
to bump each to `2`. But `sent.length === 2` also passes when **both** messages go to the wrong
recipient — precisely the duplicate those clauses existed to catch.

⇒ **Name the subjects; do not tally them.** Resolve *who* received what, not how many did.
⭐ **The tell:** a magic number that has to change because behaviour grew. A clause edited from 1 to
2 was measuring the wrong thing.

### A POSITIVE ACCESS PROBE MUST COMPARE AGAINST SERVICE-ROLE GROUND TRUTH
**2026-09-03 (T266).** `artemio-tenancy-probe` reported FAIL on own-contracts/invoices/milestones, but Artemio had 0 rows in the database across all three tables.

A probe that checks `count > 0` and calls 0 a failure reports a passing RLS policy as broken when a new tenant simply has no data yet. Conversely, inserting dummy data just to turn the probe green creates vacuous green.

⇒ **Compare authenticated tenant counts against `service_role` (unfiltered) counts.**
- `truth == 0`: Data absence — report UNMEASURABLE / SKIP (not an authorization defect).
- `truth > 0 and client == truth`: Policy admits own rows — PASS.
- `truth > 0 and client < truth`: Policy denies own rows — FAIL (real authorization defect).
⭐ **The tell:** A probe whose failure message admits "got 0 — could be no data or policy denial". If the probe cannot tell them apart, it sends people to debug working RLS.

### AGGREGATE MAP LOOKUPS MUST TREAT ABSENT KEYS AS COUNT ZERO, NOT UNDEFINED-FALSE
**2026-09-05 (T315).** In `ClientManager.svelte:381`, `memberCounts[client.id] === undefined ? false : memberCounts[client.id] === 0` completely suppressed the `no portal access` indicator for unlinked clients.

Because unlinked clients had 0 rows in `client_users`, `counts[l.client_id] = (counts[l.client_id] ?? 0) + 1` never created an entry for them, leaving `memberCounts[client.id]` as `undefined`. Evaluating `undefined` as `false` meant only clients that had an explicit key with value 0 would trigger the marker—which could never happen from an additive loop over query rows.

⇒ **When aggregating counts from a junction table, an absent key represents count 0.** Distinguish "data failed to load" with an explicit loading state (`membersLoaded = true`), and evaluate count as `(memberCounts[client.id] ?? 0) === 0`.
⭐ **The tell:** A ternary `map[id] === undefined ? false : map[id] === 0` on an aggregated dictionary. If the aggregator only loops over existing rows, an absent key is the zero count.

### A FINANCIAL RECONCILER MUST REJECT AN EMPTY SET AS VACUOUS, NEVER PASS IT AS RECONCILED
**2026-09-18, T373 / T290.** A financial ledger reconciler comparing Stripe vs Supabase reported 0 mismatched records when both Stripe and the local database held zero shared transactions.

A naive loop over Stripe charges or database records trivially finds 0 discrepancies when the set is empty, giving a false sense of production billing parity.

⇒ **Enforce a 3-state exit contract for financial reconciliation:**
- Exit 0: All records match AND at least 1 verified live record exists.
- Exit 1: Record mismatch OR vacuous empty set (0 Stripe records and 0 DB records).
- Exit 2: Unmeasurable / missing dependencies / network error.
⭐ **The tell:** A reconciler that reports "0 errors, all 0 records matched" and exits 0 on a freshly initialized database.

---

### ⛔ A BACKUP THAT HAS NEVER BEEN RESTORED IS AN ASSUMPTION, NOT A BACKUP
**2026-08-18 (T229).** A 28 MB dump existed and read as safety. Restoring it into a scratch database
produced **965 errors**, and two of the causes were things **nothing anywhere recorded**: the dump
does not carry a `postgres` role (414 errors — Homebrew names the superuser after the OS user), and
it needs **pgvector**, without which the vector-bearing tables do not restore *at all* (342). Both
would have been met for the first time during a recovery, on a fresh host, under pressure.

⇒ **Exercise the recovery path, not the production path.** The artefact existing is not the claim;
the artefact *working somewhere else* is. Prerequisites discovered this way go into the tool's
preflight so the next person never re-derives them from wreckage.
⭐ **The tell:** "we have backups" with no record of anyone reading one back.

### ⛔ ASK WHAT EXECUTED — "LOOKS IDLE" AND "IS IDLE" ARE DIFFERENT CLAIMS
**2026-08-18 (T229).** A project everyone described as stale turned out to run a `*/5 * * * *` cron —
**81,052 runs over 9 months, 288/day, zero failures** — and to be the estate's *larger* database at
**57% of its plan cap**. The first signal checked, `last_autovacuum`, said "today" and **proved
nothing**: autovacuum runs on idle databases too. What settled it was `cron.job_run_details`, i.e.
asking what had actually *run*.

⇒ **Prefer an execution log to an activity-shaped signal.** Many signals move on their own; few
record work. Name which one you used.
⭐ **The tell:** a freshness timestamp offered as evidence of use.

### A CLEANUP MUST DELETE BY AN IDENTIFIER IT RECORDED AT CREATION — NEVER ONE IT DERIVES

Both halves of this failed on 2026-08-26, in opposite directions, from one root cause: the cleanup's
notion of *mine* was **derived** rather than **recorded**.

- **Over-deleting.** [[T281]]'s E2E teardown scoped by ADDRESS — every identity at a reserved domain.
  `@example.com` belongs to no real person, so the rule read as safe, and it deleted two fixtures
  created in **May** that the run had never made. An address identifies a **namespace, not an owner**.
- **Under-deleting.** Hours later the stage-2 suite leaked **26 rows into production** by recording
  its contract and project ids in an *assertion* step. Runs that acted and then failed before
  asserting never registered them. Its leads and proposals were cleaned, so the obvious rows were
  gone and the leak read as nothing at all.

🔑 **The rule: record the id at the moment you create the row, or derive it from a parent you
already own.** Not from a name, a title, an address, or a step that may not run.
⚠️ And a half-completed deletion must SAY so. T281's loop discarded every error and printed
`Purged 2 orphaned test identities` while two of them were still there, profiles gone and auth rows
alive — a state that cannot be retried into a good one.

### AN ADMIN ACTING FOR THE PLATFORM MUST NOT SUFFER SILENT ROLE DEGRADATION BY DOMAIN CONTEXT
**2026-09-03 (T310).** Accessing `cp.webomage.com` forced authenticated administrators into `effectiveRole = "member"`, completely hiding the Business console (Clients, Contracts, Projects, Invoices) and triggering member-scoped RLS.

The middleware hardcoded a role demotion based on domain suffix, conflating portal tenancy with operator identity.

⇒ **Preserve highest active operator credentials across domain boundaries.** If domain-based role scoping is applied to limit tenant views, administrative (`admin`) and owner principals must retain platform-wide capabilities unless explicitly choosing to act under a narrower persona or hat.
⭐ **The tell:** An administrator navigating to a control plane portal and seeing an empty dashboard or missing navigation sections because a hostname override silently stripped their privileges.

### A SELECTION SURFACE MUST ENUMERATE THE CATALOGUE, NOT PREVIOUS ASSIGNMENT ROWS
**2026-09-03 (T310).** The Control Panel project hat switcher rendered completely blank because it queried `public.hats` (which had 0 rows), preventing admins from wearing any hat.

Even though 13 units existed in `public.units` and active projects existed in `public.projects`, an admin could not put on a hat because the UI expected an existing assignment record before allowing selection.

⇒ **When designing universal assignment or role selection, query the canonical reference catalogue and auto-provision on wear.**
Admins allowed to wear "any hat on any project" must be presented with the catalogue of available units joined against projects, with wearing an unassigned unit automatically provisioning or activating the assignment tuple in `public.hats`.
⭐ **The tell:** An empty-state dropdown where a user with permission to assign or adopt any role cannot do so because no one has assigned it to them yet.

### CUSTOMER-FACING ROLES MUST BE DECOUPLED FROM INTERNAL AGENCY MATRIX UNITS
**2026-09-04 (T311).** Hats management in CP bound directly to internal agency matrix compensation grades (`public.units`), forcing delivery projects to display internal matrix titles (e.g. "Senior Fullstack Specialist IV") instead of customer-contracted functional positions (e.g. "Tech Lead" or "UI/UX Designer").

Internal seniority units track compensation, career progression, and matrix squads. Project delivery contracts specify functional delivery roles per engagement. Coupling them in the database schema forced missing roles (e.g. Designers) to have no representation and prevented projects from defining custom team rosters.

⇒ **Model functional customer delivery roles (`project_roles`) separately from organizational seniority grades (`units`).**
Bridge them through an optional minimum qualification or backing unit (`min_unit_id`), and let hats reference either or both.
⭐ **The tell:** A client or project delivery switcher whose options read like internal HR payroll grades rather than team roles.

### NEVER GRANT anon A BLANKET USING (true) ON A TABLE CARRYING SCOPED POLICIES FOR authenticated
**2026-09-14 (T254).** `authz-probe` flagged `AC4-blanket-beside-scoped FAIL` on `device_sessions`.

A migration added `CREATE POLICY "device_sessions_select_anon" ON public.device_sessions FOR SELECT TO anon USING (true);` alongside an existing tenant-scoped policy (`FOR SELECT TO authenticated USING (profile_id = wom_acting_profile_id())`). Because PostgreSQL permissive RLS policies combine with `OR`, adding a blanket `USING (true)` for `anon` completely dismantled row-level isolation for authenticated users—any caller can access the table anonymously or inherit permissive evaluation, turning scoped tenant boundaries into a no-op.

⇒ **In PostgreSQL RLS, permissive policies are OR-combined: an unrestricted policy for ANY role invalidates row isolation for ALL sibling policies on that command.** When `anon` must inspect rows (e.g. validating an active device token), scope the condition explicitly (e.g. `USING (revoked_at IS NULL AND expires_at > now())`) or split public tokens into a separate unprivileged table.
⭐ **The tell:** A table definition where one policy scopes by profile/tenant ID and another policy on the same action grants `TO anon USING (true)`.


## 2. Instruments

### ⛔ NEVER RUN BLANKET GIT RESETS, CHECKOUTS, OR WHOLE-TREE FORMATTERS IN A SHARED WORKTREE
**2026-09-27, T467. Multi-agent and human concurrent worktree safety.**

Running `pre-commit run --all-files` invoked the `oxfmt` hook across the entire monorepo, dirtying hundreds of untargeted files with automated formatting diffs. Attempting to back out of the cascade via `git reset HEAD && git checkout -- .` destroyed in-flight, uncommitted additions in `apps/cp/src/components/admin/ProjectManager.svelte` and `project/test-suites.json`. In a collaborative engineering workspace simultaneously inhabited by human developers, Claude Code, Antigravity, and background agents, blanket resets operate under a false single-tenant assumption and destroy uncommitted concurrent work without trace.

⇒ **All git discard, revert, and formatting operations in a shared worktree MUST be strictly surgical and file-scoped.**
- **Never execute blanket discards:** `git checkout -- .`, `git reset --hard`, or `git clean -f` at repo root are strictly prohibited.
- **Never run repo-wide automated formatters:** Do not run `pre-commit run --all-files` or full-tree formatting on a dirty or shared tree. Pre-commit hooks must run only on staged files (`pre-commit run`).
- **Audit before touching:** Run `git diff <file>` to verify ownership before touching or reverting any file in a dirty working tree.
- **Collaborative respect (T235):** Just as an agent must never commit another's in-flight work, it must never discard another's in-flight work.
⭐ **The tell:** Reaching for `git checkout -- .` or `git reset` to undo a tool-induced cascade (such as a linter/formatter). If a tool dirties files you did not touch, unstage or revert only the exact files the tool modified, never the entire tree.

### A SEARCH THAT LOOKED AT NOTHING ANSWERS EXACTLY LIKE ONE THAT LOOKED EVERYWHERE
**2026-09-20, T406.** `rg` at the estate root: **64 hits, 0.06s**. The same pattern, per repo:
**5,268**.

`@wom/.git/info/exclude` lists every `wom7*/` directory, so the root repo excludes its own members.
A grep there is fast, exits 0, prints a plausible handful, and is looking at **19 tracked files out
of 92,467**. Nothing in a diff can tell you — `.git/info/exclude` is unversioned. And the obvious
correction is worse: `--no-ignore-vcs` returns **462,277 hits in 5.8s** by walking `node_modules`.

The same session found the other half. The shape that actually costs minutes is not the working
tree (wom7web: **0.28s**) but **history**: 20 commits **4.1s**, 100 commits **17.5s / 379k lines**,
all 2,877 commits ≈ **8 minutes and ~11M lines** — a session stalled, then a buried console.

⇒ **The unit of search is a REPO, and history is always bounded.** `just search` does both, and
reports a repo it could not search as UNMEASURABLE rather than as zero hits.
⭐ **The tell:** a grep that returns *few* hits *fast* for a symbol you have every reason to believe
is widespread. Suspicion belongs on the small number, not relief. Corollary: `git --no-pager` is
load-bearing — on a tty `git grep` hangs on `less` until the agent's own timeout.

### ⛔ THE AUDIT TOOL USUALLY COMMITS THE DEFECT IT HUNTS — RED-PROBE IT BEFORE TRUSTING IT
**2026-08-13/14. Four separate gates, same session, same shape.**

- `callsite-drift`'s first run read **26 storage buckets** as ghost tables, then read a hoisted
  `const g = supabase.schema(…)` handle as an unqualified call — flagging **its own ticket's fix** as
  the bug it fixed.
- `lookup-index-gate`'s index regex anchored to end-of-string and parsed `WHERE (deleted_at IS NULL)`
  as the column list, reporting `posts.slug` as unindexed while its unique index sat right there.
  **Three of the four identifier indexes in this estate are partial**, so one regex made the whole
  report wrong.
- `debt-check`'s first run flagged **41 of 48** rows as stale because it matched every `T##` in the
  prose instead of the `Tracked` column.
- The `service-handlist` probe resolved `parents[2]` to `project/` and scanned **zero files**.

- `lookup-index` then raised **two more** false alarms on live code: `.limit(1).maybeSingle()` is
  safe *regardless* of uniqueness (the database cannot return a second row), and uniqueness is a
  property of a **filter SET**, never of one column — a query filtering a **superset** of a unique
  index reads at most one row. Judging columns independently reported a correct query as a latent
  500 because one of its four filters had no index of its own.

⇒ **Every gate ships with probes that prove it goes red, including probes for the false alarms it
already raised.** A gate nobody has watched fail is indistinguishable from one whose regex silently
stopped matching.
⭐ **The tell:** a first run whose hit rate is implausible in either direction. 41-of-48 is a broken
check; 0-of-everything is a broken corpus. Both mean *measure the measurer* before reporting.

### ⛔ A PROBE PINNED TO MUTABLE THIRD-PARTY DATA INVERTS ITS OWN SIGNAL
**2026-08-14, T182.** `state-bounds-test` asserted `by["artemio"]["verdict"] == "over"` — true the
day it was written, red five days later because **Artemio was rotated down to 50,850 B under its
81,920 B bound**. That is the gate *succeeding*, reported as the tool breaking.

The greener the estate got, the redder the probe went. The same file already carried the rule
(*"corpus assertions are read from the REGISTRY, never hardcoded"*) and had applied it only to the
project **set**, not to a **verdict**.
⇒ **Assert the gate's LOGIC against a fixture you construct, never the world's current state.**
The replacement declares a 1-byte bound on a synthetic project — nobody can turn it green by tidying
their own file.
⭐ **The tell:** a probe that names a real third party. If someone else's housekeeping can flip it,
it is measuring them, not you.

### ⛔ AN ADVISORY THAT CANNOT FAIL CANNOT ADVISE
**2026-08-14, T194.** `just drop-callers` reports 7 orphans and **exits 0**, so a hook written as
`just drop-callers || echo "⚠ …"` had a branch that could never execute.

⇒ **When you absorb a failure with `||`, check the command actually produces one.** The fix was
`--enforce` (so the exit code means something) *plus* the `||` (so it stays non-blocking) — two
separate decisions that look like one.
⭐ **The tell:** a warning nobody has ever seen printed.

### ⛔ AN EMPTY CORPUS MUST FAIL, NEVER PASS
**2026-08-13/14, T69 and T138.** A probe that scanned nothing printed a clean pass.

⇒ **Every scanner asserts its input is non-empty before reporting on it**, and says so loudly:
*"parsed 0 — fix the parse; do not read this as 'no drift'."*
⭐ **The tell:** a check that got *faster* and *greener* at the same time.

### ⛔ A CEILING IS NOT A LEVEL — READ THE SEMANTICS BEFORE CHANGING THE SETTING
**2026-08-14, tools-policy.** `gh` sat at `auto: "minor"` and 2.97.0 looked uncaught.

`auto` is the **maximum** bump auto-upgrade may apply, not the exact one: `minor` already permits
2.96.0 → 2.97.0. Nothing needed changing — `tools-outdated` already listed it AUTO. The real gap was
that **`tools-upgrade` is dry-run by default and nothing schedules it**.
⚠️ Its docstring also claimed *"never major"*, which is **false** — `ALLOW_RANK` admits major and
`gcloud` is configured that way.
⇒ **When a config looks wrong, read its definition and its implementation before editing it.**
⭐ **The tell:** "declared X" and "X happens" being assumed to be the same statement.

---

### ⛔ A CROSS-INSTANCE COMPARATOR MUST BE FREE OF ZONE, LOCALE AND ORDERING
**2026-08-18 (T229).** Comparing a restored database against live with `row::text` reported **every
table corrupt — twice, for two different reasons, and it was wrong both times.** First the local
session was `America/Cancun` while the server rendered UTC, so the same instant printed differently.
Then, with UTC pinned, `lc_ctype` quoted multi-byte characters differently and the *entire*
difference across two rows was `🧠` versus `"🧠"`. `to_jsonb(t)::text` — sorted keys, JSON escaping —
matched immediately.

⇒ **Before believing a diff, ask what else could make two identical things render differently.** A
check that had stopped at its first red would have condemned a working backup.
⭐ **The tell:** *everything* differs. Real corruption is usually narrow; a total mismatch is
usually the comparator.

### ⛔ VALIDATE WITH THE READER YOUR CONSUMERS USE, NOT A MORE FORGIVING ONE
**2026-08-18 (T229).** Adding `//` comments to `.w0m/sdlc.json` broke it for **33 consumers** that
call plain `json.load` — the file is strict JSON carrying `"_comment"` *string* keys, not JSONC. The
change passed my own check because that check **stripped comments before parsing**: I verified the
file against a tolerant reader while every real consumer used a strict one.

⇒ **A green check proves what the checker looked at, never what the consumers will do.** Parse a
config exactly as the code that loads it does — and read what is already in a file before adding a
syntax to it.
⭐ **The tell:** a validator that pre-processes the artefact it is validating.

### `SET LOCAL ROLE` OUTSIDE A TRANSACTION IS A NO-OP, AND THE PROBE STILL PRINTS AN ANSWER

Measured 2026-08-26. A live spot-check of what `anon` could read reported confidently — and
`current_user` had stayed `postgres` the whole time, because `SET LOCAL` needs an explicit
`BEGIN`. The numbers were real; they described the superuser. One reading appeared to show a client
able to see all 96 contracts, which was alarming and false.

🔑 **Assert the actor before trusting anything read under it.** One line —
`select current_user || ' as ' || wom_acting_role()` — separates "the client sees this" from "the
superuser sees this", and nothing in the output distinguishes them otherwise.
⚠️ Same family as the RLS-policy trap it was used to investigate: a policy whose subquery is itself
RLS-filtered matches NOTHING and reads perfectly correct. Both are answered the same way — read a
row back **as the actor**, never inspect the rule.

### SYNTHETIC COMPACTION DIRECTIVES IN THE USER CHANNEL MIMIC ADVERSARIAL INJECTIONS
**2026-09-09, session 5feca02b.** Context compaction triggered a synthetic turn demanding "CRITICAL: Respond with TEXT ONLY... Tool calls will be REJECTED...". The agent classified it as an in-flight prompt injection attack and refused to summarize, polluting subsequent compaction states with adversarial warnings.

⇒ **Harness lifecycle directives (compaction, summarization) must be recognized as harness protocol, not adversary input.** An agent must inspect message origin metadata before triggering injection defenses on imperative harness commands; conversely, harnesses must not format compaction triggers as user-channel text coercion.
⭐ **The tell:** An agent warning about "urgent all-caps text-only prompt injection" immediately preceding or following a `Conversation compacted` boundary.

### TRANSPARENT CLI COMPRESSION PROXIES ON SHARED PORTS SILENTLY MUTATE TOOL STREAMS
**2026-09-09, session 5feca02b.** Headroom compression proxy running on a local port colliding with a `wrangler cfworkers` app intercepted `git log`/`git show` and returned lossy summaries (`[N words compressed to M... retrieve more: hash=...]`), mimicking repository or hook tampering.

⇒ **Never run lossy compression proxies transparently across CLI tools without isolated ports and strict bypass rules.** When tool output format changes without an environment or repo change, verify whether a local background daemon/proxy is rewriting standard streams before debugging git or scripts.
⭐ **The tell:** Standard CLI commands (`git log`, `git show`) returning nonstandard truncation or paraphrasing while other shell commands return raw output.

### A `nosemgrep` SUPPRESSION MUST NAME THE EXACT RULE ID — FREE TEXT IS SILENTLY IGNORED
**2026-09-10, T325.** Semgrep blocked a commit on `python.lang.security.audit.dynamic-urllib-use-detected` for a dynamically-built URL. A first fix added a real mitigation (validate the scheme before opening) plus `# nosemgrep: scheme validated above` — and the commit was blocked again, unchanged. Only replacing the comment text with the finding's full, exact rule ID suppressed it.

⇒ **`nosemgrep` is a pattern match on the rule identifier, not a human-readable waiver.** Free text in the comment is not an error and not a warning — it is silently treated as not matching, so the finding still fires and the mistake looks identical to "I forgot to suppress it" until you diff the two attempts. Pair every suppression with a real mitigation first; this repo had zero prior `nosemgrep` precedent to copy from.
⭐ **The tell:** a `nosemgrep` comment that still gets blocked on retry — check it echoes the finding's rule ID character-for-character, not a description of why it's safe.

### A CO-TENANCY GUARD THAT ONLY KNOWS DECLARED PATHS IS BLIND TO A HOOK THAT STAGES ONE FOR YOU
**2026-09-12, T345/T346/T348 (three times in one session).** Three separate commits each swept in
another agent's brand-new, untracked `project/tickets/T##.md` — content on disk was always correct
(the other agent's real work), the problem was that *my* commit now claimed authorship of it. Each
time the fix was the same follow-up commit: `git rm --cached` to untrack it again, leaving the
working tree untouched. `stage_guard.py` (T235 AC9) — the hook that exists specifically to catch
"work this agent did not do" — passed clean every time.

It passed because its two checks are both structurally blind to this shape: the co-tenancy registry
(`project/co-tenancy.json`) only flags **paths declared in advance**, and nobody pre-declares "any
ticket file I didn't write" as a co-tenant path; the `lsof` live-write-handle check only catches a
file **currently open for writing**, not one the other agent already wrote and closed moments
earlier. The actual staging happened one layer downstream of both checks: pre-commit's own
"Refresh ticket frontmatter" and "Refresh w0m status dashboard" hooks read **every** `T##.md` present
in the working tree — tracked or not — to regenerate derived fields/the dashboard JSON, and staging
whatever they touch is exactly what makes a lint-staged-style fixup hook useful for your own files.
Applied to a shared `project/tickets/` directory with other agents writing into it concurrently, the
same mechanism silently annexes their in-progress files into whoever happens to commit next.

⇒ **A guard against "not my work" must reason about the *file*, not just the *path*.** A path-based
registry can never anticipate a file that didn't exist yet when the registry was written; the
guard needed a check closer to "was this file untracked one second ago, and did *my* diff create
it" — not "is this exact path on a pre-declared list."
⭐ **The tell:** `git commit` succeeds, `stage_guard`/T235 prints clean, and the resulting commit's
`--stat` still lists a `project/tickets/T##.md` you never wrote. Check `git show --stat HEAD`
against what you actually staged, every time a ticket-adjacent hook ran — a clean guard is not
proof the diff is yours.

### MIDDLEWARE URL/HOSTNAME LOGIC MUST BE VERIFIED AGAINST A REAL DEV RUNTIME, NOT SYNTHETIC URL OBJECTS
**2026-09-12 (T220/T221, delivery/artemioquierocomer.mx).** T208 added an `http:` → `https:` 301 redirect in `src/middleware.ts` with a `localhost`/`127.0.0.1` exemption, validated only by unit tests passing hand-built `URL` objects. The unit test stayed green for two tickets. But `wrangler.jsonc` declared a `custom_domain` route, causing `wrangler dev --local` to rewrite the `Host` header and `url.hostname` to the production domain on every local request. The `localhost` exemption never matched locally, and every preview request 301-looped forever until caught by local E2E.

⇒ **When middleware branches on request URL, hostname, or protocol headers, verify against an actual running server instance.** Synthetic `URL` unit tests prove internal function logic, but cannot prove what headers or hostname the platform dev server injects.
⭐ **The tell:** Routing or redirect unit tests are 100% green, but running `just preview` or local E2E against the real dev server hangs in an infinite 301 redirect loop.

### SCOPE PLAYWRIGHT LOCATORS TO CONTAINERS WHEN INTERACTIVE ELEMENTS ARE DUPLICATED IN DOM
**2026-09-12 (T222, delivery/artemioquierocomer.mx).** An unscoped `page.locator('button:has-text("..."), ...').first()` timed out after 30 seconds during an E2E run. Both the Hero section and the sticky `UnifiedTopBar` rendered duplicate copies of the language switcher simultaneously, toggling visibility via CSS opacity and `pointer-events-none`. Because the inert copy preceded the interactive copy in DOM order, `.first()` selected an unclickable element.

⇒ **Scope locators to the specific active container rather than relying on DOM-order selectors (`.first()` / `.last()`).** When components keep inactive instances in the DOM for smooth CSS transitions, target the parent container holding the interactive instance (e.g. `#active-header button`).
⭐ **The tell:** A Playwright click times out after 30s on an element that visually appears visible and interactive on screen.

### PLAYWRIGHT getByRole('button', { name }) SUBSTRING MATCHES BY DEFAULT — USE EXACT MATCHING
**2026-09-12 (T223, delivery/artemioquierocomer.mx).** `page.locator('#section-menu').getByRole('button', { name: "Delete" }).first()` unexpectedly clicked "Delete Category" instead of "Delete" (the item delete button). In Playwright, `name: "Delete"` performs case-insensitive substring matching unless `{ exact: true }` is passed. Because `<Button>Delete Category</Button>` appeared earlier in the DOM tree, `.first()` matched the compound button, opening the category deletion modal and failing downstream assertions.

⇒ **Always supply `{ exact: true }` (or an anchored regex `/^Delete$/`) when matching short generic button labels ("Delete", "Add", "Edit") where compound buttons exist.**
⭐ **The tell:** An action button opens a modal or initiates an action with unexpected scope or parameters (e.g. category-level modal instead of item-level).

### HEADLESS MERMAID VALIDATION PREVENTS SPEC AND DIAGRAM ROT WITHOUT BROWSER OVERHEAD
**2026-09-12 (T213, delivery/artemioquierocomer.mx).** Loose `.mmd` files in `docs/` and wikilink syntax in Obsidian MOC notes broke Mermaid parsing (`Expecting 'SPACELINE', 'NL', 'EOF', got 'NODE_ID'`). Concurrently, specs concatenated multiple diagrams with `---` dividers in a single file, breaking downstream parsers.

⇒ **Validate Mermaid syntax headlessly via `mermaid.parse` over jsdom in static quality gates (`just lint-mmd` / `mmd-validate`).** Keep single diagrams per `.mmd` file or embed inside standard markdown fences with valid identifier quotes.
⭐ **The tell:** Markdown preview or Obsidian displays raw red parse error blocks on system architecture diagrams.

### DO NOT EMIT EMOJI VARIATION SELECTORS (\uFE0F) IN AUTOMATION SCRIPT OUTPUT
**2026-09-14 (T207).** `just emoji-check` broke pre-commit on a new verification script emitting an info glyph with a variation selector.

`project/scripts/ds_conformance.py` included a print line formatted with an informational glyph. In Unicode, the standard information symbol `\u2139` followed by variation selector-16 `\uFE0F` forms an emoji presentation. While protocol glyphs like plain `i` or standard checkmarks are parsed as allowed protocol markers in specific tools, unmanaged variation selectors are classified as pictographs under `project/scripts/emoji_policy_check.py`, tripping the zero-tolerance ratchet.

⇒ **Use plain ASCII status tags (`[INFO]`, `[WARN]`, `[FAIL]`, `[OK]`) in tool outputs, never terminal emoji.** When a visual symbol is required by protocol parsers, verify it matches the exact code point declared in `project/emoji-policy.json` without trailing variation selectors (`\uFE0F`).
⭐ **The tell:** A script printing what looks like a benign info badge or warning failing git pre-commit with `ratchet baseline exceeded`.

### STATIC NAVIGATION AUDITORS MUST PARSE SCRIPT DATA STRUCTURES, NOT ONLY TEMPLATE href ATTRIBUTES
**2026-09-14 (T207).** `cp-nav-check` reported false-positive orphaned pages across the client control plane.

`cp_nav_policy_test.py` parsed Astro template markup for literal `<a href="...">` attributes. In `ClientLayout.astro`, navigation links were declared in a frontmatter data array (`const navItems = [{ href: '/cp/client/contracts', ... }]`) and rendered dynamically via `{navItems.map(...)}`. Because the AST regex only inspected markup attributes, every client portal page was flagged as an unlinked orphan, threatening the `--enforce` gate.

⇒ **Static navigation and route checkers must inspect both AST/template attributes AND frontmatter data arrays (`navItems = [...]`).** When components separate navigation data from presentation, the policy parser must resolve both surfaces before concluding a route is dead or unlinked.
⭐ **The tell:** A page visibly clickable and rendered in the browser navigation menu, but flagged as an unregistered orphan by static policy audits.

### A TOOL POINTED AT THE WRONG ROOT DOES NOT FAIL — IT RETURNS A CONFIDENT WRONG ANSWER
**2026-07 through 2026-09-15 (T190), four occurrences of the same shape.** None of these tools
crashed or errored. Each ran cleanly, against the wrong directory, and reported a plausible result.

- **`@wom/.serena/project.yml`** ([[D32]]/[[T172]]) — a session rooted at the `@wom` umbrella
  activates the workspace-root serena config, not the per-repo one, with its own language set;
  symbol results came back prefixed `@wom/…` instead of the repo name, and nothing said so.
- **`just skill check` run from `wom7api`** (during [[D42]]) — produced a *false* "several unmanaged
  skills" claim, since retracted, because it was reading `wom7api`'s tree while the manifest it
  should have compared against lived in `wom7web`.
- **`just skill relock`** run from a repo with no `.w0m/skills.json` — instead of refusing, it
  **created** an empty manifest and lockfile and printed `lockfile re-hashed.`, a success message
  for an operation that governed nothing (reproduced live from `wom7api` during D42's own fix;
  fixed under T190 AC1/AC4).
- **The estate root before [[T232]]** — `@wom/.agents/skills/` held 23 real, tracked skills while
  every governance tool reported clean, because `skill check` was scoped to `wom7web/.claude/skills`
  and `skills-sync check` only ever wrote there; neither tool had a notion of the level above it.

⇒ **A tool that resolves "which project/root am I checking?" implicitly will eventually check the
wrong one, cleanly, and say so with a straight face.** The fix is never "trust it more" — it is
making the resolved root part of the printed output (`w0m skill check`'s `[project scope: <path>]`
line, adopted after this pattern's third occurrence) and, where the tool can invent state instead
of refusing, making the manifest-less case a hard refusal rather than a silent bootstrap.
⭐ **The tell:** a governance/audit tool that has never once printed which directory it resolved to
before reporting on it.

### A GATE MATCHER MUST INSPECT EXECUTABLE CAPABILITY, NOT RECIPE SYNTAX
**2026-09-17 (T240).** `run_suites.py --drift` matched on recipe names (`-check|-test`) and body text (`--enforce|--check|--drift`), reporting 0 undeclared while 12 gates were invisible because they used standard argument forwarding (`*args:` / `{{args}}`).

The recipe forwards CLI flags to an underlying script whose `argparse` or `sys.argv` declares the `--enforce`, `--check`, or `--drift` capability. Text matching on the recipe body only sees the `{{args}}` placeholder, producing a vacuous green report.

⇒ **When discovering gates behind forwarding wrappers, inspect target script parameters (argparse / sys.argv capability), not recipe shell syntax.**
⭐ **The tell:** A recipe defined as `<gate> *args:` whose body delegates via `{{args}}` without literal flag strings.

### A "RE-MEASURE EVERYTHING" PIPELINE MUST VERIFY ALL OUTPUT ARTIFACTS WITH A RED PROBE
**2026-09-17 (T205).** `authz-remap` advertised re-measuring the entire authorization surface and regenerating every map, but silently omitted `office_caps.json` and `all_caps.json`. The stale snapshots showed `devops` holding both `deploy.approve` and `deploy.execute` (a false separation-of-duties violation) even after database migrations had renamed the office to `tech.ops` and decoupled the capabilities.

A pipeline that produces multiple output artifacts without asserting each one's existence and recency provides false confidence ("vacuous-green").

⇒ **Every multi-artifact mapping pipeline must be accompanied by an offline integrity probe suite that verifies every declared artifact is generated and fails closed if any output is missing or stale.**
⭐ **The tell:** A pipeline recipe that claims broad coverage but has no test checking that each downstream consumer artifact is written on each run.

### CLI WRAPPERS FOR DESKTOP ORCHESTRATORS MUST NORMALIZE PROMPT INJECTION FLAGS
**2026-09-17 (Orca Opencode integration).** Orca launches agents configured with `promptInjectionMode: 'flag-prompt'` by passing `--prompt "<query>"`. When invoking Claude Code as the underlying engine, Claude Code rejected the flag with `error: unknown option '--prompt'`, silently breaking agent startup from worktree cards and prompt dispatch buttons.

⇒ **Intermediary CLI wrappers between IDE orchestrators and underlying AI agents must normalize orchestrator-specific command-line arguments (e.g., converting `--prompt` to positional arguments or `--prefill`).**
⭐ **The tell:** An agent launching successfully from a bare terminal but failing or erroring on unrecognized flags when triggered from an IDE card or popup button.

### PROCEDURAL TEST SCRIPTS MUST BE RUN IN SUBPROCESSES UNDER PYTEST COLLECTORS
**2026-09-18 (T376).** Migrating 86 test scripts to a pytest runner caused immediate `INTERNALERROR SystemExit` when importing scripts calling top-level `sys.exit()` directly in-process.

When a repository contains legacy procedural test scripts alongside native test classes/functions, importing the procedural scripts into pytest's process causes top-level `sys.exit(0)` or `sys.exit(1)` to abort pytest collection prematurely.

⇒ **In pytest collection hooks (`pytest_pycollect_makemodule`), inspect file ASTs to partition procedural scripts from class/function test modules. Wrap procedural scripts in custom `pytest.Item` collectors that execute them in isolated subprocesses (`subprocess.run`), capturing stdout/stderr and mapping exit codes cleanly to pytest pass/fail states.**
⭐ **The tell:** `pytest` aborting collection with `INTERNALERROR` pointing to `SystemExit` from a procedural script's top-level execution.

### NEVER RUN A SECRET-STORE LIST COMMAND — EXISTENCE CHECKS MUST USE A GETTER, NOT A TABLE DUMP
**2026-09-19 (T201).** While checking only whether `CLOUDFLARE_API_TOKEN` existed before a guarded Turnstile-secret retrieval, `infisical secrets --env=beta --silent | grep -i "cloudflare"` was run to narrow the output. `infisical secrets` is a **list** command — it prints every secret's plaintext **value** in its table by default, with no masked mode. The `grep` only filtered which *rows* appeared; every matching row still carried the full value, so `CLOUDFLARE_API_TOKEN` and `CLOUDFLARE_ACCOUNT_ID` were printed in full into the tool output and the conversation transcript. Piping a value-bearing command through a filter does not make it existence-only — the value was already captured before grep ever ran.

⇒ **To check whether a secret exists, capture the getter's output into a shell variable and pattern-match it — never let the raw output reach anywhere it gets printed, and never trust the exit code.** `infisical secrets get NAME --env=<env> --silent` **always exits 0**, whether the key exists or not (verified 2026-09-19) — `>/dev/null 2>&1; echo $?` reports "success" unconditionally and tells you nothing. The actual signal is in the table body: `out=$(infisical secrets get NAME --env=<env> --silent 2>&1); echo "$out" | grep -q '\*not found\*' && echo missing || echo present; unset out` — this only ever prints the derived boolean, never `$out` itself. A list command is for a human looking at their own terminal, not for a command whose stdout is captured into an agent transcript. Any secret whose value has entered a transcript this way must be treated as compromised and rotated at its source (e.g. Cloudflare dashboard → API Tokens), not merely stopped from being reused.

⭐ **The tell:** reaching for a `grep`/`awk` filter on top of a store's `list`/`env`/`secrets` command to "just check for one name" — the filter narrows rows, not the value already inside them. Also: trusting a CLI's process exit code to mean "found" without first proving it returns nonzero on a deliberately-fake key.

### A RELOCATED SCRIPT ACCESSED BY PROBE AST/READ_TEXT MUST BE A SYMLINK, NOT A PYTHON SHIM
**2026-09-20 (T412).** Relocating `sync_github.py` from `wom7web/project/scripts/` to root `@wom/scripts/` and replacing the original with a Python forwarding wrapper (`from scripts.sync_github import main`) caused `just board-identity-test` to fail.

Probes like `test_board_identity.py` assert invariants by reading the script's raw text (`(SCRIPTS / "sync_github.py").read_text()`) or parsing its AST, rather than executing its `main()`. A forwarding shim satisfies execution callers (`subprocess.run`), but breaks static source/AST inspections which see only the forwarder stub.

⇒ **When relocating scripts or configs across monorepo boundaries while preserving legacy caller paths, use relative filesystem symlinks instead of language-level forwarding wrappers.** Symlinks are transparent to both code execution and filesystem/AST readers (`read_text()`), ensuring zero behavioral or probe divergence.
⭐ **The tell:** A CLI command works when invoked, but a test asserting its internal strings or AST structures fails with missing declarations.

### ATTACH @deprecated TO THE ALIAS, NEVER TO THE REPLACEMENT SYMBOL
**2026-09-20 (T327).** In `apps/cp/src/lib/supabase.ts`, introducing `export const staffAdminClient = adminClient();` and deprecating the legacy `supabase` export by placing `/** @deprecated ... */` above `staffAdminClient` caused `astro check` to raise `ts(6385): 'staffAdminClient' is deprecated` when defining `export const supabase = staffAdminClient;`.

TypeScript applies JSDoc tags to the immediate subsequent identifier declaration. Deprecating the new symbol warns on the assignment within the very file providing the transition alias, while leaving the legacy alias unflagged.

⇒ **Always place `/** @deprecated ... */` directly above the legacy symbol being phased out (`export const supabase = ...`), never above the canonical replacement (`staffAdminClient`).** This provides instant IDE and typecheck hints to existing callers while keeping the new canonical export clean.
⭐ **The tell:** Typechecker warnings flagging the new replacement symbol as deprecated instead of the legacy export being phased out.

### HOST SECURITY INSPECTION MUST FAIL CLOSED ON PERMISSION DENIAL — NEVER CONFUSE "CANNOT READ" WITH "CLEAN"
**2026-09-20 (T233).** Auditing macOS TCC permission grants (`TCC.db`) requires Full Disk Access (FDA) for the runner process. If the runner lacks FDA, sqlite queries on `~/Library/Application Support/com.apple.TCC/TCC.db` throw permission errors.

Catching the exception and returning an empty list of apps holding high-privilege entitlements (camera, microphone, screen recording, FDA) turns a hard blind spot into a false clean report. An unprivileged rogue process running the posture check would proudly report zero sensitive entitlements granted.

⇒ **When a system-level audit query cannot read protected state due to OS permissions or sandboxing, fail closed to `NOT MEASURED` (or exit 2 / error), never to empty results or `PASS`.** Always explicitly surface why the dimension could not be evaluated and what entitlement is missing, adhering strictly to T96 AC3 ("a check that did not run is not a check that passed").
⭐ **The tell:** An exception handler around a sensitive inspection command returning `[]` or `status: PASS` with detail "0 findings".

### ⛔ A GATE SCOPED TO "PUSHES THAT TOUCH X" IS BLIND TO A CHANGE APPLIED FROM ANOTHER REPO — ADD A SCHEDULED FULL RUN
**2026-09-29, T497.** The authorization probes run on a push only when it touches `supabase/migrations/|authz-|policies`. T465's
migration re-created four admin/manager policies as *possession* tests on 2026-09-26 21:00, and the probes were **RED with 98
violations for three days** (an admin who narrowed to the member hat read every contract again) because every push in between was a
wom7web push that touched none of those paths, and a migration lives in wom7api. The last full run before the regression was 09-26
09:16. It surfaced only when an unrelated push happened to carry an `authz-` path.

⇒ **A path-scoped gate needs a second trigger that does not depend on the path:** a scheduled full run (the daily audit already
exists) or a run on the *applied* migration. Scoping saves 49 s per push; it must not convert "checked on every change" into "checked
when someone happens to touch the right file".
⭐ **The tell:** a gate whose trigger is a file-path filter, over a surface (the live database) that other repos and other people
change. Ask "when did this last run in full?": if the answer is a date, not "today", the scope is hiding drift.

### ⛔ WHEN A MIGRATION REWRITES A FAMILY OF POLICIES, COPY THE PATTERN THAT WAS RIGHT — AND PROBE EVERY MEMBER, NOT ONE
**2026-09-29, T497.** T465 rewrote five policies in one file. `client_milestones` was written as
`wom_jwt_is_aal2() and wom_acting_in('admin','manager')` (the WORN hat, correct); `contracts`, `projects` (x2) and `project_roles`
were written as `is_admin() or exists(user_roles ... role in (...))` (possession, which T198 D2 had already removed, and which
defeats the hat because policies are OR-ed). Only `contracts` had a probe, so three of the four regressions were silent. The
template for the fix was one file away, in the same migration.

⇒ **Rewriting N sibling objects: diff the N against each other before commit, and probe all N.** A probe on one member proves that
member only.
⭐ **The tell:** a migration that touches several tables' policies and a probe suite that names one of them.

### ⛔ A "MY DATA" PAGE MUST FILTER ON THE CALLER'S OWN PROFILE — RLS ALONE LISTS EVERYONE'S TO AN ADMIN
**2026-09-29, T493.** `/me/upwork/proposals` read `proposals` through the user session, and the `proposals_member_own` policy looked
sufficient. Run as `w0m@` (an admin) the same query returned all **1,782** of another person's proposals, because admin policies are
OR-ed in. A page that trusts RLS to mean "mine" is correct for a member and wrong for the one user most likely to look.

⇒ **Filter `profile_id = <caller's profile>` explicitly on every `/me` data query, fail closed when there is no profile, and test it
with the ADMIN identity, not the member's.** `me-pages-own-rows.test.ts` fails if a `.from()` on those pages lacks the filter.
⭐ **The tell:** a member-facing query verified only by signing in as a member.

### ⛔ A PROBE'S EXCEPTIONS BELONG IN A DECLARED FILE THE PROBE READS — AND THE DECLARATION NEEDS ITS OWN GUARDS
**2026-09-29, T497 (G3).** `G3-views-security-invoker` went RED on `public.public_team_members` (T470), a *deliberate* definer view
(an invoker view would empty the public roster once T198 dropped anonymous SELECT on `team_members`). The probe could not express a
deliberate exception, and its own message named a different view. The fix is `project/authz-public-views.jsonc`: the probe reads it
(no second copy, the F1 lesson), `G3b` fails when a declared view is gone (a list of things that used to be true), `G3c` fails when a
declared view exposes an email-, phone-, token- or secret-shaped column, because a definer view is closed only by its column list.

⇒ **An allowlist without a stale-entry check and a content check is a hole with a paper trail.**
⭐ **The tell:** an exception added by editing the probe's SQL, or by deleting the probe.

### A RATCHET THAT COUNTS ONE SPELLING OF A THING MISSES THE OTHERS — DETECT THE THING, PROBE EACH SPELLING
**2026-09-29, T457.** The admin-client ratchet counted importers of the shared singleton and reported 11. The same RLS-bypassing client
was also built inline (`createClient(url, serviceKey)`, 11 files), through the sanctioned factory (`adminClient()`, 21 calls), and
behind silent fallbacks (`serviceKey && …`, 6 sites in 4 files), none of which the ratchet saw. Its own first version then had a bug:
`\bSERVICE_ROLE_KEY\b` does not match inside `SUPABASE_SERVICE_ROLE_KEY`, because `_` is a word character. The red probe caught it.

⇒ **Name each construction shape as its own counted set with its own limit, and give every spelling a fixture that must fire.** A
detector that "found nothing" on a spelling it was never shown is silent, not clean.
⭐ **The tell:** a count that fell to zero after a refactor that only renamed a variable. And any `\b` around an identifier that can sit
inside a longer one.
 
### ⛔ GAUGE STEP MODULES EVALUATE EAGERLY AT STARTUP — WRAP ENV READS & CLIENT INIT IN LAZY GETTERS
**2026-09-30, T507.** Running `gauge validate specs/web/goldens.spec` or running local visual smoke tests threw `Error: [urls] SUPABASE_URL / PUBLIC_SUPABASE_URL is not set` and crashed before running any test step.

Gauge ts-node loads and compiles *every* `.ts` step definition file in `tests/` upon startup regardless of which `.spec` was specified. Evaluating `supabaseBase()` or initializing client SDKs at top-level module scope causes innocent, decoupled test suites (like visual golden image audits) to fail whenever Supabase environment variables are absent.

⇒ **All environment-dependent endpoints, URLs, and external client factories inside test step files MUST be encapsulated in lazy getters or inside step hooks, never evaluated at module top level.**
⭐ **The tell:** A test suite crashing with missing environment variables for a service that the spec under test never uses.

### ⛔ A LESSON THAT LIVES ONLY IN THIS FILE DID NOT STOP THE REPEAT: TURN IT INTO A GATE
**2026-10-06, T546 and T549. Bit twice in three days.**

The T531 lesson ("a suite recipe must be visible from `wom7api/`") was written on 2026-10-04. Two days later a different agent registered the `tools-upgrade` suite with its recipe only in the root justfile. `just suites-drift` said **"0 undeclared"** (it reads declarations, not resolution), the suite's own test passed, and the full `test` tier then reported `🚫 0 check(s) — recipe not found`, a blocking failure, at deploy time. The same suite also printed no `✅`/`❌` lines, so `run_suites.py` counted its checks as `?`.

⇒ **A rule an agent has to remember is a rule the next agent will not.** When a lesson names a mechanical check ("run `cd wom7api && just --show <recipe>`"), the check belongs in the gate that already runs (here, `suites-drift` must resolve every registered recipe the way the runner does, T549), not in prose.
⭐ **The tell:** a gate that says "0 problems" about a registry while the runner that consumes the registry says "not found". Two readers of one registry that resolve it differently.
⚠️ Query before you write: `just lessons <topic>`. Add the recurrence to the existing entry; do not start a second one.

### ⛔ A TEST THAT READS GIT STATE MUST PASS IN AN AGENT TREE, NOT ONLY IN THE LIVE CHECKOUT
**2026-10-06, T503.**

`test_tasks_render.py` asserted that ticket links match `.../blob/[^/]+/.tasks/T\d+.md`. An agent tree is on branch `agent/<name>` (AgDR-0032), so the branch segment contains a slash and the check failed, which made `py-test` (a blocking suite) red in **every** agent tree while it passed in the live root. It surfaced only when a tree ran the full suite.

⇒ **Anything a test learns from `git` (branch, remote, HEAD, path under `~/.w0m/work`) must hold for the agent-tree shape**: a slash in the branch, a different root, no `node_modules`, a detached HEAD in a release worktree. Run the suite once in an agent tree before landing a change to such a test.
⭐ **The tell:** a test green in the live checkout and red in a tree, or a regex with `[^/]+` over a branch name.

### ⛔ BEFORE REPORTING A DEFECT, RE-RUN IT THE WAY THE REPO'S OWN RECIPE RUNS IT, AND RETRACT IN THE SAME MESSAGE
**2026-10-06.**

An agent ran `npx vitest run src/auth/middleware.spec.ts` from `wom7web/packages/lib`, saw "cannot find astro:middleware", and reported a pre-existing broken suite through several summaries. From the workspace root (where the repo runs it) it passes 5/5. The failure was the invocation.

⇒ **Name the working directory and command with every "X is broken" claim, and reproduce it the repo's own way (`just <recipe>`, or from the root) before it leaves your hands.** If a re-run disagrees with something you already said, retract it in that message, not three messages later.
⭐ **The tell:** an import or module-resolution error for a virtual module (`astro:*`, a workspace alias) when you are not at the root.


## 3. Deploys and platforms

### ⛔ SERVE `.svg` WITH `<img>`, NEVER ASTRO'S `<Image>`
**2026-06-11.** SVG logos rendered as broken images on Cloudflare Pages.

Astro's `<Image>` routes through Cloudflare's image service (`compile`), which does not parse vector
SVG. *(Carried over from the previous `.agent/LESSONS.md`, rewritten into this format.)*

### ⛔ DEV CONFIG THAT DISAGREES WITH PROD IS A BUG IN DEV, NOT A CONVENIENCE
**2026-08-14, T134.** The admin CP had **never** been loggable locally.

`apps/cp` set `base: NODE_ENV === 'production' ? undefined : '/cp'`. The shared auth middleware
matches **absolute** paths (`pathname.startsWith("/api/auth")`), and Astro hands middleware the
base-prefixed pathname — so in dev the auth callback arrived as `/cp/api/auth/callback`, failed every
predicate, and **the login endpoint sat behind the login gate**. Measured: `/api/health` 200 vs
`/cp/api/health` 401.
⇒ **A dev-only prefix, port or host must be tested against every path predicate it changes.**
⭐ **The tell:** a fresh credential failing at the callback. That reads as expiry and is often routing.
⚠️ `demo`, `job` and `join` still carry the identical pattern.

---

### ⛔ READ THE ERROR BODY BEFORE BLAMING THE CREDENTIAL — A 403 CAN BE THE EDGE
**2026-08-18 (T229).** A script hitting the Supabase Management API died `403 … error code: 1010`
while **curl with the same token succeeded in the same second**. `1010` is Cloudflare **bot
detection**: `urllib` sends `Python-urllib/3.x` and the edge rejects it. My first error message
blamed the PAT — which would have recreated [[T67]] exactly, where a recorded "revoked, 403" claim
sent later sessions around a token that had been working for weeks.

⇒ **A recorded breakage has no expiry, so never write one you have not proven.** When an auth-shaped
status appears, reproduce it with a second client before concluding anything about the credential.
⭐ **The tell:** a 401/403 that only one client sees.

### TART RPC OVER GUEST AGENT BYPASSES HOST NETWORK, WHEREAS GUEST IP/SSH TRAFFIC HANGS IN HOST WARP/VPN ROUTING
**2026-09-10, T295 / T297.** `nc -zv 192.168.64.56 22` failed with `No route to host` on macOS because Cloudflare WARP (`utun4`) and `bridge100` routing swallow or drop guest IP traffic.
At the same time, `tart exec` via the Tart Guest Agent connected instantaneously and reliably. The guest agent communicates over the hypervisor's virtio-serial port (`/dev/virtio-ports/tart-version-*`), completely independent of host TCP/IP, VPN routing tables, or DHCP lease drift.

⇒ **Always use `tart exec` via the baked-in Tart Guest Agent for host-to-guest control and automation; never depend on raw guest IP addresses or SSH.**
⭐ **The tell:** Scripts running `tart ip` followed by `ssh <ip>`, which silently hangs or errors with `No route to host` when host VPN/WARP is active.

### BACKGROUND VMS AND IN-GUEST DAEMONS MUST HAVE HOST SUPERVISION AND HEALTH PROBES, NEVER FIRE-AND-FORGET
**2026-09-10, T295 / T297.** `tart list` showed `bridgeroad-base` running orphaned on serial console for hours, and `w0m-bridgeroad` had `orca-ide` wedged at 99.9% CPU for 5h 37m with crashed Xvfb and zombie processes, completely invisible to the host.
Neither VM was registered in estate tracking, neither process was monitored, and nothing on the host noticed the orphaned VM or wedged 100% CPU spinning.

⇒ **Any VM or in-guest background server must have host-side registration, health heartbeats, and process lifecycle supervision rather than being launched unmonitored.**
⭐ **The tell:** Long-running background `tart run &` or `nohup` invocations without PID tracking, automated health checks, or watchdog teardown.

### CLIENT SOURCE TREES IN VMS MUST BE READ-ONLY AT THE HYPERVISOR LEVEL (:ro), NEVER VIA IN-GUEST MOUNT FLAGS
**2026-09-10, T265 / T295.** Probed live with `sudo touch /mnt/w0m/repo/.probe` inside `w0m-bridgeroad`: returned `Permission denied` even for guest root.
An in-guest `mount -o ro` is advisory (a guest root `mount -o remount,rw` bypasses it and writes directly to host files), whereas a hypervisor-level virtiofs `:ro` export (`--dir=repo:<path>:ro`) is strictly enforced by the macOS host kernel and cannot be overridden by guest root.

⇒ **Mount client repositories with hypervisor `:ro` exports, and mount separate writable scratch volumes (`:rw`) for agent session state.**
⭐ **The tell:** Relying on guest-side mount options or trusting in-guest root/user permissions to protect client codebases.

### GUI GUEST AGENTS REQUIRE A SYSTEMD USER SERVICE, WHILE HEADLESS AGENTS USE A SYSTEM SERVICE
**2026-09-10, T296.** In `w0m-bridgeroad`, `tart-guest-agent` runs as a system unit under `ubuntu`. For headless execution, RPC/`tart exec` works. But for GUI desktop features (shared clipboard), Linux requires `WAYLAND_DISPLAY`/`DISPLAY` and `XDG_RUNTIME_DIR`, which a system unit lacks—causing clipboard sync to fail silently while `tart exec` appears healthy. Furthermore, `/dev/virtio-ports/com.redhat.spice.0` is `0600 root:root` by default and requires explicit udev rules (`MODE="0666"`) or user access for SPICE file transfer.

⇒ **Run GUI guest agents as `systemctl --user`, and ensure udev permissions on `/dev/virtio-ports/`. Headless sandboxes stay as system units.**
⭐ **The tell:** Reusing the identical systemd system unit across headless and GUI VM templates.

### TELEGRAM getUpdates AND WEBHOOKS ARE MUTUALLY EXCLUSIVE — NEVER POLL ON AN ACTIVE WEBHOOK
**2026-09-12 (T215, delivery/artemioquierocomer.mx).** An admin control panel attempted to pair manager devices by polling `https://api.telegram.org/bot<TOKEN>/getUpdates`. Because a webhook was actively registered (`https://<domain>/api/telegram`), Telegram rejected the call with `409 Conflict: can't use getUpdates method while webhook is active`.

⇒ **When a Telegram bot runs in webhook mode, do not poll `getUpdates`.** Log inbound chat interactions inside the webhook handler into a rolling KV buffer (e.g. `telegram_recent_chats`), and provide self-enrollment (`/manager`) or manual ID entry in the admin interface.
⭐ **The tell:** Admin or setup flows failing with HTTP 400 or 409 when attempting to detect Telegram bot updates on production.

### COMPOSITE FOREIGN KEYS REQUIRE CHILD TABLE TEARDOWN BEFORE RE-POINTING PARENT KEYS
**2026-09-15, T363.** During data consolidation between legacy and canonical profiles, updating `hats.profile_id` failed with SQLSTATE 23503 because `worn_hats` carried a composite foreign key `(hat_id, profile_id, project_id) REFERENCES hats(id, profile_id, project_id)`. Modifying the parent `hats.profile_id` directly broke referential integrity against the still-pointing child rows.

⇒ **When migrating parent records linked via composite foreign keys, delete dependent child assignments (`worn_hats`) or nullify FKs first, consolidate the parent records, and then re-insert active child state pointing to the canonical ID.**
⭐ **The tell:** A data migration failing with `foreign key constraint violation` when attempting to re-parent a record that appears to have an active cascade or composite constraint.

### NAME ARTIFACTS BY WHAT THE PROCESS DID, NEVER BY TEXT PATTERNS IN OUTPUT
**2026-08-26 / 2026-09-17 (T291).** `deploy_logged.py` decided a transcript's file prefix (`deploy-<release>.log` vs `run-*.log`) by regex-matching any version string in stdout.

Running read-only diagnostic commands like `deploy_logged.py version-check` or `just version-check` emitted version numbers, causing the wrapper to fabricate `deploy-*.log` release records for operations that never published anything. These fake release records subsequently tripped `changelog-drift`, blocking commits and pushes until manual deletion.

⇒ **Artifact classifications must depend on intentional command intent and process exit status, never opportunistic string matching on command output.** Determine release artifacts strictly from `exit_code == 0` and explicit release recipe membership (`RELEASE_RECIPES = {"deploy", "_deploy-chain", "deploy-all", "_deploy-all-chain"}`).
⭐ **The tell:** A logging or audit wrapper naming an artifact as a deployment or transaction because the word "version" or "release" appeared in stdout.

### SUPABASE CLI CANNOT BUNDLE SYMLINKS POINTING OUTSIDE THE REPO ROOT
**2026-09-19 (T8).** `just deploy-agent-consultant` failed remote API bundling with `WARN: Skipping import path outside source root: ../../wom7web/packages/webmcp/src/manifest.ts` followed by `Cannot find module './tool-manifest.ts'`.

`supabase/functions/_shared/tool-manifest.ts` was a symlink pointing across estate repositories to `wom7web`. When using the Supabase Management API deployment (`supabase functions deploy --use-api`), the CLI packaging step ignores any symlinks targeting files outside the function project's source root, dropping them from the deployed bundle.

⇒ **Edge functions in `wom7api/supabase/functions/_shared/` must be standalone modules contained within the repository root, never cross-repo symlinks to sibling workspaces.**
### OPENSPEC CAPABILITY SPECS REQUIRE EXPLICIT DELTA HEADERS (## ADDED/MODIFIED/REMOVED), NEVER GENERIC ## REQUIREMENTS
**2026-09-23 (T422).** `npx openspec validate <change>` rejected a spec with `[ERROR] No delta sections found. Add headers such as "## ADDED Requirements" or move non-delta notes outside specs/`.

An author wrote `## Requirements` in a change's capability spec. While human-readable, OpenSpec's AST parser classifies requirements solely by delta headers (`## ADDED Requirements`, `## MODIFIED Requirements`, `## REMOVED Requirements`, `## RENAMED Requirements`). Omitting the delta classifier causes the change to register zero deltas and fails pre-push gates (`w0m-audit`).

⇒ **Always use explicit delta headings (`## ADDED Requirements`, `## MODIFIED Requirements`) in OpenSpec capability files under `specs/<capability>/spec.md`.**
⭐ **The tell:** `openspec validate` failing with `No delta sections found` or `Change must have at least one delta` despite well-formed `### Requirement:` and `#### Scenario:` blocks.

### HOSTED SUPABASE CLOUD RESTRICTS SECONDARY MFA TO TOTP — WEBAUTHN IS PRIMARY (PASSKEYS) ONLY
**2026-09-28 (T100).** Calling the Supabase Management API (`PATCH /v1/projects/<ref>/config/auth`) with `mfa_web_authn_enroll_enabled: true` was rejected with `HTTP 422: Enabling of MFA with WebAuthn not currently supported`.

While `@supabase/auth-js` has client-side methods for WebAuthn factor enrollment (`factorType: "webauthn"`), hosted Supabase Cloud supports WebAuthn exclusively for passwordless Passkeys (primary sign-in) and not as a secondary AAL2 MFA factor.

⇒ **On Supabase Cloud, MFA (AAL2) requires TOTP. Passkeys replace password sign-in (AAL1), but cannot satisfy AAL2 challenge gates.** If designing MFA enrollment UI, ensure TOTP is the active secondary factor and clearly message the provider limitation to users.
⭐ **The tell:** A 422 Unprocessable Entity error when attempting to enable WebAuthn MFA in Supabase project auth config.

### SUPABASE MFA ENROLLMENT REQUIRES UNIQUE FACTOR FRIENDLY NAMES PER USER
**2026-09-28 (T100).** Enrolling a second TOTP authenticator crashed with `400 Bad Request: A factor with the friendly name 'My Authenticator App' for this user already exists`.

A static friendly name (e.g. `'Authenticator App'`) works for the first factor, but Supabase Auth enforces uniqueness per user across all enrolled factors. Attempting to enroll a backup authenticator or a second device with the same label fails at the API.

⇒ **Dynamically assign distinct friendly names when enrolling factors.** Inspect currently enrolled factors and append an incrementing index (e.g. `getNextFriendlyName(factors, "Authenticator App")` -> `"Authenticator App 2"`).
⭐ **The tell:** An authenticator enrollment flow failing with `400: A factor with the friendly name ... already exists` as soon as a user tries to enroll a second device.

### ⛔ A GATE THAT CAN FAIL ONLY AFTER THE IRREVERSIBLE STEP IS A REPORT, NOT A GATE

**2026-09-30, T503.** `_deploy-all-chain` was `db-migrate`, then `deploy`, and the test gate lived INSIDE `deploy`. Two migrations were applied to the live database and then five blocking suites failed, leaving the schema ahead of the code. The same shape had happened the day before. The gates were not even in the chain's dependency graph (they hid in a recipe body), so nothing about the recipe list said the order was wrong.

⇒ **Every check that can fail runs before the first step that changes live state, and the order is pinned by a test that reads the real recipe graph (`just --dump`), with a red probe that feeds it the old order.**
- **Split by effect, not by name:** `_deploy-gates` writes nothing live; `_deploy-ship` does. A test asserts no mutator is a dependency of the gate recipe.
- **A fast check belongs where the change is made.** Four of the five failures were ratchets that take under a second and only ran inside an 8-minute gate, after a release cut and a Touch ID. A registry flag (`"prepush": true`) puts them in pre-push and in a pre-flight that runs BEFORE the confirmation prompt; the flag is validated (offline, blocking) and the tier is capped so it stays fast.
- **A repo with no pre-push hook has its cheap gates at pre-commit.** The umbrella's ticket edit was checked for the first time inside the deploy.
- **A hook and its registry must agree in BOTH directions.** Four steps were in the hook but not registered (so never checkpointed) and the checker only looked one way.
⭐ **The tell:** a deploy log where `db-migrate` appears above the first `test` line, or where the failing suite is one you could have run in a second.

### ⛔ "READY TO DEPLOY" MEANS THE DEPLOY'S OWN STAGES PASSED ON THE COMMIT THAT WILL BE CUT, NEVER THE FAST TIER
**2026-10-06, T503. The deploy failed, and replaying its stages found five more blockers.**

An agent said the estate was ready after `just test-prepush` and `preflight --fast`. The deploy then stopped at `_deploy-preflight` because `STATE.md` was stale (a ticket had been created after `state-save`). The stages behind it had never been run together: `check-guardrails` (the inline-credential scan tripped on four test fixtures), the full `test` tier (`py-test` could not collect: `psycopg` 3 was used but undeclared; the skills suite found canonical-vs-active drift; `tasks-bounds` found a board row that disagreed with a done ticket), and `goldens`. Also, the release is cut from `origin/beta` after a fetch, never from a working tree (`release.py`), so another agent landing first changes what ships.

⇒ **Before saying "ready", run, on the commit that will be cut:** `just _deploy-preflight`, `just check-guardrails`, `just test`, `just goldens`, `just check-warp`, `just check-infisical`, and `just state-check` **last**. State what only the owner's run can exercise (the Touch ID confirm, `db-migrate`, the ship, `smoke-live`). **Re-measure after any landing on `beta`**: a green result is about one commit.
⭐ **The tell:** a readiness claim that cites `test-prepush` or "preflight" only; "ready" said while another tree still has unlanded work.
**Measured again after agy landed, 2026-10-07:** a duplicate migration version (above) surfaced only on the re-measurement, because another agent had landed hours after the first green. The same re-run also found an unreachable CP page from that landing and 70 tickets whose stored hot score had gone stale at midnight (`tickets-frontmatter-check` is date-dependent until T552), so a readiness claim carries its commit AND its date: re-run after any landing and after midnight.
⚠️ `just goldens` kills and restarts whatever is on :4321: check `lsof -iTCP:4321` first so the owner's `just redev` is not killed. A `just deploy-dry-run` that runs exactly these stages is proposed on T503.

### ⛔ A SCHEDULED JOB MUST NEVER WRITE A TRACKED FILE IN THE LIVE CHECKOUT
**2026-10-06, T546.**

`com.w0m.tools-weekly` (launchd, Mondays) ran in the live checkout and rewrote `project/policies/tools-policy.json`, and nothing committed it. The owner's checkout sat dirty for a day, `git merge --ff-only` aborted on it, and a bump the weekly run had *held* (semgrep: "upgrade did not take") was written anyway by the reconcile step, with no smoke behind it.

⇒ **A scheduler observes and proposes; a person or an agent in an agent tree commits.** Record what a job verified in machine-level state outside every tree (`~/.w0m/state/`), and land it through a re-verifying step (`just tools-promote --apply`, refused outside an agent tree). Manual edits stay legitimate: a new advisory can force a change at any time.
⭐ **The tell:** a launchd/cron command whose script calls `write_text` on a path inside the repo; a live checkout that is dirty on a Monday morning.

### ⛔ A TOOL THAT WRITES TO A SHARED CHECKOUT AND PUSHES ONCE IS A RACE: BUILD ON THE FETCHED TIP, RETRY, AND LEAVE THE CHECKOUT ALONE
**2026-10-07, T554.**

The deploy shipped and published its tags, then `record_release` committed `releases/<v>.json` and `CHANGELOG.md` on the owner's live checkout and ran one `git push origin beta`. Another agent had landed in the meantime, so the push was rejected (non-fast-forward), the message said "push it later" (no command existed), and the commit stayed on the live branch: ahead 1, behind 1, which also broke the owner's `git merge --ff-only` catch-up. Three siblings of the same shape: a copy of the generated changelog into the shared tree, "the newest release record" read from the working tree (invisible when it landed elsewhere), and an exit code of 0 for a step that had failed.

⇒ **With more than one agent landing on `beta`, any tool that must put a commit on `origin/beta` does it the way `agent-tree-land` does: fetch, build the commit on the new tip, push, and on a non-fast-forward fetch and rebuild (bounded, with backoff); a refusal that is not a race is not retried.** For machine-generated files build the commit with plumbing (`read-tree` into a private index, `hash-object`, `write-tree`, `commit-tree`) so no working tree, index or local branch is touched and nothing can be stranded. When it cannot land, park the payload outside every tree and print the exact command that finishes it; never "push it later". Read shared facts (release records, ledgers) from `origin/beta`, not from a working tree, and make a failed step fail the exit code.
⭐ **The tell:** a deploy or generator whose last step runs `git commit` or `git push` inside the live checkout; a message containing "push it later"; the live branch showing ahead and behind at once after a tool finished.
⚠️ The push still runs the repository's pre-push hook; `--no-verify` stays prohibited.


## 4. Dependencies and config

### ⛔ TOOLCHAIN CONFIG SHARED ACROSS RUNNERS MUST NOT SILENTLY COUPLE — ZERO WARNING TOLERANCE
**2026-10-01, T520.** `pnpm` workspace settings in `.npmrc` (`enable-pre-post-scripts=true`, `verify-deps-before-run=true`) caused `npm` / `npx` to emit deprecation warnings: *"Unknown project config... This will stop working in the next major version of npm."*

When configuration files are shared across tooling ecosystems (`.npmrc` parsed by both `pnpm` and `npm`), a legitimate option added for one tool creates an unknown configuration warning in another. In `npm@11+`, unknown configs graduate from warnings to fatal errors (exit 1), causing a small, legitimate change in one place to break secondary tool invocations in a fragile, delayed way.

⇒ **Enforce single canonical execution runners (`pnpm exec` / `pnpm dlx` over `npx`) and never dismiss toolchain warnings as 'tool chatter'. Treat warnings as early smoke signals of latent fragility: identify, audit, and eliminate them before upstream tool upgrades turn warnings into catastrophic breaks.**
⭐ **The tell:** A command emitting 'Unknown config' or 'This will stop working in the next major version' that passes today but creates delayed breakage for other tools sharing that config.

### ⛔ ASSET URLS IN SHARED GLOBAL CSS FORCE BUNDLER RESOLUTION ACROSS ALL CONSUMING APPS
**2026-09-30, T507.** Vite emitted build warnings in `apps/join`, `apps/job`, and `apps/demo` attempting to resolve `/assets/info-1-web.webp` through `/assets/info-4-web.webp`.

When background slideshow scenes were deprecated in `packages/lib/src/background.ts` under T452, `--bg-slide-1..4` CSS variables with `url('/assets/...')` were left inside `apps/web/src/styles/global.css` and `apps/cp/src/styles/global.css`. Because other monorepo apps imported those shared global stylesheets, Vite's asset bundler attempted to resolve those root-relative paths within each consumer app at build time, failing and emitting warnings.

⇒ **Deprecating or removing visual assets requires removing their CSS custom property declarations from shared global styles atomically, rather than leaving orphan `url(...)` references or copying dummy assets into consumer apps.**
⭐ **The tell:** Consuming monorepo apps emitting Vite asset resolution warnings for assets that only a deprecated or separate app feature referenced.


### ⛔ VERIFY EVERY CREDENTIAL KEY NAME AGAINST THE STORE — NEVER TRANSCRIBE FROM MEMORY
**2026-08-14, T134.** Of eleven key names written from knowledge of the services, **six were wrong**.

AWS uses `AWS_ACCESS_KEY` / `AWS_ACCESS_SECRET` here — **not** the SDK-standard
`AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`. Anything reading them through a default AWS
credential provider finds nothing.
⇒ **A wrong key name is not a typo — it makes a service report "credential missing" forever**, i.e.
the surface is confidently wrong about the one thing it exists to report.
⭐ **The tell:** a key name that matches the vendor's documentation exactly. That is a sign it was
recalled, not measured.

### MIRROR MULTI-TENANT SETTINGS TO LEGACY KEYS ON SAVE FOR ZERO-DOWNTIME ROLLOUTS
**2026-09-12 (T215, delivery/artemioquierocomer.mx).** Migrating a single-value configuration key (`telegram_chat_id`) to a collection (`telegram_managers`) broke secondary consumers across the repository (review submissions, status badges) that still read the legacy key.

⇒ **Update handlers must mirror the primary active record into the legacy key on save, deleting the legacy key only when the collection is emptied.** Migrate on read if the new key is missing to preserve zero-downtime backward compatibility.
⭐ **The tell:** Refactoring a single-value storage key into an array while disparate consumers across the repo still read the legacy scalar key.

### SCOPE BUILDER COMPILATION AND ISOLATE PYTHON VIRTUALENVS IN STATIC LINTERS
**2026-09-12 (T219, delivery/artemioquierocomer.mx).** `astro check` passed with 0 errors but emitted 15 compilation hints because `tsconfig.json` included `**/*`, compiling one-off scratch scripts, deprecated Node buffer calls (`buf.slice`), and test files alongside production code. Concurrently, `eslint` failed with 8 fatal `no-undef` errors because third-party JS shims inside a Python virtualenv (`.venv_tg`) were inspected.

⇒ **Scope `tsconfig.json` `"include"` strictly to application paths (`src/**/*`, `scripts/**/*`) and explicitly exclude scratch files and virtualenvs.** Add `.venv/**` and `.venv_*/**` to global linter ignores (`eslint.config.mjs`, `oxlint`).
⭐ **The tell:** `astro check` or linters reporting errors and hints on files in virtual environments, node shims, or temporary root scripts.

### GOVERNED SKILL PATHS MUST BE RECONCILED IN CANONICAL wom7skills, NEVER DRIFTED LOCALLY
**2026-09-12 (T220, delivery/artemioquierocomer.mx).** `w0m-sdlc-research`'s Step 2 cited `.agent/LESSONS.md` (deprecated 2026-08-14 in favor of root `LESSONS.md`), causing agents to silently miss earned lessons. Correcting the path locally in a consumer repo fixed the prompt but caused `just skill-check` to fail with a cryptographic SHA-256 hash mismatch against `skills-lock.json`.

⇒ **Backport skill corrections upstream to `wom7skills/skills/` via `just skills-backport`, re-hash the lockfile, and synchronize downstream via `just skills-update --canonical`.** Never leave ad-hoc local skill modifications that break governance integrity gates.
⭐ **The tell:** `just skill-check` reporting `HASH MISMATCH` on a governed skill after someone manually fixed a typo or path in an installed copy.

### RETIRE REDUNDANT TOOL AND SKILL COMPATIBILITY SHIMS ONCE UPSTREAM STANDARDIZES ON .agents/skills
**2026-09-17 (T372, Orca / OpenCode / Claude Code integration).** When Claude Code v2.1 natively adopted `.agents/skills/`, legacy `.claude/skills/` symlink shims were retired under T372. However, `skills.ts` continued generating `.opencode/skills/` symlinks pointing to `.agents/skills/`. Because Orca and modern Claude Code traverse both repo and parent directories looking for skills, having `.agents/skills` and `.opencode/skills` side-by-side caused identical skills (e.g. `/w0m-tasks`) to register up to 5 times in the autocomplete interface and system prompts.

⇒ **Remove all compatibility symlink trees (`.claude/skills`, `.opencode/skills`) as soon as agents share the universal standard (`.agents/skills`).** Dual discovery trees always produce N-fold token bloat and duplicated UI autocompletions.
⭐ **The tell:** Slash command autocompletions showing multiple identical entries with the same name, or prompt token counts scaling linearly with the number of symlink folders.

### A SECRET IN INFISICAL IS NOT SYNCED UNTIL IT IS NAMED IN THE SYNC ALLOWLIST — TWICE NOW
**2026-09-19 (T201).** `TURNSTILE_SECRET` was set correctly in Infisical `beta` and `just sync-secrets` + `just deploy-functions` were both run — twice — yet `contact-submit` kept treating Turnstile as unconfigured and let captcha-less submissions through (Gauge: 2 of 4 scenarios wrongly getting 200 instead of 400/303). Root cause: `wom7api/scripts/sync_supabase_secrets.py` pushes to Supabase only the keys named in its hardcoded `keys_to_sync` list — the list still had `("HCAPTCHA_SECRET", "HCAPTCHA_SECRET")` and had never been updated to include `TURNSTILE_SECRET`, so the secret sat correctly in Infisical and was silently never forwarded. **This is the identical failure class the file's own comments already document for `HONEYCOMB_API_KEY`** (present in Infisical since 2026-03-14, never in the list, Supabase copy stuck at the empty-string digest for months) — it recurred because adding a new secret consumer did not come with a checklist item to add it to this file.

⇒ **When introducing a new secret an edge function reads, treat "add it to `sync_supabase_secrets.py`'s `keys_to_sync`" as part of the same change as writing the Infisical value — not a separate, forgettable step.** A secret can be present, correctly valued, and timestamped fresh in Infisical while being completely absent from Supabase, and nothing in either store's own tooling will say so; the only way to see the gap is to diff the two stores' key sets directly (`supabase secrets list` vs the Infisical env) rather than trusting that "I set it in Infisical" implies "it reached the consumer."
⭐ **The tell:** a `Deno.env.get("X")`-backed feature behaves as if `X` is unset in production, despite `infisical secrets get X --env=<env>` proving it exists and `just sync-secrets` having been run — check `sync_supabase_secrets.py`'s allowlist before suspecting anything else.

### INFISICAL SECRETS DELETE DEFAULTS TO --type=personal — A SHARED SECRET 404s 51 TIMES BEFORE THAT REGISTERS
**2026-09-19 (T201).** `infisical secrets delete HCAPTCHA_SECRET --env=beta --silent` returned `404 Secret not found` 51 times in a row, even though `infisical secrets get HCAPTCHA_SECRET --env=beta` found it seconds earlier (type: `shared`, per its own output). Root cause: `secrets delete --help` shows `--type` defaults to `personal`; `secrets get` has no such flag — it transparently merges `personal` and `shared` (`--secret-overriding` decides precedence when both exist). Every shared secret in this estate (which is effectively all of them) is invisible to a bare `delete` call. Fixed with `--type=shared` added; deleted on the first try after that.

⇒ **`get`/`list` and `delete` are not symmetric on secret type — check `--help` on the mutating subcommand before trusting that a passing read implies the write will target the same object.** A 404 from a delete/write command right after a successful read is a strong signal of a default-flag mismatch, not that the object vanished between the two calls.
⭐ **The tell:** `infisical secrets get NAME` succeeds, `infisical secrets delete NAME` 404s with "Secret not found" using the identical name/env — add `--type=shared` before assuming the secret was already gone.

### ⛔ A TERMINAL CHECK IS NOT A HUMAN CHECK — VERIFY PROCESS ANCESTRY AND HUMAN PRESENCE
**2026-09-24, T435.** The deploy/migrate confirmation gate was self-confirmed by an AI agent (agy) holding a pseudo-terminal on 2026-09-17 (`run_command just db-migrate` followed by `manage_task send_input "yes\n"`), applying live migrations to production database.

Checking `stdin.isatty()` or opening `/dev/tty` only proves an interactive terminal stream exists, which modern agent harnesses (like Antigravity or `script -q /dev/null`) allocate natively.

⇒ **Gate mutating operations against process ancestry, agent environment markers, and OS-level human presence.**
- Walk the process ancestry up to PID 1 / launchd and inspect environment variables (`CLAUDECODE`, `AI_AGENT`). If an agent binary or harness is present, fail closed (`REFUSED-AGENT`).
- If ancestry cannot be read, fail closed (`REFUSED-UNMEASURABLE`).
- A typed "yes" at a terminal must be backed by OS-level human verification (macOS `LocalAuthentication` Touch ID / password dialog) so even a detached terminal cannot spoof human intent.
⭐ **The tell:** A security gate that relies on `isatty()` or prompt typing as proof that the caller is human. An agent with execution privileges can always allocate a pty.

### ⛔ AMBIENT ROOT CONSENT MUST NEVER SURVIVE ITS SCRIPT OR PERMIT UNINTENDED STANDALONE MUTATIONS
**2026-10-04, T541.** After authenticating `just deploy-all` with Touch ID, running `just db-migrate` standalone in the same terminal within 45 minutes did not prompt for confirmation.

When a root command (`deploy-all`) is granted consent, an ambient JSON file in `$TMPDIR` was written with a 45-minute TTL covering all 23 steps (`covered: ["db-migrate", ...]`). Rule 2 checked `step in consent["covered"]` before Rule 4 could prompt, letting subsequent, separate invocations ride the earlier authorization. Furthermore, the consent file survived after the deploy script exited.

⇒ **Single-use step consumption + process teardown cleanup.**
- Sensitive steps like `db-migrate` that may run once inside a root flow must be marked `single_use`: Rule 2 immediately consumes their authorization on disk (`consent["covered"].remove(step)`) upon pass, so a second or standalone invocation is withheld.
- Deploy scripts (`deploy_logged.py`, `release.py`) must invoke `confirm_step.py --clear` in a `finally` block on exit, ensuring ambient consent never outlives the invoking command.
⭐ **The tell:** A test suite that clears state manually in test setup (`clear()` before running standalone assertions). If tests only pass because setup wipes the ambient file, real users who don't manually clear the file will leak consent between commands.

### ⛔ A NAME LIVES IN ELEVEN PLACES — INVENTORY THEM BY CLASS BEFORE A RENAME AND PROVE ZERO LIVE ONES AFTER
**2026-09-29, T453 follow-up.** `wom7cfworkers` -> `wom7func` was recorded as *"renamed completely"* on 2026-09-18. Eleven days
later `just name-refs wom7cfworkers` found **603 hits in 11 repos, 144 of them live**: a health check whose default host
(`os.environ.get("WORKERS_URL", "https://wom7cfworkers.…workers.dev")`) now answers **404**, three `../wom7cfworkers/CLAUDE.md`
pointers to a file that moved, a deploy step (`cd wom7cfworkers`), the architecture docs, 38 spec lines, and the policy JSON.
A rename is done when the name is gone from every **live** surface, not when the folder moved.

⇒ **Where to look, in this order — the class decides how you change it:**
1. **Code** — imports, path deps (`../../wom7func/src/index`), type imports across repos. The compiler finds these; do not stop here.
2. **Env-var DEFAULTS** — `environ.get("X", "https://old-name…")`, `process.env.X || "…old…"`. A hard-coded copy of the name that
   survives every secret update. Different from the env var's *name* and from its *value*.
3. **Env-var VALUES** — a secret holding a URL of the renamed thing (`WORKERS_WEBHOOK_URL`). Not greppable: Supabase secrets expose
   SHA-256 digests, Cloudflare secrets are write-only (verify behaviourally), Infisical prints plaintext (never list it).
   `name-refs` prints the URL-shaped env names read near a hit as the candidate list.
4. **Config** — `wrangler.jsonc` `name` (this IS the deployed script name and its `workers.dev` host), justfile recipes, hooks,
   `.graphifyignore`, `stacks-policy.json`, `sdlc.json → repos`, editor `*.code-workspace`.
5. **Specs** — openspec live changes and Gauge `.spec` files. Archived ones are history: leave them.
6. **Docs** — current-state prose, ASCII/Mermaid diagrams (re-pad a box after renaming), setup commands (`cd <dir>`).
7. **Paths and symlinks** — the folder, and tracked symlinks whose *target* holds the name (`wom7func/justfile -> ../wom7api/justfile`).
8. **Remotes** — `git remote -v` in every clone and worktree, the GitHub repo name.
9. **Generated files** — `DECISIONS.md`, `TASKS.md`, graph indexes. Regenerate; never hand-edit. (A rename that shifts lines
   also shifts every `file:line` anchor in `DECISIONS.md` — see the umbrella `decisions-index-fresh` hook.)
10. **Live infra** — the Cloudflare script, its routes, cron triggers and bound Workflows; Infisical paths.
11. **Machine config outside the repos** — `~/.claude.json` MCP args, launchd plists, shell rc (`name-refs --outside` lists paths only).

**Do not rewrite** tickets, LESSONS, STATE, ADRs, archived specs or migrations: they describe the past and a migration is immutable.
A line that says it is history ("was named X until 2026-08") is counted as a visible `note`, not a live hit.

⭐ **The tell:** a rename ticket whose acceptance criteria say "folder renamed" and "docs updated" but none says
`just name-refs <old> --gate` exits 0. Two more: a grep of *one* file type, and any default value that embeds a hostname.
Use `just name-refs <old>` before, `--gate` after; `--files` lists every line, `--outside` scans the machine.

### ⛔ NEVER COPY A SECRET YOU HAVE SEEN INTO A FILE — TEST FIXTURES USE SYNTHETIC VALUES OF THE SAME FORMAT
**2026-09-29, T213.** Reading the job sources printed three live credentials into a tool result. When I wrote red-probe fixtures for
the new ast-grep rules I reproduced them as the "must flag" cases, and gitleaks and semgrep blocked the commit (correctly). Nothing was
committed, but the values had by then been in a transcript and a scratch file. The rule is not "the scanner will catch it": it caught
this one because the values matched known formats.

⇒ **Mask at print time** (`sed -E "s/(['\"])[A-Za-z0-9_-]{16,}\1/\1<MASKED>\1/"`), **write fixtures from a format, never from a value,** and
treat any secret that appeared in output as compromised, so the rotation is the fix, not the deletion. A JWT-shaped fixture is
assembled from pieces so no source line matches the detector.
⭐ **The tell:** a fixture or comment whose "example" was copied from a file you had just read.

### A DEFAULT THAT NAMES A CREDENTIAL IS THE CREDENTIAL — `env.X || 'value'` MAKES A MISSING SECRET INVISIBLE
**2026-09-29, T213.** `process.env.JOOBLE_API_KEY || '<real key>'` (x3) meant rotating or injecting the secret changed nothing, the
key sat in git with no known owner (so it could not be rotated in an incident), and when one died (Reed answered 403) the source
returned `[]` and reported a healthy empty run. Measured after the fix: none of the four secrets existed in the vault, so the worker had
been running on the literals as its configuration. A `'placeholder-key'` fallback in the Upwork helper did the same to the service key.

⇒ **Read the injected env with no default and throw naming the variable at first use; a non-2xx from a provider THROWS, it never returns
empty.** Two ast-grep rules now hold the shape (name-keyed and literal-shape-keyed); gitleaks cannot, because it matches known formats and
these are provider-specific.
⭐ **The tell:** a source whose failure path is `return []`, and an env read with a string on its right-hand side.

### AN AUTH ROUTE MUST NEVER LOG THE REQUEST HEADERS — THEY ARE THE SESSION
**2026-09-29, T52.** Both `update-password` routes logged the whole header map on every password change, which wrote the access and
refresh token cookies to the logs. It sat there as "debug logging moved to top". A guard test now scans every auth route in every app
for the shape (red-probed), and the explanatory comment that quoted the shape tripped it, which is the guard working.
⭐ **The tell:** `console.log(..., request.headers)` anywhere under `pages/api/auth/`.

### A FAILED `terraform apply` IS NOT A FAILED CHANGE — READ THE LIVE VALUE BEFORE RETRYING
**2026-09-29, T52.** `supabase-settings-apply` failed with "unhealthy service realtime": Supabase restarts auth on a settings change and
the provider's health wait timed out. The right next move was to read the live value (still 6), the health of every service (all
healthy) and a fresh plan (still exactly one change), then retry. Retrying blind risks doubling a change; assuming it applied risks
recording something false.
⭐ **The tell:** an error that arrives *after* "Modifying...". Verify state, then repeat the idempotent step.

---

### ⛔ RUN TESTS UNDER THE PROJECT'S OWN RUNNER: SYSTEM PYTHON HIDES AN UNDECLARED IMPORT
**2026-10-06, T539.**

`upwork_loader.py` and its tests import `psycopg` (v3). `wom7web/pyproject.toml` declared only `psycopg2-binary`. System `python3` has `psycopg`, so every local run passed; `uv run pytest` (the deploy's `py-test`) could not import it, and **one collection error interrupted all 984 tests**.

⇒ **When a change adds an import, declare it in the project file and run the suite through the project's runner** (`uv run pytest`, `just py-test`), not the interpreter on your PATH. Re-lock (`uv lock`) in the same commit.
⭐ **The tell:** `ModuleNotFoundError` only under `uv run`; a new `import` with no matching line in `pyproject.toml`.

### ⛔ A FAKE PASSWORD INSIDE A CONNECTION-STRING LITERAL IS A LEAKED CREDENTIAL TO THE PRE-DEPLOY SCAN
**2026-10-06, T535, T539, T532.**

`check-guardrails` greps tracked files for `scheme://user:password@` with a 6+ character password (gitleaks misses connection strings, T32). Four test fixtures matched: a redaction test that builds a URL around a distinctive fake password, and two others with short literal passwords. They are fixtures, but the scan cannot know, and it runs only at deploy time, so it failed the deploy.

⇒ **Keep the distinctive fake secret in a named constant and interpolate it (`f"<scheme>://user:{FAKE_PASSWORD}@host/db"`), or use a placeholder under 6 characters when the value is never asserted on.** Never weaken the regex for a fixture.
⭐ **The tell:** a new test that builds a database URL with a password in the literal. Run `just check-guardrails` before landing a test that does.
⚠️ The same applies to prose: this lesson's first draft quoted the fixture URLs and the secrets hook (gitleaks rule `wom-postgres-uri-inline-password`) rejected the commit. Describe such a value, never paste it, including in tickets and reports.

### ⛔ A NEW ADVISORY CAN BLOCK A COMMIT YOU DID NOT CAUSE: RAISE THE FLOOR, NEVER SKIP THE HOOK
**2026-10-06, T112.**

The `osv-scanner` pre-commit hook blocked an unrelated commit on four new advisories (`sharp` 8.9, `source-map-js` 8.7, `tinypool` 9.5, all dev-tool dependencies of wrangler, vitest and oxfmt). The fix was to raise three `pnpm.overrides` floors in `wom7api/package.json` and run `pnpm install --lockfile-only`, then re-scan (`osv-scanner --lockfile=pnpm-lock.yaml`: no issues).

⇒ **Find the dependency path (`pnpm why <pkg>`), raise the floor to the fixed version, regenerate only the lockfile, and re-scan.** Hand edits to `known_good`/`min` and override floors are supported; `--no-verify` is prohibited.
⭐ **The tell:** `osv-scanner` failing a commit that touched no dependency file.

### ⛔ A MIGRATION VERSION IS THE LEDGER KEY: TWO AGENTS PICKING THE SAME TIMESTAMP DROP ONE MIGRATION SILENTLY
**2026-10-07, T551 and T544.**

An agent landed `20261006120000_t544_...` in the afternoon; another landed `20261006120000_t461_...` in the evening. Each was correct alone. Both readers of the migrations directory (`db_drift_check.local_migrations`, `db_migrate`) build a `version -> filename` dict, so the later-sorted file replaced the other: `just db-drift-check` listed **four** pending migrations where **five** existed, and `supabase db push` would have failed on a duplicate key in the middle of the deploy, after the Touch ID and after earlier migrations had been applied. A ledger-gated authz probe would also have switched on against a policy that had not been applied.

⇒ **Anything keyed by a value two agents can pick independently needs a uniqueness check at the place it is created, offline, in the push gate.** `just migration-versions-check` is now a pre-push suite, and the full drift check refuses a collision before it reads the ledger. When it fires, renumber the file that is NOT yet applied (14 digits, a free timestamp) and update every reference.
⭐ **The tell:** two files in `wom7api/supabase/migrations/` with one 14-digit prefix; a pending list shorter than `git log` says it should be. Tests must also exercise a collision on the REAL directory, not only a temp one, and an empty or missing directory must fail rather than pass.
⚠️ Detection is built; prevention (a `migration-new` that takes the next free version from `origin/beta`, like the ticket-id guard in `agent-tree-land`) is T551 AC4.


## 5. Records

### ⛔ SEVERITY IS SET BY EXPOSURE, AND EXPOSURE IS MEASURED — NEVER INFERRED FROM SHAPE
**2026-08-14, [[T213]].** Filed **P0** — *"four credentials leaked in live workflow code"* — on the
strength of `process.env.X || "<literal>"` and nothing else. The owner pushed back (*"this looks
like just a token automatically created, I never created it manually"*). Every claim that set the
severity was wrong:

| filed | measured |
|---|---|
| leaked | **both repos are PRIVATE**; neither live key appears in public GitHub code |
| four live credentials | **two** live, **one dead** (403, identical to a bogus key), one an app id |

The shape is a strong **prior**, not a finding. Reading it as one produced a P0 that would have
pre-empted real work, and the confident *"leaked"* framing would have travelled into a rotation
plan nobody needed.
⇒ **Before assigning severity, measure the two things severity actually depends on: is it
reachable, and is it live?** Repo visibility is one command. Liveness is one request — and send a
**deliberately wrong** credential first, so a rejection is distinguishable from a rate-limit or an
outage.
⭐ **The tell:** a severity that follows from what the code *looks like* rather than from a number
you obtained. ⚠️ And note the symmetry — the ticket it was split from made the **opposite** error
in the same line, calling the code *"dead"* when a live Workflow imports it. Both directions come
from describing code instead of running it.
🟢 **The correction is what found the real defect:** testing revealed all three sources
`return []` on any HTTP failure, so a dead credential is recorded as a successful zero-result
fetch. Worth more than the thing it was filed for — **let the test rewrite the ticket.**

### ⛔ CHECK THE QUEUE BEFORE FILING — A NEWER DUPLICATE OUTRANKS ITS ORIGINAL
**2026-08-13, T208.** Filed with 9 findings; **7 already belonged to T194**, by file and line, for
three days.

The duplicate scored *higher* than the original because it was newer, and it lacked context the
original carried (the replacement columns are plaintext at rest).
⇒ **Grounding is a step before filing, not after.** `w0m-sdlc-new` exists to force it.
⭐ **The tell:** filing a ticket that feels urgent because you just found it.

### ⛔ A COMMENT IS NOT A CONTROL — READ THE NEXT LINE
**2026-08-14, T138.** `linkedin-share/index.ts` documented its safety property in full —
*"Because this function is running with Anon key + Auth Header, RLS applies. They can only see
tokens they inserted… only the person who linked the page can post to it."* — and **two lines
later built a `service_role` client, which bypasses RLS entirely**.

The lookup then matched on `(provider, provider_urn, is_active)` with no `user_id`, so any
admin/editor could retrieve **another user's LinkedIn OAuth access token** by URN and post as them.
`user.id` was already in scope, and already used correctly 20 lines above.
⇒ **A stated control is a claim about code that must be re-read, especially when the comment is
long and confident.** This one also explains itself — it says *"if we want anyone in the agency to
post, we need a service_role query here"*, and someone did exactly that without removing the
sentence describing the property they had just deleted.
⭐ **The tell:** a comment arguing for a safety property rather than stating one. And note what
found it — not a security review, but an *indexing* gate asking why `.single()` could match two rows.

### ⛔ THE GRANT IS NOT THE CONTROL — RLS IS, AND THEY FAIL DIFFERENTLY
**2026-08-13/14, T69 and T210.** The `gamification` schema had `nspacl = NULL` — **no USAGE for any
role, including `service_role`** — so RLS policies written in May had been unreachable ever since.
~50 call sites across 9 edge functions were dead, and adding the missing `.schema()` qualifier alone
would have turned a silent `0 XP` into a 401 while the ticket read as fixed.

Conversely, `profiles` grants anon `SELECT` and **RLS is the only thing closing it** — a policy edit
alone can open it without touching a grant.
⇒ **RLS filters a grant; it does not substitute for one. Check both, and check them per role.**
⭐ **The tell:** a policy that "looks right" being offered as proof. A policy that *compiles* is not a
policy that *scopes* — count rows as each role.

### ⛔ DECLARED ≠ CONFIGURED ≠ LISTENING ≠ CONNECTED — NEVER COLLAPSE THEM TO A GREEN DOT
**2026-08-07 (T154) and 2026-08-13 (T134).** An MCP server sat at three of those four states for
**12 days** and read as healthy.

⇒ **A status surface renders each state independently, and says which it cannot observe.** `unknown`
("not observable from here") and `no` ("observed absent") are different claims.
⭐ **The tell:** one badge summarising several questions.

### ⛔ A DECLARATION FILE IS NOT A GATE — SOMETHING MUST READ IT
**2026-08-14.** `schema-drift` compares tables and columns, **never policies**, so
`_shared/database/schema.ts` declares an `"Allow all access … to public"` policy the database does
not have, and no gate can see the difference. The same shape retired the Supabase debt census in
July: 48 hand-written `TECH-DEBT.md` rows that **no gate had ever read**, of which 17 are tracked by
a ticket that is already done.
⇒ **When you add a register, add the check that reads it in the same commit.**
⭐ **The tell:** a file whose accuracy depends entirely on people remembering to update it.

### A GATE'S METRIC MUST BE THE THING YOU CARE ABOUT, NOT A PROXY THAT USUALLY MOVES WITH IT
**2026-08-23 (T261).** A responsive-layout gate measured **lines** and passed **all 33 rows** while
**every H1 on the site rendered at 16px** — a destroyed heading fits on one line everywhere. The
cause was a Tailwind arbitrary value with a function nested in its `var()` fallback
(`text-[var(--text-hero,clamp(...))]`), which generates **no CSS rule at all**, silently. I reported
"H1 on one line at every pair" to the owner as success before the proxy was caught.
⇒ **Ask what a catastrophic failure would look like in your metric.** If it looks like a pass, the
metric is wrong. The fix here was an `h1-font-size` band — the property actually at risk.
⭐ **The tell:** a metric that is a *consequence* of the property you want, rather than the property.

### A PROMOTION TRIGGER MUST NAME A STATE OF THE PRODUCT, NEVER OF THE PAPERWORK
**2026-08-24 (T261 → T275).** A suite was registered non-blocking with the trigger *"flip to
blocking when that finding is resolved **or accepted as debt**"*. The finding **was** accepted as
debt — so the condition fired the moment the debt row was written — while the same paragraph argued
that flipping it would redden the aggregate for a decision already made. **A trigger whose condition
has fired and whose reasoning says do not act on it is a dead instruction**: the next reader either
flips it (permanent red) or ignores it (governance text nobody obeys), and neither is a decision.
⇒ **Condition promotion on a measurable state of the code** — *"when D60 and D61 are resolved"* —
never on a ticket closing. Archiving a ticket must not arm a gate that cannot pass.
⭐ **The tell:** a trigger you can satisfy by writing something down.

### A GATE THAT BLOCKS ON WHAT IS OUTSIDE YOUR CHANGE ARGUES FOR THE ONE FORBIDDEN ACTION
**2026-08-23/24 (T267, T274 AC7 → T267 AC8).** Two gates fired on things the committer was not
committing: `deploy-in-flight` scans `ps` **host-wide**, so another project's deploy blocked a commit
here — in a repo that has no `confirm_step.py` at all; and `emoji-check` globs the **working tree**,
so an **untracked** file nobody had staged blocked a commit, and unstaging did not help. Both fail
closed, so each cost only a wait — but the only way past either is `--no-verify`, **prohibited in
every w0m repo**.
⇒ **Scope a gate to the change at commit time, and to the invariant at push time.** Note they need
*different* fixes: one needs a narrower predicate, the other the same predicate at a later moment.
⚠️ And neither was *wrong about its finding* — the file really did breach the rule. **A scoping
error is not a false positive**, and fixing it must defer the finding, not delete it.
⭐ **The tell:** you can satisfy the gate by deleting someone else's file.


### WHEN TWO GATES DISAGREE ABOUT THE SAME PROPERTY, ONE OF THEM IS LYING
**2026-08-26 (T289).** A new probe reported `wom_acting_is` reachable by anon *via PUBLIC*. The
suite's long-standing `G2-definer-acl-explicit` guard asserted, on the same database in the same
minute, that **no** definer function in `public` retained the default PUBLIC grant. Both had passed
their own tests. G2 was wrong: it tested `p.proacl IS NULL`, and `proacl` is NULL only while **no
grant statement has ever touched the function** — Supabase's `ALTER DEFAULT PRIVILEGES` materializes
an ACL on every function at creation, so the count was 0 on every run and **could not have been
anything else**. The `=X/postgres` entry sat inside those ACLs, unread, for the guard's whole life.
Rewritten to `aclexplode(proacl) WHERE grantee = 0` it found 2 real violations immediately.
⇒ **Resolve the disagreement, do not average it.** The temptation is to trust the older gate
because it has more runs behind it; runs are not evidence when the predicate cannot fire.
⚠️ **G2's own rationale text contained the refutation** — *"All 32 carry explicit ACLs"* — i.e. the
author knew `proacl` was non-NULL everywhere and still shipped `IS NULL` as the test.
⭐ **The tell:** a gate whose green you cannot describe a way to turn red.

### A REVOKE THAT SUCCEEDS IS NOT A GRANT THAT IS GONE
**2026-08-26 (T289).** A function in `public` carries up to **two independent** EXECUTE grants —
PostgreSQL's own `=X/postgres` (PUBLIC, on every new function) and Supabase's `anon=X/postgres`
(from `ALTER DEFAULT PRIVILEGES`) — and anon reaches it through **either**. This estate got it wrong
in **both** directions inside one day: two migrations revoked `FROM PUBLIC` and left anon's grant,
then the correction revoked `FROM anon` and left PUBLIC's on **7 of 8** functions. Every statement
succeeded. Every diff read correctly. `current_profile_id` was the only one that flipped, because
its ACL happened to carry no PUBLIC entry — seven identical-looking functions behaved differently
for a reason visible only in `proacl`.
⇒ **`revoke ... from public, anon;`** and verify with `has_function_privilege(...)` on **production**
— a restored dump never receives the `ALTER`, so the property reads clean on a scratch DB while
being false live. **A grant is gone when the ACL says so, not when a REVOKE naming it succeeds.**
⭐ **The tell:** you checked the migration text instead of the ACL.

### CROSS-SURFACE HANDOFF (DESKTOP ↔ ORCA) RE-BINDS ACTOR METADATA ON COMPACTION
**2026-09-09, session 5feca02b.** A session started in Claude Desktop (`aleksei@webomage.com`) was continued in Orca (`servicios777@webomage.com`). Upon context compaction, the harness refreshed `userEmail` to the active Orca runner identity, leading the agent to suspect an in-flight session compromise despite the split being explicitly documented in memory.

⇒ **Session compaction re-reads local harness identity, not the historical creator.** When handing off session state between manager (desktop) and runner (Orca) surfaces, the runtime identity legitimately shifts to the host surface. Agents must verify local surface architecture records before treating identity refreshes as an anomaly.
⭐ **The tell:** A mid-session `userEmail` switch occurring simultaneously with a `Conversation compacted` event across known split accounts.

### A WORKFLOW FILE MISSING FROM A SURFACE IS NOT A SURFACE THAT SOMETIMES SKIPS THE STEP
**2026-09-11, T336/T337.** Antigravity (Orca, "Agy") committed both tickets cleanly across two
commits — ticket body, `ROADMAP.md`, `TASKS.md` all correct — but neither carried a `gh_issue`
and neither existed in `project/tickets-sync-index.json`; `just sync-tickets` had never run for
them. Checked `.agent/workflows/` (Antigravity's autoload surface, [[T192]]) against
`.claude/skills/w0m-sdlc-new/SKILL.md`: the `w0m-sdlc-*` family is **entirely absent** there — only
`opsx-*` plus four unrelated `w0m-*` files exist. `.opencode/skills/w0m-sdlc-new/SKILL.md`, by
contrast, carries the identical Step 5 ("Finalize … run `tickets.sync`") verbatim. "pi" is not even
a declared surface in `.w0m/sdlc.json → ide_surfaces.connected` for this project.
⇒ **This was never a behavioral lapse to retry — it is a file that does not exist on that surface.**
`just ide-trace` checks each connected surface against the non-negotiables (never `--no-verify`,
etc.) but does not check **skill/workflow-file parity** — whether a surface's copy of a multi-step
gate (like `w0m-sdlc-new`'s Finalize step) is present at all, let alone current. Treat
`.claude/skills/` as the golden copy and diff every other declared surface's equivalent file
against it; a missing file is a harder failure than a stale one and neither is caught today.
⭐ **The tell:** a ticket with acceptance criteria and a clean commit, but no `gh_issue` and no row
in `tickets-sync-index.json` — sync didn't fail, it was never invoked, because the surface that
created the ticket had no instruction telling it to.

### A MISSING GATE IN A CLIENT REPO MAY BE A DECIDED BOUNDARY, NOT A GAP
**2026-09-11, T334 AC6.** An AC required "all changes … pass linters/typechecks/tests without
`--no-verify`" across two estate repos and one client repo (`artemioquierocomer.mx`). The client
repo had **no pre-commit hook at all** — only a bare `commit-msg` — which read as the exact defect
the AC existed to catch, and the reflex was to install one there to match.

`project/clients-policy.json → tiers.half-managed.contract_surfaces.quality_gates` already answered
it: *"DECLARED, NOT ENFORCED — we cannot install a hook in a repo we do not control."* That line was
an explicit owner decision ([[T265]] AC2), not an oversight — the half-managed tier states what good
looks like without installing enforcement in a repo that is not this estate's to govern.
⇒ **Before treating an absent gate in a client/half-managed project as something to build, check
whether its tier already decided that on purpose.** Verify the property some other way (here: run
the client's own equivalent check directly, `just skill-check`) instead of extending estate
enforcement into a repo the policy deliberately keeps hands off.
⭐ **The tell:** an AC written against "every repo we touch" that, read literally, would have you
writing infrastructure into a repo whose ownership tier says otherwise.

### CHECKING OFF THE LAST TASKBOX AT `VERIFY` OBLIGATES `ARCHIVE` BEFORE THE NEXT PUSH
**2026-09-12/13, T352.** The `verify` gate found `tasks.md`'s 12 checkboxes and the spec's 8
acceptance-criteria checkboxes still `- [ ]` despite the work being done, and checked them off
against real evidence — the gate's own job. The very next `git push` failed on the pre-push
`spec-drift` gate: an openspec change that is **100% complete but not yet archived** is exactly
what that gate exists to catch, so completing the checklist inside `verify` created a new,
unavoidable requirement to run `w0m-sdlc-archive` (`openspec archive`) before the accumulated
commits could reach `origin`.
⇒ **This is not a bug in the gate — the fix is to keep going through the lifecycle, not to look
for a way around the block.** `--no-verify` was never on the table; the correct read was "one more
gate stands between here and pushed," not "something is broken." Deploy can (and did) still ship
from local disk in the interim, since this project's deploy pipeline builds from the working tree,
not from `origin`.
⭐ **The tell:** a push blocked immediately after a verify-gate commit that checked off the last
remaining task/AC boxes — check `just spec-drift` / `openspec status` before assuming the failure
is unrelated to what you just committed.

### AN UPSERT'S `ON CONFLICT DO UPDATE` ONLY TOUCHES COLUMNS IN THE PAYLOAD — AN OMITTED ONE KEEPS ITS OLD VALUE
**2026-09-12, T352 (review gate).** `roles.ts`'s `assign` action upserted a `hats` row without
`is_fallback` in the payload. On a fresh `INSERT` that's fine — the column defaults to `false`.
But `INSERT ... ON CONFLICT (profile_id, project_role_id, project_id) DO UPDATE SET col =
excluded.col` only ever sets the columns named in that `SET` clause; a column absent from both the
payload and the `SET` list is left exactly as it was. Re-assigning a profile that currently holds a
system-provisioned fallback hat (`is_fallback = true`) would silently keep it flagged as a fallback
forever, because the UPDATE path never touches that column.
⇒ **Fixed by adding `is_fallback: false` to the upsert payload explicitly** — a deliberate
assignment always clears the fallback flag, on both the insert and the update path.
⭐ **The tell:** an `ON CONFLICT DO UPDATE` whose `SET`/payload list is shorter than the table's
column set, touching a column whose value can legitimately have been set by something other than
this code path (here: a trigger). INSERT-only thinking about a payload is a false comfort once
`ON CONFLICT` enters the picture.

### EPICS MUST BE ROOTED IN OBSIDIAN VAULTS AND BIDIRECTIONALLY SYNCHRONIZED WITH ISSUE TRACKERS
**2026-09-12 (T214, delivery/artemioquierocomer.mx).** When epics exist only as conversational milestone labels, ticket tracking drifts from client deliverables. Injecting `epic: "EPIC-XX"` into ticket frontmatter and maintaining corresponding notes in the client Obsidian vault (`_msg/Epics/`) provides an unbroken traceability chain from client requirements to git commits.

⇒ **Maintain an authoritative mapping from Epic ID to GitHub Milestone and local Obsidian Epic note.** Synchronizers must match milestones by both exact title and canonical prefix (`EPIC-XX`).
⭐ **The tell:** Tickets referencing arbitrary epic names with no corresponding issue tracker milestone or specification note.

### CLIENT ENGAGEMENT RECORDS BELONG IN DEDICATED _msg/ OBSIDIAN VAULTS WITH IN/OUT DIRECTIONALITY
**2026-09-03 (Proposal / T212).** Flat date folders (`2026.07.08/`, `2026.08.31/`) scattered across workspace roots clutter agent context, obscure chronological communication history, and create search friction.

⇒ **Standardize client project communication into a dedicated `_msg/` Obsidian vault with strict directional separation (`YYYY.MM.DD/in/` for client briefs and `out/` for formal quotes and deliverables), linked by a master `Index.md` Map of Content.**
⭐ **The tell:** Multiple date-stamped proposal drafts, chat dumps, and meeting transcripts scattered in workspace root folders.

### GOVERNANCE CONTRACTS MEASURE FROM THE DECLARED ROOT, NOT BY REQUIRING LEAF FILES
**2026-09-03 (T308 / Inventory Correction).** An inventory audit reported six of the seven canonical w0m estate repos as "ungoverned" (`.w0m Contract: No`) because none contained a local `.w0m/sdlc.json`. The estate deliberately governs all seven repos centrally from `wom7web/.w0m/sdlc.json` via its `repos` mapping.

⇒ **Measure governance compliance against the configuration root the policy declares, never an assumed per-repo file presence.** Checking leaf directories for standalone config files reproduces the exact scoping fallacy documented in AGENTS.md.
⭐ **The tell:** An audit script flagging canonical monorepo members or subprojects as unmanaged when a central workspace orchestrator already declares them.

### PER-PROJECT FOLDER PARTITIONING IN SHARED QA TOOLS (JAM.DEV) PREVENTS ARTIFACT CONTAMINATION
**2026-09-12 (Jam Standard).** Recording bug captures and visual proof into the team root in Jam.dev mixed client artifacts (`artemioquierocomer.mx`) with internal estate recordings, making automated triage and ticket linking ambiguous.

⇒ **Scope all visual recordings and bug links to dedicated project folders named after the canonical repo ID (`--folder <project_id>`).** Provide dedicated public intake links (`https://recorder.jam.dev/<id>`) and project-scoped CLI recipes (`just jam-proof`).
⭐ **The tell:** A shared QA dashboard containing an unorganized list of uncategorized recordings from multiple disparate client engagements.

### UNIFIED RESOURCE MONITORING PREVENTS SILENT DISK EXHAUSTION ACROSS HYPERVISORS AND RUNTIMES
**2026-09-11 (Resource Governance Proposal).** Concurrent development across iOS simulators (`simctl`), local LLM weights (`~/.cache/huggingface`, Ollama), hypervisor virtual machines (Tart, UTM), and Docker (`Docker.raw`) silently consumed 838 GB, leaving only 9.5% free disk space and risking hypervisor disk stalls.

⇒ **Monitor storage across all four virtualization and cache pillars centrally (`just resources`), with automated preflight warnings when free host disk space falls below 10%.**
⭐ **The tell:** Build or VM operations failing with obscure I/O or disk space errors while host cleanup scripts only inspect node_modules.

### PURE EVENT-DRIVEN GAMIFICATION OVER PHANTOM TASK-TRACKING HIERARCHIES
**2026-09-17 (T27 / AgDR-0022).** Maintaining a shadow gamification database hierarchy (`adventures`, `raids`, `quests`, `unit_members`) alongside canonical engineering trackers (`TASKS.md`, GitHub PRs, `public.projects`) created 8 empty phantom tables with 0 rows for months, while the live player economy ran independently on `xp_ledger` and `wallets`.

Synchronizing engineering state into a duplicate database task tree creates dual-source drift, schema bloat, and phantom operational overhead. Adopting Model A (Pure Event-Driven Gamification) decouples corporate work (tracked canonically in git/tickets/projects) from gamification (pure internal motivational lens). Real engineering milestones directly invoke `award_gamification_xp` with deterministic idempotency keys and verifiable `source_ref` artifact references into `gamification.xp_ledger` and `wallets`.

⇒ **Gamification layers must be purely event-driven reputation ledgers (`xp_ledger`, `wallets`, `badge_awards`) listening to canonical delivery events, never shadow copies of task-management hierarchies.**
⭐ **The tell:** A gamification schema defining tables like `quests`, `tasks`, or `tickets` that mirror what git repositories or issue trackers already track canonically.

### MULTI-AGENT CONCURRENCY REQUIRES INDIVIDUAL TICKET FILES AND COORDINATED SUBREPO WORKTREES
**2026-09-20 (T411).** Parallel AI agents working simultaneously across the estate collided on two major choke points:
1. `TASKS.md` was a 268 KB monolithic table updated by every agent on every commit, triggering frequent merge conflicts.
2. Spawning git worktrees at the root wrapper (`casualuser/w0m`) only branched the root repo; because estate child repos (`wom7web`, `wom7api`) are git-excluded subdirectories, all agents in different worktrees actually shared the *exact same* unbranched physical working directories, silently colliding on unstaged files and blocking each other's pre-push gates (`state-check` and `openspec validate`).

⇒ **Deconstruct monolithic tracker boards into individual per-ticket files (`.tasks/T##.md`) as the exclusive Source of Truth, treating `TASKS.md` as a purely rendered view (`just tasks-render`). Scope pre-push validation to the branch diff (`--scope-diff`), and orchestrate multi-repo worktrees (`just worktree-agent <id> [subrepos]`) so every agent operates in an isolated physical tree across root and child repos.**
⭐ **The tell:** Agents failing pre-push hooks due to uncommitted draft files left by another agent, or merge conflicts on tracking files (`TASKS.md`) when concurrent PRs touch unrelated code.

### LOCAL MERGE QUEUE (BATCH SIZE 1) PREVENTS MULTI-AGENT COLLISION ON SHARED BRANCHES WITHOUT PRS
**2026-09-24 (T425).** With 2–3 autonomous coding agents operating in dedicated physical worktrees, committing directly to `beta` in the shared main checkout causes push races, non-fast-forward rejections, and accidental cross-ticket staging when agents use `git add -A`.

A local merge queue of batch size 1 (`scripts/land.py` via `just land <worktree>` and `just land root --ticket T<id>`) eliminates this by enforcing single-committer serialization via an exclusive `.git/w0m-land.lock`. The landing agent rebases its branch onto `beta` inside its own worktree, runs the pre-push quality gates there, and fast-forwards `beta` in the main checkout with `--ff-only`. Root landing stages only explicit ticket artifacts, discards agent edits to generated tracker views (`TASKS.md`, `STATE.md`) in favor of deterministic regeneration, and blocks ticket-ID races against `beta`.

⇒ **Serialize multi-agent integration to `beta` through a local merge queue (`just land`); agents rebase and verify locally in worktrees, and root commits stage only unit paths without `git add -A`.**
⭐ **The tell:** Frequent `--ff-only` merge rejections, uncommitted files from other agents swept into root commits, or merge conflicts on rendered tracker views.

### A COUNT OF DIRECTORIES IS NOT A MEASUREMENT OF WHAT THEY HOLD
**2026-09-30 (T481).** A report said 30 release worktrees were using about 90 GB and the disk was at risk. The 30 was a count of entries in
`~/.w0m/releases`, and the 3 GB was the size of ONE old worktree, multiplied. Measured properly afterwards, `releases` was 0.00 GB: all 30 entries
were manifest-only and none had a worktree (`git worktree list` and `du` of the whole set say so in seconds). The claim reached the owner,
changed what was proposed (a cleanup, a retention rule sized against a full disk), and was only corrected later.

⇒ **Before stating a size, a count or a cost about a set, measure the set itself (`du` of the whole directory, a listing that shows each entry is
the thing you named). Never multiply one sample by a count.**
⭐ **The tell:** a figure built as `N x one_example`, or a number of directories reported as if it were the number of the large objects inside them.

### A PROBE THAT SURVIVES A DELIBERATE BREAK IS A MISSING PROBE
**2026-09-30 (T481).** The retention rule for release worktrees deletes things, so each probe was checked by breaking the rule on purpose, one branch
at a time. Four of five breaks turned named probes red. The fifth ("the deployed release that is kept need not still have a worktree") left all 60
probes green: the suite passed with a wrong rule. It was found only because the break was run, and a new probe now closes it. A first version of a
second probe also crashed instead of failing, so a regression would have shown as an error with no named case.

⇒ **After writing probes for any rule that deletes or refuses, break each branch of the rule in turn and require a NAMED probe to go red. A survivor
is a case nobody wrote. Make the break fail a probe, not crash the run.**
⭐ **The tell:** a deleting rule whose probes were only ever run against the correct code, or a probe count that rose without any break being tried.

### EDITING A GATE SCRIPT MEANS RUNNING EVERY TEST THAT READS IT, NOT THE ONE NAMED AFTER IT
**2026-10-01 (T510).** Adding probes to `authz_probe_suite.py`, I ran its own test file, `test_authz_probe_suite.py`, and it was green. A second test, `test_authz_public_views.py`, also reads that file as text and
asserts that no declared view name appears in it ("two authorities, the bucket-list failure", T199 AC1). My probe X25 named `public_team_members`, so that test failed. Every commit hook and every push passed, because the pre-push
tier is a handful of one-second ratchets and `py-test` (about 2.5 minutes) is not in it. The first sign was the deploy itself, six minutes into its test tier. The probe was also redundant: G3c already scans every declared view
for email and `resume_url` columns, so the fix was to delete mine, not to patch it.

⇒ **Before committing a change to a script, list the tests that name it (`git grep -l <file> -- project/scripts/tests`) and run all of them. A green test file named after the script is not evidence that the script is safe to change.**
⇒ **Before adding a check, look for the guard that already owns that question.** A second, narrower copy is the thing the estate's SSOT tests exist to refuse.
⭐ **The tell:** a test file you did not open that opens the file you just edited; or a new check whose subject (a view, a table, a list) already has a declaration file somewhere.

### A RELEASE SEES ONLY WHAT IS PUSHED, AND "ALL REPOS PUSHED" MUST BE COUNTED FROM THE MANIFEST, NOT FROM MEMORY
**2026-10-01 (T510 / T392).** A deploy failed its blocking `decisions` suite because `wom7ava` and `wom7clips` each held one local commit that had never been pushed. The suite passed in the working checkout, where the line existed, and
failed in the release worktree, which is cut from `origin/beta` of every repo in the release manifest. I had just reported "all three repos pushed" after checking the three repos I was working in; the manifest lists ten. The release
worktree did exactly its job: it refused to let a local-only change count as tested. The mistake was mine, in how I counted.

⇒ **Check push state by iterating the repo list the release itself uses (`manifest.json`, or `estate_repos()`), and print the count checked. Never report "everything is pushed" from a list you typed.**
⇒ **A test that passes in the checkout and fails in the release worktree is a finding about unpushed or untracked state first, and a flaky test last.**
⭐ **The tell:** a suite green locally and red in `~/.w0m/releases/<v>/w0m`; or a status report naming fewer repos than the manifest.

### THE DEPLOY'S TEST TIER IS THE ONLY GATE THAT RUNS EVERYTHING: RUN ITS BLOCKING SUITES IN `stable` BEFORE YOU START A DEPLOY
**2026-10-01 (T481 / T510).** The pre-flight inside `deploy-all` (`--prepush`, `state-check`) passed, and only the `test` gate, minutes later, ran the 215 suites, of which `py-test` and `decisions` are blocking. Nothing about the failure
was related to the database: the chain runs `test` before `db-migrate`, and neither failing suite touches the database. Moving the migration earlier or later changes nothing about suites that never read it.

⇒ **After pushing and before a deploy, sync `stable` (a mirror of `origin/beta`) and run the blocking suites there (`py-test`, `decisions-test`, `suites-drift`). It costs about three minutes and costs no Touch ID, no release cut and no worktree.**
⇒ **Do not "fix" a test failure by reordering the deploy chain. Find which suite is blocking (`blocking` in `test-suites.json`) and why; the transcript names it.**
⭐ **The tell:** "2 blocking suite(s) failed" in a deploy that had already passed its pre-flight, or a question like "is it because the database is migrated later" about a suite that does not query the database.

---


### A CLEANUP THAT RUNS AFTER A STEP CANNOT HOLD A CAP ON THAT STEP
**2026-10-01 (T481).** The release-worktree rule was "keep 5 and the newest successful one", pruned in two places: before the cut and after a successful deploy. The owner meant "5 in total".
Running every sequence of success, failure and interrupted deploy through the rule showed it held up to 6 (1,024 of 4,608 outcome sequences went over 5), and that a prune placed only after the
deploy is worse than it looks: a failure returns before it and an interrupt never reaches it, so each such run adds a worktree that nothing removes (7 after seven interruptions). The only
placement that never went over the cap was a prune BEFORE the cut that reserves the place for the new release.

⇒ **A cap on something a step adds is enforced before that step, reserving its place, never after it. Decide the placement by running every outcome sequence (success, failure, interrupt)
through the rule, not by argument.**
⭐ **The tell:** a retention or quota rule whose cleanup lives in the success path of the thing it limits.

### AN OWNER DECISION COMES WITH ITS CONTEXT: ABOUT THREE LINES OF WHY, NOT A BARE QUESTION
**2026-10-01 (T493, Hero Epic).** I ended a research step with three one-line "decisions I need" (re-scope an acceptance criterion, split a ticket, make a sync fail closed). Each was clear to me and opaque to the owner: what the rows were, what the choice would
change and what it would cost were all in my head and in the ticket, not in the question. The owner asked for more detail on that list and on every later one, and not to be asked twice.

⇒ **Every question for the owner carries a short paragraph, about three lines: what the thing is in plain words, what the data or code showed, what each answer changes and costs. Then the recommended answer first, with its weight (cost, risk, what it unblocks). Put the
context in the first message, so no clarifying round is needed. A bare one-liner that the owner must open a ticket to understand is not a question yet.**
⭐ **The tell:** a numbered list of decisions where an item cannot be understood without opening the ticket, or where the owner's reply is "what does this mean".

### A DEPENDENCY OVERRIDE NEEDS AN UPPER BOUND, AND THE FIX GOES IN THE FILE PNPM ACTUALLY READS
**2026-10-01 (Hero Epic, wom7web).** The commit hook (osv-scanner) blocked every commit on `devalue@5.9.2` (7 advisories, fixed in 5.9.3). The fix is a pnpm override, so I added `devalue@<5.9.3: ">=5.9.3"` to `pnpm-workspace.yaml`, where the other devalue rules live, and the
lockfile did not change: the rules that take effect are `pnpm.overrides` in `package.json`, and the lockfile's own override list is the proof. Raising that line to a plain `">=5.9.3"` then resolved `devalue@6.0.2`, a new major with a Node 22.17 engine floor, under Astro and Svelte.
The repo already bounds some overrides (`undici <8`, `js-yaml <5`, `nanoid <6`); this one had not been.

⇒ **A `>=` override with no upper bound picks the newest major, not the fix. Bound it to the line you are patching (`>=5.9.3 <6`), and after editing check that the lockfile diff is only the intended package and that the lockfile's `overrides:` block shows your rule; a rule that does not appear there is not in force.**
⭐ **The tell:** a security fix whose lockfile diff shows a major version jump, or an override edit that leaves `pnpm-lock.yaml` unchanged.

### A SCOPED GATE CAN STOP BEING ABLE TO SEE ITS OWN INPUTS WHEN THE FILES MOVE REPOS
**2026-10-01 (T527).** `state-check` failed at the deploy preflight because two tickets I created had no row on the rendered board (`TASKS.md`). Three repos had just been pushed without complaint. The pre-push step runs `state-check` only when the push range touches `STATE.md`, `TASKS.md` or
`.tasks/`, looked for in wom7web's range; those files moved to the root repo, so in wom7web the condition can never be true, and the root repo has no such step. The gate was declared, green and unreachable. Separately, I created tickets and never re-rendered the board, because
nothing in the ticket path does it.

⇒ **A hook that skips unless certain files changed must be tested against the repo it actually reads: if none of its trigger paths exist there, it is a dead branch that prints "skipped" forever. After creating or retitling a ticket run `just tasks-render`, then `just state-save`, before pushing.**
⭐ **The tell:** a gate that has only ever printed "untouched in push range", or a deploy preflight failing on a fact every push had passed.

### A MUTATION RUN LEAVES THE MUTATED CODE IN `__pycache__`: CLEAR IT BEFORE TRUSTING A DIFFERENT RUNNER
**2026-10-01 (T481).** I proved a test by breaking the script under test 11 times and restoring the file. The restore was byte-identical, but one test then failed under pytest while it passed under `python3` and `unittest`. The cause was a stale `.pyc` of a mutated version, still newer than the restored
source's recorded stamp. Deleting `project/scripts/__pycache__/push_cadence_check*.pyc` made it pass. I then cleared the bytecode of every other module I had mutated that day (`release`, `cp_feature_index`, `sync_epic_vocabulary`) and re-ran their tests from a clean cache: all green. A first mutation harness also left the file broken when one anchor did not match, because the restore was not in a `finally`.

⇒ **After any mutation run: restore the file inside a `finally`, delete the module's `__pycache__` entries, and re-run the tests under a SECOND runner (pytest if you used unittest, or `python3 -B`). A green result from the same process that did the mutating proves less than one from a clean start.**
⭐ **The tell:** a test that passes under one runner and fails under another right after a mutation session, with the source file identical to the good copy.

### A TEST THAT READS THE ENVIRONMENT MUST SET IT, NOT INHERIT IT: THE DEPLOY RUNS EVERY SUITE WITH ITS OWN VARIABLES
**2026-10-01 (T481).** I fixed `push-cadence` so the stable worktree counted as a detached mirror, with 11 tests. Hand runs, pytest and the stable run of the whole blocking tier all passed, and the next deploy stopped at the blocking `py-test` suite on exactly two of them. `just deploy` exports `W0M_RELEASE_WORKTREE=1` to everything it runs, and the code under test reads that variable; my tests patched
the environment with `clear=False`, so they inherited the flag, saw "release worktree" where they expected "stable worktree" or "unknown", and failed. They passed everywhere except the one place that mattered. The stable run could not show it because stable does not set the flag.

⇒ **A test of code that reads an environment variable sets that variable to the exact state it is testing, removing it when it should be absent (`patch.dict(..., clear=True)` over a copy without it). After writing one, run the suite with the deploy's variables set (`W0M_RELEASE_WORKTREE=1`) as well as unset, under both runners. Mutation-test the clearing itself: the break "flag not cleared" must fail under the flag.**
⭐ **The tell:** a suite that is green by hand, in pytest and in stable, and red only inside the deploy's test gate; or a test that patches `os.environ` without `clear=True` for a variable the code branches on.

### A DERIVED FILE GENERATED IN A SCRATCH COPY CARRIES THE COPY'S PATHS: GREP FOR THE SCRATCH ROOT BEFORE COMMITTING IT
**2026-10-01 (Hero Epic).** To keep another agent's uncommitted edits out of `STATE.md`, I regenerated it in a scratch view (`git archive HEAD` plus my files) and copied the result back. The generator writes absolute ticket links from the root it discovers, which in the view was my scratchpad, so the committed file held 20 links into `/private/tmp/claude-503/...`. It was pushed once and committed again before I saw it. Nothing caught it: the view's own `state-check` passed (links resolve there), the live `state-check` does not compare link paths, and the hooks do not look at them. It surfaced only because the diff of the next regeneration showed the old lines starting with `/private/tmp`. The ticket list is exactly the surface the owner reads, and dead absolute links in it were reported once before (2026-08-16).

⇒ **After generating any file in a scratch copy, grep it for the scratch root before staging, and check that every link it contains resolves in the real tree. A check that passes inside the copy proves the copy.**
⭐ **The tell:** a generated file whose diff shows a path prefix changing wholesale, or a derived file produced anywhere other than the checkout it will live in.

### ⛔ EDIT THE CANONICAL COPY OF A SKILL, NEVER THE INSTALLED ONE
**2026-10-06, T532.**

A commit added `osv-scanner.toml` to `wom7web/.agents/skills/mmd-validate/` (the **active** copy) only. The next sync saw a file present in the active copy and absent from canonical, so the skills suite failed ("canonical and active copies agree": 1 !== 0) and the lockfile's integrity hash for `mmd-validate` was stale.

⇒ **Change `wom7skills/skills/<name>/`, then `pnpm version:stamp`, `pnpm skills:sync`, `just skill relock <name>` (re-stamp; `relock-all` is for a NEW skill), and commit canonical, active and the lock together.** Run `just skill check` and `pnpm skills:check` before landing.
⭐ **The tell:** `git status` shows a file under `.agents/skills/` that is not under `wom7skills/skills/`.

### ⛔ AFTER ANY TICKET CREATE OR EDIT, REGENERATE THE DERIVED FILES IN ORDER AND RUN `state-check` LAST
**2026-10-06, T548 and T503.**

Tickets T545 to T548 were committed without `just tasks-render`, so `TASKS.md` had no rows for them, and ticket T532 was `done` while its board row said `in-progress` (`tasks-bounds` treats that as a blocking "truth" finding). `STATE.md` was stale because T548 was created after `state-save`; `state-check` is the first stage of the deploy, so it was the first thing to fail. Fixing one derived file can re-stale another.

⇒ **Order: create/edit tickets, `just tasks-render`, `just state-save`, `just decisions`, then `just state-check` last**, in a COMPLETE agent tree (never a partial one). A pre-commit hook rewrites ticket frontmatter (`x_*` fields): commit its changes too, or the tree is dirty and `agent-tree-land` refuses.
⭐ **The tell:** a `.tasks/T*.md` in the diff with no `TASKS.md` change beside it.
⚠️ `STATE.md` ticket links currently embed the generating tree's absolute path (T548).


## 6. UI/UX & Interactions

### CARD DRAG-AND-DROP CONTAINERS REQUIRE FLOATING HIGH-CONTRAST HANDLES OVER MEDIA HEADERS
**2026-09-12 (T216, delivery/artemioquierocomer.mx).** Adding rich media headers (dish photographs, thumbnails) to cards managed by `svelte-dnd-action` displaced in-flow drag handles below the fold, breaking drag ergonomics and distorting media bounding boxes.

⇒ **Float drag handles as an absolute badge at the top-left of the media container (`absolute top-2 left-2 z-10 bg-black/60 hover:bg-black/80 backdrop-blur-md text-white/90 border border-white/10`).** This guarantees immediate touch/mouse target visibility across light and dark imagery without visual layout shift.
⭐ **The tell:** Adding an image header to an interactive grid card and leaving the drag handle inside the text body below the image.

### MULTI-TIER STICKY HEADERS REQUIRE COORDINATE SYNCHRONIZATION AND SCROLL-LISTENER ISOLATION
**2026-09-12 (T218, delivery/artemioquierocomer.mx).** Injecting an expandable mobile search input (Row 2, 44px) increased total header height from 56px to 100px. Downstream sticky category headers remained docked at static 66px offsets, causing titles to slide behind the search pill. Concurrently, an uncoordinated hero scroll listener detected micro-scrolls on search input focus and prematurely collapsed the search input.

⇒ **Calculate and broadcast downstream sticky offsets atomically via CSS variables (`--row3-sticky-top`, `--row4-sticky-top`), and strictly gate passive scroll-collapse listeners behind header merge state (`!$isHeaderMerged`).**
⭐ **The tell:** Sticky category titles colliding with expanded search bars on mobile, or search inputs instantly collapsing on focus because an inactive hero scroll listener fired.

### CONTEXT-LOCAL DELIVERY HAT SWITCHERS MUST ENFORCE SINGLE-TOKEN PAYLOAD ATOMICITY
**2026-09-18 (T54).** Supporting multi-project delivery roles (`role@project`) alongside global administrative hats previously risked creating split session state (a disjoint `sb-active-project` cookie vs `sb-active-role`), leading to desynchronization when exiting hats or switching projects.

Embedding `projectId`, `projectTitle`, `projectRoleId`, `projectRoleName`, and `projectRoleSlug` directly inside the signed `ActiveRolePayload` (`sb-active-role`) guarantees atomic role and project transitions in a single cryptographically signed cookie. Furthermore, keeping project hat switching context-local within the portal (`redirectTo = "/"`) avoids unnecessary cross-domain SSO dances required only for global application jumps (e.g. `cp.w0m.xyz` ↔ `webomage.com`).

⇒ **Embed hierarchical resource scope directly within the signed role token payload, and keep resource-scoped hat switches context-local to the active portal.**
⭐ **The tell:** Introducing disjoint cookies (`sb-active-role` and `sb-active-project`) that can drift out of sync on partial failure or reset.

### EMBEDDED DOCUMENT STYLING IN WORKSPACE INTERFACES REQUIRES ROOT CONTAINER SCOPING
**2026-09-23 (T165, CP Resume Studio).** Integrating production branding CSS templates (`ats-plain`, `classic`, `modern`, etc.) into an interactive CP admin dashboard component caused document-level selectors (`body`, `h1`, `a`, typography) to bleed into the global admin interface, distorting navigation and page layouts.

⇒ **Scope all document stylesheet rules under an explicit container class (`.resume-sheet.template-*`), and confine document-wide pagination rules (`@page`, `@media print`) strictly inside print media queries.**
⭐ **The tell:** Importing document stylesheets into an interactive workspace island without an enclosing container class namespace.

---

## 7. Performance & Edge Integration

### DEFER AUXILIARY AND DIAGNOSTIC FLOATING WIDGETS WITH client:idle TO PROTECT LCP AND TTI
**2026-09-12 (T217, delivery/artemioquierocomer.mx).** Global floating bug report widgets (`BugReportWidget.svelte`) mounted with `client:load` forced immediate bundle evaluation and event listener registration during initial page load, degrading Largest Contentful Paint (LCP) and Time to Interactive (TTI).

⇒ **Hydrate auxiliary diagnostic and floating support widgets with `client:idle` (e.g. `<BugReportWidget client:idle />`).** This defers script execution until the main browser thread is idle, ensuring zero impact on initial storefront rendering or Core Web Vitals.
⭐ **The tell:** Mounting non-critical administrative, feedback, or diagnostic islands with `client:load` on high-traffic storefront layouts.

### ZERO-DEPENDENCY CANONICAL MANIFEST FOR CROSS-RUNTIME SHARING (DENO EDGE + BROWSER)
**2026-09-17 (T21).** Unifying LLM tool declarations across client-side WebMCP and server-side Supabase Edge Functions (`chat-core.ts`) required a single source of truth without runtime import divergences.

Node/browser modules that import bundler-specific utilities or Node globals fail to resolve or typecheck in Deno edge functions when symlinked. Keeping `manifest.ts` pure zero-dependency TypeScript with explicit schema typing allows direct symlink importing by Deno (`supabase/functions/_shared/tool-manifest.ts`) and Node/Vite packages simultaneously, preventing schema drift while passing both `deno-check` and monorepo `typecheck`.

⇒ **Declare cross-runtime tool contracts and schemas in pure, zero-dependency modules that rely only on standard TypeScript types.**
⭐ **The tell:** Duplicating tool parameter schemas between edge functions and client packages because an import map or bundler plugin fails in Deno.

### LOCAL INFERENCE RUNTIMES REQUIRE STRICT CONTEXT BOUNDING TO PREVENT METAL THREADGROUP CRASHES
**2026-09-17 (T153 / Local Gemma 4 on Apple Silicon oMLX).** Routing Claude Code directly to local `gemma-4-e4b-it-4bit` on oMLX inside a monorepo workspace loaded `CLAUDE.md`, `AGENTS.md`, and 112 skills, producing a 19,666-token prompt. In oMLX, TurboQuant's KV-cache quantization kernel requested a threadgroup size of 1024, violating Apple Silicon Metal's limit (`Thread group size (1024) is greater than the maximum allowed threads per threadgroup (640)`). This locked the Metal command queue with `kIOGPUCommandBufferCallbackErrorSubmissionsIgnored`, causing all subsequent requests to fast-fail in ~300ms and return empty text `[{"type":"text","text":""}]`, which appeared in Orca as an instant `* Cooked for 1s · done`.

⇒ **Local small-model inference (4B–12B) must enforce a lean prompt budget (< 2,000–3,000 tokens) using isolated config directories (`CLAUDE_CONFIG_DIR`), strict MCP server limits (`--strict-mcp-config`), and skill pruning.** Never point an unconstrained cloud-agent profile at a local GPU inference daemon.
⭐ **The tell:** An interactive agent session responding instantly with `* Cooked for 1s · done` or empty cogitation, coinciding with Metal buffer submissions being ignored in `omlx.log`.
⚠️ Cloud models (Sonnet 3.7) easily handle 200k tokens via prompt caching; context bounding applies specifically when routing to local hardware.

### UNIFIED MEMORY CEILINGS AND METAL PAGING DEATH SPIRAL IN LOCAL LLM INFERENCE
**2026-09-18 (T153 / Local Gemma 4 on Apple Silicon oMLX).** Running multi-model local inference on a 32 GB unified memory Mac without strict allocation ceilings allowed oMLX 0.5.3 to balloon to 22 GB resident RAM + 12 GB compressed memory. This pushed the operating system into 20.6 GB of SSD disk swap (`vm.swapusage`) and triggered over 67 million swapouts. On Apple Silicon, unified memory bandwidth dropped from 200 GB/s to disk paging speeds (~100 MB/s), causing generation throughput to collapse from 30 tok/s down to 0.02 tok/s (generating 16 tokens required 2,343 seconds / 39 minutes).

⇒ **Local inference daemons must enforce an explicit physical RAM ceiling (`memory_guard_tier: safe`, `memory_guard_custom_ceiling_gb: 10.0`) and prohibit concurrent loading of unquantized auxiliary models.** Weights and active KV caches must remain 100% resident in physical RAM; paging even 1 GB of model weights to swap induces an unrecoverable latency death spiral.
⭐ **The tell:** `omlx-server` CPU dropping to near 0% while load average surges above 20 and `vm.swapusage` shows tens of gigabytes of encrypted disk swap.

### THINKING BUDGET SUPPRESSION FOR LOW-LATENCY LOCAL TOOL-CALLING AGENTS
**2026-09-18 (T153 / Local Gemma 4 in Orca Desktop).** In multi-turn coding loops (`/w0m-tasks`), local Gemma 4 hung for 19m 13s in Orca emitting `* Boondoggling... (19m 13s · 594 tokens · deep in thought)`. Small instruction-tuned models with thinking enabled allocate large default thinking budgets before generating tool calls or responses. Under local inference speeds (10–30 tok/s), spending 500–1,000 tokens on hidden cogitation consumes 30–60 seconds per turn; when combined with memory paging, it locks the UI for tens of minutes.

⇒ **Explicitly disable thinking budgets for local tool-calling models (`thinking_budget_enabled: false`, `thinking_budget_tokens: 0`, `enable_thinking: false` in `model_settings.json`).** Coding and tool routing on 4B–12B models must emit tool calls and structured outputs immediately without multi-turn latent chain-of-thought delays.
⭐ **The tell:** An agent UI hanging on `Boondoggling... (Xm Ys · 500+ tokens · deep in thought)` before any bash or editing tool execution begins.

### DUAL-PORT PROXY TOPOLOGY FOR DISJOINT LOCAL AND CLOUD AGENT UPSTREAMS
**2026-09-18 (T153 / Headroom + Claude Code + oMLX).** Headroom proxies bind a single static upstream target URL per protocol per process instance (`api_targets.anthropic`). Attempting to share port 8787 between Cloud Claude Code (Anthropic API with OAuth) and Local Claude Code (oMLX with local dummy key) forced an impossible mutually exclusive configuration: repointing 8787 to oMLX broke Cloud Claude, while leaving 8787 pointing to Anthropic broke Local Gemma.

⇒ **Partition disparate agent upstreams across dedicated, persistent daemon ports via LaunchAgents: port 8787 for Cloud (`sh.brew.headroom` → Anthropic) and port 8788 for Local (`sh.brew.headroom-local` → oMLX:8888).** Both daemons operate simultaneously without cross-talk, enabling instant switching between cloud and offline local development.
⭐ **The tell:** Local agents receiving 401 Unauthorized from Anthropic Cloud when attempting to talk to local inference, or cloud agents receiving local model errors when proxy targets are manually toggled in place.

### HEADROOM TARGET INJECTION ROUTING TRAP AND CONTEXT LIMIT COLLISION
**2026-09-18 (Headroom Proxy + Cloud Claude + oMLX).** In Headroom's unified handler (`headroom/proxy/handlers/anthropic.py`), defining `OMLX_TARGET_API_URL` causes any request whose model name does not strictly begin with cloud prefixes (`claude-3`, `claude-opus`, `claude-haiku`, `claude-sonnet-4`, `claude-2`) to evaluate `not is_cloud` as `True` and divert the connection to local oMLX (`http://127.0.0.1:8888`). When standard Claude Code sends shorthand `"model": "sonnet"` through port 8787, the cloud session is silently routed into local hardware. When user context (such as pasted images or multi-file prompts) exceeds the local engine's 32,768 hardware context limit, oMLX rejects the turn with `API Error: 400 Prompt too long: 45396 tokens exceeds max context window of 32768 tokens`, baffling users who assume they are talking to Anthropic Cloud's 200k window.

⇒ **Never inject `OMLX_TARGET_API_URL` or fallback routing logic into the primary cloud proxy daemon.** Cloud proxies must remain strictly dedicated to upstream cloud endpoints with zero local interception. Keep local proxies on dedicated ports (8788) with explicit upstream parameters (`--anthropic-api-url http://127.0.0.1:8888`).
⭐ **The tell:** Cloud Claude sessions failing with `API Error: 400 Prompt too long: ... exceeds max context window of 32768 tokens` even though Anthropic Cloud supports 200,000 tokens.

### MODEL-AGNOSTIC LOCAL AGENT IDENTITY (CLAUDE-OMLX) FOR SEAMLESS WEIGHT SWAPPING
**2026-09-18 (oMLX + Claude Code Wrappers).** Naming local Claude configurations, CLI flags, and settings after specific ephemeral model checkpoints (e.g. `claude-sonnet-5`, `gemma4`) tightly couples client scripts, launch wrappers, and desktop IDE tabs to fixed model weights. When Gemma 4 proved memory-bound and was replaced by Qwen 2.5 Coder 7B (54 tok/s, 4.17 GB RAM), all wrapper scripts and settings files risked requiring synchronized renaming, causing confusion with Claude's official Sonnet naming.

⇒ **Standardize local agent identity on a universal alias (`claude-omlx`) across all configuration surfaces (`~/.openclaude/settings.json`, wrapper scripts, desktop tabs).** In the local inference server (`oMLX`), map `model_alias: "claude-omlx"` to whichever underlying weights are active. Swapping between 7B, 12B, MoE, or vision checkpoints requires only changing the backend alias, while all developer tooling remains stable.
⭐ **The tell:** Hardcoded model names like `claude-sonnet-5` in local wrapper scripts causing confusion with cloud Sonnet tiers and requiring multi-file rewrites when testing new quantized models.

### DISJOINT CLIENT REMEDIATION: NEVER BULK-MIGRATE LEGACY SUPABASE IN BROWSER SVELTE RUNTIMES
**2026-09-21 (T413 / Build hints analyzer & automated remediation).** TypeScript deprecation `ts(6385)` flags legacy `import { supabase }` across server pages (`.astro`, `.ts`) and client components (`.svelte`). While server-side endpoints require explicit `staffAdminClient` or `adminClient()`, replacing `supabase` with `staffAdminClient` inside `.svelte` components will throw at runtime in the browser (`adminClient() called in the browser. The service-role key must never be bundled — use userClient(accessToken)`). Automated codemods must guard by file extension: server routes (`.astro`, `.ts`) receive `staffAdminClient`/`adminClient()`, while browser Svelte components continue using `userClient()` or component props.

⇒ **Codemods targeting privilege refactors must partition by runtime execution boundary.** Guard against modifying `.svelte` client files with privileged server-side clients.
⭐ **The tell:** A build-clean refactor that introduces browser runtime crashes on mount due to `adminClient()` invocation in the browser bundle.

### ZERO SHADOW SYMLINKS AND CLEAN CUTOVER OVER BACKWARD-COMPATIBILITY SHIMS
**2026-09-21 (T414 / AgDR-0025 — Central Registers and Estate Tooling Elevation).** When elevating canonical registers (`LESSONS.md`, `STATE.md`, `ROADMAP.md`, `TECH-DEBT.md`) or tooling from subprojects (`wom7web`, `wom7api`) to the workspace root (`@wom`), leaving legacy symlinks behind creates "shadow files" that defeat the single source of truth. Shadow symlinks cause duplicated search results, mask missing references, confuse git ignore checkers, and act as unobservable silent fallbacks. Similarly, writing fallback search ladders (`if (root / path).exists(): ... elif (web / path).exists(): ...`) keeps dead paths artificially alive and encourages permanent drift.

⇒ **Enforce strict single-source-of-truth invariants: clean cutover over shims, zero shadow symlinks, and fail closed immediately if a canonical file is missing (AgDR-0025).**
- When relocating an estate file to the root, delete the old file completely across all repos in the same commit.
- Update 100% of callers, policy files, and configurations atomically to address the new canonical root path.
- Subproject tools like `mypy` running inside member repos must resolve root-level Python scripts via explicit config (`mypy_path = ../scripts` in `mypy.ini`) rather than relying on local symlinks.
⭐ **The tell:** A tool searching multiple legacy locations sequentially, or `git diff` / `grep` finding two identical files under different directory paths because a symlink was left in place "for backward compatibility".

### STATIC DESIGN CHOICES BELONG IN CODE, NEVER IN RUNTIME SSR DATABASE QUERIES
**2026-09-25 (T452 / Fixed Warp Background).** Root layouts across `web` and `cp` queried `site_settings` and `slide_config` via Supabase SSR on every page request just to resolve a background animation scene and palette. Because the owner decided Warp is the sole canonical background, querying the database and Cloudflare KV on every initial render added unnecessary SSR latency, database connection pressure, theme flash on slow connections, and fragile client-server state synchronization.

⇒ **Hardcode settled, canonical visual constants (`ACTIVE_BACKGROUND`) directly into shared packages (`@webomage/lib/background`) and eliminate runtime database queries from root SSR layouts.**
- Mark obsolete scenes and modes as `@deprecated` and disable them in administrative management UIs without deleting legacy code or preview routes.
- Guard layout render paths with automated unit test AST/text scans (`background.spec.ts`) asserting that layout templates and manager components never import database clients or invoke `getPublicSettings()`.
⭐ **The tell:** A root layout (`Layout.astro`) performing an `await` database query on every page load to retrieve visual configuration (theme, background, colors) that is actually an invariant product choice.

---

## 8. Open Source & External PRs

### MANDATORY UPSTREAM PRIOR-ART AND ISSUE/PR DISCOVERY BEFORE CREATION
**2026-09-21 (Open Source / Upstream Contributions & w0m-prs).** When submitting upstream PR #2085 to `oraios/serena` for Astro language server support, maintainers noted two earlier unfinished Astro PRs (#886 from Feb 2026 and #1669 from July 2026) that had used dual-server TypeScript companion architectures. While PR #2085 was intentionally designed as a lean, single-process server (and the earlier PRs had stalled on an unmerged base class #829, merge conflicts, and unsigned CLAs), the lack of pre-flight search meant the initial PR description failed to cite prior art or proactively justify the architectural departure, leading to review friction. Conversely, on `stablyai/orca`, performing pre-flight searches for mobile orientation and theme bugs surfaced active PRs #21191 and #19599, preventing redundant PR creation and enabling targeted, high-value validation and patches.

⇒ **Always search open AND closed issues and pull requests (`gh pr list --state all --search "<keywords>"`, `gh issue list --state all --search "<keywords>"`, or `just prs search`) before opening an upstream PR or issue.**
- **If an active PR exists**: Do not open a duplicate PR. Test it, validate behavior, and contribute constructive review findings or targeted patches directly.
- **If stalled/closed PRs exist**: Inspect why they stalled (unmerged dependencies, CLA blocks, conflicts, architecture). Citing them in the PR body is mandatory: explain why they are superseded, contrast architectural trade-offs upfront (e.g. single vs. companion server), and address historical design concerns preemptively.
- **If an open issue exists**: Link it in the PR description (`Fixes #123` / `Addresses #123`) and announce the PR on the issue.
⭐ **The tell:** A maintainer asking in review: *"There are already two other PRs for X (#886, #1669) using architecture Y, why does this PR do Z?"*

### NEVER CACHE TRANSIENT OR EMPTY INITIALIZATION RESPONSES IN LSP/INDEXING SUBSYSTEMS
**2026-09-22 (Serena PR #2085 / SolidLanguageServer).** Language servers (Nextflow, Lean, Kotlin, Astro) defer AST parsing and full symbol resolution during startup. Calling `get_document_symbols` immediately upon document open returns an empty list `[]`. Persisting `[]` in the document symbols cache permanently poisoned future lookups: subsequent queries returned the cached empty list instead of querying the fully initialized server, breaking downstream callers and causing test flakiness.

⇒ **Never persist empty results (`[]` or null) from language server requests during startup into durable cache maps.** Only populate the cache on non-empty results (`if result: self._symbols_cache[path] = result`), or mark empty results with an explicit transient flag that forces re-querying until indexing completion is affirmed.
⭐ **The tell:** A test or feature asserting `len(symbols) > 0` that fails intermittently across test suites, but passes when run in isolation or after inserting a sleep prior to the first query.

### BOUNDED DEADLINE POLLING OVER RIGID ASSERTIONS FOR ASYNCHRONOUS MULTI-PROCESS READINESS
**2026-09-22 (Serena PR #2085 & Orca PRs #21157 / #21148).** Integration tests across child processes (LSP daemon workers, Electron renderer IPC) failed intermittently on loaded CI runners (especially GitHub Actions Windows and macOS runners) when using single immediate assertions or fixed `sleep(1)` calls. The child process took 1.2s instead of 0.8s, causing assertions to evaluate before readiness and fail with 0 results.

⇒ **Always synchronize cross-process states with bounded monotonic deadline polling rather than fixed sleeps or single assertions.**
```python
deadline = time.monotonic() + timeout_seconds
while time.monotonic() < deadline:
    if condition_met():
        break
    time.sleep(poll_interval)
assert condition_met()
```
⭐ **The tell:** A test that passes 100% locally in 200ms but flakes on CI runners with "expected count > 0, got 0".

### STRICT TYPE NARROWING FOR SUBCLASS LIFECYCLES UNDER STATIC CHECKERS (TY / MYPY)
**2026-09-22 (Serena PR #2085 / Nextflow Test Fixtures).** When inspecting or testing subclass-specific properties (e.g. `_ts_server_started`) on an instance typed as base `SolidLanguageServer`, checking `hasattr(ls, "_ts_server_started")` satisfied runtime Python, but strict type checkers (`ty`, `mypy --strict`) rejected the attribute access in CI: `Property '_ts_server_started' does not exist on type 'SolidLanguageServer'`.

⇒ **Narrow subclass instances explicitly with `assert isinstance(ls, TargetSubclass)` before accessing subclass properties, or define abstract hooks on the base protocol.** Static type checkers cannot infer attribute existence from `hasattr()`.
⭐ **The tell:** CI failing on a strict type check step on code guarded by `if hasattr(obj, "field"): obj.field`.

### CONFIGURATION PROTOCOL WIRE CONTRACTS: RETURN EMPTY ARRAYS FOR PLURAL SETTINGS
**2026-09-22 (Serena PR #2085 / Astro Volar LSP Integration).** When `AstroLanguageServer` responded to `workspace/configuration` requests, returning `{}` or omitting keys for plural settings like `html.customData` or `css.customData` caused the underlying Volar HTML plugin to crash with `TypeError: customData is not iterable`.

⇒ **Wire protocol handlers answering client/server configuration requests must return empty iterables (`[]`) rather than empty objects (`{}`) or undefined for array-typed configuration sections.**
⭐ **The tell:** An LSP worker process terminating unexpectedly with `TypeError: ... is not iterable` during initial workspace handshake.

### BIDIRECTIONAL READINESS LATCHES FOR OS-LEVEL DEEP LINK AND IPC DELIVERIES
**2026-09-22 (Orca PRs #21157 & #21148 / Protocol & Worktree Handlers).** When an Electron application opens via an OS-level protocol URL (`orca://worktree/create?...`) on cold boot, the main process parses the URL before the renderer UI has loaded or registered IPC event listeners. Pushing the payload immediately via `webContents.send()` silently dropped the event. Storing it in state without an explicit consumer pull meant replacement windows never processed pending links. Furthermore, leaving the latch `true` when a window closed allowed subsequent links to be pushed to an unready or non-existent window.

⇒ **Coordinate cold-start IPC payloads with a 4-phase bidirectional latch:**
1. Main process buffers incoming protocol payloads in state.
2. Renderer pulls and consumes pending state on mount via `consumePending*()` IPC, which sets `listenerReady = true`.
3. Main process pushes subsequent links live only when `listenerReady` is true; otherwise it buffers.
4. The latch MUST be reset to `false` both on window reload (`did-finish-load`) and window closure (`mainWindow = null`).
⭐ **The tell:** Protocol deep links working reliably when the app window is already running, but silently failing or requiring two clicks when launched from a cold desktop state.

### STRICT INPUT SANITIZATION AND INJECTION SHIELDS ON DESKTOP PROTOCOL SCHEMES
**2026-09-22 (Orca PR #21157 / Worktree Creation Deep Links).** Protocol handlers registered with the operating system (`orca://`) can be invoked by arbitrary third-party applications, terminal commands, or malicious web links. Passing query parameters (such as `name`, `branch`, or `repoId`) directly to underlying `git worktree add` commands exposes the application to command option injection (`--bare`, `-b`), directory traversal (`../../.git`), or string truncation via NUL bytes (`\0`).

⇒ **Sanitize all external protocol query parameters before passing them to internal workflows or shell commands:**
- Reject values starting with `-` to block CLI flag injection.
- Reject path traversal sequences across all platforms (`..`, `/`, `\`).
- Reject control characters and NUL bytes (`\0`).
- Validate against strict character allowlists for branch and workspace identifiers.
⭐ **The tell:** A URL parameter parser accepting `--exec` or `../../secret` as a valid identifier without throwing an explicit validation error.

### NATIVE SSH COMMIT SIGNING OVER FRAGILE GPG DAEMONS FOR UPSTREAM CONTRIBUTIONS
**2026-09-22 (Orca PRs #21157, #21148 / Verified Commits Requirement).** Upstream repositories (such as `stablyai/orca`) require or enforce verified commits. Developers often encounter severe friction with GPG on macOS: lockfile contention (`pubring.db.lock`), missing pinentry GUI prompts in non-interactive agent shells, and identity mismatches between local GPG keys and GitHub emails. Commits pushed without signatures show as "Unverified" on GitHub, blocking review and merging.

⇒ **Adopt Git 2.34+ native SSH commit signing (`gpg.format = ssh`):**
- Use existing SSH keys (`~/.ssh/id_rsa.pub`) with zero background daemon overhead.
- Configure git scoping (`~/.gitconfig-wom`) with `user.signingkey` and `commit.gpgsign = true`.
- Add the SSH public key to GitHub as a **Signing Key** (Settings → SSH and GPG keys).
- Configure `gpg.ssh.allowedSignersFile` locally so `git log --show-signature` verifies commits natively.
⭐ **The tell:** GitHub PRs displaying gray "Unverified" commit badges, or `git commit` failing with `gpg: signing failed: Inappropriate ioctl for device` in automated or agent shells.

### VOICE AND ATTRIBUTION SEPARATION: NEVER USE "WE" ON PERSONAL OPEN-SOURCE REPOS
**2026-09-22 (External PRs / Serena & Orca Contributions).** When interacting on upstream open-source repositories (PR descriptions, review comments, commit messages) authored under a personal GitHub account (`casualuser@gmail.com`), using collective or agency-style plural phrasing ("we fixed", "our implementation", "we would like to propose") sounds unnatural, corporate, and out-of-place to open-source maintainers. Conversely, internal w0m and client-facing estate work deliberately operates under the agency plural ("we").

⇒ **Strictly separate voice and persona by repository boundary:**
- **External open-source repositories (authored by `casualuser`):** NEVER use "we" or "our". Use objective, imperative phrasing for commits and code comments (`fix: clear readiness latch on window close`), and singular first-person ("I noticed", "I updated", "I ran tests") or neutral passive/constructive phrasing ("This change ensures...", "The latch prevents...") for PR bodies and review discussions.
- **Internal estate / w0m / agency repositories:** Continue using "we" and "our" where acting on behalf of the agency, team, or collective architecture as established in internal records.
⭐ **The tell:** A commit headline, PR description, or maintainer comment on an external repo starting with *"We updated the handler..."* or *"We would like to propose..."* from a personal GitHub handle.

### VISUAL ARCHITECTURAL REPORTS VIA ARTIFACTS AND .agents/reports/ PRESERVATION
**2026-09-22 (T165 / Visual Reports & Terminal Overflows).** When emitting wide Mermaid diagrams (`graph LR`, complex subgraphs) or comprehensive multi-page architectural specs directly as conversational terminal chat markdown, the terminal renderer attempts ASCII box drawing. When diagram widths exceed the viewport (e.g. 386 > 222 cols), it degrades to raw unrendered code blocks with warning banners (`Diagram exceeds terminal width. Displayed as code block. Widen terminal to view inline.`). Furthermore, complex reports generated during chat sessions are lost to context compaction unless committed to disk.

⇒ **Deliver visual/architectural reports via Antigravity Artifacts and persist them in `.agents/reports/`:**
1. Generate an Antigravity **artifact** (`write_to_file` with `ArtifactMetadata`, `UserFacing: true`) so diagrams render with interactive vector SVG, pan, zoom, and collapsible carousels in the IDE webview.
2. Mirror and preserve a permanent copy under `.agents/reports/YYYY-MM-DD-<topic>.md` in the workspace root (and `wom7web/docs/reports/` for canonical monorepo architecture).
3. In conversational chat responses, output only a concise status brief and clickable markdown file links (`[Report](file:///...)`), never raw wide diagram code blocks.
⭐ **The tell:** A terminal warning stating `Diagram exceeds terminal width (... cols). Displayed as code block. Widen terminal to view inline.`




### A CHECK THAT SWALLOWS THE CLI'S ERROR WILL NAME THE WRONG CAUSE
**2026-09-23 (T429 / `check-infisical` after the T421 deploy elevation).** `just deploy-all` stopped with *"Infisical session invalid/expired"* while the session was fine: run from `wom7api`, the same probe injected 105 secrets. T421 had moved the deploy recipes into `@wom/justfile`, which runs from `@wom`, and `@wom` has no `.infisical.json` project link. The CLI said exactly that (*"Please either run infisical init … or pass in project id with --projectId flag"*), but the recipe ran it with `>/dev/null 2>&1` and mapped **every** non-zero exit to "expired". The owner re-logged in for nothing, and a hand-copied `.infisical.json` was the only thing that unblocked the deploy.

⇒ **A pre-flight check must classify the failure from what the tool actually said, and print that line:**
- Capture stderr (never stdout of a secrets command), and match it to *named* causes (no project link / wrong project id / expired session). Anything unrecognised prints the first stderr line as **"not classified"**. Never default to the most familiar cause.
- When recipes move to a new cwd (an elevation), their **implicit per-directory config** (`.infisical.json`, `.env`, tool links) doesn't move with them. Make it explicit: the root justfile now passes `--projectId={{ infisical_project_id }}` from one variable at all 22 call sites, and a test asserts none is missing.
⭐ **The tell:** a check's error message tells you to redo something you just did successfully (re-login, re-auth), and the underlying command's own output was redirected to `/dev/null`.

### USE EXPLICIT RELATIVE MARKDOWN LINKS OVER BARE WIKILINKS FOR SLUGGED AND CROSS-DIRECTORY REFERENCES
**2026-09-26, T458 / Orca Markdown Navigation.** Bare wikilinks `[[AgDR-0027]]`, `[[AgDR-0028]]`, and `[[T458]]` in `TERMINOLOGY-MAP.md` rendered as dead text or unresolved grey-dashed links in Orca.

Authors wrote bare wikilinks (`[[AgDR-0027]]`, `[[T458]]`) expecting Orca/Obsidian to magically resolve them. However:
1. Decision records on disk carry descriptive slugs: `docs/decisions/AgDR-0027-platform-companies-persons-and-operator-gate.md`. Without an exact filename match (`AgDR-0027.md`) or frontmatter `aliases: [AgDR-0027]`, Orca marks bare `[[AgDR-0027]]` as an unresolved link.
2. Tasks live in `.tasks/` (a hidden dot-directory), which desktop editors often ignore or lag in indexing for newly-created tickets (`T458.md`).
3. External viewers (GitHub, Quartz docs, CP Astro webview) do not support Obsidian wikilinks at all and render them as raw unclickable text.
Meanwhile, adjacent standard Markdown links (`[WORKFLOW-COVERAGE.md](WORKFLOW-COVERAGE.md)`) in the same file rendered as bright blue, solid, 100% clickable links across all tools.

⇒ **Always use explicit relative Markdown links `[label](relative/path.md)` for decisions, tickets, and cross-directory documentation:**
- Decisions: `[AgDR-0027](../decisions/AgDR-0027-platform-companies-persons-and-operator-gate.md)`
- Tickets: `[T458](../../.tasks/T458.md)`
- If wikilinks are used within an Obsidian vault, the target file must explicitly declare the ID in its frontmatter `aliases: [AgDR-0027]`, or use piped full slugs: `[[AgDR-0027-platform-companies-persons-and-operator-gate|AgDR-0027]]`.
- Standard relative Markdown links are the only format that works universally across Orca, Obsidian, VS Code, GitHub, and Quartz with zero reliance on background cache indexing.
⭐ **The tell:** A link written as `[[ID]]` where the file on disk has a slug suffix (`ID-title.md`), or links into hidden directories (`.tasks/`), rendering with grey dotted/dashed underlines in Orca/Obsidian or raw brackets on GitHub.



## Auto-Mined Lessons — 2026-09-29 (T482)

### [SDLC Toolchain] Pre-commit gate rejection
- **Problem**: Agent executed commits that failed pre-commit quality hooks.
- **Lesson =>**: Always run pre-commit on staged files before committing, and fix violations organically rather than using --no-verify.
- ⭐ **The Tell**: Pre-commit hook exiting non-zero on staged git commits.

### [Human Confirmation Gate] Agent attempted gated deploy or live migration
- **Problem**: Agent attempted to directly execute deployment or migration gated by human Touch ID confirmation.
- **Lesson =>**: Agents must prepare code, verification checks, and explicitly prompt the human developer to run deploys.
- ⭐ **The Tell**: Agent command blocked by deploy-confirm gate or Touch ID requirement.

### [Command Registry] Invalid or missing justfile recipe call
- **Problem**: Agent attempted to invoke an undeclared just recipe.
- **Lesson =>**: Inspect `just --list` before running recipes to verify available command contracts across repos.
- ⭐ **The Tell**: just exiting with 'recipe failed' or 'does not contain recipe'.

### [Records & Governance] Untracked report artifact without ticket citation
- **Problem**: Report authored in `.agents/reports/` without citing an active ticket in filename or header.
- **Lesson =>**: Every report must cite an existing ticket ID (e.g. `YYYY-MM-DD-t###-...`) in filename and first 12 lines (T428).
- ⭐ **The Tell**: `just reports-ticket-check` reporting un-cited reports.

### [State Tracking] STATE.md drift against active ticket queue
- **Problem**: Manual or stale edits produced drift in STATE.md's mechanical block.
- **Lesson =>**: Always regenerate STATE.md using `just state-save` (or `just land`), never hand-edit the mechanical block.
- ⭐ **The Tell**: `just state-check` failing on pre-push.

### [Collaborative Worktree Safety] Blanket destructive git command attempted
- **Problem**: Agent attempted blanket reset or clean on a shared working tree.
- **Lesson =>**: Collaborative worktrees are shared with other agents and humans; never run blanket git restores or resets, use surgical file-scoped git adds and reverts.
- ⭐ **The Tell**: Blanket git reset/clean in terminal history.

### A default argument that holds the real transport sends the real request from a test (T537, 2026-10-02)

`def step(..., net: Net = _http_post)` binds the function object when the module loads. A test that patched `module._http_post` afterwards patched a name the step no longer looked up, so the test used the REAL transport and sent a real registration request to Upwork, to a third party, before the owner had given the per-step go.

- Tell: a test that is supposed to use a fake fails on an assertion about the RESPONSE (here, `registered` was false) rather than erroring on a missing fake. A fake that is wired in answers exactly what it was told to.
- Rule: bind the transport at call time (`net = net or _http_post`), and give any test file that exercises code with an outward path a module-level guard that makes the real transport raise, plus a test that proves the guard fires. Write the guard BEFORE the first test that touches a step, not after the first surprise.

### The database host is IPv6-only; when it "does not resolve" the route is usually fine (2026-10-03)

Measured in the agent shell from 2026-10-02 17:41 to 2026-10-03 11:53 (-05:00): `psql` and Python failed with `could not translate host name "db.<ref>.supabase.co"` / `gaierror Errno 8`, so every read of the live database stopped while WARP reported Connected and healthy.

What was tested, and what each result showed:

- `dig`: 0 A records and 1 AAAA record. The host is IPv6-only, as the repo rules say.
- `dig` and `dscacheutil` returned the IPv6 address, but `getaddrinfo` (Python, psql, curl) failed for it AND for any other AAAA-only name (`ipv6.google.com`), while names with an A record (the API host, `example.com`) resolved, IPv4 only.
- A plain TCP connect to the database's IPv6 address on port 5432 succeeded. The route works.
- `scutil --nwi` printed `No IPv6 states found`, although WARP's tunnel interface held a global IPv6 address.

Reading: a resolution failure, not a network failure. macOS appears to refuse AAAA-only names while no IPv6 service is registered. That cause is consistent with all four results but not proven (one machine, one day).

**Confirmed fix, 2026-10-03:** the owner reconnected WARP in their own terminal (it drops the session's own connection, so an agent cannot do it). Re-running the same probes in the same order: `getaddrinfo` now resolves the database host and `ipv6.google.com` (IPv6), `scutil --nwi` lists `en0` with `IPv4,IPv6,DNS` where it had said "No IPv6 states found", and the standard read-only helper returned the live counts (95 contracts, 55 rooms, 170 messages, identical to before the outage). Mechanism still unproven: the reconnect re-registered an IPv6 service and resolution followed.

**Recurred, 2026-10-03 15:04 -05:00 (about 2.7 hours after the fix at 12:20):** same signature. `getaddrinfo` failed for the database host and `ipv6.google.com`; `dig` still returned the AAAA record; a TCP connect to the IPv6 address on 5432 still succeeded; `scutil --nwi` listed `en0` as `IPv4,DNS` only with `No IPv6 states found`, while the WARP tunnel interface still carried IPv6; `warp-cli` still said Connected and healthy. So the reconnect is a temporary fix: whatever deregisters the IPv6 service came back. The trigger was not identified (not measured: Wi-Fi roaming, sleep and wake, VPN re-keying). Rule added: re-run the `getaddrinfo` probe immediately before any step that needs the database (a deploy, `db-migrate`, a live query), not only once per day; and when it fails, say so and ask for a WARP reconnect then, instead of assuming the earlier fix still holds.

**Root cause and a working configuration, 2026-10-04.** The owner's Wi-Fi sits behind the internet provider's own modem (`192.168.0.1`, DNS search domain `cpe.cun.cablemas.com.mx`), which offers no IPv6 at all: no router advertisement reaches `en0`, only the link-local `fe80::` address exists. macOS skips IPv6 lookups while the primary interface has no IPv6 service, and WARP's tunnel interface (which does hold a global IPv6 address) does not count. That is why the failure was permanent on this network and why every WARP reconnect was at best temporary.

Measured on the same machine, same minute, one change at a time:
- Reconnecting WARP: no lasting effect. `networksetup -setv6LinkLocal Wi-Fi`: `en0` still `IPv4,DNS`, lookup still fails. A static private address with no router: address applied, `en0` still `IPv4,DNS`, lookup still fails.
- **Working:** `networksetup -setv6manual Wi-Fi fd00:0:0:1::2 64 fd00:0:0:1::1` (a made-up private address AND a made-up router). `scutil --nwi` then listed `en0` with IPv6, `getaddrinfo` resolved the database host, and `scripts/check_db_host.py` made a real TCP connection to port 5432. The traffic still leaves through WARP, because nothing sits behind the made-up router.
- Undo: `networksetup -setv6Automatic Wi-Fi`. It is a standing setting on this Mac for every Wi-Fi network; on a network with real IPv6 it should be harmless but is untested.
- Other fixes: a network that has IPv6 (a phone hotspot), or IPv6 switched on in the modem (the permanent fix, the provider's to give).
- Rule: the lookup failure is a property of the network the machine is on, not of WARP. When `just check-warp` fails with `[resolve]`, read `scutil --nwi | grep en0` first; a reconnect that changes nothing there changes nothing.
- Rule: the failure message of `scripts/check_db_host.py` now names this fix, and a test pins that it does not point back to a plain WARP reconnect.

- Tell: the error says "could not translate host name" (resolution), not "connection refused" or "timed out". The HTTPS API host keeps working because it has an IPv4 record, so only database-bound tools fail, which looks like a database outage and is not one.
- Rule: test with `getaddrinfo`, never with `dig`, which answered while the libraries every tool uses did not: `python3 -c "import socket; socket.getaddrinfo('db.<ref>.supabase.co', 5432)"`, and `scutil --nwi | grep -A1 'IPv6 network'`.
- Rule: never "fix" it with an IPv4 endpoint or pooler (AGENTS rule; the host has no A record anyway).
- Rule: do not swap in a different path and call it the same measurement. A REST read with the new-style `sb_secret_` service key answered 401 and was not resolved; it proved nothing about the database.
- Rule: when the database is unreachable, say so with this evidence and mark any live-schema claim unverified. T539 AC2 was left half done for this reason.

### A pre-push gate can be blocked by a COMMITTED state, not only by the working tree (2026-10-03)

For two days a push from a clean detached checkout was the way round another agent's uncommitted draft blocking the live tree's pre-push gates. On 2026-10-03 it stopped working: the blocker was agy's finished T538 change (9/9 tasks, ticket done, never archived), which is committed, so a clean checkout carries it too and the spec-drift gate refuses.

- Tell: the gate names a change or ticket that is committed, and it fails the same way from a clean checkout. The clean-checkout trick only helps when the blocker lives in the working tree.
- Fix that worked: apply the gate's own named remedy (`openspec archive <change> --yes`) in the clean checkout, commit it, and let the real gates judge the push; then fast-forward the live checkout with `git merge --ff-only`, so nothing of another agent's can be lost. Check first that the owner's change files and ticket have been idle (here 111 and 75 minutes) and that the archive's effect is visible before it is pushed.
- Rule: a gate that is red because of a committed state is a record that needs fixing, not a tree that needs cleaning. Do the fix in a throwaway checkout, never in the shared live tree.

### A preflight check must ask the question the failing step asks (T542, 2026-10-03)

The deploy preflight printed "IPv6 connectivity OK" and, on failure, "no IPv6, advisory only, the deploy path is IPv4", while the database host is IPv6-only and its NAME stopped resolving. The check pinged a dual-stack site (`curl -6 cloudflare.com`): a connection test where the failing step needed a name lookup. The deploy then ran 19 minutes of tests and died at `db-migrate`. Fix: `scripts/check_db_host.py` calls `socket.getaddrinfo` on the database host (what psql calls) and then a TCP connect, and `check-warp` runs it first.

- Tell: a gate that mentions the same subject as the failure ("IPv6") yet passed. Read what it actually tests, not its label.
- Rule: derive the preflight from the failing step, and watch it FAIL on the real case before trusting it. Here the resolver was broken on the machine at the time, so the new check failed on the first real run, in seconds, where the old one printed a green line on the same machine.
- Rule: never write an "advisory only" excuse into a check's failure branch for a path you have not verified. That line was false and hid the cause.

### Two agents picking "the next free id" collide, and a no-gap rule makes landing order matter (2026-10-03)

While T542 was in progress another agent created T541 in the live tree. Landing T542 first left `origin/beta` with a hole at 541, which fails the blocking `org-migrate-plan-test` ("every number from 1 to max with no gap") until T541 is pushed. A renumber was required (T541 to T542), and the push order now decides whether the branch is green.

- Tell: a blocking suite red on "gaps: [N]" right after a landing; `git ls-tree` of `.tasks` on origin shows N missing while another tree holds it unpushed.
- Rule: with separate trees, take a ticket id from `origin/beta` at landing time, not from your own view, and land ticket creation before work that cites it, or land in id order. The durable fix is T531's atomic-id layer; until it exists, check `git ls-tree origin/beta .tasks` for the highest id immediately before you push.

### A separate worktree must be a COMPLETE estate, or its derived files are wrong (2026-10-03)

First try: a root worktree without its member repos, and the root hooks failed on broken couplings to `wom7web/...`. Second try, only `wom7web` and `wom7api` added: `docs/DECISIONS.md` regenerated one entry short (a `wom7skills` file was missing) and the freshness hook accepted it, so a wrong file would have been committed. With all nine members nested inside the root worktree (341 MB, seconds to create), the regenerated file was byte-identical to `origin/beta`.

- Rule: an agent workspace is the root worktree with every member repo nested inside, built from `origin/beta`; never regenerate a derived file (`DECISIONS.md`, `TASKS.md`, `STATE.md`) in a partial layout, and compare it with `origin/beta` before committing.

### A suite recipe must be visible from `wom7api/`, not only from where you ran it (T531, 2026-10-04)

The new `agent-tree` suite went red on the very first stable run as `MISSING` (exit 127): `scripts/run_suites.py` resolves every recipe with `just --show` from `wom7api/`, and `agent-tree-test` lived only in the root justfile. I had run it from the root, where it worked, and registered the suite on that evidence. `release-test` is root-only too and passes only because `wom7api/justfile` carries a one-line forwarder (`@just --justfile ../justfile release-test`). My own `grep "^release-test:"` found no match because that recipe is declared `release-test *args:`.

- Tell: a suite reported `MISSING` with exit 127 and 0 checks and an empty log, while the recipe runs by hand.
- Rule: after registering a suite, run `cd wom7api && just --show <recipe>` (exactly what the runner does) before landing, and run the stable tier before calling it registered. Grep for a recipe with `^name\b`, not `^name:`.


### A mocked-client test can prove a rule the database will never let run (T553, 2026-10-07)

- T461 shipped "Delivered & Verified, 49 tests": the unit tests mocked the Supabase client, so the QH rules passed. The routes wrote through the user session and the migration gave `authenticated` no write path, so every write was denied in production (an MFA admin could write `hat_collections`, nobody could write the other four). One Postgres session as the real role found it in minutes.
- Tell: a feature whose tests mock the data client and whose migration adds tables has not been shown to write at all. Check `has_table_privilege` and the write policies for the role the route actually uses.
- Rule: authority that must hold (who may assign, compose, or change a rule) belongs in the database, in a function the tables' only write path goes through, and its proof is a scratch Postgres as role `authenticated` with a mutation that removes each rule (T544 pattern). A mocked route test then pins only the contract (which function, which arguments, 403 / 400 / 500 mapping).

### A plpgsql `if` condition that contains `case ... then` ends at the first `then` (T553, 2026-10-07)

- `if x <> case when a then b else c end then` parses as `if x <> case when a then` and fails with "syntax error at end of input" far from the cause.
- Rule: compute the `case` into a variable first and test the variable.

### A collection written add-only can still create a rule that breaks the data (T553, 2026-10-07)

- `wom_apply_collection` as the API wrote it gave every non-dev role the rule `collapses into pm`, including `pm` itself. The fallback trigger would then flip the real PM's hat to `is_fallback`. Nothing hit it because no write ever succeeded.
- Rule: when a write path that never worked is made to work, read every default it applies as if it will now run. Add the invariant as a check constraint (`role_slug <> collapses_into`) as well as in the function.


### A retired name survives in function bodies and probes, not only in data (T553, 2026-10-07)

- `tpm` (the early name of the Tech Lead seat) was archived as a role and deleted as an office on 2026-09-05 (T319), yet it stayed in three definitions of `wom_role_office`, the Indie project type, the 1-click provisioner (which would have re-created the archived role), three specs and two live probes that asserted the deleted rows still existed. I then built a security rule on the premise that `tpm` was a role.
- Tell: a dedup migration that archives rows but whose commit message names no code change. Before reasoning about a name, measure that it exists in the live catalog (`select ... from project_roles group by slug, status`).
- Rule: retiring a name means a grep of the whole estate (code, specs, probes, functions) in the same ticket, and a probe that asserts the name is ABSENT.

### A filter on text another parser will read must refuse the encodings, not list the bad words (T555, 2026-10-08)

- The PDF worker's first stylesheet check blocked `url(https://...)` with a regex. A CSS parser reads `u\72l(...)` as `url(` and `image-set("https://...")` fetches without `url(` at all, so a blocklist that was correct for the strings it listed was open for the ones a browser also accepts. The automated review of the pushed commit found it, not the tests, because the tests tried the spellings I had thought of.
- Rule: for any text you pass on to a parser (CSS, HTML, a path the service role will read), allow what the use needs and refuse everything else, including the escape syntax itself. Write the bypass spellings as test rows before the fix.
- Same review: "the caller can read the row" is not "the caller owns the row" when an admin read arm exists. Compare the row's owner to the caller's own identity.

