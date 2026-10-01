# The 37 "no caller" scripts: weighted review (2026-09-30)

Owner direction that triggered it: *"I can see that some or even most of these scripts are super useful and should be converted into regular tools; recheck and weight it for each."*

The first pass (the T509 research) recommended deleting about 18 of 37 by name and reference count. Re-reading each script's own description, size, age and whether it writes or touches a live system changed the outcome: **12 convert to tools, 9 fold into existing tools, 7 wait on an owner decision, 8 retire.** The per-script weights (Value, Reuse, Ready, each 1 to 5) and the reasoning live in the four tickets:

| Group | Ticket | Count |
|---|---|---|
| A. Convert to regular tools | [[T516]] | 12 |
| B. Fold into existing tools | [[T517]] | 9 |
| C. Owner decision first | [[T518]] | 7 |
| D. Retire | [[T519]] | 8 |

Not on the list because it is not a script: `__init__.py` (a package marker; the research counted 31 references). `init_tinybird_schemas.py` was read for its structure only, never its token value; its leak was closed under [[T515]].

Method: for each script, purpose line, lines of code, last commit date, commit count and flags (secrets, writes, arguments, dry-run guard) were extracted by script; references were counted per repo with `git grep -w` across all seven repos and the tickets. Scripts with no description were read in full or in their working lines. Their inputs were checked for existence (for example `wom7web/src/content/posts`, `design/codemap.yml` and `wom7web/src/data` no longer exist).

## Appendix: raw per-script facts

Format: `repo/file | lines | last commit | commit count | flags`, then the purpose text found in the file (empty when the file has none).

