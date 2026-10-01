> Preserved copy of read-only deep research (2026-09-30). Ticket: [[T508]] (scope), [[T512]] (propagation split). Verbatim from the session scratchpad; counts are as measured that day.

# Research: skills catalogue lost the estate's largest manifest

Date: 2026-09-30. READ-ONLY research (nothing in any repo was edited, staged or deleted; the only
writes are scratch files under the session scratchpad). All paths are relative to
`/Users/proto/Projects/@self/@wom` unless absolute. `wom7web/justfile` is a symlink to
`wom7api/justfile`, so recipe line numbers below are `wom7api/justfile`.

## Summary

1. **Root cause is one line, and it is not "T414".** `skills_catalogue.py:242` resolves each project
   as `(ROOT / p["root"])` and `catalogue_project` then reads `<root>/.w0m/skills.json`
   (`:141`, `:144`) and `<root>/.agents/skills` (`:150`). The `w0m` registry entry has
   `root: "."` AND `canonical_repo: "wom7web"` (`project/policies/clients-policy.json:10,25`). Two
   sibling tools (`state_bounds.py:100`, `client_inventory.py:397-411`) honour `canonical_repo`;
   the catalogue ignores it AND ignores `repos`. So for a multi-repo workspace it measures only the
   workspace-root surface. The same tool run on the `w0m` project: catalogue says **25 installed**,
   `client_inventory` says **99 declared** (it reads the canonical repo) -- two tools, one project,
   two answers (measured, section Evidence E2).
2. **Onset was 2026-09-07 (T232, commit `e506674`), not 2026-09-20/21.** T294 (`8bd38d5e2`,
   2026-09-02) changed the w0m registry root `wom7web` -> `.`; at that moment `@wom/.agents` was a
   symlink to `wom7web/.agents` and `@wom/.w0m/` did not exist. T232 (2026-09-07) replaced the
   symlink with a real 25-skill `.agents/skills` + a new `@wom/.w0m/skills.json`. From then on the
   catalogue's `w0m` row has been the 25-skill root. T412 (2026-09-20) only moved sdlc.json/policies
   to the root and made the web copies symlinks. T385 (created 2026-09-18) already lists
   `skills-catalogue-test` as 5/18 red.
3. **Several manifests are intentional (per-consumer install selection); the dual-SSOT defect is in
   propagation, not in the count of manifests.** The SSOT for skill *content* is
   `wom7skills/skills/` (one). Each root that loads skills carries its own manifest + lock by design
   (T127, T149, T232 "decouple wom7api", `wom7skills/AGENTS.md:60-65`). But the same declaration is
   copied into 2-3 manifests with independent hashes and nothing syncs/relocks/gates all of them:
   right now **2 of the 3 surfaces are out of sync** (root `w0m-tasks` integrity+version drift,
   wom7api `w0m-ticket-audit` stale vs canonical; measured E5).
4. **It is not only the w0m project.** The same blind spot hits `k7` (catalogue 0 installed; its
   canonical repo `k7/k7d/k7d` has a 4-skill manifest). Plus 3 more post-T412/T294 root-anchored
   readers (section Evidence E7).
5. **Of the 5 red test assertions, 2 are this scope shrink, 3 are client drift**; fixing scope alone
   does not turn the suite green, and measuring all repos exposes two defects in the tool itself
   (node_modules counted as "shipped executables": 8,144 phantom files; comment lines counted as host
   invocations).
6. **Recommendation: Option 1** -- measure every governed surface of every enabled project (root U
   `repos` members, de-duplicated by realpath), keep the manifests, harden three tool defects, derive
   the test's expectations from manifests, and split propagation/drift into a dependent ticket.

## Evidence

### E1. Every `.w0m/skills.json` / `skills.lock.json` in the estate

Found by `find` from the workspace root (excluding node_modules) and `git ls-files`: exactly three
pairs inside the workspace. wom7skills, wom7func, wom7ext, wom7sec, wom7mlx, wom7ava, wom7clips have
no `.w0m/` and no `.agents/skills` or `.claude/skills` (checked directly). `~/.claude/.w0m/` (the
user manifest named in `.w0m/sdlc.json:652+`) does not exist; 23 user-scope skills are ungoverned.

| manifest | `skills` | `exclude` | lock entries | installed in `.agents/skills` | `project` | last change |
|---|---|---|---|---|---|---|
| `.w0m/skills.json` (workspace root) | 25 | none | 25 | 25 | `w0m` | `207b58c` 2026-09-27 |
| `wom7web/.w0m/skills.json` | 99 | 10 (openspec-* family, each with a reason) | 99 | 109 | `wom7web` | `a9a49950` 2026-09-30 |
| `wom7api/.w0m/skills.json` | 9 | none | 9 | 9 | `wom7api` | `66fe6db` 2026-09-19 |

