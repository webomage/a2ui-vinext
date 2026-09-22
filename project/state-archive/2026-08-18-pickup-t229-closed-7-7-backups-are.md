<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-08-18 — **T229 CLOSED 7/7 — backups are real, proven and watched. Plus a CV attribution bug tha -->

## ⭐ PICK UP HERE — 2026-08-18 — **T229 CLOSED 7/7 — backups are real, proven and watched. Plus a CV attribution bug that put a Rust TUI on a 2004 helpdesk job.**

**T229 2/7 → 7/7, ARCHIVED.** Stage-0's exit needed a probe result **and** an exercised restore;
both are now real, repeatable and proven red by mutation. Ticket `done`, board ✅, issue #226
closed, debt rows **D57/D58/D59** opened for what it deliberately did NOT close.

- **AC1** — the 27 MB dump RESTORES. Diffed against live: **114/114 tables, 23,341 rows, 6/6 content
  tables byte-identical**. Every difference accounted for as post-dump change, not loss — live's own
  `count(*) where created_at <= dump_time` matches the restored count exactly.
- **AC5** — the owner ran the backup; no deny-list exception needed.
- **AC4** — **555 Storage objects / 53.9 MB across 13 buckets** now backed up with a sha256 manifest.
  `pg_dump` captured **none** of it, and half the tables reference storage paths.
- **New recipes:** `just db-restore-verify` (+`-test`, 21 offline checks) and `just storage-backup`
  (+`-test`, 23). Both **fail closed on an empty comparison**.

🔴 **Two prerequisites the dump does NOT carry**, both found by failing, now checked up front:
a **`postgres` role** (414 errors — Homebrew names the superuser after the OS user) and
**pgvector** (342 — without it the vector tables do not restore *at all*). A recovery on a fresh
host mid-incident would have hit both cold.

⚠️ **`row::text` is not a valid cross-instance comparator** and it burned the first verification
twice — local timezone vs the server's UTC, then locale-dependent quoting where the entire
difference on two rows was `🧠` vs `"🧠"`. **Use `to_jsonb(t)::text`.** A check that stopped at the
first red would have condemned a good backup.

**AC2/AC6 landed too:** `just backup-freshness` (a stopped job is visible from the DISK, since the
scheduler surface is split) and `just supabase-limits`. 🔴 **Two premises died on measurement:**
there are **TWO orgs** and the second (`w0m space`) is **EMPTY 0/2**, so a third project needs it
rather than Pro; and **`solar_flares` is NOT idle** — a `*/5` cron, **81,052 runs**, 284 MB ≈57%
of its cap. ⚠️ Egress is **unmeasurable** (API 404s) and storage restore is **unproven** — no
scratch bucket the way there is a scratch database.

**Owner decision 2026-08-18: stay on Supabase FREE**, Pro only for w0m if genuinely needed.

**Also this session — the CV corpus.** The claim extractor sliced each role from its heading to
*end of file*, so everything below the **last** role heading landed on it — and the last role
heading is always the **oldest job**. The 2004–2006 SWsoft support role carried **19 claims, 15
wrong** (a Rust Kubernetes TUI, an Apple Watch app, a pgvector RAG pipeline). Fixed with a section
terminator; all 15 verified already present in their correct homes. 📌 **The first measurement of
this was VACUOUS** — `claims.json` was 12 days stale because `cv-claims` only writes under `--json`,
so the diff compared a stale file to itself and reported "0 lost".

⚠️ **A merge applied to a GENERATED file does not survive.** Regenerating restored `work[]` to 28:
the Kayse/Renowned merge had been hand-edited into `resume.json`. Redone in the private CV — the
spine, an **input**. Same rule `resolutions.json` already states for conflicts.

**T230** is 6/7, not 7/7: AC7 was ticked while its own text said *"not built"*. `ticket-schema-check`
now errors on that shape, with markers split by strength after a false positive on T34.