```text
## wom7web/backfill_upwork_proposals.py | 189 loc | last 2026-09-15 | 1 commits | writes,cli-args,dry-run-guard
   T155: Backfill Upwork proposal cover letters from proposals_archive.jsonl into public.proposals. Updates existing proposals with cover letters and aligned tags (AC3, AC6), and inserts historical archive proposals attributed to the owner profile.
## wom7web/ds_inventory.py | 155 loc | last 2026-09-24 | 1 commits | writes,cli-args
   Design-system component inventory and diff (T439). Answers, for one point in time: which components the design system SPECIFIES (`design-system/components/**/*.d.ts`), which the runtime SHIPS (`packages/ui`, `@webomage/ui`), which each app builds LOCALLY, and how often apps import each shared component. The diff sections are wha
## wom7web/env_rename_migrate.py | 174 loc | last 2026-09-18 | 3 commits | secrets,writes,cli-args,dry-run-guard
   Migrate the estate from `--env=dev` to `--env=beta` — but only once `beta` actually resolves. Owner 2026-08-19: *"since we have live prod deployment aligned to default beta branches let's actually rename env from dev to beta"*. The rename is not cosmetic. `--env=dev` resolves to `db.pqbbjgeapylcengbuvee` — the LIVE database ([[i
## wom7web/graph_callsites.py | 201 loc | last 2026-09-18 | 4 commits | cli-args
   T151 AC1 — enumerate what actually invokes graphify vs codegraph across the estate. Answers one question: *before changing which code-graph tool the estate reaches for, what is currently wired to call each one?* Three things this deliberately does that a naive grep does not: 1. **Dedupes by RESOLVED path.** `wom7web/justfile` an
## wom7web/status_truth.py | 121 loc | last 2026-09-23 | 2 commits | writes
   Status-truth pass — measure every `in-progress` ticket against EVIDENCE, not its own field. For each one: AC progress, the last commit that MENTIONS the id, and the last commit that TOUCHED the ticket file. Those are different facts — a ticket edited today with no code commit in a month is being curated, not worked. Read-only. P
## wom7web/t352_fallback_hat_probe.py | 135 loc | last 2026-09-12 | 1 commits | writes
   T352 verification probe — devops seeding, fallback provisioning/retraction, client-side hats. Usage: python3 project/scripts/t352_fallback_hat_probe.py Every mutating check runs inside its own BEGIN ... ROLLBACK — nothing here is left behind.
## wom7web/test_obsidian_mcp.py | 54 loc | last 2026-08-14 | 1 commits | -
   
## wom7web/verify_siri_shortcuts_contract.py | 117 loc | last 2026-09-16 | 1 commits | secrets
   Verification suite for T367: Siri and Apple Shortcuts Voice Orchestration for ZeroClaw and Orca IDE via Local OMLX Inference. Verifies: 1. Apple Shortcut definition validity and action contract. 2. ZeroClaw ~/.zeroclaw/config.toml configuration: - [providers.models.custom.omlx_qwen] points to local OMLX (:8080/v1). - [gateway.pa
## wom7web/verify_t440_live.py | 135 loc | last 2026-09-24 | 1 commits | secrets,writes
   T440 Live Verification Probe. Verifies: - AC1: Re-attribution of 95 contracts, 1,782 proposals, 55 rooms, 170 messages, 3 tokens to Aleksei's person profile (8d16aff5), leaving 0 on casualuser (5691add5). - AC3: RLS evaluation — signed in as aleksei@webomage.com, the member sees 95 contracts and 1,782 proposals through RLS (not 
## wom7web/verify_t443_founder_units.py | 120 loc | last 2026-09-24 | 2 commits | secrets,writes
   T443 Live Verification Probe. Verifies: - AC1: Elena's unit is in squad Leadership, titled 'Co-founder, CEO & CFO', sort_order 10. - AC1: Aleksei's unit is in squad Leadership, titled 'Co-founder, CO & CTO', sort_order 20. - AC2: Engineering (Matrix) retains open slot 'Senior Fullstack Specialist (Hybrid) I' at sort_order 100. -
## wom7web/verify_t444_site_settings.py | 85 loc | last 2026-09-24 | 2 commits | secrets,writes
   T444 Live Site Settings Verification Probe. Verifies: - AC1: `public.site_settings` contains `external_links` with default URLs seeded. - AC3: RLS evaluation — anon and authenticated users can SELECT `external_links`. Usage: infisical run --env=beta --silent -- python3 project/scripts/verify_t444_site_settings.py
## wom7web/write_hygiene_docs.py | 628 loc | last 2026-09-18 | 5 commits | secrets,writes,cli-args,dry-run-guard
   T135 §4 — bootstrap the required human-facing files across the estate. WHAT THIS IS. A one-shot generator for the three files whose *correct* form is uniform across repos — LICENSE, SECURITY.md, CODE_OF_CONDUCT.md — plus CONTRIBUTING.md, which is uniform in structure but carries each repo's REAL gates and commands. It is committ
## wom7web/zc_compression_measure.py | 280 loc | last 2026-09-02 | 3 commits | secrets,cli-args
   Measure what ZeroClaw's context compression actually costs and saves. WHY THIS EXISTS --------------- Headroom was adopted on a compression figure that turned out to be Anthropic's prompt-cache discount re-badged; measured properly it saved **0 tokens**. The lesson was not "distrust that vendor" — it was that a compression claim
## wom7web/zeroclaw_manage.py | 266 loc | last 2026-09-18 | 2 commits | secrets,cli-args
   ZeroClaw Runtime Management & Health Probe (T153 AC1, AC5, AC7) Subcommands: sync - Generate ~/.zeroclaw/config.toml from tracked template, preserving local tokens check - Detect drift between tracked template and installed ~/.zeroclaw/config.toml health - Run comprehensive ZeroClaw runtime health audit (AC7): * Binary version &
## wom7api/backfill_news.py | 123 loc | last 2026-05-08 | 2 commits | -
   Configuration
## wom7api/backfill_post_images.py | 169 loc | last 2026-05-08 | 4 commits | secrets,cli-args,dry-run-guard
   Call the Supabase Edge Function to generate and upload an image. Returns: {"success": bool, "image_url": str, "error": str}
## wom7api/check-upwork-proposal.js | 29 loc | last 2026-08-19 | 3 commits | secrets
   Secrets arrive by PROCESS INJECTION (T135 §6 / AC10) — no dotenv, no .env: infisical run --env=beta --silent -- node scripts/check-upwork-proposal.js
## wom7api/fetch-upwork.js | 14 loc | last 2026-08-19 | 3 commits | secrets
   Secrets arrive by PROCESS INJECTION (T135 §6 / AC10) — no dotenv, no .env: infisical run --env=beta --silent -- node scripts/fetch-upwork.js
## wom7api/fix_diagrams.mjs | 30 loc | last 2026-08-19 | 3 commits | secrets,writes
   Secrets arrive by PROCESS INJECTION (T135 §6 / AC10) — no dotenv, no .env: infisical run --env=beta --silent -- node scripts/fix_diagrams.mjs
## wom7api/fix_missing_prompts.py | 36 loc | last 2026-01-17 | 2 commits | secrets,writes
   
## wom7api/gen_codemap_mmd.py | 104 loc | last 2025-12-29 | 2 commits | writes
   Global styling
## wom7api/gen_tracks_artifacts.py | 63 loc | last 2025-12-29 | 1 commits | writes
   Frontend data path (../wom7web/src/data/tracks.json)
## wom7api/get_keys.py | 32 loc | last 2026-07-17 | 2 commits | secrets
   Never hardcode the access token. Read the Supabase PAT from the environment (SUPABASE_ACCESS_TOKEN), matching the .env / Infisical convention used repo-wide.
## wom7api/get_upwork_auth.ts | 8 loc | last 2026-02-11 | 1 commits | -
   
## wom7api/index_internal_docs.py | 88 loc | last 2026-08-08 | 3 commits | secrets,writes
   Config Checked individually rather than with `all([...])` — see the note in ingest_blueprints.py.
## wom7api/infisical_set_prod.py | 129 loc | last 2026-06-23 | 1 commits | secrets,cli-args,dry-run-guard
   infisical_set_prod.py — push rotated secrets into the Infisical PROD environment. Reads KEY=VALUE pairs from a LOCAL file you create and creates/updates them in the w0m project's `prod` environment via the Infisical API. Secret *values* are never printed — only key name + create/update + ✓/✗. Designed for part-by-part rotation: 
## wom7api/init_tinybird_schemas.py | 48 loc | last 2026-06-04 | 1 commits | secrets
   
## wom7api/resume-assist-eval.ts | 261 loc | last 2026-09-30 | 2 commits | secrets
   resume-assist-eval.ts (T501 AC6) — pick the model behind `w0m-llm-personnel` by measurement, on the member's own text. Runs each candidate through the production path (`WORKERS_WEBHOOK_URL/ai/chat`, the proxy every edge function uses) with the exact prompts and the exact chunking the `w0m-personnel` function uses, and scores the
## wom7api/security_audit.py | 162 loc | last 2026-07-23 | 2 commits | secrets
   
## wom7api/smoke_test.py | 37 loc | last 2025-12-23 | 1 commits | -
   Worker URL (Production)
## wom7api/update_system_status.py | 60 loc | last 2025-12-23 | 1 commits | -
   Configuration In a real scenario, this would check APIs, Terraform state, etc. For now, we simulate a check of the core components defined in the registry.
## wom7api/validate_content.py | 85 loc | last 2025-12-26 | 1 commits | -
   
## wom7api/validate_rust_vs_python.py | 187 loc | last 2025-12-23 | 1 commits | secrets
   Validation script to test Rust MLX implementation against Python baseline
## wom7api/validate_tracks.py | 65 loc | last 2025-12-29 | 1 commits | -
   
## wom7api/verify_cf_ai.py | 49 loc | last 2026-05-08 | 2 commits | secrets
   
## wom7api/ai-eval.ts | 152 loc | last 2026-09-29 | 2 commits | secrets
   ai-eval.ts — reusable model scorecard for w0m chat agents. Runs a fixed eval suite (grounding, identity-safety, jailbreak refusal, formatting) against each candidate CF Workers AI model, DIRECTLY via CF's ai/run (offline — no live agents touched), and prints a comparison table. Retrieval is model-independent, so a representative
```