Set arithmetic (computed): root-web overlap 20 skills, byte-identical content for all 20; api-web
overlap 8; root-only 5 (`doubt-driven-development`, `feynman`, `socrates`, `torvalds`, `w0m-prs`);
api-only 1 (`score-orchestration`); 133 manifest rows, 105 distinct names. Installed distinct
(including web's 10 excluded) = 115 (that equals the "115" the policy comment measured on 2026-08-09,
`project/policies/skills-policy.json` `detect_executable._comment`, a coincidence of arithmetic not
of provenance).

Clients (read-only, listed for completeness, not touched): artemio 56 + 10 excluded; 1945 15;
`@k7/k7d/k7d` 4 (workspace project `k7`, `canonical_repo: k7d`, `clients-policy.json:165-180`);
servicios777 manifest only; bridgeroad json+lock (all from `client_inventory.py` output).

Who reads them (file:line):

| reader | what it reads | which surface it sees |
|---|---|---|
| `wom7web/project/scripts/skills_catalogue.py:141,144,150-151,242` | `<registry root>/.w0m/skills.{json,lock.json}`, `.agents/skills`, `.claude/skills` | root only for `w0m` (25); root `k7` has none (0) |
| `wom7web/project/scripts/client_inventory.py:165-205` via `:397-411` | same files under the project's CONTRACT repo (`canonical_repo`) | `w0m` -> wom7web (99); `k7` -> k7d (4) |
| `wom7skills/skills.ts:117-131,173-175,212-224` | target dir's manifest; default target `../wom7web` | one target per invocation; `just skills-sync` takes no target (`justfile:3284-3285`, root `justfile:797`) so root/api need a manual `tsx skills.ts <dir>` |
| `wom7skills/w0m_skill.ts:136,139` (`manifestPath`/`lockPath`) | `<--project>/.w0m/...` | whichever dir `just skill ...` is invoked from (`justfile:3289-3290` uses `invocation_directory()`) |
| `wom7skills/w0m_skill.ts:1746-1760` (`discoverEstateRoots`, used by `estate`/`gaps`) | `sdlc.json -> repos` resolved from `configRoot/cfg.root` | see E7 (broken from wom7web since T412) |
| `wom7skills/scripts/audit_vendoring.ts:85` via `justfile:3403` | `--project ../wom7web` manifest | web only |
| `scripts/repo_hygiene.py:420-436` + `hygiene-policy.json:112-121` | each declared repo's `.w0m/skills.json` provenance (`first_party_provider`) | every declared repo; fails loud if missing |
| pre-commit `skills-drift`, `wom7web/.pre-commit-config.yaml:122-139` | `skills.ts --check ../wom7web` | web only. Root `.pre-commit-config.yaml` and `wom7api/.pre-commit-config.yaml` have NO skills hook (grep) |
| `project/scripts/toolset_status.py:36,46` | `just skill check` with cwd `wom7web` | web only; root and api never gated |
| `wom7skills/tests/w0m_skill.test.ts:699,765` | `LIVE = ../wom7web` | web only |
| NOT readers | `discovery.py`, `install_generic.ts` (writes no `.w0m/`, `justfile:3445-3450`), `preflight.py` (comment mention only) | -- |

Note `.w0m/sdlc.json:266-275` declares `skills.manifest`, `skills.lockfile`, `skills.layers.governed/
runtime` (`.agents/skills`, `.claude/skills`); `skills_catalogue.py` reads only `skills.policy`
(`:208-215`) and hardcodes the other paths (`:141,144,150,151`). Declared-but-not-read keys: the same
"decorative declaration" shape the file's own docstring warns about (`:197-202`).

### E2. The measured disagreement (2026-09-30, live runs)

- `python3 wom7web/project/scripts/skills_catalogue.py`: w0m 25 installed / 25 managed / 0 excluded;
  artemio 66/56/10; 1945 15/15/0; k7 0; mob 0; servicios777 0; personaje0 0; bridgeroad 0; user
  scope 23; advisory exit 0.
- `python3 wom7web/project/scripts/client_inventory.py`: w0m `skills governed: 99 declared, lock
  present`; k7 `4/json+lock`.
