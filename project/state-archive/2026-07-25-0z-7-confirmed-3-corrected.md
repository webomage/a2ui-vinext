<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0z. 🔎 TRUTH-VALIDATION PASS — 2026-07-25 (late night). Owner asked to validate the hot 10. **7 confirmed, 3 correcte -->

### 0z. 🔎 TRUTH-VALIDATION PASS — 2026-07-25 (late night). Owner asked to validate the hot 10. **7 confirmed, 3 corrected.** DO NOT RE-DERIVE.

Every claim was checked against a live system rather than the board. Methods are recorded so a
successor can re-run them cheaply, and so the *wrong* methods are not repeated.

**Confirmed ✅** — T135 (status + 0 open questions + no spec dir) · T99(d) (56/56 strict-valid, 18/18
tests, stamp absent, 0 ciphertext columns, both keys absent) · T117 (17 subject-commits, 2/10 ACs) ·
T138 (0 duplicate email groups; only 2 identifier indexes; `pg_trgm`/`unaccent`/`citext` absent) ·
T137 (§30 covers both depths; T111 fileless) · T21/T35/T29/T30 (all four change dirs live, not
archived) · T136 (zero WP anywhere; Hostinger zero installs).

**Corrected ⚠️ — three, and each was wrong in an instructive way:**
1. **The fileless-ticket count was UNDER-stated.** Not five but **six** with no file — T111, T87, T90,
   T94 and **T96** (missed, and [[T137]]'s own Links section points at it). And **[[T112]] has neither a
   file NOR a board row**: its 6 `TASKS.md` hits are all wikilink citations *from other rows*. It is
   referenced by T135, §0m and §0n yet is **unfindable on the board**. ⇒ A ticket that cannot be opened
   cannot be gated, and T137's AC0 depends on one of them.
2. **The skills-versioning claim was wrong in BOTH directions** (see the fix table above). The lesson is
   the measurement, not the number: **`.w0m/skills.json`'s `version` field holds provenance labels, not
   versions.** First attempt measured `wom7skills/skills/*/SKILL.md` and reported "1 mentions
   infisical"; the corpus is **40 `SKILL.md` files across nested dirs**, and the recursive count is
   exactly **2** (`w0m/w0m-deploy`, `w0m-sdlc-start`) — so **§0m's "2 of 27" claim is CONFIRMED**, and
   the *27* is top-level dirs, not skills.
   > 🔴 **THIS CORRECTION WAS ITSELF PARTLY WRONG — re-measured 2026-07-25 (late night, next session).
   > Do not quote the "0 of 40 / wrong in both directions" line above.** It counted only a **top-level**
   > `^version:` key. **11 of 40 `SKILL.md` files do declare a version** — all as an *indented*
   > `metadata.version`. So the ORIGINAL *"16 of 27"* was **arithmetically correct** at directory
   > granularity (27 dirs − 11 versioned = 16); against the true corpus it is **29 of 40**.
   > The provenance-label finding **stands and was the real catch**, but it is only half the story:
   > `.w0m/skills.json` carries **two** version-ish fields — `version` = provenance label
   > (`unknown` ×56 / `canonical` ×13 / `vendored` ×1) and **`observed_version` = the real scraped
   > version, present on 58 of 70**. "How many skills are versioned?" has three defensible answers
   > (70 / 58 / 11) depending on which field you read — always say which.
   > ⇒ The statement to actually use, because it is denominator-free and unambiguous:
   > **zero canonical skills carry a *conforming* `YYYY.MM.DD-<unixtimestamp>` version** (of the 11,
   > ten are `w0m-sdlc-*` with a hand-set `"1.0"`/`"2.0"`, and the one three-part version belongs to an
   > imported upstream skill). T131's premise is **strengthened**. Full detail in `project/tickets/T131.md`.
   > 📌 **Meta-lesson, and the reason this is left visible instead of deleted:** a correction pass is not
   > self-validating. This one over-corrected because it silently narrowed the definition of "declares a
   > version" to a top-level key — the same *"my measurement is the truth"* error it was written to fix.
3. **T120 cannot be verified from this environment at all.** Needs Search Console or the Safe Browsing
   Lookup API with a key. Recorded as unverifiable rather than assumed either way.

**Two board rows were found stale — both now in the fix table:** **T49 is genuinely DONE** (0 unpinned
definer functions / 32 pinned / stamp present) and **T32's P0 severity is stale** (3 of 4 ACs
satisfied; the remainder is T17's).

**🔴 §0t was corrected THREE times by querying the live DB — its own warning that it was
migration-file + ORM truth was justified.** Full detail in `project/tickets/T138.md`; the headline:
1. **The `units.squad` trigger is NOT broken.** §0t claimed *"every unit insert … fails today, including
   from the CP admin UI"*. Live `pg_proc` shows `public.squads` (schema-qualified) and stamp
   `20260720190000` is applied. §0t **read the migration's own fix-comment as the current state.**
   ⚠️ *Generalise: a migration comment describes the state it changed, not the state you are in.*
2. **"No FK existed" is false** — the FK graph is real: `contracts`/`projects` → `clients`, `blueprints`;
   `invoices` → `clients`, `contracts`; `leads` → `clients`; `proposals` → `blueprints`, `contracts`,
   `projects`. The gap is **identifier indexes + uniqueness**, not referential integrity.
3. **Live slug columns are `posts.slug` + `technologies.slug`** — not §0t's
   `gamification.badge_definitions.icon_slug`, which does not exist live.

ℹ️ **Environment gotchas confirmed this session — all three cost a wasted run:**
- **`timeout` is a pyenv shim, not GNU `timeout`** (`ModuleNotFoundError: No module named 'examples'`).
  Use the tool-level timeout instead of wrapping a command.
- **The shell is zsh: `$PIPESTATUS` is bash-only** and silently yields empty — use `${pipestatus[1]}`
  (1-indexed). ⚠️ Also: **`cmd | tee` reports *tee's* exit code**, which briefly turned a `cargo check`
  failure into an apparent success this session.
- **`infisical run` must be invoked from the repo holding `.infisical.json`** (e.g. `wom7web/`), or it
  fails with *"run infisical init … or pass in project id"*. Running from the workspace root fails.
- **To check a secret exists, presence-check it through `infisical run`** — never `infisical secrets
  --plain` / `--format=json` (debt row **D19** exists because a values-printing call leaked
  `ADMIN_LOGIN_PASSWORD` into a transcript). `--format=json` is also unsupported by this CLI version.