- Calling `catalogue_project` directly on the three real surfaces (no code change): root 25/25/0/0;
  wom7web 109 installed, 99 managed, 10 excluded, 0 unmanaged; wom7api 9/9/0/0. So the machinery is
  correct per root; only the root *selection* is wrong.
- `skills-catalogue-test` today: 13/18 (the ticket text says 15/18; D53 17/18 -> 15/18 -> 13/18, it
  keeps sliding). Failing: (a) `the openspec family is counted as excluded` (test:95-97, expects
  `{"w0m":10,"1945":0,"artemio":10}`, got w0m 0); (b) `every skill shipping runnable files has an
  EXPLICIT decision` (test:101-102); (c) `no declaration is contradicted by a call site`
  (test:103-104); (d) `host invocation is MEASURED ... justfile:215` (test:105-106); (e) `an
  inherited default over runnable code is flagged` (test:125-129). `test:100` ("exactly 2") still
  passes, by accident (the 2 are now both artemio's).
- Attribution of the five: (a) and (e) are the scope shrink -- (e) because `webapp-testing`, the one
  w0m runnable skill, lives only in wom7web and so vanished from the catalogue (its override
  `w0m:webapp-testing`, `skills-policy.json:25`, now matches nothing and nothing reports that);
  (b), (c), (d) are client drift in artemio (E6).

### E3. History and intent (is multi-manifest intentional?)

- T127 (skills manager): manifest + lock live in the CONSUMING project (`wom7skills/AGENTS.md:60-65`,
  `skills.schema.json:5` "Lives at <project>/.w0m/skills.json").
- T149 narrowed sync from a `w0m*` prefix to "the consumer's manifest decides"
  (`skills.ts:12-26`; `AGENTS.md:37-57`, the Two-Repo Rule: a canonical skill reaches nobody until
  the consumer's manifest entry lands). That makes a per-consumer manifest the mechanism that keeps
  `w0m-ui-expert` out of Tailwind-free projects. Collapsing to one manifest undoes T149.
- T232 progress note 2026-09-07 (`.tasks/T232.md:329-331`): "Decoupled `@wom/.agents` from
  `wom7web/.agents` symlink. Configured `@wom/.w0m/skills.json` ... 23 estate-level governance and
  reasoning skills" and "Decoupled `wom7api` from `wom7web`: established governed
  `wom7api/.w0m/skills.json` ... containing only backend stack skills". Explicit intent, three levels.
- Owner decision 2026-08-17 (T147 AC2+AC4) recorded at `.w0m/sdlc.json:652+`
  (`skills_governance_scopes._comment`): "a project manifest describes one repo"; governed per root,
  not annexed by whichever project you run from.
- Verdict: **intentional, per-root selection.** Not a dual SSOT of *content* (wom7skills/skills/ is
  the one source; `skills.ts` copies, `version.ts` stamps).
- But the same fact ("skill X at version V, hash H is installed") is recorded in up to three
  manifests/locks plus three on-disk copies, with a single-target sync, a web-only drift hook, and
  web-only gating. That is a latent dual-copy defect (measured red in E5). Memory
  `wom-skills-governance-gap` already records the symptom: editing a canonical skill = stamp, sync,
  relock "3 repos incl. hand-copy to @wom root" -- commit `207b58c` is literally titled "hand-copy
  w0m-sdlc-research and w0m-sdlc-spec to the umbrella; relock".
- Registry-side history: `8bd38d5e2` (T294, 2026-09-02) `root: "wom7web"` -> `"."` plus
  `canonical_repo: wom7web`, whose note says `canonical_repo` "keeps the contract (.w0m/sdlc.json)
  where its readers already expect it"; `e506674` (T232, 2026-09-07) created the root manifest and
  removed the `.agents` symlink; `ae22a0efd`/`8eb914e` (T412, 2026-09-20) elevated sdlc.json
  (`root` `".."` -> `"."`) and symlinked web's copies of policies (`wom7web/project/clients-policy.json
  -> ../../project/policies/clients-policy.json`). The catalogue reads `CANONICAL/project/clients-
  policy.json` (`:47`) through that symlink, fine, but never learned `canonical_repo`.

### E4. How the catalogue resolves things and who consumes it (Q3)

Resolution: registry from `CANONICAL/project/clients-policy.json` (`:47,234`), one catalogue row per
enabled project (`:239-245`); `root = (ROOT / p["root"]).resolve()` (`:242`, `ROOT` = `@wom`, `:45`);
manifest/lock at `root/.w0m` (`:141,144`); governed layer `root/.agents/skills`, runtime layer
`root/.claude/skills` (`:150-152`); overrides keyed `<project>:<skill>` (`:138,162`; schema pattern
`^[a-z0-9-]+:[a-z0-9-]+$`, `skills-policy.schema.json`, one colon only); `build()` refuses an
empty total (`:249-252`) but nothing refuses a *shrunk* corpus.

Consumers of its output:
- `just skills-catalogue` / `skills-catalogue-test` (`wom7api/justfile:4208-4216`).
- `client_check.py:48` (runs it with NO project argument, so it catalogues everything and uses only
  the exit code; `:111` says it is advisory by design); profile key `skills` tier required, gate
  `skills-catalogue` (`project/client-profile.json:49-58`).
- `project/test-suites.json:734-739` (suite `skills-catalogue`, `blocking: false`, reason still says
  "RED as of 2026-08-13 (17/18) ... one assertion"; stale) and `:1774-1775` (recipe excluded,
  advisory).
- Debt rows `TECH-DEBT.md:70` (D53) and `:105` (D66); tickets T385 AC3 (`.tasks/T385.md:42`,
  which wrongly says fix "declarations ... in `.w0m/sdlc.json`"; overrides live in
  `project/policies/skills-policy.json`) and T226 (AC1 asks exactly "did the client change or did the
  test rot", AC2 asks to kill the hardcoded coordinates).
- NOT consumed by: STATE (`state-check`), deploy pre-flight, preflight, pre-push, `toolset_status`
  (it runs `just skill check`, a different tool), the `--enforce` flag (only the test passes it,
  `test:109,132`). Blast radius of changing its scope is therefore: the one test, the advisory
  output, and the `skills` profile gate (exit code only).

What changes if it measured every repo manifest (computed by calling the existing functions on the
three real roots, no code edits):
- Rows 143 (25 + 109 + 9), distinct names 115; unmanaged 0; excluded 10 (web).
- web `mmd-validate` reports 8,146 "runnable files": 8,144 are under
  `wom7web/.agents/skills/mmd-validate/node_modules/` (gitignored, `.gitignore:5`; only 4 files of
  that skill are tracked besides SKILL.md); real set is `test.mjs`, `validate.mjs`. Cause:
  `ships_executable` (`:70-86`) does an unfiltered `rglob("*")` and treats any `.js` or exec-bit file
  as runnable. Also a perf cost on every run.
- Its `host_invocations` (`:89-116`) matches any line containing `skills/` and any of the 8,146
  basenames; that produces 5 hits for web `mmd-validate`: `justfile:1266` and `:1274` are REAL
  (`node ../wom7skills/skills/mmd-validate/validate.mjs`, `test.mjs`), `:3279`, `:3411`, `:3447` are
  FALSE positives (comments, matched on the basename `y.js` from node_modules). Comments are not
  filtered anywhere in that function.
- Because `wom7web/justfile` is a symlink to `wom7api/justfile`, scanning both repos would read one
  file twice (needs de-dup by realpath).
- web `webapp-testing` ships `scripts/with_server.py`, host hits none; policy override
  `w0m:webapp-testing` (`skills-policy.json:25`) would apply again if the override key stays
  project-scoped, which restores assertion (e) of the test.
- New real finding it would add: web `mmd-validate` is `sandboxed: true` (inherited) while
  `justfile:1266/1274` run its shipped code on the host (same shape as artemio's).

### E5. Current propagation drift (the real SSOT hazard), measured with read-only commands

- `skills.ts --check ..` (root): clean. `--check ../wom7web`: clean (44 selected). `--check
  ../wom7api`: **drift** `w0m-ticket-audit/SKILL.md (active copy differs from canonical)`; api's
  `observed_version` 2026.09.19-1789854184 vs canonical 2026.09.22-1790054019; the diff also shows
  api's copy still points at the retired `project/tickets/` path (T418 moved it to `.tasks`).
- `w0m skill check` on root: **2 blocking findings**, `w0m-tasks` integrity drift (installed
  `sha256-fcb319cd...` != locked `sha256-0521d11d...`) and version drift (installed
  2026.09.28-1790589022 != manifest 2026.09.22-1790054019), caused by canonical commit `fd3a232`
  (2026-09-28) synced to root and web but relocked only in web. Web and api: green.
- Nothing automated runs either of those two red checks: the only drift hook targets web
  (`wom7web/.pre-commit-config.yaml:135`), `toolset_status` runs `just skill check` from wom7web
  (`:36,46`), the root and api pre-commit configs have no skills hook.
- `just skills-sync` has no multi-target form: `justfile:3284-3285` (api/web) and root
  `justfile:797-798` both resolve to the default target `../wom7web` (`skills.ts:174`).

### E6. Client artemio: a runnable skill inheriting `sandboxed: true` with a host call site

(Read-only; client repo is OWNER-WRITE-ONLY; no write proposed.)
`/Users/proto/Projects/_self/delivery/artemioquierocomer.mx` (registry id `artemio`):
- `.w0m/skills.json` declares `mmd-validate` as `w0m-native`, `observed_version`
  2026.09.02-1788352673 (56 declared, 10 excluded). Its `.agents/skills/mmd-validate/` ships
  `validate.mjs` and `test.mjs` (plus package.json, no node_modules there).
- `justfile:394-396`: `lint-mmd *args:` runs
  `node /Users/proto/Projects/@self/@wom/wom7skills/skills/mmd-validate/validate.mjs {{...}}`
  (T213). The catalogue flags it at `justfile:396` (confirmed): `declared sandboxed: true, but its
  shipped code is invoked directly ... ON THE HOST`.
- Two facts beyond the catalogue's own message: (i) the path executed is the ABSOLUTE path into
  w0m's canonical `wom7skills` checkout, NOT artemio's vendored copy, so the vendored copy is never
  what runs here, and the client recipe is machine-specific (breaks on any other machine/CI);
  (ii) the catalogue matched only because the line contains `skills/` + `validate.mjs`.
- `idea-refine`: override `artemio:idea-refine` (`skills-policy.json:21`) is correct (`sandboxed:
  false`), but the call site moved `justfile:215` -> `:267` (`idea-refine-init`, `bash
  .claude/skills/idea-refine/scripts/idea-refine.sh`), so the test's hardcoded `justfile:215`
  (test:105-106) is dead.
- Decision belongs in w0m's policy (an override with a reason in `project/policies/skills-policy.json`,
  our file), and the justfile path fix is an owner-run change in the client repo.

### E7. Other tools with the same post-elevation scope shrink (Q4; do not fix)

Class: "reads `<registry root>/...` or `<repo>/...` where the content now lives elsewhere".

1. `skills_catalogue.py:242` -> **k7**: catalogue shows 0 (root `@wom/k7` has no `.w0m`); its
   `canonical_repo: k7d` has `.w0m/skills.json` (4 skills, lock, `.agents/skills` 4). `mob`/
   `bridgeroad` have no skills at their canonical repo, so are correct-by-luck. (Evidence: catalogue
   output E2; `ls k7/k7d/k7d/.w0m`.)
2. `client_check.py:79,119,130` and `client_profile_check.py:205,243`: read
   `ROOT / p["root"] / ".w0m" / "sdlc.json"`. For workspace projects whose contract lives in a
   member repo this gives "undeclared": `python3 project/scripts/client_check.py k7` prints
   `profile: 9 required key(s) -- 0 declared, 9 missing` and every gate `n/a`, while
   `@k7/k7d/k7d/.w0m/sdlc.json` exists (measured, exit 1); `client_profile_check` likewise lists
   `k7 missing 9` (output lines 20,31). Note `client_inventory.py` and `state_bounds.py:100-101`
   handle `canonical_repo` correctly, so inventory and these two disagree about k7.
3. `wom7skills/w0m_skill.ts:1746-1760` (`discoverEstateRoots`, behind `just skill estate` and
   `gaps`): resolves `repos` against `configRoot/cfg.root`. Since T412 `root` is `"."` and the
   sdlc.json is reached through `wom7web/.w0m/sdlc.json` (symlink), so `configRoot=wom7web` and every
   repo becomes `wom7web/<repo>`. Measured: `--project wom7web estate` -> all 10 repos
   `no-skills-directory`, and `gaps` prints `(missing on disk)` for all 10 and "8 canonical skill(s)
   installed nowhere" (false); the same command with `--project <@wom root>` works.
4. `wom7web/project/scripts/epic_completeness.py:21`: `ROADMAP = REPO / "ROADMAP.md"` with `REPO =
   wom7web`; ROADMAP.md moved to the root in T414 -> running it raises `FileNotFoundError:
   .../wom7web/ROADMAP.md` (measured). No recipe in `wom7api/justfile` references it (grep), so it is
   an orphan script, not a live gate.
5. Already correct (the contrast): `changelog_drift.py:36-38` and `sync_epic_vocabulary.py:20-22` use
   `ROOT = WEB.parent`; `org_migrate_plan.py:46` uses `ROOT / ".tasks"`; `state_bounds.py`
   `canonical_repo`.
6. Not a shrink but adjacent: the root `.w0m/sdlc.json:2` `$schema: ./sdlc.schema.json` dangles
   (reported by `client_profile_check`); it dangled before T412 as well (`ae22a0efd^` same value, no
   such file), so not caused by the elevation.

## Options + matrix

Estate rules applied: one SSOT per fact; no fallback ladders; clean cutover; fail closed; read-only
on client repos.

- **O1. Catalogue measures every governed surface of every enabled project** (surfaces = registry
  `root` U each `repos` member, de-duplicated by realpath; a surface exists if it carries
  `.w0m/skills.json` or `.agents/skills` or `.claude/skills`). Manifests stay as they are. Row id
  `<project>` stays; add `surface` (repo label). Overrides keep `<project>:<skill>` and apply to all of
  that project's surfaces (no schema change).
- **O2. Honour `canonical_repo` only** (mirror `state_bounds`/`client_inventory`): w0m -> wom7web
  (99), k7 -> k7d (4). Three-line change.
- **O3. Collapse to ONE manifest** (root) and make every repo consume it.
- **O4. Per-repo project entries in `clients-policy.json`** (`w0m-web`, `w0m-api`, `w0m-root`, new
  role e.g. `estate-member`), catalogue unchanged.
- **O5. Leave the tool, edit the test** (hardcode w0m excluded 0 / re-point at 25).

Weights 1 (bad) to 5 (good); "cost" and "risk" scored so 5 = cheap / safe. Weighted total uses
weights cost 2, risk 3, unblocks 3, SSOT/rule-fit 3 (max 55).

| option | cost (x2) | risk (x3) | unblocks (x3) | rule fit (x3) | total | notes |
|---|---|---|---|---|---|---|
| O1 measure all surfaces | 3 (about a day: ~40 lines + 3 tool fixes + test rewrite) | 4 (read-only, readers limited to 1 test + advisory) | 5 (T385 AC3, T226, D53/D66 rows, k7, restores assertion (e), exposes web:mmd-validate) | 5 (no new SSOT, fail-closed, honours registry `repos`) | **50** | recommended |
| O2 canonical_repo only | 5 | 3 (moves the blind spot: root 25 and api 9 stay unmeasured, silently) | 2 | 3 (matches 2 siblings, but the shrink class survives) | 32 | acceptable stopgap only |
| O3 collapse manifests | 1 (re-architect skills.ts/w0m_skill/ide surfaces, relock 3 repos) | 1 (undoes T149/T232; wom7api would load 99 skills or lose its own; unmeasured whether a repo session sees `@wom/.agents`) | 2 | 2 (removes duplication but fights a recorded owner decision) | 22 | reject |
| O4 per-repo registry entries | 2 | 2 (registry is read by about 8 tools; "exactly one role: estate" invariant in `client_inventory.py:260-262`; duplicates the repo list a second time) | 4 | 2 (second SSOT for `repos`) | 29 | reject |
| O5 edit test only | 5 | 1 (cements a measurement that silently excludes 124 of 143 rows; the exact vacuous-check shape in LESSONS) | 1 | 1 | 22 | reject |

## Recommendation

Adopt **O1**, as follows (design only; nothing implemented here):

1. **Surface discovery, one rule.** For each enabled registry project: candidate surfaces are the
   project `root` plus every path in `repos` (`clients-policy.json:16-24` for w0m; `k7`, `mob`,
   `bridgeroad` have their own maps). Resolve with `.resolve()`, de-duplicate by realpath, require
   each declared path to exist (error, not skip: "declared repo is not on disk -- scope would silently
   shrink", the wording `repo_hygiene.py:267` already uses). A surface with no manifest and no
   skills directory is listed as `no skills surface` (counted, visible), not dropped. A surface with a
   skills dir but no manifest is `unmanaged` (existing behaviour, `:158-161`).
2. **Output shape.** Keep `projects[]`; add `surfaces[]` inside each (label, root, manifest/lock
   presence, counts, rows). The only structured consumer is the test; `client_check` uses the exit
   code.
3. **Three tool fixes that O1 forces** (each with a red probe): prune `node_modules`/gitignored files
   in `ships_executable` (or restrict to `git ls-files`), ignore comment-only lines and de-dup by
   realpath in `host_invocations`, and make an override key that matches no catalogued skill an
   error (today `w0m:webapp-testing` silently decayed for 23 days).
4. **Decisions that go in w0m's own policy** (`skills-policy.json`, owner approves): `w0m:mmd-validate`
   and `artemio:mmd-validate` get `sandboxed: false` with reasons (headless mermaid parse run via
   `just mmd-validate` / `lint-mmd`); `w0m:webapp-testing` stays. Do not edit artemio.
5. **Tests assert properties, not census** (T226 AC2): expected excluded counts come from reading each
   manifest in the test; host-invocation detection is proven on a fixture justfile, not on
   `artemio justfile:215`; "no manifest on disk under a declared project is uncatalogued" is computed
   independently of the tool (`git ls-files` per repo).
6. **Split** (estate rule on leftover scope, different kind of work): new ticket `Split from: T???`
   for propagation. One command that syncs + relocks every declared consumer, a `--check` over
   root/web/api wired into `just test` and pre-commit for root and api, and `estate`/`gaps` root
   resolution. It is currently red (E5, E7-3) and blocked_by nothing; the catalogue ticket does not
   need it to land.

## Draft acceptance criteria

Each AC names its verifying probe; "red probe" = a fixture mutation that must flip the result.

1. **AC1 Scope = every manifest.** `just skills-catalogue --json` for project `w0m` lists surfaces
   `.`, `wom7web`, `wom7api` with `installed` 25 / 109 / 9 (values derived, never hardcoded). Probe:
   `skills-catalogue-test` asserts set-equality between catalogued surface roots and
   `git ls-files '*/.w0m/skills.json'` run per declared repo plus the root. Red probe: fixture
   workspace with a second repo carrying a manifest -> row count rises; removing it -> falls.
2. **AC2 Canonical-repo blind spot closed.** Project `k7` reports 4 installed (from `k7d`). Probe:
   live assertion `k7` installed == count of `.agents/skills` dirs at its canonical repo, plus a
   fixture (`canonical_repo` != root) red probe.
3. **AC3 No silent shrink.** A declared repo path missing on disk -> exit 2 naming it; a corpus
   smaller than the number of manifests found -> exit 2. Probe: fixture registry with a bogus repo
   (exit 2), fixture with zero surfaces (exit 2, already `:249-252` for the empty case).
4. **AC4 Excluded counts are derived.** Per surface, `excluded == len(manifest.exclude)`; web == 10.
   Probe: test reads manifests; red probe deletes one exclude entry from a fixture manifest and the
   unmanaged count rises by one.
5. **AC5 Executables are real files.** `ships_executable` ignores `node_modules` and untracked
   output: web `mmd-validate` = exactly `{test.mjs, validate.mjs}`; run time of `just
   skills-catalogue` measured before/after (record it). Red probe: a `.js` inside a fixture skill's
   `node_modules` is not counted; a tracked `.py` is.
6. **AC6 Host invocation is a real invocation.** Comment-only mentions do not count; one physical
   file (symlinked justfile) is scanned once. Probe: fixture justfile with the basename only in a
   `#` comment -> `runs_on_host == []`; fixture with a recipe line -> reported once; web
   `mmd-validate` hits are exactly the recipes at `justfile:1266,1274` (resolved by recipe name in the
   test, not by line number).
7. **AC7 Orphan overrides fail closed.** An override key matching no catalogued skill -> exit 2 naming
   the key. Probe: fixture policy with `w0m:nonexistent` (exit 2); live `skills-policy.json` has zero
   orphans.
8. **AC8 Every runnable skill has a decision.** `webapp-testing`, `mmd-validate` (web and artemio),
   `idea-refine` each have an override with a reason in `skills-policy.json` (schema minLength 30),
   owner-approved. Probe: `just skills-catalogue-test` and live `skills_catalogue.py` print no
   "inherits the default" / "contradicted" suggestion for them; `--enforce` exit code reported (it
   will stay 1 while the 23 user-scope skills are undecided; state that explicitly rather than hide
   it).
9. **AC9 Test is green and property-based.** `just skills-catalogue-test` passes N/N (N reported), no
   assertion pins a line number or a census of a client repo (grep of the test for `justfile:\d+` is
   empty); every previously failing assertion has a red probe (T226 AC4). Then
   `project/test-suites.json:734-739` is updated (reason rewritten or `blocking` flipped, owner
   decision) and `just ac-recipe-check` stays green.
10. **AC10 Tools agree.** `client_inventory` w0m `skills.declared` equals the catalogue's web
    surface `project_managed`. Probe: one assertion in `skills-catalogue-test` comparing the two
    tools' output.
11. **AC11 Debt and tickets reconciled.** D53 and D66 rows updated with re-measured numbers, T385 AC3
    wording corrected (policy file, not sdlc.json) and marked `[x] ... split into [[T...]]` where
    applicable; T226 AC1 answered per assertion (E2 mapping) -- `just debt-check`.
12. **Split ticket ACs** (propagation, separate ticket): `skills.ts --check` green for root, web and
    api in one recipe; wired in `just test` and a pre-commit hook for root and api; `just skill
    estate`/`gaps` from `wom7web` report zero `(missing on disk)`; red probe = edit one canonical
    skill, skip the relock, and the aggregate fails.

## Definition of Done

- AC1-AC11 verified with the named probes; `just skills-catalogue`, `just skills-catalogue-test`,
  `just client-inventory`, `just test` (offline tier) output pasted in the ticket.
- No file in any client repo changed; `git status` of artemio unchanged (read-only run proven).
- Numbers in D53/D66, T385, T226 and `test-suites.json` re-measured on the day of archive, not copied
  from this report.
- STATE/TASKS updated in the same commit; no `--no-verify`; commit references the ticket.
- Open questions below closed by an owner reply, leftovers split into a dependent ticket.

## Risks

- **False assurance in reverse.** Measuring 143 rows with a 20-skill overlap inflates totals; report
  distinct names beside rows, or "installed N skills" becomes meaningless (measurement-trap lesson).
- **Override key semantics.** Keeping `<project>:<skill>` for all surfaces is simple but cannot
  express "sandboxed in api, not in web" for the same name; today no such case. Revisit if one appears
  (schema pattern change needed).
- **Performance.** An unfiltered `rglob` over web's `mmd-validate/node_modules` (8,144 files) runs on
  every invocation; AC5 must measure it.
- **Test coupling to live manifests.** Property tests that read the live manifests are still coupled
  to the live repo, but only through derived values; fixtures carry the red probes.
- **Hidden decision:** `webapp-testing` and `mmd-validate` sandboxing declarations are owner policy;
  an agent must not pick `sandboxed: false` silently (the catalogue's own T182 lesson).
- **Concurrent edits.** The working tree is shared; the root `.w0m/skills.json` and web manifests move
  daily (`a9a49950` today). Re-measure before acting; do not stage other agents' files.
- **k7/mob are symlinked workspaces outside the repo** (`k7 -> /Users/proto/Projects/@self/@k7`); a
  realpath-based de-dup must not follow a link into a different repo and double count.

## Open owner questions (recommended answer, weight)

1. Keep per-repo manifests (O1) or collapse (O3)? Recommend **keep** (T149/T232/T147 decisions;
   collapse cost L, risk high). Weight: decides the whole design; one reply.
2. Is the 20-skill root/web duplication wanted, i.e. does a session started in `wom7web` see
   `@wom/.agents/skills`? Not measured here (needs a live session probe). Recommend **measure first**,
   then decide whether web drops the 20 root-level skills; unblocks removing the largest duplicate
   (cost S to measure, M to change).
3. Approve `sandboxed: false` + reason for `mmd-validate` (w0m web and artemio) and keep
   `webapp-testing` as is? Recommend **yes**, w0m-side only. Money/accounts: none; policy edit.
4. Artemio `justfile:396` hardcodes `/Users/proto/Projects/@self/@wom/wom7skills/...`: owner to repair
   in the client repo (use the vendored `.agents/skills/mmd-validate/validate.mjs`, or drop the
   recipe). Owner-write-only; w0m will only record the finding. Weight: low risk, P3.
5. After AC9 is green, flip `skills-catalogue-test` to `blocking: true`? Recommend **yes after one
   week green** (T135 AC8 pattern: never install a gate red; a permanently-advisory suite rots, D53).
6. The 23 user-scope skills (`~/.claude/skills`, no `~/.claude/.w0m/`) keep `--enforce` permanently
   red since 2026-08-17 (`sdlc.json:652+ user_scope_open`). Recommend splitting a separate ticket
   (provenance needs a content diff against upstream per skill; do not fabricate sources). Weight:
   unblocks using `--enforce` at all.
7. Create the split propagation ticket now (sync + relock + drift gate for every consumer, plus
   `estate`/`gaps` root fix)? Recommend **yes**; it is currently red on two surfaces and no gate sees
   it. Cost M, unblocks safe canonical skill edits.
8. Should `client_check.py`/`client_profile_check.py` (k7/mob look "0 declared") and
   `epic_completeness.py` (crashes on moved ROADMAP.md) get tickets? Recommend **one grouped
   "post-elevation root-anchored readers" ticket**; they are the same class as this one (E7).
