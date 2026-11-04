# ── @wom/just/estate.just — Estate-wide & cross-repo recipes elevated from w0m-api/justfile (T509 L2) ──


# Start Cloudflare Tunnel for DB access
db-tunnel:
    @cloudflared tunnel --config w0m-api/cloudflared/wom.yml run wom

# T431 probe for scripts/deploy_function.py (validation + dry-run only; never deploys).
deploy-function-test:
    @python3 scripts/tests/test_deploy_function.py

confirm-log:
    @tail -40 w0m-web/.git/w0m-confirm.log 2>/dev/null || echo "(no confirmations recorded yet)"

# Seed/reset the two LIVE demo personas (T41: demo-client + demo-candidate) via the
# seed-demo edge fn; idempotent (reset-and-reseed by the demo_account marker). Prints the
# magic-link logins to hand to a prospect. Entry point #1 of 3 (CP button + scheduled reset reuse the fn).
seed-demo:
    @echo "Seeding/resetting demo personas via the seed-demo edge fn..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'curl -sS -X POST "https://{{ project_ref }}.supabase.co/functions/v1/seed-demo" -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" -H "Content-Type: application/json"' | python3 -m json.tool

# Sync Infisical secrets to Supabase project secrets.
#
# Delegates to the Python script (tool ladder: logic in Python, not shell). This used to
# interpolate `KEY="$KEY"` inline, which writes a literal EMPTY STRING whenever the source var is
# unset — the store then holds a present, timestamped secret containing nothing, whose digest is
# e3b0c442… (SHA-256 of ""). Every "is it configured?" check reads it as fine and the consumer gets
# ''. That is how GOOGLE_API_KEY ended up empty in Supabase (T134 AC11). The script skips empties
# LOUDLY instead. `just sync-secrets dry` previews without writing.
sync-secrets mode="": (_confirm "sync-secrets")
    @echo "Syncing secrets from Infisical (dev) to Supabase project {{ project_ref }}"
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/sync_supabase_secrets.py {{ if mode == "dry" { "--dry-run" } else { "" } }}

# RETIRED 2026-07-22 (T119 AC2b). `sync-env` exported Infisical into
# apps/{web,cp}/.dev.vars — i.e. it MATERIALISED 83 secrets onto disk, which is the exact
# thing AC2b removes. Those files are deleted; recreating them would undo the work.
# Secrets now reach a process by injection: `infisical run --env=beta --silent -- <cmd>`,
# which is what the dev/build/e2e recipes do. Verified 2026-07-22 that all apps boot and
# serve with no .dev.vars present at all.
sync-env:
    @echo "❌ sync-env is retired (T119 AC2b): it wrote 83 secrets to disk as .dev.vars."
    @echo "   Secrets are injected now — run your command under:"
    @echo "     infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- <cmd>"
    @echo "   The dev/build/e2e recipes already do this."
    @exit 1

# Sync Infisical secrets to Cloudflare Pages project (Production)
sync-cf-secrets project="webomage": (_confirm "sync-cf-secrets")
    @echo "Syncing secrets from Infisical to Cloudflare Pages project {{ project }}"
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c ' \
      echo "$PUBLIC_SUPABASE_URL" | pnpm exec wrangler secret put PUBLIC_SUPABASE_URL --name {{ project }} && \
      echo "$PUBLIC_SUPABASE_ANON_KEY" | pnpm exec wrangler secret put PUBLIC_SUPABASE_ANON_KEY --name {{ project }} && \
      echo "$SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SERVICE_ROLE_KEY --name {{ project }} && \
      echo "$SUPABASE_SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SUPABASE_SERVICE_ROLE_KEY --name {{ project }} && \
      echo "$WORKERS_WEBHOOK_URL" | pnpm exec wrangler secret put WORKERS_WEBHOOK_URL --name {{ project }} && \
      echo "$WORKERS_WEBHOOK_SECRET" | pnpm exec wrangler secret put WORKERS_WEBHOOK_SECRET --name {{ project }} && \
      echo "$LINKEDIN_APP_ID" | pnpm exec wrangler secret put LINKEDIN_APP_ID --name {{ project }} && \
      echo "$LINKEDIN_APP_SECRET" | pnpm exec wrangler secret put LINKEDIN_APP_SECRET --name {{ project }}'

# Sync secrets to Cloudflare Workflows (w0m-cf)
# 🔴 T231 AC3b — TELEGRAM_AGENCY_CHANNEL_ID was ABSENT from the worker until 2026-08-20, and every
# Telegram send is guarded `if (BOT_TOKEN && CHANNEL_ID)`, so `document-generator.ts` had been
# skipping its notifications SILENTLY for as long as that guard existed. The estate's only alerting
# path was inert and nothing said so — a presence guard turns missing config into silence.
# Its source is `TELEGRAM_ADMIN_ID` (one bot, one admin — owner 2026-08-20); the names disagree and
# the CONTENT is what matters, which is why the mapping is written here rather than assumed.
# ⚠️ `test -n` guards it: pushing an empty value would read as CONFIGURED while delivering nothing,
# T231 AC3b — the R2 pair is the WATCHDOG's credential and is `Object read only` BY DESIGN,
# verified 2026-08-21: list succeeds on both prefixes, and put_object AND delete_object both
# return AccessDenied. ⚠️ Never substitute R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY here — those
# are the PRODUCER's read-write pair (`backup_push_r2.py --keep` prunes, so they can delete), and
# handing them to an internet-reachable worker would give the watchdog the power to destroy the
# backups it watches. That is the one thing T231 AC3 was designed to prevent.
# which is the empty-secret trap this estate has hit before (6 secrets holding "").
# ✅ TELEGRAM_BOT_TOKEN is now synced — it was deliberately EXCLUDED until 2026-08-21, because it was
# set on the worker while ABSENT from Infisical, so listing it here would have pushed an EMPTY string
# and DESTROYED the working token: a restore path that breaks the thing it restores. It is in the
# vault now (46 chars, no trailing newline) and verified by `getMe` as @webomage_bot — a valid token
# rather than a plausible-looking string. ⚠️ The order mattered: set the vault, VERIFY, then wire it
# in. Reversed, the first sync would have silently replaced a working token with an unchecked one.
sync-cfworkers-secrets: (_confirm "sync-cfworkers-secrets")
    @echo "Syncing secrets from Infisical to Cloudflare Workflows project: w0m-cf"
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c ' \
      echo "$SUPABASE_URL" | pnpm exec wrangler secret put SUPABASE_URL --name wom7func && \
      echo "$SUPABASE_SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SUPABASE_SERVICE_ROLE_KEY --name wom7func && \
      echo "$CLOUDFLARE_ACCOUNT_ID" | pnpm exec wrangler secret put CLOUDFLARE_ACCOUNT_ID --name wom7func && \
      test -n "$TELEGRAM_ADMIN_ID" && \
      echo "$TELEGRAM_ADMIN_ID" | pnpm exec wrangler secret put TELEGRAM_AGENCY_CHANNEL_ID --name wom7func && \
      test -n "$TELEGRAM_BOT_TOKEN" && \
      echo "$TELEGRAM_BOT_TOKEN" | pnpm exec wrangler secret put TELEGRAM_BOT_TOKEN --name wom7func && \
      test -n "$R2_READONLY_ACCESS_KEY_ID" && test -n "$R2_READONLY_SECRET_ACCESS_KEY" && \
      echo "$R2_READONLY_ACCESS_KEY_ID"     | pnpm exec wrangler secret put R2_READONLY_ACCESS_KEY_ID     --name wom7func && \
      echo "$R2_READONLY_SECRET_ACCESS_KEY" | pnpm exec wrangler secret put R2_READONLY_SECRET_ACCESS_KEY --name wom7func'

# Sync secrets to w0m-api (Cloudflare Worker)
# ⚠️ CLOUDFLARE_API_TOKEN is the account API token with D1/KV/Browser Rendering permissions (read by src/workflows/pdf-generator.ts).
# 🔑 MISTRAL_API_KEY is used by w0m-api AI workflows.
# T213: ADZUNA_APP_ID / ADZUNA_APP_KEY / JOOBLE_API_KEY feed the job-aggregator; they can be managed in CP /admin/connections
# (`public.admin_secrets`) or synced from Infisical when present, and this loop never pushes an EMPTY one over a working secret.
sync-api-secrets: (_confirm "sync-api-secrets")
    @echo "Syncing secrets from Infisical to w0m-api Cloudflare Worker..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c ' \
      echo "$SUPABASE_URL" | pnpm exec wrangler secret put SUPABASE_URL --name wom7api && \
      echo "$SUPABASE_SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SUPABASE_SERVICE_ROLE_KEY --name wom7api && \
      echo "$WORKERS_WEBHOOK_SECRET" | pnpm exec wrangler secret put WEBHOOK_SECRET --name wom7api && \
      echo "$CLOUDFLARE_ACCOUNT_ID" | pnpm exec wrangler secret put CLOUDFLARE_ACCOUNT_ID --name wom7api && \
      echo "$CLOUDFLARE_API_TOKEN" | pnpm exec wrangler secret put CLOUDFLARE_API_TOKEN --name wom7api && \
      echo "$MISTRAL_API_KEY" | pnpm exec wrangler secret put MISTRAL_API_KEY --name wom7api && \
      for n in ADZUNA_APP_ID ADZUNA_APP_KEY JOOBLE_API_KEY; do \
        if [ -n "$(printenv $n)" ]; then \
          printenv $n | pnpm exec wrangler secret put $n --name wom7api || exit 1; \
        else \
          echo "ℹ️  $n is not in Infisical beta — skipped (manage in CP /admin/connections or /admin/secrets, or provision in Infisical for T213)."; \
        fi; \
      done'

# Sync secrets to apps/join (join.webomage.com)
sync-join-secrets: (_confirm "sync-join-secrets")
    @echo "Syncing secrets from Infisical to apps/join (webomage-join)..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c ' \
      echo "$PUBLIC_SUPABASE_URL" | pnpm exec wrangler secret put PUBLIC_SUPABASE_URL --name webomage-join && \
      echo "$PUBLIC_SUPABASE_ANON_KEY" | pnpm exec wrangler secret put PUBLIC_SUPABASE_ANON_KEY --name webomage-join && \
      echo "$SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SERVICE_ROLE_KEY --name webomage-join && \
      echo "$SUPABASE_SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SUPABASE_SERVICE_ROLE_KEY --name webomage-join'

# Sync secrets to apps/job (job.webomage.com)
sync-job-secrets: (_confirm "sync-job-secrets")
    @echo "Syncing secrets from Infisical to apps/job (webomage-job)..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c ' \
      echo "$PUBLIC_SUPABASE_URL" | pnpm exec wrangler secret put PUBLIC_SUPABASE_URL --name webomage-job && \
      echo "$PUBLIC_SUPABASE_ANON_KEY" | pnpm exec wrangler secret put PUBLIC_SUPABASE_ANON_KEY --name webomage-job && \
      echo "$SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SERVICE_ROLE_KEY --name webomage-job && \
      echo "$SUPABASE_SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SUPABASE_SERVICE_ROLE_KEY --name webomage-job && \
      echo "$WORKERS_WEBHOOK_URL" | pnpm exec wrangler secret put WORKERS_WEBHOOK_URL --name webomage-job && \
      echo "$WORKERS_WEBHOOK_SECRET" | pnpm exec wrangler secret put WORKERS_WEBHOOK_SECRET --name webomage-job'

# Sync secrets to apps/cp (cp.w0m.xyz)
sync-cp-secrets: (_confirm "sync-cp-secrets")
    @echo "Syncing secrets from Infisical to apps/cp (webomage-cp)..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c ' \
      echo "$PUBLIC_SUPABASE_URL" | pnpm exec wrangler secret put PUBLIC_SUPABASE_URL --name webomage-cp && \
      echo "$PUBLIC_SUPABASE_ANON_KEY" | pnpm exec wrangler secret put PUBLIC_SUPABASE_ANON_KEY --name webomage-cp && \
      echo "$SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SERVICE_ROLE_KEY --name webomage-cp && \
      echo "$SUPABASE_SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SUPABASE_SERVICE_ROLE_KEY --name webomage-cp && \
      echo "$LINKEDIN_APP_ID" | pnpm exec wrangler secret put LINKEDIN_APP_ID --name webomage-cp && \
      echo "$LINKEDIN_APP_SECRET" | pnpm exec wrangler secret put LINKEDIN_APP_SECRET --name webomage-cp && \
      echo "$WORKERS_WEBHOOK_URL" | pnpm exec wrangler secret put WORKERS_WEBHOOK_URL --name webomage-cp && \
      echo "$WORKERS_WEBHOOK_SECRET" | pnpm exec wrangler secret put WORKERS_WEBHOOK_SECRET --name webomage-cp'

# Sync secrets to apps/demo (demo.webomage.com)
# T79 demo showcase: minimal secrets footprint — only read-only anon Supabase URL
# and server-side service role key for ephemeral demo session cleanup.
# ⚠️ No Hume, LinkedIn, or webhook secrets: demo runs sandboxed with no external integrations.
sync-demo-secrets: (_confirm "sync-demo-secrets")
    @echo "Syncing secrets from Infisical to apps/demo (webomage-demo)..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c ' \
      echo "$PUBLIC_SUPABASE_URL" | pnpm exec wrangler secret put PUBLIC_SUPABASE_URL --name webomage-demo && \
      echo "$SUPABASE_SERVICE_ROLE_KEY" | pnpm exec wrangler secret put SUPABASE_SERVICE_ROLE_KEY --name webomage-demo'

# Quick psql connectivity test
db-psql: (_confirm "db-psql")
    @echo "Testing DATABASE_URL with psql (\dt)..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'psql "$DATABASE_URL" -c \'\\dt\'' || true

db-psql-ssl:
    @echo "Testing DATABASE_URL with psql (sslmode=require, \\dt)..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'psql "$DATABASE_URL?sslmode=require" -c \'\\dt\'' || true

# Cloudflare Terraform helpers
cf-plan:
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN" terraform -chdir=w0m-api/cloudflare plan'

cf-apply: (_confirm "cf-apply")
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN" AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" terraform -chdir=w0m-api/cloudflare apply'

# Azure jumphost Terraform helpers
azure-jumphost-plan:
    @cd w0m-api && terraform -chdir=jumphost plan

azure-jumphost-apply: (_confirm "azure-jumphost-apply")
    @cd w0m-api && terraform -chdir=jumphost apply -auto-approve

# Ensure cv bucket exists
ensure-cv-bucket:
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta -- node supabase/scripts/ensure-cv-bucket.mjs

# T542: the database host must RESOLVE (getaddrinfo, what psql does) and accept a TCP connection. The old line here pinged a dual-stack site and said "the deploy path is IPv4",
# which is false: the database host is IPv6-only, and on 2026-10-03 its name stopped resolving after 19 minutes of tests had already run.
check-db-host-test:
    @python3 scripts/tests/test_check_db_host.py

# Health check all production services and report status
healthcheck:
    @cd w0m-api && python3 scripts/healthcheck.py

# Run SQL migrations
# db-ddl-audit: list schema changes made OUTSIDE `just db-migrate` (T157).
# The wom_ddl_guard event trigger refuses these on public/gamification, so a row here means
# someone deliberately set `w0m.migration = 'on'` in an ad-hoc session — legitimate in an
# emergency, but it must leave a trace and get a migration written after the fact.
# Complements db-drift-check: that one only sees changes that wrote a LEDGER row, this one
# sees the DDL itself.
db-ddl-audit:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- sh -c 'psql "$DATABASE_URL" -c "SELECT occurred_at, db_user, command_tag, object_identity FROM public.schema_change_log WHERE NOT in_migration ORDER BY occurred_at DESC LIMIT 50;"'

# The T198 AC8 red-probe suite — every authorization claim as a runnable assertion.
# Advisory by default; `just authz-probe --enforce` exits 1 on any RED.
authz-probe *args:
    @cd w0m-web && python3 project/scripts/authz_probe_suite.py {{args}}

# T240 AC4 — the SUITE form of the probe above, and it needs its own recipe rather than a registry
# row. `run_suites.py` invokes `["just", recipe]` with NO arguments, so registering bare
# `authz-probe` would declare a suite that exits 0 unconditionally — a suite that can never go red,
# which is the vacuous green `test-suites.json` already refuses in two of its `excluded` reasons.
# 🔑 Enforcing is correct as of 2026-08-20 because the probe's OWN promotion trigger has fired:
# "wire --enforce when RED reaches 0" — measured 0 RED of 18, with A2-cross-client (stage-0's exit
# criterion) green. ⚠️ Read-only, but it reaches the LIVE database — see the header above.
authz-probe-check:
    @cd w0m-web && python3 project/scripts/authz_probe_suite.py --enforce

# T289 AC3/AC4 — can `anon` EXECUTE functions in `public`, and is that getting worse?
# 🔴 Reads the LIVE database on purpose. Supabase's `ALTER DEFAULT PRIVILEGES ... GRANT EXECUTE ON
# FUNCTIONS TO anon` means every new function in `public` arrives with an EXPLICIT anon grant, and a
# restored dump never receives that ALTER — so on a scratch database this property reads as clean
# while being false in production. T4's probe asserted it and passed for exactly that reason. A
# probe for this bug that runs anywhere but production reproduces the bug.
# Downward-only: baseline in `project/anon-execute-baseline.json`, tighten with `--save`, and
# NEVER raise it to go green. Three functions are anon-reachable by design and are listed there
# with the call site that needs them — a blanket revoke is the T246 outage, not a fix.
anon-execute-ratchet *args:
    @cd w0m-web && python3 project/scripts/anon_execute_ratchet.py {{args}}

# The gate's own red probes — proves it fails when it should, including the case the counts alone
# would miss: swapping one definer function for another keeps the total flat and must STILL fail.
anon-execute-ratchet-test:
    @cd w0m-web && python3 project/scripts/anon_execute_ratchet.py --selftest

# Owner rule 2026-08-20: "we have to push at least daily and with every completed ticket also."
# Unpushed work exists in exactly one place. The rule was written after a day that ended with 34
# commits across 6 repos, none pushed — while the ticket being worked (T231) was about not depending
# on a single laptop for backups. The estate had a gate for a stale STATE.md and none for this.
# Two conditions: the oldest unpushed commit exceeding --max-age-hours (default 24), and any
# unpushed commit naming a ticket whose status is now `done`. The second is not implied by the
# first — a ticket can be finished and left local within the same hour.
push-cadence *args:
    @python3 scripts/push_cadence_check.py {{args}}

# T228 AC5b — populate the Projects v2 fields from the TICKET FILES. Empty fields are worse than
# absent ones: a column of blanks reads as "unknown" when the fact sits in frontmatter three feet
# away. The ticket is the source; the board is a projection.
# ⚠️ `--limit N` exists because a mis-mapped single-select writes the wrong state onto every item and,
# unlike a rename, cannot be undone by renaming back. Prove on a handful, then run.
populate-project-fields *args:
    @python3 scripts/populate_project_fields.py {{args}}

# T228 AC5 — carry ticket facts in Projects v2 FIELDS, from the vocabularies declared in
# project/tickets-schema.jsonc. The board held GitHub's defaults (Todo/In Progress/Done) where the
# schema declares five states, so "Todo" covered four of them and `blocked`/`paused` were invisible;
# Priority, Area and Epic had no field at all and lived only as labels.
# 🔑 RENAMES the defaults onto the declared names rather than replacing the option list — a rename
# preserves every item's value (100 of 100 sampled kept theirs), a replacement would blank 234 items.
sync-project-fields *args:
    @python3 scripts/sync_project_fields.py {{args}}

# T228 AC6 — mirror the local batch↔member relationship onto GitHub as native sub-issues. The
# batches exist locally and `just ticket-graph` already proves their symmetry; GitHub showed 10 flat
# rows with the structure living only in a markdown table.
# 🔑 Rebuilt from the TICKET FILES, never from issue titles — a title is prose an editor can change
# in the web UI, so deriving structure from it would let the tracker redefine the record it reflects.
# ⚠️ Uses ticket_graph.py's OWN batch criterion (a declaring title + members). A first version keyed
# only on "≥2 member rows" found 4 batches where the gate finds 2. Dry run unless --apply.
sync-subissues *args:
    @python3 scripts/sync_subissues.py {{args}}

# T236 AC4 — Svelte components no page mounts. The two removed under T236 were orphaned on
# 2026-05-14 when the CP extraction deleted their PAGES and COPIED the components, then absorbed
# THREE commits of maintenance — including a Svelte 5 runes migration — while nothing rendered them.
# They were found by an RLS analysis that happened to enumerate Supabase callers: luck, not process,
# since a component querying nothing would never have surfaced. This looks at MOUNTING instead.
# ⚠️ Sound only because nothing here loads components dynamically (verified 2026-08-20). If that
# changes, this needs a registry, not a wider grep. Advisory; `--enforce` exits 1.
orphan-components *args:
    @cd w0m-web && python3 project/scripts/orphan_components_check.py {{args}}

# T240 AC6 / T236 AC4 — regression test for orphan-components check
orphan-components-test:
    @cd w0m-web && python3 project/scripts/tests/test_orphan_components.py

# T2 AC5 — the client-registration handoff suite. Boots the web app and runs ONE Gauge spec that
# mocks both endpoints (`w0m-consultant`, `client-register`), so unlike `e2e-local` it needs no
# local Supabase and no Docker — the point under test is the FE contract, not the database.
#
# 🔴 SAFETY, and the reason this is not just `gauge run`: tests/support/hooks.ts `@AfterSuite`
# runs pattern-matched DELETEs (`contact_messages` ilike '%test%', '%example.com%', …) against
# whatever PUBLIC_SUPABASE_URL + SERVICE_ROLE_KEY it finds in the environment. Injecting beta's
# values would aim that purge at the LIVE database. The teardown skips when EITHER is missing, so
# gauge is run with both stripped — deliberately, and it must stay that way. The dev server still
# gets them (it needs PUBLIC_SUPABASE_ANON_KEY to build the widget); only the TEST process is blind.
#
# ⚠️ E2E_BASE_URL is resolved, not assumed: astro dev binds IPv6-only here, so the harness default
# of http://127.0.0.1:4321 (tests/support/urls.ts) cannot connect and every scenario fails on a
# missing element — indistinguishable from a broken handoff. Cost one full red run to learn.
client-registration-test:
    #!/usr/bin/env bash
    set -uo pipefail
    cd w0m-web
    if ! curl -s -f -o /dev/null --max-time 3 "http://[::1]:4321/chat" \
       && ! curl -s -f -o /dev/null --max-time 3 "http://127.0.0.1:4321/chat"; then
      echo "  ▶ starting the web app…"
      infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter web dev > /tmp/w0m-t2-ac5-dev.log 2>&1 &
      DEV=$!
      trap 'kill $DEV 2>/dev/null || true' EXIT
      for i in $(seq 1 90); do
        curl -s -f -o /dev/null "http://[::1]:4321/chat" 2>/dev/null && break
        curl -s -f -o /dev/null "http://127.0.0.1:4321/chat" 2>/dev/null && break
        sleep 1
      done
    fi
    BASE=""
    curl -s -f -o /dev/null --max-time 3 "http://[::1]:4321/chat" && BASE="http://[::1]:4321"
    [ -z "$BASE" ] && curl -s -f -o /dev/null --max-time 3 "http://127.0.0.1:4321/chat" && BASE="http://127.0.0.1:4321"
    if [ -z "$BASE" ]; then
      echo "  ❌ web app never served /chat:"; tail -15 /tmp/w0m-t2-ac5-dev.log 2>/dev/null; exit 1
    fi
    echo "  ✅ /chat on $BASE"
    # `gauge` is a HOST binary (/opt/homebrew/bin/gauge), not an npm package — `gauge-ts` is only
    # the TS runner plugin. `npx gauge` fell through to PATH once and then began failing with
    # "could not determine executable to run"; bare `gauge` is what `e2e-local` uses too.
    # 🔴 Keep this comment ABOVE the command. Putting it between a `\` continuation and the binary
    # makes the comment the continuation, so `env` receives NO command and silently prints the
    # environment instead of running anything — 6/6 scenarios "failed" with no step detail at all.
    env -u SERVICE_ROLE_KEY -u SUPABASE_SERVICE_ROLE_KEY -u PUBLIC_SUPABASE_URL -u SUPABASE_URL \
      E2E_BASE_URL="$BASE" \
      gauge run specs/web/client_registration_handoff.spec

# stage-1 exit (ROADMAP §33) — the magic link a client is EMAILED must actually sign them into the
# portal. Nothing covered this seam before 2026-08-25: the handoff suite stops at "a link was sent"
# and `specs/ui/client_portal.spec` starts at a PASSWORD login against an account that does not
# exist in auth.users (and is unregistered, so it never ran).
# 🔴 Unlike `client-registration-test` this recipe must KEEP the service role, not strip it — the
# suite mints a link via the admin API. `generate_link` MINTS and does not send, so no email leaves
# the server. The fixture is the SEEDED demo client, never a real one: `beta` is the live database.
# ⚠️ Runs against the CP on :4325, NOT the web app on :4321 — `client-register` points its link at
# `CP_URL`, and the callback that redeems `token_hash` lives in `apps/cp`.
client-magic-link-test:
    #!/usr/bin/env bash
    set -uo pipefail
    cd w0m-web
    if ! curl -s -f -o /dev/null --max-time 3 "http://127.0.0.1:4325/login" \
       && ! curl -s -f -o /dev/null --max-time 3 "http://[::1]:4325/login"; then
      echo "  ▶ starting the CP app…"
      # 🔴 CLEAR A STALE DAEMON FIRST (T286). `astro dev` runs a background daemon and REFUSES to
      # start a replacement — "Dev server already running (pid N)" — so when the health check above
      # fails, the start below silently no-ops and the loop then finds the SAME broken server. That
      # has cost three debugging sessions: a 23h server answering 500 on IPv6 (stage-1), one
      # serving 404s for island modules (stage-2), and pid 67324 answering 500 on everything.
      ( cd apps/cp && pnpm exec astro dev stop >/dev/null 2>&1 ) || true
      infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter cp dev > /tmp/w0m-stage1-cp.log 2>&1 &
      DEV=$!
      trap 'kill $DEV 2>/dev/null || true' EXIT
      for i in $(seq 1 90); do
        curl -s -f -o /dev/null "http://127.0.0.1:4325/login" 2>/dev/null && break
        curl -s -f -o /dev/null "http://[::1]:4325/login" 2>/dev/null && break
        sleep 1
      done
    fi
    BASE=""
    curl -s -f -o /dev/null --max-time 3 "http://127.0.0.1:4325/login" && BASE="http://127.0.0.1:4325"
    [ -z "$BASE" ] && curl -s -f -o /dev/null --max-time 3 "http://[::1]:4325/login" && BASE="http://[::1]:4325"
    if [ -z "$BASE" ]; then
      echo "  ❌ CP never served /login:"; tail -15 /tmp/w0m-stage1-cp.log 2>/dev/null; exit 1
    fi
    echo "  ✅ CP on $BASE"
    # `gauge` is a HOST binary, not an npm package — see client-registration-test for why `npx` is
    # wrong here. Keep this comment ABOVE the command, not inside a `\` continuation.
    infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- \
      env E2E_BASE_URL="$BASE" gauge run specs/web/client_magic_link_portal.spec

# stage-2 exit — a client REVIEWS a blueprint proposal and ACCEPTS it, and acceptance creates a
# contract AND a delivery container. The AND is the assertion: a check that asserted only the
# contract would pass on half a feature.
# 🔴 THIS WRITES TO THE LIVE DATABASE, because beta IS production. Three rules keep that honest and
# they are T281 AC7 applied rather than quoted: it uses the SEEDED demo tenant, it CREATES its own
# lead and proposal rather than accepting a real prospect's, and its teardown deletes ONLY the ids
# it recorded as it created them — never a pattern. A cleanup failure is reported LOUDLY, because a
# row left in production that nobody hears about is worse than a red test.
# ⚠️ Two controls, not just the happy path: acceptance must be IDEMPOTENT (a double-click must not
# bill a client twice) and the created container must be UNREADABLE BY ANON (stage-2 is the trigger
# T204 predicted, so the feature and its exposure are tested by the same walk).
client-proposal-accept-test:
    #!/usr/bin/env bash
    set -uo pipefail
    cd w0m-web
    if ! curl -s -f -o /dev/null --max-time 3 "http://127.0.0.1:4325/login" \
       && ! curl -s -f -o /dev/null --max-time 3 "http://[::1]:4325/login"; then
      echo "  ▶ starting the CP app…"
      # 🔴 CLEAR A STALE DAEMON FIRST (T286). `astro dev` runs a background daemon and REFUSES to
      # start a replacement — "Dev server already running (pid N)" — so when the health check above
      # fails, the start below silently no-ops and the loop then finds the SAME broken server. That
      # has cost three debugging sessions: a 23h server answering 500 on IPv6 (stage-1), one
      # serving 404s for island modules (stage-2), and pid 67324 answering 500 on everything.
      ( cd apps/cp && pnpm exec astro dev stop >/dev/null 2>&1 ) || true
      infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter cp dev > /tmp/w0m-stage2-cp.log 2>&1 &
      DEV=$!
      trap 'kill $DEV 2>/dev/null || true' EXIT
      for i in $(seq 1 90); do
        curl -s -f -o /dev/null "http://127.0.0.1:4325/login" 2>/dev/null && break
        curl -s -f -o /dev/null "http://[::1]:4325/login" 2>/dev/null && break
        sleep 1
      done
    fi
    BASE=""
    curl -s -f -o /dev/null --max-time 3 "http://127.0.0.1:4325/login" && BASE="http://127.0.0.1:4325"
    [ -z "$BASE" ] && curl -s -f -o /dev/null --max-time 3 "http://[::1]:4325/login" && BASE="http://[::1]:4325"
    if [ -z "$BASE" ]; then
      echo "  ❌ CP never served /login:"; tail -15 /tmp/w0m-stage2-cp.log 2>/dev/null; exit 1
    fi
    echo "  ✅ CP on $BASE"
    # `gauge` is a HOST binary, not an npm package. Keep this comment ABOVE the command.
    infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- \
      env E2E_BASE_URL="$BASE" gauge run specs/web/client_proposal_accept.spec

# stage-1 exit, condition 1 — has a REAL client actually walked the funnel? The plan said this
# "becomes checkable when the E2E exists", which conflates a MACHINE walking the path with a PERSON
# walking it. `auth.users.last_sign_in_at` is the trace a person leaves and an E2E cannot forge.
# 🔴 Non-vacuity is the whole design: seeded personas are excluded by address, and an all-seed or
# empty result is UNMEASURABLE (exit 2), never a pass. Exit 1 = not walked yet.
# 🔴 A RECORDED NEGATIVE RESULT, not a tool to run. `type` cannot be backfilled by rule — measured
# 2026-08-25: tightened for precision the classifier abstains on 76% of the labelled set, and 2 of
# the 8 it was "100% confident" about were wrong by hand. Report-only; `--apply` is deliberately
# not wired anywhere. Keep it so the next person asking "why is type blank on 244?" gets a number.
type-backfill *args:
    @python3 scripts/type_backfill.py {{ args }}

# T277 AC3/AC5 — `client-register` may not be a re-usable trigger for real email, and the address
# must keep coming from the STORED lead row. Reads the function's source, so it proves the guard is
# WRITTEN, not that the deployed function behaves — the live check is one call with an
# already-converted lead expecting `suppressed: "already_provisioned"`, and needs a deploy first.
# T283 — what a REAL client sees on first sign-in: no fixture money, a self-consistent portal, a
# resolving /client, a 404 that does not accuse, and anchors that keep their Tailwind colour.
client-portal-firstrun-test:
    @cd w0m-web && python3 project/scripts/tests/test_client_portal_firstrun.py

# T317 AC4/4.2 — regression guard for the client-hat DS-component migration (AC5) + pins G1/G2.
client-ds-migration-test:
    @cd w0m-web && python3 project/scripts/tests/test_client_ds_migration.py

client-register-guard-test:
    @cd w0m-web && python3 project/scripts/tests/test_client_register_guard.py

purge-patterns-test:
    @cd w0m-web && python3 project/scripts/tests/test_purge_patterns.py

stage1-walk-check:
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 project/scripts/stage1_walk_check.py

# T238 AC2 — write the running stack's local keys into a GITIGNORED properties file that Gauge
# merges. They are Supabase's published local defaults, but committing them trips
# `wom-postgres-uri-inline-password` — the gitleaks rule added after a real leaked-superuser
# incident. Allowlisting a security rule for convenience is how the rule stops meaning anything, so
# the values are generated instead of committed. Read from the stack, never from memory.
db-local-env:
    #!/usr/bin/env bash
    set -euo pipefail
    if [ -z "${DOCKER_HOST:-}" ] && [ -f scripts/oci_sandbox.py ]; then
      DOCKER_HOST="$(python3 scripts/oci_sandbox.py env)"
      export DOCKER_HOST
    fi
    s=$(cd w0m-api && W0M_DB_MIGRATIONS=false supabase status -o json)
    out=w0m-web/env/local/generated.properties
    {
      echo "# GENERATED by \`just db-local-env\` — do not commit, do not edit."
      echo "PUBLIC_SUPABASE_ANON_KEY = $(echo "$s" | python3 -c 'import json,sys;print(json.load(sys.stdin)["PUBLISHABLE_KEY"])')"
      echo "SERVICE_ROLE_KEY = $(echo "$s" | python3 -c 'import json,sys;print(json.load(sys.stdin)["SECRET_KEY"])')"
      echo "DATABASE_URL = $(echo "$s" | python3 -c 'import json,sys;print(json.load(sys.stdin)["DB_URL"])')"
    } > "$out"
    echo "  ✅ wrote $(basename $out) — $(grep -c '=' "$out") value(s), gitignored"

# T238 AC5 — seed the LOCAL database from an EXISTING backup. Owner 2026-08-19: "for AC5 let's seed
# from backup??" — yes, and for a better reason than convenience: pulling fresh rows from the hosted
# project spends the very Supabase quota whose exhaustion stopped live testing. The dumps already
# sit on this machine, so this costs nothing.
# ⚠️ Data-only, onto the baseline schema. Restoring the 27 MB dump WHOLE gives 579 errors (grants,
# default privileges, and the auth/storage/realtime schemas the local role cannot touch) — the rows
# still land, but nobody reads a 579-error restore and real failures hide in it.
# 🔴 Refuses any target that is not loopback. A seeding tool that can be pointed at production is a
# data-loss incident with a convenient interface.
db-local-seed *args:
    @cd w0m-api && python3 scripts/db_local_seed.py {{args}}

# T478 AC2 — a full test team on the LOCAL stack: admin, manager, lead, member, client (with the client hat
# its company's `client_users` trigger grants), recruit, and a person with nothing granted. Loopback only;
# random passwords per run, written to the gitignored w0m-web/env/local/test-team.properties, never printed.
# Nobody is a webomage team member: the operator gate admits only @webomage.com, and tests live on
# @test.webomage.com. Re-running converges. Order: db-local-up → db-local-env → db-local-seed → this.
test-team-local:
    @cd w0m-api && python3 scripts/test_team_local.py
    @db=$(grep '^DATABASE_URL' w0m-web/env/local/generated.properties 2>/dev/null | cut -d= -f2- | tr -d ' '); [ -n "$db" ] && psql "$db" -q -c "ALTER ROLE authenticator SET pgrst.db_schemas = 'public, graphql_public, gamification'; GRANT USAGE ON SCHEMA gamification TO anon, authenticated, service_role; GRANT SELECT ON ALL TABLES IN SCHEMA gamification TO anon, authenticated, service_role; NOTIFY pgrst, 'reload config'; NOTIFY pgrst, 'reload schema';" >/dev/null 2>&1 || true

# T478 — serve the edge functions against the LOCAL stack (foreground; Ctrl-C stops it). Secrets arrive by
# `infisical run` and reach the CLI through a pipe, never a file. Functions get an ALLOWLIST: AI keys and request
# secrets only; db, service key and worker point local; Telegram/SMTP/LinkedIn/Stripe/GitHub/Upwork/telemetry
# are absent. Inference goes to the live worker through a loopback proxy that forwards ONLY POST /ai/chat and
# /ai/embed — the same URL carries chat-memory writes, which it refuses. Runs as a recipe because config.toml
# reads `env(W0M_DB_MIGRATIONS)`, which this justfile exports; outside it the CLI fails ProjectConfigParseError.
edge-local:
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 scripts/edge_local.py

# T238 AC1 — regenerate the schema baseline from the live database (READ-ONLY). The migration chain
# cannot be replayed: `supabase start` dies on migration 1 of 226 because `20251215183000` ALTERs
# `public.cache_file`, which no migration creates and which the live database does not have either.
# The chain records the CHANGES without the STARTING SCHEMA, and nothing noticed in 226 migrations
# because nothing ever replayed them — every environment is the one live database.
db-baseline:
    @cd w0m-api && python3 scripts/db_baseline.py --generate

# T238 AC3 — the half that matters: replay the committed baseline into a THROWAWAY container and
# assert it reproduces every table. A baseline nobody replays is the same artefact that got us here.
# ⚠️ Exits 2 when Docker is unreachable or the baseline is absent — unknown, never a clean 0.
db-baseline-verify:
    @cd w0m-api && python3 scripts/db_baseline.py --verify

# T234 — is the ai-memory checkout+binary still the VALIDATED one? Owner 2026-08-19: adopt it, but
# "do not auto-update it without revalidating changes". Verifies THREE things, because each drifts
# alone: the checkout commit (someone pulled), the binary sha256 (rebuilt from other sources, or
# replaced), and the reported version (a prebuilt dropped in). Commit-only would pass a binary from
# anywhere — the precise supply-chain risk that made build-from-source the condition of adoption.
# ⚠️ RED here is expected after any pull; the fix is to revalidate and move the pin, never to silence it.
ai-memory-check *args:
    @python3 scripts/ai_memory_pin_check.py {{args}}

# T202 AC7 — which RLS policies are LOAD-BEARING, asked so the service-role bypass cannot fake the
# answer. T198/T199 concluded "no caller depends on these arms" while most SERVER callers held a
# service-role client — under a bypass no policy is load-bearing, so the conclusion was true for a
# reason unrelated to the policies. Browser code never had the bypass (a client bundle only gets
# PUBLIC_* vars, so the legacy chain lands on the anon key), which makes .svelte callers the honest
# sample. Reports the tables they read, and separates DEAD components — whose reads prove nothing.
# ⚠️ Answers "which policies must work", not "do they work" — that is `just authz-probe`.
authz-load-bearing *args:
    @cd w0m-web && python3 project/scripts/authz_load_bearing.py {{args}}

# T198 AC4 — fail when a blanket permissive arm appears that project/authz-allowlist.jsonc
# does not declare. Advisory until the allowlist holds 0 defect + 0 decision-needed entries.
authz-blanket-check *args:
    @cd w0m-web && python3 project/scripts/authz_blanket_gate.py {{args}}

# T198 AC8b — attempt real writes instead of reading pg_policies. Everything runs inside
# BEGIN ... ROLLBACK. 🔴 contracts/jobs/proposals are PERMANENTLY out of scope: outbound pg_net
# triggers, and a rollback does not recall an HTTP call. Classifies DENIED / ALLOWED /
# INCONCLUSIVE — a non-42501 failure is never counted as a pass.
authz-write-probe *args:
    @cd w0m-web && python3 project/scripts/authz_write_probes.py {{args}}

# T458 S0 — every client has its org (AgDR-0027 decision 10). Live and read-only by default;
# `--probe` runs the trigger's behaviour inside BEGIN ... ROLLBACK once migration 20260926120000 is applied.
org-client-parity *args:
    @cd w0m-web && python3 project/scripts/org_client_parity.py {{args}}

# T458 S0 — offline red probes of the parity script and the S0 migration.
org-client-parity-test:
    @cd w0m-web && python3 project/scripts/org_client_parity.py --test

# T458 S1 — org kinds (platform | company | personal), Backstage-valid slugs, org sides. Live, read-only.
org-kinds-verify *args:
    @cd w0m-web && python3 project/scripts/org_kinds_verify.py {{args}}

# T458 S1 — offline red probes of the org-kinds judge.
org-kinds-verify-test:
    @cd w0m-web && python3 project/scripts/org_kinds_verify.py --test

# T463 (P0) — admin privileges need an MFA-verified (AAL2) token in the database. Live, read-only: the real
# admin under simulated AAL1 and AAL2 tokens; AAL1 must be refused everything admin, AAL2 must keep it.
admin-aal-verify *args:
    @cd w0m-web && python3 project/scripts/admin_aal_verify.py {{args}}

# T463 — offline red probes of the admin-AAL judge.
admin-aal-verify-test:
    @cd w0m-web && python3 project/scripts/admin_aal_verify.py --test

# T465 (P1) — manager privileges need an MFA-verified (AAL2) token in the database. Live: manager account
# under simulated AAL1 and AAL2 tokens; AAL1 must be refused everything manager, AAL2 must keep it.
manager-aal-verify *args:
    @cd w0m-web && python3 project/scripts/manager_aal_verify.py {{args}}

# T465 — offline red probes of the manager-AAL judge.
manager-aal-verify-test:
    @cd w0m-web && python3 project/scripts/manager_aal_verify.py --test

# T458 S2 — org units (team per company, delivery/fin/growth on webomage, platform admin/system/talent). Live, read-only.
org-units-verify *args:
    @cd w0m-web && python3 project/scripts/org_units_verify.py {{args}}

# T458 S2 — offline red probes of the org-units judge.
org-units-verify-test:
    @cd w0m-web && python3 project/scripts/org_units_verify.py --test

# T458 S3 — fixture deletion in owner-approved batches (report: .agents/reports/2026-09-26-s3-account-batches-T458.md).
# DRY RUN: performs the batch's real deletes in one transaction, prints every row, and ROLLS BACK. Re-measures every
# account first and refuses the whole batch on any dependent outside its allowed set.
s3-delete batch:
    @cd w0m-web && python3 project/scripts/s3_delete.py {{batch}}

# T458 S3 — the same transaction, COMMITTED. Owner-run only, behind the Touch ID confirm gate on every call.
s3-delete-apply batch: (_confirm "s3-delete-apply")
    @cd w0m-web && python3 project/scripts/s3_delete.py {{batch}} --apply

# T458 S3 — offline red probes of the planner and its refusals.
s3-delete-test:
    @cd w0m-web && python3 project/scripts/s3_delete.py --test

# T458 S4 — every person has a home org (team unit), the operator gate, personal orgs private. Live, read-only.
org-homes-verify *args:
    @cd w0m-web && python3 project/scripts/org_homes_verify.py {{args}}

# T458 S4 — offline red probes of the org-homes judge.
org-homes-verify-test:
    @cd w0m-web && python3 project/scripts/org_homes_verify.py --test

# T458 S5 — fold the secondary login casualuser@gmail.com into aleksei@ (audit rows moved, not deleted). DRY RUN.
s5-merge:
    @cd w0m-web && python3 project/scripts/s5_merge.py

# T458 S5 — the same transaction COMMITTED. Owner-run only, Touch ID on every call.
s5-merge-apply: (_confirm "s5-merge-apply")
    @cd w0m-web && python3 project/scripts/s5_merge.py --apply

# T458 S5 — offline red probes.
s5-merge-test:
    @cd w0m-web && python3 project/scripts/s5_merge.py --test

# T468 phase A — the Upwork source layer and source links exist with the right access. Live, read-only.
upwork-layer-verify *args:
    @cd w0m-web && python3 project/scripts/upwork_layer_verify.py {{args}}

# T468 phase A — offline red probes of the Upwork-layer judge.
upwork-layer-verify-test:
    @cd w0m-web && python3 project/scripts/upwork_layer_verify.py --test

# T327 AC1/AC4 — Enforcing downward-only ratchet for RLS-bypassing admin client
authz-admin-client-check:
    @cd w0m-web && python3 project/scripts/authz_admin_client_triage.py --enforce

# T404 AC6 — Enforce zero unexempted process.env reads in worker-bundled sources.
worker-env-check *args:
    @cd w0m-web && python3 project/scripts/worker_env_gate.py {{args}}

# T404 AC6 — Unit tests and red probes for worker_env_gate.py (15 probes)
worker-env-test:
    @cd w0m-web && python3 project/scripts/tests/test_worker_env_gate.py

# T117 AC8 — the Drizzle schema against the live database. Two directions, only one is a defect:
# a GHOST (declared, not live) fails at RUNTIME and nothing else catches it — the estate has no
# generated `Database` types and no `createClient<Database>` anywhere, so column names are unchecked
# from TypeScript entirely. UNDECLARED (live, not in Drizzle) is reported, never gated: the schema
# covers 44 of 98 public tables BY CHOICE — it is the edge-function data layer, not a mirror.
schema-drift *args:
    @cd w0m-web && python3 project/scripts/schema_drizzle_drift.py {{args}}

# T69 AC5 — the same idea one layer down: every `.from('<table>')` CALL SITE against the live
# catalog. schema-drift is blind to all three of T69's live bugs because nothing DECLARED those
# tables — the queries just named them. Four classes: GHOST (in no schema), UNQUALIFIED (only in a
# schema the call does not name — the `0 XP` bug), MISQUALIFIED (.schema(S) but not in S), and
# UNREACHABLE (correct name, correct schema, no USAGE grant → 403 whatever you write; the whole
# `gamification` schema was in this state, unreachable even by service_role).
# ⚠️ `supabase.storage.from('<bucket>')` is NOT a table — the first version of this check read all
# 26 storage calls as GHOSTs. Buckets live in no schema by design.
callsite-drift *args:
    @cd w0m-web && python3 project/scripts/call_site_schema_drift.py {{args}}

# The red probes for the above. Offline (synthetic catalog, no DB, no secrets), so a green run
# proves the CHECK works rather than proving the live schema happens to agree with it. Every
# "clean" probe is a false alarm this checker actually raised before it was fixed.
callsite-drift-test:
    @cd w0m-web && python3 project/scripts/call_site_schema_drift_test.py

# T235 AC9 — refuse to commit work this agent did not do. Born from a real incident: `git add -A`
# in this SHARED worktree swept the parallel Antigravity agent's in-flight `upwork_mcp_sync.py`
# into a w0m commit, caught only because `version-check` tripped on a version string inside it.
# Two checks of different kinds — a declarative co-tenancy registry (durable, blind to undeclared
# paths) and a live open-write-handle probe (catches undeclared paths, but only while the handle is
# open). Neither suffices alone; `project/scripts/stage_guard.py` says so in its own docstring.
stage-guard:
    @python3 scripts/stage_guard.py

# The probe. Stages the ACTUAL file from the 2026-08-19 incident and asserts the guard turns red —
# a guard that has only ever passed cannot be told from one that cannot fail. Restores staging state.
stage-guard-test:
    #!/usr/bin/env bash
    set -uo pipefail
    cd w0m-web
    reg=project/co-tenancy.json
    # 🔑 The probe carries its OWN fixture. The first version staged the real incident file
    # (upwork_mcp_sync.py) and asserted the guard went red — which worked until the owner took
    # ownership of that work on 2026-08-20, the registry stopped claiming the path, and the probe
    # began failing for a reason that was not a defect. A probe that depends on live state tests
    # the state, not the guard.
    bak=$(mktemp); cp "$reg" "$bak"
    fixture="project/.stage-guard-fixture.tmp"
    cleanup() { cp "$bak" "$reg"; rm -f "$bak" "$fixture"; git restore --staged "$fixture" 2>/dev/null || true; }
    trap cleanup EXIT
    python3 - "$reg" "$fixture" <<'PY2'
    import json, sys
    reg, fixture = sys.argv[1], sys.argv[2]
    d = json.load(open(reg))
    d["agents"]["_probe"] = {"reason": "synthetic fixture for stage-guard-test; removed on exit",
                             "paths": [fixture]}
    json.dump(d, open(reg, "w"), indent=2, ensure_ascii=False)
    PY2
    echo "probe" > "$fixture"
    pre=$(git diff --cached --name-only | sort)
    git add -f "$fixture" 2>/dev/null
    python3 ../scripts/stage_guard.py >/dev/null 2>&1; red=$?
    git restore --staged "$fixture" 2>/dev/null
    python3 ../scripts/stage_guard.py >/dev/null 2>&1; green=$?
    post=$(git diff --cached --name-only | sort)
    [ "$pre" = "$post" ] || { echo "  ❌ probe altered the staging set"; exit 1; }
    if [ "$red" -eq 1 ] && [ "$green" -eq 0 ]; then
      echo "  ✅ stage-guard probe — red on a registered co-tenant path (exit 1), green once unstaged (exit 0)"
    else
      echo "  ❌ stage-guard probe FAILED — staged=$red (want 1), unstaged=$green (want 0)"
      exit 1
    fi

# T195 AC7 — mermaid validation, given a `just` front door. It runs on EVERY commit
# (.pre-commit-config.yaml -> mmd-validate) but was invoked raw as `node …/validate.mjs`, so it had
# no recipe, no registry entry and no probe — and `suites-drift` enumerates justfile recipes, so it
# was unreachable by that gate however the matcher was widened. With no argument it scans the tree;
# pre-commit passes the staged files.
mmd-validate *files:
    @cd w0m-web && node ../w0m-skills/skills/mmd-validate/validate.mjs {{ files }}

# The probe it shipped without. Its centrepiece is the 2026-08-10 regression: a PROSE MENTION of
# the ```mermaid fence (how CLAUDE.md documents the convention) opened a phantom diagram under the
# old unanchored regex, miscounting 3 diagrams as 4 and blocking a legitimate commit.
# ⚠️ Exits 2 rather than 0 when jsdom/mermaid are absent — validate.mjs skips in that state, so a
# probe that returned green would be certifying a validator that validates nothing.
mmd-validate-test:
    @cd w0m-web && node ../w0m-skills/skills/mmd-validate/test.mjs

# T194 — a `DROP TABLE` leaves its callers behind and nothing notices. Replays the migrations to
# find relations dropped and never recreated, then searches the app/worker/edge code for callers
# (`.from('<rel>')` AND the relation named in raw SQL).
# 🔑 Not a duplicate of `callsite-drift`: that resolves call sites against the LIVE CATALOG and
# reports the same orphans as GHOSTs, but cannot say WHICH MIGRATION removed the table or when.
# Opposite blind spots — a catalog diff cannot see a relation that never existed, a drop diff
# cannot see one dropped out-of-band. Run both.
# ⚠️ Absent at the migrations' END STATE, not merely dropped somewhere in history: a rebuilt table
# is not a finding, and a gate that says otherwise is one people stop reading.
drop-callers *args:
    @cd w0m-web && python3 project/scripts/drop_caller_gate.py {{ args }}

# 16 offline probes. The ones that matter most assert a finding is NOT raised — recreate, rename,
# a comment quoting the DDL, and a storage bucket sharing the relation's name.
drop-callers-test:
    @cd w0m-web && python3 project/scripts/tests/test_drop_caller_gate.py

# T138 AC1/AC2 — every column the code MATCHES ON, against the indexes that exist. Three severities:
# UNSAFE (a `.maybeSingle()` with no UNIQUE behind it = a latent 500), CONDITIONALLY UNIQUE (a
# PARTIAL unique index, so the guarantee holds only for rows matching its predicate), and UNBACKED
# (no index at all — slow, not wrong).
# ⚠️ Known limits, stated because they bound what a green run means: uniqueness is checked per
# COLUMN, so a composite `.eq(a).eq(b).maybeSingle()` backed by a composite unique index still
# reports; and statement scoping is a 600-char window, which can span two queries.
lookup-index-gate *args:
    @cd w0m-web && python3 project/scripts/lookup_index_gate.py {{ args }}

# 13 offline probes. The one that matters is PARTIAL-INDEX parsing: the gate's first run read a
# `WHERE` clause as the column list and reported `posts.slug` as unindexed while its unique index
# sat right there. Three of the four identifier indexes here are partial.
lookup-index-test:
    @cd w0m-web && python3 project/scripts/tests/test_lookup_index_gate.py

# T95 AC4 — every `services-policy.json` services[] entry's doc exists and holds the 3 required
# headings, AND every file under docs/backend/connectors/ is declared by some entry. Deliberately
# scoped away from oauth_providers[] — that's T94(b)'s separate, not-yet-built doc timeline.
connector-check *args:
    @cd w0m-web && python3 project/scripts/check_connectors.py {{ args }}

# 8 offline probes, both directions: a registry entry pointing at a missing/incomplete doc, and a
# doc file with no registry entry naming it.
connector-check-test:
    @cd w0m-web && python3 project/scripts/tests/test_check_connectors.py

# Governs every w0m-authored ignore file: inventory drift, required secret rules, and — the one
# that matters — TRACKED files that an ignore rule matches. git cannot un-track a file by adding a
# pattern later, so a rule written after the fact is silently inert and invisible from both sides:
# `git status` is clean and the .gitignore reads correct. 540 such files when first measured.
# Scope is DECLARED in project/ignore-policy.json, because most ignore files here belong to
# third parties or tools; an undeclared one inside a governed repo is drift and blocks.
#
# Ignore-file audit — inventory, required rules, rule-vs-index. Offline.
ignore-audit *args:
    @python3 scripts/ignore_audit.py {{ args }}

# Prove it goes RED — fixtures, so it cannot pass merely because today's estate is tidy.
ignore-audit-test:
    @python3 scripts/tests/test_ignore_audit.py

# A RATCHET, not a ban. `headroom`, `just` and `local-dev` are unprefixed today and work; this
# stops the NEXT one being added that way. Found the expensive way on 2026-08-31: Antigravity binds
# `/tasks` to its own thing, so w0m's `/tasks` was shadowed and unreachable there — and no ADE's
# built-in command list is readable from disk, so every unprefixed name is a bet against a
# namespace nothing here can see. Never raise the baseline; the number only falls.
#
# Command namespace — are our slash-commands collision-safe? Offline.
command-namespace-check *args:
    @python3 scripts/command_namespace_check.py {{ args }}

# Host surface check (T196) — scans LaunchAgents, LaunchDaemons, crontab for dead executables and secrets.
host-check *args:
    @python3 scripts/host_surface_check.py {{ args }}

# Red probes for host-check (T196 AC3) — proves gate flags dead executables and plaintext credentials on fixture.
host-check-test:
    @python3 scripts/tests/host_surface_check_test.py

# T390 — Unit test suite for push_report.py pre-push warning & advisory extractor.
push-report-test:
    @python3 scripts/tests/test_push_report.py

# T413 — Automated build hints and deprecation remediator.
fix-hints *args:
    @cd w0m-web && python3 project/scripts/fix_hints.py {{ args }}

# T413 — Unit test suite for fix_hints.py codemod.
fix-hints-test:
    @cd w0m-web && python3 project/scripts/tests/test_fix_hints.py

# T210 Phase 1 task 1.5 — proves person/account detachment PER ROLE against a real accountless
# fixture row, inside a transaction that always rolls back. Asserts service_role CAN see the row
# as well as that anon/authenticated cannot: a passing "nobody sees it" is otherwise
# indistinguishable from a revoked grant, which is how T69 hid for three months.
profile-detach-probe *args:
    @cd w0m-web && python3 project/scripts/profile_detach_probe.py {{ args }}

# T210 Phase 2 task 2.2 — proves the email-uniqueness migration by MANUFACTURING the collision it
# refuses, inside transactions that always roll back. The guard is the deliverable, not the index:
# without the RED case a guard that cannot fire looks identical to one that works. ⚠️ Note that
# Postgres ALSO exits non-zero on a duplicate, so "did it fail?" is not the test — the probe checks
# the guard NAMED the rows, which is the half `CREATE UNIQUE INDEX` does not do (verified against a
# guard-stripped mutant 2026-08-14). Empty corpus = failure, since the migration tolerates one.
profiles-email-probe *args:
    @cd w0m-web && python3 project/scripts/profiles_email_unique_probe.py {{ args }}

# T210 Phase 3 tasks 3.1/3.4/3.5 — drives SIGNUP itself (real auth.users inserts, rolled back) and
# proves a candidate keeps their profile ID through it. ⚠️ The id assertion is the point: "a profile
# exists afterwards" is satisfied by a RECREATED profile, which is the exact failure the ticket
# exists to prevent. Two cases are regressions for defects that were live on 2026-08-14 — a
# candidate's signup raised a unique violation, and a new signup could not see their own profile —
# and both were confirmed RED against the unmigrated schema before the fix landed.
profile-claim-probe *args:
    @cd w0m-web && python3 project/scripts/profile_claim_probe.py {{ args }}

# T210 Phase 4 task 4.1 — proves a connection belongs to the PERSON. 🔑 The case that matters is
# `accountless_connection`: it inserts the row [[T194]] AC5 was declared blocked on for months (a
# candidate's LinkedIn token with no account behind it) and requires it to be accepted. 🔴 It also
# asserts D1 — SELECT stays revoked from anon/authenticated, which is what makes the token columns
# unreadable from a client, not the RLS policies. That assertion was mutation-tested: granting
# SELECT makes the migration refuse, by name.
social-rekey-probe *args:
    @cd w0m-web && python3 project/scripts/social_rekey_probe.py {{ args }}

# T349 AC7 — verify durable verified levels on public.clients and gamification.compliance_profiles
kyc-probe *args:
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 project/scripts/t349_kyc_probe.py {{ args }}

# T254 AC6 — verify unified device identity schema and relational cascade
device-identity-probe *args:
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 project/scripts/t254_device_identity_probe.py {{ args }}

# T254 AC2b/A7 — verify AI quota checks fail closed on RPC error and enforce dual keying
quota-failclosed-check *args:
    @cd w0m-web && python3 project/scripts/quota_failclosed_check.py {{ args }}

# T254 AC2b/AC3 — shadow-mode hardware fingerprint entropy and collision report
fingerprint-entropy *args:
    @cd w0m-web && python3 project/scripts/fingerprint_entropy.py {{ args }}

# T134 — a service hand-listed in a page is the defect the derived catalog replaced:
# `system/services.astro` held five hardcoded health URLs until 2026-08-13. Proves itself first by
# firing on a seeded hand-list, and refuses to report clean over an empty corpus — which is how it
# caught its own wrong root path during authoring.
service-handlist-test:
    @cd w0m-web && python3 project/scripts/tests/test_no_service_handlist.py

# T207 AC1 — the cp member route policy must live in exactly ONE place. It used to be a literal
# list in middleware.ts (13 entries, the ACCESS decision) AND a shorter one in AdminLayout.astro
# (6, the NAV filter) — and they had drifted, so three member-allowed pages were never shown.
# Also reports any member route that is neither in navGroups nor declared deep-link-only.
cp-nav-check *args:
    @cd w0m-web && python3 project/scripts/cp_nav_policy_test.py {{args}}

# T439 Plan B — live, read-only proof of the context RBAC migration: slugs, offices, hat backfill, client hats,
# grants, and both RPCs called AS a client user and AS a tech lead. Exit 2 = unmeasured (DB unreachable).
cp-context-rbac-verify:
    @cd w0m-web && python3 project/scripts/verify_t439_context_rbac.py

# T439 — red probes for cp-nav-check's context checks (unmapped route, pending/live file existence, duplicate,
# role names, context page without a nav.ts entry), then the live apps/cp tree.
cp-nav-check-test:
    @cd w0m-web && python3 project/scripts/tests/test_cp_nav_context.py

# T207 AC5+AC6 — design-system token conformance gate.
# Measures adoption by tokens (hardcoded hex, distinct palette) and native controls (<select>, <input>, <button>)
# across apps/cp instead of component imports. Enforces non-regression against project/ds-conformance-baseline.json.
ds-conformance *args:
    @cd w0m-web && python3 project/scripts/ds_conformance.py {{args}}

ds-conformance-test:
    @cd w0m-web && python3 project/scripts/tests/test_ds_conformance.py

# T422 AC4 — every token in design-system/tokens/*.css exists in packages/ui/src/tokens.css with the
# same value, per selector. T422 ticked this AC on 2026-09-23 citing a recipe that did not exist; built
# 2026-09-24 under T439 when the admin accent changed both files. Exit 1 = drift, 2 = unreadable.
tokens-parity:
    @cd w0m-web && python3 project/scripts/tokens_parity.py

# Red probes (missing, changed, per-selector, comment/whitespace, unreadable), then the live check.
tokens-parity-test:
    @cd w0m-web && python3 project/scripts/tests/test_tokens_parity.py

# T199 AC6 — the GRANT layer is asserted, not assumed. Every RLS finding sits on top of a grant
# nobody checks: a policy only runs if the role holds a table privilege first, and pg_policies
# cannot see that. 🔴 The case it exists to catch: `gamification` holds 8 `USING true` policies that
# are inert ONLY because `authenticated` has no USAGE on the schema — one GRANT arms all 8 at once.
# Drift is checked in BOTH directions; a grant vanishing breaks a live caller too.
authz-grant-check *args:
    @cd w0m-web && python3 project/scripts/authz_grant_gate.py {{args}}

# Red probes for the grant gate — offline, no DB. It starts GREEN, which is what makes these the
# deliverable: a gate that has only ever passed cannot be told from one that cannot fail.
# T304 — proves the gate tells a CREDENTIAL failure apart from a security finding. Offline; every
# input is a verbatim message captured on 2026-09-02, when three pushes were refused as
# "an authorization probe is RED" and none was an authorization violation.
authz-unavailable-test:
    @cd w0m-web && python3 project/scripts/authz_unavailable_test.py

authz-grant-check-test:
    @cd w0m-web && python3 project/scripts/authz_grant_gate_test.py

# T206 AC5 — red probes for per-service Postgres roles (offline + live)
authz-service-roles-test:
    @cd w0m-web && python3 project/scripts/tests/test_authz_service_roles.py

# T199 AC1 — which storage buckets may be public is a REVIEWED LIST (project/authz-buckets.jsonc),
# not a remembered one. A bucket is exposed on TWO axes and closing it needs both: the `public`
# flag (direct path reads, needs no policy — `snapshots` is public with ZERO policies) and a
# public-role SELECT policy (listing). The gate checks both and fails on drift in either direction.
authz-bucket-check *args:
    @cd w0m-web && python3 project/scripts/authz_bucket_gate.py {{args}}

# Red probes for the bucket gate — offline, no DB. Includes `boolean-spelling`, which is the near
# miss the gate actually made: `public::text` is 'true', not the 't' psql displays, so the first
# version read all 13 buckets as private, reported 0 public, and emitted 6 confident STALE findings.
authz-bucket-check-test:
    @cd w0m-web && python3 project/scripts/authz_bucket_gate_test.py

# T199 AC2 — the SECURITY DEFINER surface as a reviewed list. Fails on an undeclared definer
# function, a grant that drifted in either direction, an unpinned search_path, or a reasonless
# entry. 🔴 It never recommends a revoke: revoking anon EXECUTE broke the AI quota check OPEN once.
authz-definer-check *args:
    @cd w0m-web && python3 project/scripts/authz_definer_gate.py {{args}}

# Do agents in OTHER ADEs read the same rules as Claude? `ide-trace` answers "is it declared" and
# "does the file carry the rules"; this answers the third question neither asks — is that surface
# REACHABLE where the agent actually runs. Orca is a RUNNER: it provisions a git worktree and
# executes a CLI agent inside it, so a surface reaches that agent only if git carries it AND any
# symlink resolves inside the repo. Computed statically; validated against real worktrees of
# w0m-web and w0m-api 2026-08-29, agreeing on all 10 surfaces. Advisory; `--enforce` to block.
ade-rules-parity *args:
    @python3 scripts/ade_rules_parity.py {{args}}

# Red probes for the parity gate. Each builds a REAL temp repo and a REAL worktree and checks the
# static verdict against what is actually on disk there — a prediction never compared to the thing
# predicted is a guess with a percentage sign. Offline, no network. 12 checks incl. 2 mutations.
ade-rules-parity-test:
    @python3 scripts/tests/test_ade_rules_parity.py

# T102 Phase 3 — the DB↔UI contract for the hat switcher. `wom_my_hats` column names ARE the JSON
# keys the Svelte component destructures, so a rename in a later migration yields `undefined` in the
# panel and raises nothing. Reads the field list OUT of the component so the check cannot drift from
# what it protects. Live: needs the beta DB. Mutation-tested (adding a field the RPC lacks fails it).
hat-switcher-contract:
    @cd w0m-web && python3 project/scripts/tests/test_hat_switcher_contract.py

# Red probes for the definer gate. It is GREEN on its first run, which makes these MORE important:
# a gate that has only ever passed is indistinguishable from one that cannot fail.
authz-definer-check-test:
    @cd w0m-web && python3 project/scripts/authz_definer_gate_test.py

# Red probes for the gate above — proves it FAILS when it should. Offline, no DB.
# A gate with no test that makes it fail is a gate nobody has proven works.
authz-blanket-check-test:
    @cd w0m-web && python3 project/scripts/authz_blanket_gate_test.py

# Re-measure the whole authorization surface and regenerate every docs/backend map.
authz-remap:
    @cd w0m-web && python3 project/scripts/authz_probe.py \
        && python3 project/scripts/authz_coverage.py \
        && python3 project/scripts/authz_edge_fns.py \
        && python3 project/scripts/authz_gen_maps.py

# T205 AC6 / DoD — verify authz-remap generates all required artifacts including office/capability bundles. Offline.
authz-remap-test:
    @cd w0m-web && python3 project/scripts/tests/test_authz_remap_outputs.py

# db-drift-check: prove the database is reproducible from the migrations directory (T156).
# FAILS when the remote ledger holds a version with no local migration file — a schema change
# that is live, unreviewable and absent from any fresh environment. Reports pending migrations
# without failing (that is what db-migrate is for). Wrapped in `infisical run` for DATABASE_URL;
# without it the script skips rather than passing, so it can run where secrets are absent.
db-drift-check:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-web/project/scripts/db_drift_check.py

# attribution-drift-check: T325 AC4 — prove the contract/client attribution classification the
# 2026-09-10 backfill established still matches live data (unclassified rows, a link with a stale
# state, a client_less contract whose name now matches a real client, or a new BridgeRoad-shaped
# portal gap). Read-only via PostgREST; exit 2 (could not measure) is distinct from exit 0
# (measured clean) — a failed read is never reported as zero findings (T242).
attribution-drift-check:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-web/project/scripts/attribution_drift_check.py

# Backup Remote Database
db-backup: (_confirm "db-backup")
    @echo "Backing up remote database..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/db_backup.py

# T229 AC1 — restore the newest dump into a scratch database and PROVE it matches live.
# `db_backup.py` says in its own docstring that it cannot do this: a `pg_dump --list` on a plain-SQL
# dump proves nothing, and a real restore needs a scratch database. This is that sibling.
# Reads live but writes only to a LOCAL scratch db (dropped afterwards unless --keep), so it is not
# in always_confirm: the destructive surface is a database it created seconds earlier.
# 🔴 Fails closed on an EMPTY comparison — zero tables, or zero content hashes, exits 1. A backup
# verifier reporting green over nothing would certify an unrestored dump.
db-restore-verify *args:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/db_restore_verify.py {{ args }}

# T4 AC2 — the machine-draft matcher must still FIRE against the live blueprint catalog.
# `proposal-seed.test.ts` proves the logic against fixed rows; this proves the logic and the real
# catalog still agree, which is the half that fails silently.
# 🔴 The obvious eligibility filter is `is_published` — and all 27 blueprints carry FALSE, so a
# matcher written the obvious way would match nothing, forever, with no error and no exception. The
# seed filters `access_scope='public'` (24 rows) and this makes that assumption falsifiable.
# It shells out to Deno running the PRODUCTION matcher rather than reimplementing the scoring, and
# it asserts the seed has not drifted to a different filter than the one it reads with.
# Reads live; writes nothing. Two NEGATIVE controls must decline, or a guessing matcher passes.
proposal-seed-catalog-check *args:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/proposal_seed_catalog_check.py {{ args }}

# T198 AC1 — a client page must scope by the client's ORGANISATION and must not hide its own errors.
# Static, fast, deterministic: it reads `apps/cp/src/pages/client/*.astro`.
# 🔴 BLOCKING, because the defect it catches is INVISIBLE. Every symptom is an empty page, which is
# also what a client with no data legitimately sees — so it survived two weeks in two shipped pages
# after being found and fixed in a third. `client_milestones` was being filtered by a column that
# does not exist, erroring for every client, every time, and reading as "no milestones".
# ⚠️ Both of its assertions were mutation-tested, and the second one FAILED that test first: it
# matched only `const { data: x } = await supabase…` and sailed past the ternary form these pages
# actually use. Widened to match the destructure rather than the right-hand side.
client-page-tenancy-test:
    @cd w0m-web && python3 project/scripts/tests/test_client_page_tenancy.py

# T287 — `project_repos` behaves, proven by RUNNING the migrations against a scratch restore.
# 🔴 The load-bearing check is the CLIENT READ, and it is behavioural for a specific reason: the
# policy reaches tenancy through `EXISTS (SELECT 1 FROM projects …)` — the exact shape that matched
# NOTHING in T4 the same week, because an RLS expression runs as the querying user and `leads` had
# no client arm. It works here only because `projects` DOES. That difference is invisible in the
# SQL, so it is measured rather than read.
# ⚠️ A separate file from `stage2-schema-check` on purpose: that one is stage-2's EXIT check, and a
# T287 defect must not make stage-2 report red.
t287-repos-check *args:
    @cd w0m-api && python3 scripts/t287_repos_check.py {{ args }}

# T510 (U1) — proves resume publication by APPLYING its migration (twice) to a scratch restore of the newest dump and exercising it as real roles: the
# owner-only settings table, one primary resume per profile, and the public team view carrying only what is switched on. Needs a local Postgres (exit 2 =
# NOT MEASURED without one). A separate file from t287-repos-check on purpose: a defect in one ticket's proof must not turn the other red.
t510-publication-check *args:
    @cd w0m-api && python3 scripts/t510_publication_check.py {{ args }}

# T290 AC2 — `simulate_payment` must be gone from the DEPLOYED client-api, not just from the source.
# 🔴 A grep proves the file; an edge function keeps serving its LAST DEPLOY, so those are different
# claims. It authenticates as a real client (mint a link, exchange it, call) because an
# unauthenticated call returns 401 whether or not the verb exists — a result that cannot tell
# "removed" from "rejected at the door".
# ⚠️ Carries a CONTROL: an unknown verb must answer the same way, or the call never reached the
# router and the verdict is measuring the door. Missing config exits 2 (UNMEASURABLE), never 0.
simulate-payment-gone *args:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/simulate_payment_gone_check.py {{ args }}

# T373 AC6 / T290 AC3-AC4 — Anti-vacuous financial reconciliation against live Stripe API.
# Distinguishes 3 states: 0 (reconciled), 1 (mismatched or empty/vacuous), 2 (unmeasurable).
reconcile-stripe *args:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/reconcile_stripe_invoices.py {{ args }}

# T4 / T204 AC5 — stage-2's three migrations, APPLIED to a scratch restore and then exercised.
# An agent cannot run `db-migrate` and deploy needs a human, so "the migration is written" is the
# most anyone could otherwise claim. This runs them.
# 🔴 The load-bearing checks are BEHAVIOURAL, not structural, and the file says why: the first draft
# of the projects migration passed every structural check while leaving a NEW client project
# world-readable, because `projects` has FOUR policies and the listing query silently hid two of
# them. It also caught a live authorization hole — a NULL-valued predicate in `accept_lead_proposal`
# that let an unauthorized caller through, since `not (NULL or NULL)` is NULL and never fires.
# Needs local postgres; touches only a scratch db it creates and drops.
stage2-schema-check *args:
    @cd w0m-api && python3 scripts/stage2_schema_check.py {{ args }}

# T229 AC4 — back up STORAGE, which pg_dump does not touch. 555 objects / ~54 MB across 13 buckets;
# a database restore that brings back rows pointing at missing files is a half-restore that looks
# whole. In always_confirm with db-backup and for the same reason: the output is secret material
# (private buckets hold applications, blueprints, domain scans and the Upwork corpus).
# 🔴 Refuses on ZERO buckets or ZERO objects — a downloader that finds nothing and reports success
# would certify that files are safe when none were copied.
storage-backup *args: (_confirm "storage-backup")
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/storage_backup.py {{ args }}

# T229 AC4 — prove storage-backup can go RED. Offline: a stub API serves a known corpus, and each
# refusal (empty bucket list, empty object list, a short download, a failed fetch) is exercised.
storage-backup-test:
    @python3 w0m-api/scripts/tests/test_storage_backup.py

# T229 AC2 — is there a RECENT backup? Reads the artefacts on disk, never a scheduler: this estate's
# scheduler surface is split (desktop-app routines are invisible to the CLI scheduler), so a routine
# can exist and never fire. Output is the only honest evidence, and it is scheduler-agnostic.
# 🔴 ZERO backups FAILS — a freshness checker reporting "nothing to check ✓" is the exact failure
# T229 documents, wearing a tick. No credentials, no network; safe on every push.
backup-freshness *args:
    @python3 w0m-api/scripts/backup_freshness.py {{ args }}

# T229 AC2 — prove backup-freshness goes RED: no directory, an empty one, a stale dump, a truncated
# dump, and a filename it cannot date. Runs on fixtures; never reads the real backups.
backup-freshness-test:
    @python3 w0m-api/scripts/tests/test_backup_freshness.py

# T231 — retention for scheduled backups. ~28 MB a dump + ~54 MB a Storage copy compounds to ~2.5 GB
# a month if nothing prunes, so this is part of scheduling rather than a follow-up.
# 🔴 Refuses --keep 0 and never touches a name it does not recognise.
backup-prune *args:
    @python3 w0m-api/scripts/backup_prune.py {{ args }}

# T231 AC3 — the offsite WATCHDOG's two static claims. The watchdog itself runs in the Cloudflare
# Worker on the existing `0 8 * * *` cron; these check the things a deploy would not catch:
#   · `backup-watchdog.ts` embeds MAX_AGE_DAYS (a Worker cannot read `.w0m/sdlc.json` at runtime),
#     so it is a SECOND ENCODING of one fact and is only tolerable while something gates it.
#   · AC3's own criterion — it rides an EXISTING slot; Workers Free caps triggers at 5 per ACCOUNT
#     and refuses the 6th with code 10072. Asserted here, cheaply, rather than at deploy time.
# 🔴 Exit 2 when a file or symbol is missing: "could not read the Worker" must never render as
# "the Worker agrees".
backup-watchdog-drift *args:
    @cd w0m-web && python3 project/scripts/backup_watchdog_drift.py {{ args }}

backup-watchdog-drift-test:
    @cd w0m-web && python3 project/scripts/tests/test_backup_watchdog_drift.py

# T231 AC2 — the OFFSITE half. T229 proved the dump restores; it did not stop the only copy living
# on one laptop. The Mac produces (only place `pg_dump` runs) and pushes to R2 directly.
# 🔑 A Worker is NOT involved and does not need to be: it cannot reach a file on this laptop, so for
# the Postgres dump there is nothing for it to mirror FROM. The honest design is smaller than the
# one first sketched.
# 🔴 Refuses an empty push, and asks R2 what it stored rather than trusting a 200.
backup-push-r2 *args:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/backup_push_r2.py {{ args }}

# T231 AC2 — prove the offsite copy is REAL: download the newest object of each kind and re-hash it.
# A size match is not integrity, and head_object only reports what R2 believes.
backup-verify-r2:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/backup_push_r2.py --verify

# T231 / debt D59 — restore the OFFSITE dump, not the local one. `backup-verify-r2` proves the
# remote bytes round-trip; this proves they RESTORE, a different claim and the one T229 established
# matters. Pulls the newest r2://wom7-backups/postgres/ object and runs the full restore+diff.
db-restore-verify-r2:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/db_restore_verify.py --from-r2

# T231 / debt D59 — the STORAGE half of restoring from offsite: pull the newest tarball, extract it,
# and verify all 555 objects against the manifest they were uploaded with. Distinct from
# `backup-verify-r2`, which hashes the ARCHIVE — this checks the FILES inside it.
# ⚠️ It does NOT re-upload into Supabase Storage; that is destructive and has no scratch bucket.
storage-restore-verify-r2:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/storage_backup.py --from-r2

# T231 AC7 — prove backup-push-r2 goes RED. Offline: a fake S3 client, never the real bucket.
backup-push-r2-test:
    @python3 w0m-api/scripts/tests/test_backup_push_r2.py

# T229 AC6 — watch the Free-tier limits the estate has CHOSEN to live inside (owner, 2026-08-18:
# stay on Free, Pro only if genuinely needed). These fail abruptly rather than gradually.
# 🔴 Reports what it could NOT measure and never folds it into a pass — egress has no Management API
# endpoint, so it is listed as NOT MEASURED rather than silently omitted from a green tick.
supabase-limits *args:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-api/scripts/supabase_limits.py {{ args }}

# T229 AC6 — prove supabase-limits goes RED and, just as importantly, that it never reports a pass
# over an empty inventory or hides an unmeasured surface.
supabase-limits-test:
    @python3 w0m-api/scripts/tests/test_supabase_limits.py

# T229 AC1 — prove db-restore-verify can go RED. Seeds a scratch dump with a dropped table, an
# inflated row and an unrecognised error, and asserts each is caught. Never touches a real dump.
db-restore-verify-test:
    @python3 w0m-api/scripts/tests/test_db_restore_verify.py

# Infra-as-Code Deployment
deploy-infra-tf: (_confirm "deploy-infra-tf")
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'CLOUDFLARE_API_TOKEN="$CLOUDFLARE_API_TOKEN" AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" terraform -chdir=w0m-api/cloudflare apply -auto-approve'

# T131 AC2 — the shared stamp helper on its own, for a target that builds by other means. Same
# rule: pass the triple you already hold; never let a second producer appear.
_stamp version at commit:
    @cd w0m-web && python3 project/scripts/stamp_build.py \
        --version "{{ version }}" --at "{{ at }}" --commit "{{ commit }}"

# T429: probe for check_infisical.py (no-link / wrong-id / expired / other), against a fake CLI.
check-infisical-test:
    @python3 scripts/tests/test_check_infisical.py

# Dev convenience: mint fresh admin session(s) (service-role, no email) and open the CP logged in.
# w0m.xyz (admin console) and webomage.com are SEPARATE registrable domains = separate cookie
# scopes, so by default we seed BOTH: cp.w0m.xyz (admin console) + cp.webomage.com (whose
# .webomage.com session carries to join/job/webomage.com). Override with a comma-list, e.g.
# `just login-admin https://cp.w0m.xyz` for admin-only. Pin the admin with ADMIN_EMAIL=…
login-admin bases="https://cp.w0m.xyz,https://cp.webomage.com": check-infisical
    @echo "🔑 Minting fresh admin session(s)…"
    @urls="$(cd w0m-web && ADMIN_CP_BASES='{{bases}}' infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- node apps/cp/scripts/mint-admin-login.mjs)"; \
        [ -n "$urls" ] || { echo "❌ mint failed (see above)"; exit 1; }; \
        printf '%s\n' "$urls" | while IFS= read -r u; do [ -n "$u" ] && { echo "🌐 Opening → $u"; open "$u"; }; done
    @echo "🚪 Done testing? Run 'just logout-admin' to revoke what this minted."

# Companion to login-admin (T159 AC5): a break-glass mint with no exit just accumulates live
# admin sessions. /api/auth/signout revokes at GoTrue's default "global" scope — every session
# for that user, everywhere — so this only needs to fire the request from a browser tab that
# still carries the session cookie login-admin just opened; no service-role access required.
logout-admin bases="https://cp.w0m.xyz,https://cp.webomage.com":
    @printf '%s\n' "{{bases}}" | tr ',' '\n' | while IFS= read -r b; do \
        [ -n "$b" ] && { echo "🚪 Signing out → $b/api/auth/signout"; open "$b/api/auth/signout"; }; \
    done

# Setup Python env + Playwright binaries
setup-python:
    @cd w0m-api && if [ ! -d ".venv" ]; then uv venv; fi
    @cd w0m-api && uv pip install -r pyproject.toml
    @cd w0m-api && uv run playwright install chromium

# AI helper recipes
ai-infra-explain path:
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/ai_tools.py infra-explain {{ path }}

ai-copy-rewrite path:
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/ai_tools.py copy-rewrite {{ path }}

ai-case-scaffold path:
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/ai_tools.py case-scaffold {{ path }}

# Generate a news post
news-generate source_url bullets_file title_hint slug:
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/generate_news_post.py --source-url "{{ source_url }}" --bullets-file "{{ bullets_file }}" --title-hint "{{ title_hint }}" --slug "{{ slug }}"

# Trigger automated news generation
news-trigger-automated:
    @echo "Triggering automated news generation..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'curl -s -X POST "https://{{ project_ref }}.functions.supabase.co/daily-news-scheduler" \
      -H "apikey: $SUPABASE_SERVICE_ROLE_KEY" \
      -H "Authorization: Bearer $SUPABASE_SERVICE_ROLE_KEY" \
      -H "Content-Type: application/json" \
      -d "{}"'

# Check and update system status
check-status:
    @cd w0m-api && python3 scripts/healthcheck.py

# Health alias
health:
    @cd w0m-api && python3 scripts/healthcheck.py

# Content / site sanity checks
check-titles frontend_path="w0m-web":
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/archive/check_duplicate_titles.py {{ frontend_path }}

check-post-images frontend_path="w0m-web":
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta -- python3 scripts/archive/check_post_images.py {{ frontend_path }}

# Run SEO Audit (Meta tags, Images, Accessibility)
audit-seo:
    @echo "Running SEO Audit..."
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- node scripts/audit_seo.js

# Audit Supabase posts for media metadata
audit-media:
    @echo "Auditing Supabase news posts for media metadata..."
    # T189 AC4: this line previously carried BOTH a `-` prefix (just ignores the failure) AND
    # `|| echo` (the shell swallows it), so the recipe could not fail whatever the script did —
    # an audit that cannot report a problem. Both removed: a real failure now surfaces.
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta < /dev/null -- python3 scripts/audit_supabase_posts.py

# Legacy Gherkin-style E2E checks (superseded by Gauge)
e2e-features:
    @echo "⚠️  e2e-features is deprecated and superseded by Gauge. Running Gauge instead..."
    @just e2e

# Alias for standard "spec" command - runs Gauge E2E tests
spec: e2e


gen-sitemap-mmd frontend_path="w0m-web":
    @cd w0m-api && python3 scripts/gen_sitemap_mmd.py {{ frontend_path }}

codemaps-mmd:
    @cd w0m-api && python3 scripts/gen_blueprint_pages.py

# Verify website
verify frontend_path="w0m-web":
    @echo "Generating sitemap.mmd for {{ frontend_path }}..."
    @just gen-sitemap-mmd {{ frontend_path }}
    @echo "Generating codemap diagrams..."
    @just codemaps-mmd
    @echo "Running unified Gauge E2E verification..."
    @just e2e
    @echo "Auditing media metadata..."
    @just audit-media

# Run Chaos Monkey UI tests
verify-chaos frontend_path="w0m-web":
    @echo "Running Chaos Monkey testing on {{ frontend_path }}..."
    cd {{ frontend_path }} && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm exec playwright test tests/chaos.spec.ts

# Generate Visual Report with Screenshots
report-visual url="http://localhost:4321":
    @if [[ "{{ url }}" == *"localhost"* ]] || [[ "{{ url }}" == *"127.0.0.1"* ]]; then \
    	echo "Local target detected. Restarting dev server (redev)..."; \
    	{{ just_executable() }} redev > /dev/null 2>&1 & \
    	echo "Waiting for {{ url }} to be ready..."; \
    	bash -c 'for i in {1..30}; do curl -s -f "{{ url }}" > /dev/null && break; sleep 1; done'; \
    	echo "Server is up!"; \
    fi
    @echo "Generating visual report for {{ url }}..."
    @mkdir -p .reports
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm exec tsx scripts/generate_visual_report.js {{ url }} .reports/visual_report_$(date +%Y%m%d_%H%M%S)

# Generate Filmstrip Showcase Report (/_showcase)
report-filmstrip url="http://localhost:4321":
    @if [[ "{{ url }}" == *"localhost"* ]] || [[ "{{ url }}" == *"127.0.0.1"* ]]; then \
    	echo "Local target detected. Restarting dev server (redev)..."; \
    	{{ just_executable() }} redev > /dev/null 2>&1 & \
    	echo "Waiting for {{ url }} to be ready..."; \
    	bash -c 'for i in {1..30}; do curl -s -f "{{ url }}" > /dev/null && break; sleep 1; done'; \
    	echo "Server is up!"; \
    fi
    @echo "Generating filmstrip report for {{ url }}/_showcase..."
    @mkdir -p .reports
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- node scripts/generate_filmstrip_report.js {{ url }} .reports/filmstrip_$(date +%Y%m%d_%H%M%S)

report-tracks:
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'psql "$DATABASE_URL" -f w0m-api/supabase/queries/tracks_report.sql'

# T311: Upwork sync freshness (proposals/contracts/rooms/messages) -- read-only.
report-upwork-sync:
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'psql "$DATABASE_URL" --csv -f w0m-api/supabase/queries/upwork_sync_check.sql'

# MLX & Local LLM Serving (T184 AC8 — omlx on :8000 replaces retired serve_mlx.py / local-glm-4v)
model-serve:
    @echo "Starting omlx local LLM server on port 8000..."
    @omlx serve --port 8000

model-test:
    @echo "Testing omlx local LLM server (:8000)..."
    @curl -fsS http://localhost:8000/v1/models

ext-supabase-start:
    @echo "Starting local Supabase for w0m-ext..."
    @cd w0m-ext && pnpm dlx supabase start

ext-supabase-stop:
    @echo "Stopping local Supabase for w0m-ext..."
    @cd w0m-ext && pnpm dlx supabase stop

crawler-deploy: (_confirm "crawler-deploy")
    @echo "Deploying w0m-web/cf-crawler..."
    @cd w0m-web/cf-crawler && npm run deploy

crawler-dev:
    @echo "Running w0m-web/cf-crawler in dev mode..."
    @cd w0m-web/cf-crawler && npm run dev

migrate-crawler-data:
    @echo "Triggering data migration worker..."
    @curl https://webnames-migration.webomage.workers.dev

migrate-ext-data:
    @echo "Migrating Extension data (Local -> Remote)..."
    @cd w0m-api && python3 scripts/archive/migrate_w0m_ext_data.py

bake-pdfs:
    @echo "Baking PDFs (pandoc + weasyprint)..."
    @python3 w0m-api/scripts/bake_pdfs.py public

bake-private-cv:
    @echo "Baking Private CV PDF (pandoc + weasyprint)..."
    @python3 w0m-api/scripts/bake_pdfs.py private

# Bakes EVERY CV document in EVERY template into .cv-gallery/ (gitignored) and writes an index.
# There are 7 CV documents here and, until 2026-08-31, effectively one design — so nothing let you
# compare them, and `Aleksei_CV_2026_Public` sat for two days leading with a role that ended in
# Feb 2026 with no ongoing engagement at all. The index prints each document's word count, entry
# count, and whether it has a Present-dated role, because `just cv-validate` does NOT check that
# last one: it validates date FORMAT and canonical shape, and reported "no problems" throughout.
#
# CV gallery — bake all documents x all templates, then open the index.
cv-gallery *args:
    @cd w0m-web && python3 project/scripts/cv_gallery.py --open {{ args }}

# Same, without opening a browser (for a check or a headless run).
cv-gallery-build *args:
    @cd w0m-web && python3 project/scripts/cv_gallery.py {{ args }}

# The two docs/backend/branding CV PDFs — `Aleksei_CV_2026_Public` and
# `Aleksei_CV_2026_Private_Master`. They had NO generator until 2026-08-26: `bake-pdfs public`
# targets Aleksei_CV_2026.md, `private` targets Aleksei_CV_2026-08_Private.md, and `variants` the
# five served files, so an edit to either markdown could never reach its PDF. Same orphan class the
# variants mode was built for, found the same way — by someone asking for a change to a PDF nothing
# could produce. The two are NOT one document rendered twice: the private master carries the ACS
# reference number and the public file deliberately omits it.
bake-branding-cv:
    @echo "Baking branding CV PDFs (pandoc + weasyprint)..."
    @python3 w0m-api/scripts/bake_pdfs.py branding

# Bakes the client/applicant/trainee-facing manuals (w0m-web/docs/manuals/*.md) to PDF, with
# screenshots and embedded Mermaid fences (rendered as plain code — no mermaid-to-image filter
# wired in). Strips frontmatter and converts [[wikilinks]] to bold before handing off to pandoc.
bake-manuals:
    @echo "Baking manuals PDFs (pandoc + weasyprint)..."
    @python3 w0m-api/scripts/bake_pdfs.py manuals

# T165 task 3.4 — generate the CV Professional Experience section from `resume.json`.
# The hand-written branding CVs rendered 10 rows out of 27 canonical entries: they invented two
# employers ("Mindset", "TopDog" — zero occurrences anywhere in the estate), split Webomage into
# two mis-dated rows when canonical has one (2006 → present), buried Veeam Software, Hosting
# Concepts BV, NIR-Telecom, Yota and Beget in a generic "Regional ISPs" bucket, and dropped 21 of
# 27 outright. Prints by default; `--write` splices into both branding markdown files, after which
# `just bake-branding-cv` renders the PDFs. The employment-vs-engagement split is JUDGEMENT and
# lives in `project/data/cv/engagement-model.json`, not in the script. Fails closed on an entry the
# model does not classify — silently dropping a career is the defect this replaces.
cv-experience *args:
    @cd w0m-web && python3 project/scripts/cv_experience.py {{args}}

# T165 task 3.5 — does the CV assert more than `resume.json` + `claims.json` can support?
# 🔴 NOT `cv-claims`, which builds claims.json FROM documents. This reads the other direction:
# the CV is a covering document over a dataset, and this compares the two.
# The term corpus is DISCOVERED from the document, so a claim added tomorrow is checked tomorrow —
# a hand-listed vocabulary silently misses whatever comes next, which is how G2-definer-acl-explicit
# passed for its whole life on a predicate that could never fire.
# Deliberately scoped to the Executive Summary: widened to the skills section it reports 47
# findings, because canonical `skills` holds 5 categories x 4 loose phrases against ~90 technologies
# in the CV. That is a DATA gap, not an over-claim, and a gate firing 47 times gets switched off.
# `accepted` in project/cv-overclaim-policy.json is downward-only, and every entry carries a
# `clears_when`.
cv-overclaim-check *args:
    @cd w0m-web && python3 project/scripts/cv_overclaim_check.py {{args}}

# The gate's own red probes — 8 cases, including that a NEW unbacked claim fails and that a section
# outside the declared zone is not scanned.
cv-overclaim-check-test:
    @cd w0m-web && python3 project/scripts/cv_overclaim_check.py --selftest

# Verdict logic of the authorization probe suite (T198/T242). Offline — pure logic, no database.
# Asserts that "counted zero", "counted violations" and "could not measure" are THREE states, and
# that the third still fails closed under --enforce. It exists because `red` was
# `got != 0 or err` with `got` defaulting to -1, so an unreachable database reported as a
# violation and blocked a push while the same suite ran 0 RED five times in a row afterwards.
authz-probe-verdict-test:
    @cd w0m-web && python3 project/scripts/tests/test_authz_probe_suite.py

# T544 — profile_experience read is owner-or-admin (migration 20261006121000). Boots a THROWAWAY Postgres (Homebrew initdb/pg_ctl/psql), builds the table and its policies from the
# real T360/T363/T468 migration text, and proves: the harness reproduces the open read, the fix narrows it, the write policies are byte-identical, the source_links policy still
# works, and the authz probes X30-X34 read RED before and GREEN after. Fails (does not skip) without the Postgres binaries; tier `live` so `just test` stays green on a bare machine.
t544-profile-experience-read-test:
    @cd w0m-web && python3 project/scripts/tests/test_t544_profile_experience_read.py

# T555 — the Studio's six themes are named in three places in two repos (the Studio, the resume-pdf edge function, the worker's PDF renderer) and the stylesheet the Studio sends must pass the
# worker's refusal rules. Offline: four files, no database.
resume-themes-agree-test:
    @cd w0m-web && python3 project/scripts/tests/test_resume_themes_agree.py

# T555 AC3 — bring the member's CV tables to the 2026 CV's structure: position kind/remote/via-Upwork, the canonical highlights the one-time seed stopped short of, the summary, grouped skills
# with evidence, accreditations / open-source / education. ADDITIVE, DRY RUN by default; `--apply` is the owner's (run under `infisical run --env=beta --silent --`).
cv-structure-load *args:
    @cd w0m-web && python3 project/scripts/cv_structure_load.py {{args}}

cv-structure-load-test:
    @cd w0m-web && python3 project/scripts/tests/test_cv_structure_load.py

# T555 AC2 — which numbers and technology terms of a CV summary and skills block does the canonical corpus (resume.json, claims.json) back? READ-ONLY: two JSON files and one
# markdown file, no database, no network. Exit 1 when something is unbacked or conflicting, 2 when an input is missing.
cv-evidence-report *args:
    @cd w0m-web && python3 project/scripts/cv_evidence_report.py {{args}}

cv-evidence-report-test:
    @cd w0m-web && python3 project/scripts/tests/test_cv_evidence_report.py

# T553 — the hat write path (migration 20261007010000): five SECURITY DEFINER functions that check authority and QH1/QH4/QH5 inside the function and write the audit row in the same
# transaction. Boots a THROWAWAY Postgres (Homebrew initdb/pg_ctl/psql), applies the real T461 migration then the fix, and drives every rule as role `authenticated`. Fails (does not skip)
# without the Postgres binaries; tier `live` so `just test` stays green on a bare machine. T553_MIGRATION=<path> runs the same checks against a mutated copy.
t553-hat-write-path-test:
    @cd w0m-web && python3 project/scripts/tests/test_t553_hat_write_path.py

# T551 — no two migration files may share a version (the ledger key). Offline, no database, about a second: it runs at push, where the collision is made,
# and `db_drift_check.py` also runs it first, so `db-migrate` (which runs that check as a dependency) refuses a colliding tree.
migration-versions-check:
    @cd w0m-web && python3 project/scripts/db_drift_check.py --versions-only

# T551 — offline proof of that check (16 checks: names every colliding file, refuses before the ledger is read, real tree clean, registered as a pre-push suite).
migration-versions-test:
    @python3 w0m-web/project/scripts/tests/test_migration_versions_unique.py

# T545 — "admin reads everything" over the four member-owned personal tables, behind ONE switch (migration 20261006130000). Throwaway Postgres (Homebrew binaries), owner policies taken from the
# real T498/T505/T510 migration text. Proves: the admin read works, a password-only admin still reads nothing of anyone else's, the owner policies and grants are byte-identical, no write
# arm exists, one statement narrows all four tables for onboarding, and the authz probes (built by the real suite, executed with \gset) are GREEN in both switch states and RED on a mismatch.
t545-admin-reads-personal-data-test:
    @cd w0m-web && python3 project/scripts/tests/test_t545_admin_reads_personal_data.py

# Probes for the DECLARED board identity (T242). Offline — no gh, no network. Asserts one
# declaration in `.w0m/sdlc.json -> board`, three readers, and that both silent breaks stay shut:
# a failed `gh auth switch` must stop the run (it used to be swallowed and exit 0), and the board
# must resolve by NUMBER with the title as a guard (a `gh project copy` defeats title matching).
board-identity-test:
    @python3 scripts/tests/test_board_identity.py

# Responsive layout matrix (T261). MEASURES: for every viewport/orientation pair it records the
# resolved container max-width and padding, the H1's rendered line count, stranded last words,
# clipped text, and how much of the viewport is actually clear reading space between the header
# and the footer's overlap band. Writes a JSON report; prints a table.
#   just layout-matrix                       measure /services/ and write the report
#   just layout-matrix "/services/,/"        measure several pages
layout-matrix pages="/services/,/,/blueprints/" out="../../docs/reports/layout-matrix.json":
    #!/usr/bin/env bash
    set -euo pipefail
    cd w0m-web/apps/web
    node scripts/layout-matrix.mjs --pages '{{ pages }}' --out '{{ out }}'

# The same measurement as a GATE (T261 AC6). Boots or reuses a dev server, then fails on clipped
# text, rebalanceable orphans, horizontal overflow, an H1 that wraps at desktop width, or a clear
# reading window that is a minority of the screen.
# ⚠️ A green run here means nothing unless `layout-matrix-test` is also green — that suite is what
# proves each rule can fire at all. It has already caught this gate reporting clean for three
# different wrong reasons: an exemption keyed on `transition-property` (which initialises to
# `all`, so it exempted every element on every page), an orphan rule that was vacuous under greedy
# wrapping, and an overflow check read off `documentElement` while the real scroller is
# `.content-scroll-area`.
layout-matrix-check pages="/services/,/,/blueprints/":
    #!/usr/bin/env bash
    set -euo pipefail
    cd w0m-web
    if curl -sf -o /dev/null http://localhost:4321/; then
      echo "[layout-matrix] reusing the dev server already on :4321"
    else
      echo "[layout-matrix] booting a dev server..."
      ASTRO_DEV_BACKGROUND=1 infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter web dev > /tmp/w0m-web-layout-dev.log 2>&1 &
      DEV_PID=$!
      # Kill by PORT as well as PID: `infisical run -- pnpm dev` puts astro two levels down, so
      # killing the spawned PID alone leaks a server that the next run silently reuses (see goldens).
      trap 'lsof -ti tcp:4321 -sTCP:LISTEN 2>/dev/null | xargs -r kill 2>/dev/null || true; kill $DEV_PID 2>/dev/null || true' EXIT
      for i in $(seq 1 60); do
        if curl -sf -o /dev/null http://localhost:4321/; then echo "[OK] server ready after ${i}s"; break; fi
        if [ "$i" -eq 60 ]; then echo "[FAIL] dev server did not start in 60s"; tail -20 /tmp/w0m-web-layout-dev.log; exit 1; fi
        sleep 1
      done
      # A 200 is not readiness — a cold Astro server re-optimizes deps and reloads mid-navigation.
      streak=0
      for i in $(seq 1 45); do
        if curl -sf -o /dev/null --max-time 10 http://localhost:4321/; then streak=$((streak + 1)); else streak=0; fi
        if [ "$streak" -ge 3 ]; then break; fi
        if [ "$i" -eq 45 ]; then echo "[FAIL] server never stabilised"; exit 1; fi
        sleep 2
      done
    fi
    cd apps/web && node scripts/layout-matrix.mjs --pages '{{ pages }}' --check --out ../../docs/reports/layout-matrix.json

# Red probes for the layout detector (T261 AC6). Offline — synthetic pages, no dev server. Feeds
# every rule a page built to break it and FAILS if the rule stays quiet, then feeds it the two
# shapes it must not flag. A detector reporting zero is a hypothesis until this suite is green.
layout-matrix-test:
    @cd w0m-web/apps/web && node scripts/layout-matrix.test.mjs

# Run E2E Tests (Gauge)
e2e:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🔄 Restarting dev server for E2E tests..."
    just redev > /tmp/w0m-web-dev.log 2>&1 &
    DEV_PID=$!
    echo "🔄 Starting w0m-cf for E2E tests..."
    (cd w0m-cf && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm run dev) > /tmp/w0m-cf-dev.log 2>&1 &
    CF_PID=$!
    echo "⏳ Waiting for http://localhost:4321 to be ready (up to 60s)..."
    READY=0
    for i in $(seq 1 60); do
      if curl -s -f "http://localhost:4321" > /dev/null 2>&1; then
        echo "✅ Server ready after ${i}s"
        READY=1
        break
      fi
      sleep 1
    done
    if [ "$READY" -eq 0 ]; then
      echo "❌ Timeout: dev server did not start within 60s"
      cat /tmp/w0m-web-dev.log | tail -20
      exit 1
    fi
    echo "⏳ Waiting for http://localhost:8787 to be ready..."
    if curl -s -f "http://localhost:8787/cdn-cgi/handler/scheduled" > /dev/null 2>&1; then
      echo "✅ Worker server ready"
    else
      echo "⚠️ Timeout: worker server did not start within 60s (proceeding anyway)"
      cat /tmp/w0m-cf-dev.log | tail -20 || true
    fi
    echo "🧪 Running E2E Verification..."
    cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm test:e2e

# Launch local Astro website
dev:
    cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm run dev

# Launch specific apps locally
dev-join:
    cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm run dev:join

dev-job:
    cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm run dev:job

# The CP had NO sanctioned local dev path until 2026-08-13 — no `dev:cp` script and no recipe — so
# every launch.json pointed at a bare `pnpm --filter cp dev`. That starts, and then every page
# using Supabase dies in middleware with "environment variables are missing", because secrets reach
# a process only by infisical injection (CLAUDE.md). Same shape as the siblings.
dev-cp:
    cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm run dev:cp

# Kill all local "astro dev" running on all ports and start new one on port 4321
# `sync-env` was dropped as a dependency (T119 AC2b retired it — it now always exits 1 by design,
# which silently prevented `redev` from ever reaching `pnpm run dev`). Secrets are injected below.
redev: stop-dev
    cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm run dev

# Usage: just upwork-export --vault=../w0m-web/src/content/upwork_vault --limit=100
upwork-export *args="":
    @echo "Running Upwork Exporter (Direct to Vault)..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- node --import tsx w0m-api/scripts/upwork_exporter.ts {{ args }}

# Check Upwork auth status and tokens
upwork-check:
    @echo "Checking Upwork authentication records..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'psql "$DATABASE_URL" -c "SELECT id, updated_at FROM upwork_auth_tokens;"'
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'psql "$DATABASE_URL" -c "SELECT key, updated_at FROM admin_secrets WHERE key = '"'"'upwork_auth_token'"'"';"'

# Search Upwork Jobs
upwork-search *args="":
    @cd w0m-web && python3 project/scripts/upwork_mcp_sync.py {{ args }}

# Incremental live Upwork sync via Upwork MCP to local repository cache
# Usage: just upwork-mcp-sync [--full] [--dry-run]
upwork-mcp-sync *args="":
    @cd w0m-web && python3 project/scripts/upwork_mcp_sync.py {{ args }}

# T539 AC1: read-only probe of how Upwork pages rooms and messages and which field is a message's author (key names only, no values)
# Usage: just upwork-messages-probe [--out FILE] [--dry-run]
upwork-messages-probe *args="":
    @cd w0m-web && python3 project/scripts/upwork_messages_probe.py {{ args }}

# T539: read-only check that the sync script's contracts, proposals, invitations and agency reads still match what the server returns (key names only)
# Usage: just upwork-lists-probe [--out FILE] [--dry-run]
upwork-lists-probe *args="":
    @cd w0m-web && python3 project/scripts/upwork_lists_probe.py {{ args }}

# T533 AC1: read-only schema probe of which fields the Upwork MCP returns for proposals, offers, contracts, and rooms (key names only, no secrets)
# Usage: just upwork-schema-probe [--out FILE]
upwork-schema-probe *args="":
    @cd w0m-web && python3 project/scripts/upwork_schema_probe.py {{ args }}

# Harvest full historical proposals and cover letters archive (~2,100+ proposals)
# Usage: just upwork-harvest-proposals [--limit N] [--status STATUS] [--dry-run]
upwork-harvest-proposals *args="":
    @cd w0m-web && python3 project/scripts/upwork_harvest_proposals.py {{ args }}

# Export Upwork datasets into Markdown Knowledge Vault (project/data/upwork_vault/)
# Usage: just upwork-vault-export
upwork-vault-export:
    @cd w0m-web && python3 project/scripts/upwork_export_vault_md.py

# Full sync: Upwork API -> Supabase Storage -> Local repo
upwork-sync-full:
    @echo "Full Upwork Sync: API -> Storage -> Local..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- node w0m-web/scripts/sync_upwork_full.js

# Sync from Supabase Storage to local repo only
upwork-sync-local:
    @echo "Syncing Upwork data from Supabase Storage to local..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- node w0m-web/scripts/sync_upwork_from_storage.js

# Trigger remote upwork-poller (syncs Upwork API -> Supabase Storage)
upwork-poller-trigger:
    @echo "Triggering remote upwork-poller..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- sh -c 'curl -s -X POST "https://{{ project_ref }}.functions.supabase.co/upwork-poller" \
      -H "apikey: $SERVICE_ROLE_KEY" \
      -H "Authorization: Bearer $SERVICE_ROLE_KEY" \
      -H "Content-Type: application/json" \
      -d "{\"trigger\": \"manual\"}" | jq .'

# Upload existing local contracts to Supabase Storage (one-time migration)
upwork-upload-local:
    @echo "Uploading local contracts to Supabase Storage..."
    @infisical run --projectId={{ infisical_project_id }} --env=beta -- node w0m-web/scripts/upload_local_to_storage.js

# Verify the ZeroClaw gateway and daemon service are running
zeroclaw-status:
    @echo "🔍 Checking ZeroClaw gateway (:42617)..."
    @zeroclaw status --format exit-code > /dev/null 2>&1 && echo "✅ ZeroClaw gateway is ONLINE" || echo "❌ ZeroClaw gateway is OFFLINE"
    @echo "🔍 Checking ZeroClaw daemon service..."
    @zeroclaw service status 2>&1 | grep -q "not loaded" && echo "❌ ZeroClaw daemon service is not loaded" || echo "✅ ZeroClaw daemon service is loaded"

# Short alias: just zc start/stop/status/restart/agents/model/cp
zc command="status" arg="":
    @if [ "{{ command }}" = "start" ]; then \
    	{{ just_executable() }} zeroclaw-start; \
    elif [ "{{ command }}" = "stop" ]; then \
    	{{ just_executable() }} zeroclaw-stop; \
    elif [ "{{ command }}" = "restart" ]; then \
    	{{ just_executable() }} zeroclaw-restart; \
    elif [ "{{ command }}" = "status" ]; then \
    	{{ just_executable() }} zeroclaw-status; \
    elif [ "{{ command }}" = "agents" ]; then \
    	zeroclaw agents list; \
    elif [ "{{ command }}" = "model" ]; then \
    	if [ -z "{{ arg }}" ]; then \
    		zeroclaw models status; \
    	else \
    		zeroclaw models set "{{ arg }}"; \
    	fi; \
    elif [ "{{ command }}" = "cp" ]; then \
    	{{ just_executable() }} zeroclaw-cp; \
    else \
    	echo "Unknown command '{{ command }}'. Available: start, stop, status, restart, agents, model [name], cp"; \
    fi

# Open the ZeroClaw gateway dashboard, printing the pair-code to authenticate with.
# `zeroclaw gateway get-paircode` exits 0 even when the gateway is down, so check the text.
zeroclaw-cp:
    #!/usr/bin/env bash
    set -euo pipefail
    OUT=$(zeroclaw gateway get-paircode 2>&1 || true)
    if printf '%s' "$OUT" | grep -q "Failed to fetch"; then
    	echo "⚠️  Gateway is not running — start it with 'just zc start'"
    	exit 1
    fi
    echo "$OUT"
    echo "🌐 Opening ZeroClaw gateway dashboard..."
    open "http://127.0.0.1:42617"

# Start the ZeroClaw daemon (launchd user service com.zeroclaw.daemon)
zeroclaw-start:
    @zeroclaw service start

# Stop the ZeroClaw daemon
zeroclaw-stop:
    @zeroclaw service stop

# Restart the ZeroClaw daemon to pick up config changes
zeroclaw-restart:
    @zeroclaw service restart

# Run resilience E2E against a dead database endpoint (verifies no-DB fallback).
# Boots apps/web with PUBLIC_SUPABASE_URL pointed at a discard port, runs the
# specs-resilience suite (kept outside specs/ so default E2E never picks it up).
e2e-dbdown:
    #!/usr/bin/env bash
    set -euo pipefail
    echo "🔌 Starting web dev server with dead Supabase endpoint..."
    cd w0m-web && PUBLIC_SUPABASE_URL="http://127.0.0.1:9" SUPABASE_URL="http://127.0.0.1:9" \
      NODE_OPTIONS='--max-old-space-size=8192' infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- pnpm --filter web dev >/tmp/w0m-web-dbdown.log 2>&1 &
    SERVER_PID=$!
    trap 'kill $SERVER_PID 2>/dev/null || true' EXIT
    READY=0
    for i in $(seq 1 60); do
      if curl -s -o /dev/null http://localhost:4321; then READY=1; break; fi
      sleep 1
    done
    if [ "$READY" -eq 0 ]; then
      echo "❌ web dev server did not start within 60s"; tail -20 /tmp/w0m-web-dbdown.log; exit 1
    fi
    echo "🧪 Running resilience suite (DB unreachable by design)..."
    cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- env E2E_BASE_URL=http://localhost:4321 SKIP_UI_AUTH=true pnpm exec gauge run specs-resilience

# Run the resilience suite against a LIVE deployed site (default: production).
# Useful right now while Supabase is quota-restricted: proves the real site keeps
# rendering with the database unreachable. Override the target with BASE=...
#   just e2e-live-resilience
#   BASE=https://beta.webomage.com just e2e-live-resilience
e2e-live-resilience BASE="https://webomage.com":
    @echo "🌐 Running resilience suite against {{ BASE }} ..."
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- env E2E_BASE_URL={{ BASE }} SKIP_UI_AUTH=true pnpm exec gauge run specs-resilience

# ── T23/T25: knowledge graph + tech-debt + lexicon truth ─────────────────────
# Rebuild the code knowledge graph (graphify, zero-LLM). `just graph ..` graphs the whole workspace.
graph path=".":
    @echo "🕸️  graphify update {{ path }} ..."
    graphify update {{ path }}

# T239 AC1/AC5 — verify ticket-schema epic vocabulary matches ROADMAP.md with zero drift.
epic-vocab-check:
    @python3 scripts/sync_epic_vocabulary.py --check

# T239 AC1 — derive and update canonical epic vocabulary in tickets-schema.jsonc from ROADMAP.md.
epic-vocab-sync:
    @python3 scripts/sync_epic_vocabulary.py --sync

# FULL doc rebuild — re-extracts everything, no cache reuse. MINUTES (measured: ~47s per doc on the
# local model; the migrated vault ~= 45 min for 55 notes). Use after a big content change, or to
# repair a graph. ⚠️ NEVER put this in a hook.
graph-docs path=".":
    @command -v graphify >/dev/null || { echo "graphify not installed"; exit 127; }
    @curl -sf --max-time 5 -o /dev/null {{ OMLX_URL }}/models || { echo "🔴 local model server unreachable at {{ OMLX_URL }} — start omlx, or pass OMLX_URL=…"; exit 1; }
    @echo "🕸️  FULL doc+code extraction of {{ path }} via {{ OMLX_MODEL }} (local, nothing leaves the machine)…"
    OPENAI_BASE_URL={{ OMLX_URL }} OPENAI_API_KEY=local OPENAI_MODEL={{ OMLX_MODEL }} \
      graphify extract {{ path }} --backend openai --max-concurrency 1 --api-timeout 900

# INCREMENTAL doc rebuild — same thing, but graphify reuses its per-file cache so unchanged docs are
# not re-sent to the model.
# 🔴 UNVERIFIED, AND THAT IS WHY IT IS NOT IN A HOOK YET. The subset run printed
#   `incremental cache checkpoint failed: … not 'FileSlice'`
# which means the cache may never be written, making this identical in cost to `graph-docs`. Prove
# it before wiring: run it twice on the same unchanged path and compare wall-clock. Second run must
# be dramatically faster. If it is not, the cache is broken upstream and a hook would put a
# ~45-minute LLM job on every commit.
graph-docs-inc path=".":
    @command -v graphify >/dev/null || { echo "graphify not installed"; exit 127; }
    @curl -sf --max-time 5 -o /dev/null {{ OMLX_URL }}/models || { echo "🔴 local model server unreachable at {{ OMLX_URL }} — start omlx, or pass OMLX_URL=…"; exit 1; }
    @echo "🕸️  incremental doc extraction of {{ path }} (cache-reusing) via {{ OMLX_MODEL }}…"
    @echo "    ⚠️ if this takes as long as \`just graph-docs\`, the upstream cache is broken — do not hook it."
    OPENAI_BASE_URL={{ OMLX_URL }} OPENAI_API_KEY=local OPENAI_MODEL={{ OMLX_MODEL }} \
      graphify extract {{ path }} --backend openai --max-concurrency 1 --api-timeout 900

# Prove whether the incremental cache actually works: same path twice, timed. Read the two numbers.
graph-docs-cache-test path="w0m-web/docs/design":
    @echo "▶ run 1 (cold)…"; time just graph-docs-inc {{ path }} >/dev/null 2>&1 || true
    @echo "▶ run 2 (should be MUCH faster if the cache works)…"; time just graph-docs-inc {{ path }} >/dev/null 2>&1 || true
    @echo "⇒ comparable times = cache broken (upstream FileSlice bug) ⇒ do NOT wire into a hook."

# List TODO/FIXME in REAL source across the repos. No storage, no drift.
# Decided tech debt lives in w0m-web/TECH-DEBT.md (plain markdown, git-tracked).
# Replaced the old Supabase census 2026-07-21: 78% of its 69 rows were noise from .wrangler
# build output and generated reports, it never marked anything resolved, and the SQL the
# w0m-sdlc-start skill told agents to run referenced four columns that don't exist.
# Cross-repo pnpm dependency alignment (security floors + lockstep + exceptions).
# Policy: w0m-web/project/deps-policy.json. Raise a floor there once, then `just deps-apply`.
# `deps-check` is the read-only gate (wired into pre-push); it fails on any repo below a floor
# or a lockstep skew, and warns on advisory-lag. See w0m-web/docs/DEPS-ALIGNMENT.md.
deps-check:
    @python3 scripts/deps_sync.py

# Fix drift in place across all TS repos, then reinstall the affected lockfiles.
deps-apply:
    @python3 scripts/deps_sync.py --apply

# Install missing node_modules/.bin toolchains across all 5 TS repos (`pnpm install --frozen-lockfile --prefer-offline`).
deps-install:
    @python3 scripts/deps_sync.py --install

# Red probes for lockstep's version resolution (overrides > devDependencies > dependencies).
# Offline. Added 2026-08-11 with the fix that made lockstep usable for a DIRECT dependency —
# it previously read pnpm.overrides only, so declaring one reported `has None` on every repo
# that plainly declared it.
deps-check-test:
    @python3 scripts/deps_sync_test.py

# Show which policy tools have an upstream update (read-only): AUTO = tools-upgrade will take it
# (brew, within its `auto` bump allowance); manual = prod-gating / major / non-brew (review by hand).
tools-outdated:
    @python3 scripts/tools_check.py --outdated

# T164 AC1 evidence: which UNGOVERNED host CLIs does the estate actually invoke? Counts only
# command-position hits (line start / after a pipe, &&, ;, $(, xargs, sudo) across git-tracked
# scripts, justfiles and git hooks — a plain grep scored `tree` 73 and `uv` 67 on prose alone.
# Use this to decide tools-policy.json membership; do not add a tool with 0 uses without a reason.
tools-usage:
    @python3 scripts/tool_usage_probe.py

# Structural (AST) rules for w0m-specific defects that have actually bitten us —
# w0m-web/project/ast-grep/rules/. Exits non-zero on any finding, so it can gate.
# NOT a linter (oxlint/semgrep already run) and NOT a graph (`just ask` owns that).
# ✅ ast-grep parses .astro components via tree-sitter-astro dynamic library (T410); .svelte/.vue/.sql remain unparsed.
sg-scan *paths:
    @cd w0m-web && ast-grep scan -c project/ast-grep/sgconfig.yml \
        {{ if paths == "" { ". ../w0m-api/supabase ../w0m-api/src ../w0m-cf/src" } else { paths } }}

# Build or rebuild tree-sitter-astro dynamic library for ast-grep custom language (T410)
sg-build-astro-parser *args:
    @cd w0m-web && python3 project/scripts/build_tree_sitter_astro.py {{ args }}

# Prove each ast-grep rule fires (must_flag) and is not over-broad (must_not_flag).
# A rule with no test case FAILS the run — an untested rule is an unproven rule.
sg-test:
    @cd w0m-web && python3 project/scripts/ast_grep_test.py

# Reports tool_result bytes by tool and Read-opportunity classes. Measured 2026-08-03 over
# 309 sessions: Bash 57.5% of bytes vs Read 34.3%, and "stale (edit after read)" alone is
# 46.4% of Read bytes (~1.49M tok) — i.e. the win is workflow, not a compression proxy.
# Re-run after workflow changes to confirm the stale-read share is actually falling.
# Size agent context waste from real transcripts (read-only, no API cost, no writes).
headroom-audit *args:
    @headroom audit-reads {{ args }}

# Read-only preview; nothing is written without `just headroom-learn-apply`.
# 2026-08-03 baseline: 133 sessions / 15884 calls / 1011 failures (6.4%) → 7 recommendations.
# Mine past tool-call FAILURES into agent guidance (uses an LLM — costs tokens).
headroom-learn *args:
    @headroom learn --project {{ justfile_directory() }} {{ args }}

# PINNED to CLAUDE.local.md on purpose: a bare `headroom learn --apply` also targets the agent
# memory index (~/.claude/projects/*/memory/MEMORY.md) and would rewrite it wholesale.
# Write learned patterns to CLAUDE.local.md only (bounded blast radius).
headroom-learn-apply:
    @headroom learn --project {{ justfile_directory() }} --apply --target CLAUDE.local.md

# Idempotent — safe to re-run; it only fills in what is missing, then re-checks and proves it.
# Steps around four traps that killed the first rollout: `--providers auto` aborted on the retired
# openclaw binary (uninstalled 2026-08-10, so that one is now historical), `--memory` pins /readyz
# at 503, serena won't boot without a `projects` key, and a custom base URL silently disables
# on-demand tool loading (#746).
# Provision Headroom for this machine (daemon + serena cfg), then verify it took.
headroom-bootstrap:
    @python3 scripts/headroom_bootstrap.py --apply

# ⚠️ THE ONLY WAY TO GET A HEADROOM-ROUTED TASK OUT OF THE DESKTOP APP.
# In-app subagents (the Agent tool) do NOT route: they run inside the app's engine, which is
# spawned with a pinned ANTHROPIC_BASE_URL=https://api.anthropic.com. Measured 2026-08-04 — a
# subagent that burned 48,499 tokens moved the proxy request counter by ZERO. A subprocess
# `claude -p` is a fresh process, so it takes the base URL below and actually routes.
# Measured benefit in @wom (~200 MCP tools), tool-schema deferral only:
#   ~11k tokens/request on top of Claude Code's own tool search (ENABLE_TOOL_SEARCH=true), and
#   ~103k tokens/request when the client has no tool search of its own.
# Compression is still 0 tokens and always has been — do not expect any. Prints the proxy
# counter before/after so a task that silently failed to route is visible, never assumed.
# Run a one-shot Claude Code task THROUGH the headroom proxy.
headroom-task +task:
    #!/usr/bin/env bash
    set -uo pipefail
    stat_req() { curl -s -m5 http://127.0.0.1:8787/stats \
        | python3 -c "import sys,json;print(json.load(sys.stdin)['persistent_savings']['lifetime']['requests'])" 2>/dev/null || echo "?"; }
    curl -fsS -m3 http://127.0.0.1:8787/health >/dev/null 2>&1 || {
        echo "❌ headroom proxy is DOWN at 127.0.0.1:8787 — run \`just headroom-bootstrap\`"; exit 1; }
    before=$(stat_req)
    # Run from the WORKSPACE ROOT (@wom), not w0m-api. `just` would otherwise start the task in
    # the justfile's directory, where a question about e.g. TECH-DEBT.md (which lives in w0m-web)
    # is answered "it doesn't exist" — correct for that cwd, useless as an answer. @wom is also
    # the app's own session root, so a routed task sees what an in-app one would.
    cd "{{ justfile_directory() }}"
    ANTHROPIC_BASE_URL=http://127.0.0.1:8787 claude -p "{{ task }}"
    rc=$?
    after=$(stat_req)
    echo ""
    if [ "$before" = "$after" ]; then
        echo "⚠️  [headroom] proxy requests ${before} → ${after} — the task did NOT route through the proxy"
    else
        echo "✅ [headroom] proxy requests ${before} → ${after} — routed"
    fi
    exit $rc

# Raw upstream diagnostics — use `just headroom-status` first; this is the escape hatch.
headroom-doctor:
    @headroom doctor; headroom install status

# T247 AC3 — bring `known_good` up to the INSTALLED version, but only for versions that pass their
# smoke. This closes a hole `tools-upgrade` structurally cannot: once installed is AHEAD of
# known_good there is nothing left to upgrade, so the drift is permanent. Four tools sat in that
# state on 2026-08-21, `osv-scanner` among them — the scanner in every repo's pre-commit hook.
# 🔴 Smoke-gated, unlike `tools-check --update-known-good`, which promotes everything present with
# NO verification. Promoting an unsmoked version does not verify it, it just silences the gate.
# Dry-run by default; `--apply` PROPOSES (T546: the policy is written only by `tools-promote --apply`). Exits non-zero when anything could not be proposed.
tools-reconcile *args:
    @python3 scripts/tools_upgrade.py --reconcile {{ args }}

# T246 AC5 — which tables does an ANON-role client read, and can anon actually read them?
# 🔑 The role, not the reader COUNT: T246 AC3 measured the readers of every closed catalogue and 3
# of 4 were `service_role`, which RLS does not apply to — a count-based gate would have blocked
# three correct closures. And not the KEY either: an anon-key client that forwards the caller's JWT
# is `caller`, not anon, so it is reported separately instead of crying wolf on a guarded path.
# ⚠️ A LOWER BOUND, stated in its output: 238 of 267 `.from()` receivers get their client from an
# import or a parameter, which local analysis cannot resolve. It reports them rather than skipping.
anon-reader-check:
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 ../w0m-web/project/scripts/anon_reader_gate.py --live

# Static half only — no secrets, no network. Proves the classifier and the walker.
anon-reader-test:
    @cd w0m-web && python3 project/scripts/tests/test_anon_reader_gate.py

# T250 AC4 — the TASKS row and the ticket must not disagree about status. `CLAUDE.md` calls the
# T-row status-of-record and 7 rows contradicted their own ticket, one of them a ✅ over a `queued`
# ticket. Every fixture here exists because a real measurement was wrong first — a bare `|` split,
# a glyph-only read, a status word read out of prose, and a mapping missing 💤 entirely.
# No secrets, no network.
tasks-row-status-test:
    @python3 scripts/tests/test_tasks_row_status.py

# T242 — the org-migration DRY RUN. Mutates NOTHING; prints what a full run would create.
#
# Owner 2026-08-22: dry-run first for visibility and steps, then the full migration, "keeping in
# mind that we can any time wipe everything and re-sync/remigrate". That frame is what makes this
# safe, and it rests on a measured fact rather than optimism: the GitHub issues are a PROJECTION of
# project/tickets/T<n>.md, and T242 measured ONE comment across all 238 of them. Re-creating them
# loses essentially nothing, so the migration is idempotent.
#
# Why alignment needs CREATION and not transfer: T242 AC1b transferred a real repo and proved the
# issue numbers survive intact — which preserves today's MISALIGNMENT (25 offsets, -41..+204). A
# virgin counter is the only way to reach T<n> == #<n>, so the tracker is a new code-free repo.
#
# `--offline` skips the gh identity probe. Pass `--json` for the machine form.
org-migrate-plan *args:
    @cd w0m-web && python3 project/scripts/org_migrate_plan.py {{ args }}

org-migrate-plan-test:
    @cd w0m-web && python3 project/scripts/tests/test_org_migrate_plan.py

# T242 AC4 — execute sequential issue creation into webomage/wom7board
org-migrate-execute *args:
    @cd w0m-web && python3 project/scripts/org_migrate_execute.py {{ args }}

org-migrate-execute-test:
    @cd w0m-web && python3 project/scripts/tests/test_org_migrate_execute.py

# T242 AC6 — enforce T<n> == gh_issue == #<n>
ticket-id-align *args:
    @python3 scripts/ticket_id_align_check.py {{ args }}

ticket-id-align-test:
    @python3 scripts/tests/test_ticket_id_align.py

# T242 AC8 — close open issues in legacy tracker repo
close-legacy-tracker-issues *args:
    @python3 scripts/close_legacy_tracker_issues.py {{ args }}

close-legacy-tracker-issues-test:
    @python3 scripts/tests/test_close_legacy_tracker_issues.py

# T248 AC4 — prove `db-migrate` fails when it applies nothing it was asked to apply.
# Two halves. The static half needs nothing and pins AC2's plumbing (config.toml reads the
# variable; exactly one recipe sets it false) plus the verdict function and its mutation test.
# The live half proves the CLI STILL reports success while a migration is pending — `--dry-run`
# from a throwaway workdir, so it applies nothing and never touches supabase/migrations.
# Run without secrets and the live half SKIPS and says so; it is not a pass.
# 🔴 NOT named `db-migrate-test`: the agent deny-list entry `db-migrate*` is a GLOB, so it
# shadows the probe of the very recipe it protects — measured, the first run was refused. A
# safety rule that also blocks the test of the thing it guards is how a gate goes unrun.
migration-guard-test:
    @cd w0m-api && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 ../w0m-web/project/scripts/tests/test_db_migrate.py

# T246 AC1 — the public consultant chat, probed the way a visitor hits it: anonymous, with a real
# question, asserting an ANSWER rather than a status. Nothing did this before, which is how a 100%
# outage on the client funnel's front door went unnoticed while two anon scenarios on the same
# endpoint stayed green — both of them asserting REJECTIONS.
# Hits production directly (w0m-consultant is verify_jwt = false), so no dev server and no
# Supabase needed. 🔴 Expected RED until T246's migration is applied and w0m-consultant
# redeployed; that red IS the probe demonstrated failing before the fix.
# 🔬 Named `-check`, not `-probe`, on purpose: `suites-drift` keys on names ending -test/-check,
# and the first draft of this recipe was called `public-chat-probe` — which the gate could not see,
# so it would have depended on me remembering to register it. Conform to the matcher instead of
# relying on memory. (T247 ①, one more instance.)
public-chat-check:
    @cd w0m-web && env -u SERVICE_ROLE_KEY -u SUPABASE_SERVICE_ROLE_KEY -u PUBLIC_SUPABASE_URL -u SUPABASE_URL \
      gauge run specs/api/056-w0m-consultant-api.spec

# Weekly toolchain maintenance: refresh the outdated cache (so pre-push can warn instantly) then
# apply the safe auto-upgrades with smokes. Run by hand weekly, or schedule via launchd (see
# w0m-web/docs/DEPS-ALIGNMENT.md §Weekly). Prod/cloud/non-brew tools are report-only (never touched).
# Install / inspect / remove the LaunchAgents declared in w0m-web/project/launchd/schedules.jsonc.
# `just tools-schedule` installs+loads · `--status` reports · `--remove` unloads and deletes.
#
# 🔑 Exists because `auto: patch` in tools-policy.json was a CLAIM: nothing ran `tools-weekly`, so
# the outdated cache sat 20 days stale (measured 2026-08-10) and 12 updates piled up — including
# the infisical bump that printed an upgrade notice into the middle of a production deploy.
# Source of truth is JSONC (owner preference); the XML plist is GENERATED, never hand-written.
tools-schedule *args:
    @python3 scripts/launchd_schedule.py {{ if args == "" { "--install" } else { args } }}

# Weekly code↔SCHEMA reconciliation. These two gates cannot live in a push hook: both query the
# LIVE database (11.2s and 4.6s measured, plus network), and both answer a question that changes
# when the DATABASE changes rather than when the push does — a migration applied from another
# machine drifts them with no commit here at all. A push gate would be slow AND would still miss
# the event it exists to catch.
#   callsite-drift  — every `.from('<table>')` vs the live catalog (ghost / unqualified /
#                     misqualified / unreachable). This is the T69 class: `gamification` had
#                     nspacl = NULL for three months and ~50 call sites were dead the whole time.
#   lookup-index    — every column matched on vs the indexes that exist. Gates ONLY on the
#                     correctness class (`.maybeSingle()` with no unique constraint = a latent
#                     500); UNBACKED is reported and does not fail.
# Advisory by design: it reports, it does not block anything, and its output is the log.
schema-weekly:
    @echo "→ call sites vs the live catalog..."
    -@cd w0m-web && python3 project/scripts/call_site_schema_drift.py
    @echo "→ lookup columns vs the indexes that exist..."
    -@cd w0m-web && python3 project/scripts/lookup_index_gate.py
    @echo "→ offline suite tier — 181s, the tier no push hook can afford..."
    -@just test

tech-debt:
    #!/usr/bin/env bash
    set -uo pipefail
    base=.
    total=0
    for r in w0m-web w0m-api w0m-cf w0m-ext; do
        [ -d "$base/$r" ] || continue
        # T406 — `--no-pager` and `LC_ALL=C` are both load-bearing. Without the first, an
        # agent shell that gets a tty hangs on `less` until its own timeout, then dumps
        # everything at once. The second is a measured 2.3x on w0m-web (0.282s -> 0.123s):
        # byte matching instead of UTF-8 collation. `check-guardrails` already knew the
        # first half of this; this call site did not.
        hits=$(cd "$base/$r" && LC_ALL=C git --no-pager grep -nEw 'TODO|FIXME|HACK' -- \
                 '*.ts' '*.tsx' '*.svelte' '*.astro' '*.mjs' '*.cjs' '*.py' 2>/dev/null \
               | grep -vE 'node_modules|/dist/|\.wrangler|\.generated|/reports/|graphify-out' || true)
        n=$(printf '%s' "$hits" | grep -c . || true)
        total=$((total + n))
        [ "$n" -gt 0 ] && { echo "── $r ($n)"; printf '%s\n' "$hits" | sed 's/^/   /'; }
    done
    echo "── $total occurrence(s) in tracked source"
    echo "   Decided debt → w0m-web/TECH-DEBT.md"

# One deploy version across nested `just` processes (T431 run 7) — no deploy is run.
deploy-version-inherit-test:
    @python3 -m pytest scripts/tests/test_deploy_version_inherit.py -q -p no:cacheprovider

# lexicon-lint: verify docs/gamification/09-naming-lexicon.md matches the live schema (roles/tables).
lexicon-lint:
    @sh -c 'command -v infisical >/dev/null && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-web/project/scripts/lexicon_lint.py || python3 w0m-web/project/scripts/lexicon_lint.py'

# OpenSpec CLI (spec-driven dev) — real tool = @fission-ai/openspec, pinned in w0m-web devDeps
# (the bare `openspec` npm name is a dead placeholder). Passthrough: `just openspec list`,
# `just openspec validate <id> --strict`, `just openspec show <id>`, etc.
openspec *args:
    @cd w0m-web && pnpm exec openspec {{ args }}

# Validate an OpenSpec change strictly. `just openspec-validate <change-id>` (omit id = all changes).
openspec-validate change="":
    @cd w0m-web && pnpm exec openspec validate {{ change }} --strict --no-interactive

# skill: w0m skills governance CLI over `npx skills` (T127). Manifest + lockfile live in THIS
# project's .w0m/. e.g. `just skill list`, `just skill check`, `just skill add <id>`.
skill *args:
    @cd w0m-skills && pnpm exec tsx w0m_skill.ts --project "{{ invocation_directory() }}" {{ args }}

# skills-typecheck: type-check the w0m-skills TS toolchain (skills.ts, w0m_skill.ts, scripts/*.ts).
# Alias for `pnpm run typecheck` there; run before committing skills-subsystem changes (T127).
skills-typecheck:
    @cd w0m-skills && pnpm run typecheck

# Regression proof for the skills subsystem — 69 tests, all three files named explicitly (a `tests/*`
# glob exits 0 with ZERO tests when it matches nothing). w0m_skill.test.ts covers the governance CLI
# (T127 Phase 2): non-vacuous empty check, warn-on-unmanaged vs block-on-tamper, tamper below
# SKILL.md, the 4 Phase-1 drift classes, legacy-path/dangling detection, bare-name rejection, honest
# provenance. skills_sync.test.ts covers the T149 sync SELECTION rule: the manifest decides, an
# undeclared canonical w0m* skill is NOT installed, and every wrong-set path (missing/empty bootstrap,
# unreadable manifest, empty canonical source) fails loudly instead of degrading.
# skills_version.test.ts covers the T131 AC3/AC4 stamp: provenance decides who gets stamped, and the
# version moves with the CONTENT (an edit after stamping is a finding).
# Skill security audit (T127 AC7). A skill is INSTRUCTIONS AN AGENT FOLLOWS, so its prose is the
# risk surface — measured 2026-07-27, only 1 of 83 installed skills ships executable code at all, so
# a script-scanner would be near-vacuous. Scans for credential paths, instruction-override,
# gate-bypass, remote-exec and exfil patterns, EXCLUDING prohibitions (a skill that says "never use
# --no-verify" documents the rule, it does not break it). `--root=<dir>` to audit a consumer tree.
skill-audit *args:
    @cd w0m-skills && pnpm exec tsx skill_audit.ts {{ args }}

# MCP / network exposure inventory (T154 AC3-AC5). Answers three questions in order: what is
# listening (and owned by whom), is it USABLE without credentials, and what would that get you.
# Scope is the HOST, not just w0m — the 2026-07-27 incident was a non-w0m listener, and an
# inventory that stops at your own ports only tells you what you already knew.
# 🔴 ENUMERATE ONLY: it calls `initialize` and `tools/list`, never a tool. A monitor that invokes
# `edit` to see whether it can is itself the breach.
# Exit 1 = an MCP surface served tools/list with no credentials. Exit 2 = the sweep enumerated
# nothing, which is a broken probe, not a clean host.
mcp-exposure *args:
    @python3 scripts/mcp_exposure.py {{ args }}

# The exposure RATCHET (T154 AC7) — the host's exposure may shrink, never grow. Different question
# from `mcp-exposure`, which is why it is a different recipe: that one asks "is anything open right
# now?" and is permanently red for a container that is not ours; this one asks "did it get WORSE
# than what we declared?" A permanently-red gate gets muted, so the open findings are recorded as
# `known-open` in project/mcp-exposure-baseline.json and pinned — they may not gain a tool, a wider
# bind, or LAN reachability. ⚠️ NOT a pre-push hook (T154 AC6): these are host facts that change
# when a desktop app launches, not when code is pushed.
# `--save` locks in an improvement on a DECLARED surface; accepting a NEW one is a human edit with
# a written reason — a ratchet that auto-accepts what it finds ratifies the breach it exists to catch.
# Exit 1 = exposure grew. Exit 2 = broken sweep / malformed baseline.
mcp-ratchet *args:
    @python3 scripts/mcp_ratchet.py {{ args }}

# Regression proof for the exposure ratchet — fixture snapshots, never the network (T154 AC7).
mcp-ratchet-test:
    @python3 scripts/tests/test_mcp_ratchet.py

# T90 AC9: Verify platform adapter decoupling and integrations IA
platform-decoupling-check:
    @cd w0m-web && python3 project/scripts/platform_adapter_decoupling.py

platform-decoupling-test:
    @cd w0m-web && pytest project/scripts/tests/test_platform_adapter_decoupling.py

# T155: Upwork sync health test
upwork-sync-health-test:
    @cd w0m-web && pytest project/scripts/tests/test_upwork_sync_health.py

# T535 AC5: is the Upwork feed fresh? The freshness lines of the T155 gate only, live (read-only). Exits 1 when stale, failing or unmeasurable. Run by the full preflight.
upwork-freshness:
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-web/project/scripts/upwork_sync_health.py --freshness-only

# T539 AC3: load the Upwork data files into contracts, platform_rooms and platform_messages. A DRY RUN by default (read-only at the database); add --apply to write.
# Usage: just upwork-loader --profile-id <uuid> [--apply] [--legs contracts,rooms,messages]
upwork-loader *args="":
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-web/project/scripts/upwork_loader.py {{ args }}

# T539 AC3: the loader against a throwaway Postgres (needs the Homebrew PostgreSQL binaries and psycopg)
upwork-loader-test:
    @cd w0m-web && python3 -m pytest -q -p no:cacheprovider project/scripts/tests/test_upwork_loader.py

# T468: load the Upwork MCP sync data into the upwork mirror schema. A DRY RUN by default; add --apply to write.
# Usage: just upwork-mirror-loader [--apply] [--profile-id <uuid>]
upwork-mirror-loader *args="":
    @infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 w0m-web/project/scripts/upwork_mirror_loader.py {{ args }}

# T468: the mirror loader unit tests against a throwaway Postgres
upwork-mirror-loader-test:
    @cd w0m-web && python3 -m pytest -q -p no:cacheprovider project/scripts/tests/test_upwork_mirror_loader.py

# T539: the owner-run Upwork scripts (sync rooms and messages, the two shape probes, the vault pages, the schema probe, the OAuth spike), the server-side allowlist guard and the rule for which data files git may hold
upwork-laptop-scripts-test:
    @cd w0m-web && python3 -m pytest -q -p no:cacheprovider project/scripts/tests/test_upwork_messages_probe.py project/scripts/tests/test_upwork_lists_probe.py project/scripts/tests/test_upwork_mcp_sync_rooms.py project/scripts/tests/test_upwork_vault_conversations.py project/scripts/tests/test_upwork_data_tracking.py project/scripts/tests/test_upwork_schema_probe.py project/scripts/tests/test_upwork_mcp_spike.py project/scripts/tests/test_upwork_mcp_call_sites.py

# T543: the project-manager migration's functions run against a throwaway Postgres (needs the Homebrew PostgreSQL binaries) and its policies do not widen hats
t543-project-manager-rpcs-test:
    @cd w0m-web && python3 project/scripts/tests/test_t543_project_manager_rpcs.py

# Regression proof for the AC checkbox parser the sdlc ranking depends on. T125 reported
# **4/4 = 100%** while genuinely blocked because the parser saw only [x] and [ ]; this pins all
# four states so a false green cannot come back.
ac-progress-test:
    @python3 scripts/tests/test_ac_progress.py

# Is each VENDORED skill complete? (T128) Upstream skills defer detail to companion files, so a
# SKILL.md-only copy imports the index and drops the content — invisibly, since a link to a missing
# file renders as prose. Two classes, neither implying the other: A (default, offline) the skill's
# own text points at a companion that is not there; B (`--upstream`, needs gh) upstream ships files
# under the skill's dir that were never copied. Run BOTH before calling a vendoring complete —
# marketingskills keeps companions in a shared repo-root `tools/` tree that B cannot see, and
# `webapp-testing`'s missing files are linked by nothing, so A cannot see them.
skills-vendor-audit *args:
    @cd w0m-skills && pnpm exec tsx scripts/audit_vendoring.ts --project ../w0m-web {{ args }}

skill-test:
    @cd w0m-skills && pnpm run skill-test

# skills-version-check: gate. Every w0m-native canonical skill carries a conforming, CURRENT version
# — current meaning the recorded content hash still matches, so a skill edited without a re-stamp is
# a finding rather than a version that quietly stops meaning anything (T131 AC3/AC4). Provenance
# comes from w0m-skills/skills-registry.json: `imported` skills keep UPSTREAM's version and are
# never stamped, `unresolved` blocks. Verify-only, like state-check — it never rewrites a SKILL.md.
# Exit 1 = findings, 2 = policy/config error. Distinct from `version-check`, which polices the
# ESTATE's release-version producers; this one polices the skill corpus.
skills-version-check:
    @cd w0m-skills && pnpm run version:check

# skills-version-stamp: re-stamp every w0m-native canonical skill whose content moved. Idempotent —
# an unchanged skill is not re-versioned, so this does not churn 39 files per run. Pass names to
# scope it: `just skills-version-stamp torvalds`. Run `just skills-sync` afterwards, or the active
# copies in w0m-web drift from canonical.
skills-version-stamp *args:
    @cd w0m-skills && pnpm exec tsx version.ts stamp {{ args }}

# skills-install-plugin: symlink w0m-skills as a machine-wide Gemini plugin (idempotent).
skills-install-plugin:
    @cd w0m-skills && pnpm exec tsx scripts/install.ts

# skills-plugin-package: generate and update .claude-plugin/plugin.json and plugin.json from canonical skills (T209).
skills-plugin-package *args:
    @cd w0m-skills && pnpm exec tsx scripts/package-plugin.ts {{ args }}

# skills-plugin-check: verify .claude-plugin/plugin.json and plugin.json match canonical skills with zero drift (T209).
skills-plugin-check:
    @cd w0m-skills && pnpm exec tsx scripts/package-plugin.ts --check

# skills-plugin-verify: verify cross-client loading across Claude Code, Claude App, Antigravity, and OpenCode (T209).
skills-plugin-verify *args:
    @cd w0m-skills && pnpm exec tsx scripts/verify-cross-client.ts {{ args }}

# skills-plugin-lint: validate plugin manifest against schema with explicit skill enumeration (T209).
skills-plugin-lint *args:
    @cd w0m-skills && pnpm exec tsx scripts/lint_plugin.ts {{ args }}

# skills-install-generic: install the PORTABLE skill set into a client project (T110 AC5).
#
# The generic set is defined by `w0m-skills/skill-portability.jsonc`, and the installer DERIVES each
# skill's scope from its content before trusting that file — a disagreement aborts the install
# rather than shipping a skill nobody classified. w0m-bound skills are withheld, and no `.w0m/` is
# created (that is what switches on the enforced gates).
#
# ⚠️ Never run this against a wom7* repo — those use the w0m-sdlc-* gates and already hold the full
# set. It refuses a target that has `.w0m/sdlc.json` unless `--force`.
#
#   just skills-install-generic ~/Projects/_self/1945/1945socialclub.com --dry-run
skills-install-generic *args:
    @cd w0m-skills && pnpm exec tsx scripts/install_generic.ts {{ args }}

# skills-install-generic-test: red probes for the installer's refusals (T110 AC5). A gate nobody
# has seen fail is not a gate — each probe builds a fixture that MUST be refused.
skills-install-generic-test:
    @cd w0m-skills && pnpm exec tsx tests/install_generic.test.ts

# skills-score: scaffold a Score (score.dev/v1b1) intent file. Pass through flags, e.g.
# `just skills-score --name my-service --resources postgres,s3`.
skills-score *args:
    @cd w0m-skills && pnpm exec tsx scripts/generate_score.ts {{ args }}

# deno-check: type-check every edge function (T23 AC-4). Clean as of 2026-07-17 (55/55 pass);
# run this to keep it that way / before wiring deno-check into the deploy gate.
deno-check:
    #!/usr/bin/env bash
    set -euo pipefail
    cd w0m-api/supabase/functions
    # `deno check` is SILENT on success, which made this suite unreadable to run_suites: a run that
    # checked 60 functions and one that checked none printed identically (nothing). Owner 2026-08-16:
    # "if you can't parse checks from a tool then increase verbosity there" — fix the source, not
    # the reader. Say what was checked, in the house ✅ style, so the count is a fact rather than an
    # inference.
    files=$(ls -d */index.ts 2>/dev/null | wc -l | tr -d " ")
    deno check */index.ts
    echo "✅ deno-check — ${files} edge function entrypoint(s) type-checked, 0 error(s)"

# deno-test: unit tests for the edge stack (`supabase/functions/**/*.test.ts`). Introduced 2026-07-25
# with T99(d)'s `_shared/crypto.ts` — the edge stack had NO unit tests before, only `deno-check`.
# Registered as the `edge` stack's `test` role in ../w0m-web/project/stacks-policy.json (T130: a
# stack tool needs the recipe AND the registry entry). `--allow-env` only: these tests read key
# material from the environment and must never reach the network or the filesystem.
deno-test:
    #!/usr/bin/env bash
    set -euo pipefail
    cd w0m-api/supabase/functions
    # Same reason as deno-check: emit a countable summary rather than leaving the runner's own
    # format to be guessed at downstream.
    mapfile -t suites < <(find . -name '*.test.ts' -not -path './node_modules/*')
    deno test --allow-env "${suites[@]}"
    echo "✅ deno-test — ${#suites[@]} edge-function test file(s) passed"

# typecheck-worker: type-check the Cloudflare Worker in src/ (wrangler `main: src/index.ts`). T105 —
# src/ was excluded from tsconfig.json (only tests/+scripts/), so it had ZERO type checking. Regens
# the runtime types first (`wrangler types` → Env tracks wrangler.jsonc), then `tsc --noEmit`.
# Needs pnpm's node_modules (a stray `deno install` at the w0m-api root breaks resolution — pnpm is
# the worker's package manager; deno is only for supabase/functions/).
typecheck-worker:
    @cd w0m-api && pnpm exec wrangler types >/dev/null && pnpm exec tsc --noEmit -p tsconfig.worker.json

# Type-check the Python that implements this estate's gates (T188 / T448 AC6).
# Scope is declared in w0m-web/mypy.ini: `project/scripts/*.py`, TOP LEVEL ONLY (201 files; was 44 at T188).
# Note: mypy.ini does not set `disallow_untyped_defs` or `check_untyped_defs`; untyped defs and untyped
# JSON loads across `w0m-web/project/scripts/*.py` and root `scripts/*.py` are ratcheted downward by
# `just py-typing-check` (T448).
# T376 — Run Python tests via modern uv test suite (pytest runner)
py-test *args:
    @cd w0m-web && uv run pytest {{ args }}

# T376 — Run Python tests in parallel using pytest-xdist multi-core acceleration
py-test-fast *args:
    @cd w0m-web && uv run pytest -n auto {{ args }}

# T376 — Run Python tests with coverage reporting
py-test-cov *args:
    @cd w0m-web && uv run pytest --cov=project/scripts --cov-report=term-missing {{ args }}

# T376 — Run a specific Python test file or pattern via uv pytest
py-test-file file *args:
    @cd w0m-web && uv run pytest {{ file }} {{ args }}

# T188 / T448 AC6 — w0m-web/project/scripts, top level (201 files; was 44 at T188). Scope + rationale: w0m-web/mypy.ini.
py-typecheck-web *args:
    @cd w0m-web && mypy {{ args }}

# T189 / T448 AC6 — w0m-api/scripts, top level (49 files; was 36 at T189). Scope + rationale: w0m-api/mypy.ini.
# Split per repo ON PURPOSE: each repo's pre-commit hook calls its OWN recipe, so a w0m-web
# commit is never blocked by a w0m-api finding (and vice-versa) — the not-path-scoped complaint
# recorded against typecheck-ratchet in D6. `py-typecheck` fronts both for `just test`.
py-typecheck-api *args:
    @cd w0m-api && mypy {{ args }}

# Regenerate the w0m status dashboard (docs/STATUS-DASHBOARD.html) from TASKS.md + ROADMAP.md.
status-dashboard:
    @cd w0m-web && python3 project/scripts/gen_status_dashboard.py

# sync-tickets: mirror ticket .md frontmatter → GitHub Issues + the "w0m Delivery" project board.
# Source of truth = project/tickets/*.md (built from frontmatter, not a manual manifest); GitHub is
# the mirror. Idempotent (matches by "T<id> —" title prefix). ~2min full run. Also fires
# non-blocking in the background on pre-push when a push touches tickets. `--dry-run` to preview.
# One entry point for the whole toolset's state (T149 AC4). COMPOSES the existing checks — queue,
# stacks, skills, state, toolchain — and re-implements none of them. Each child reports its own exit
# code, duration and last line, so a failure is attributable to the check that failed rather than to
# an aggregate. Budget measured 2026-07-27: ~16.4s. ⚠️ Deliberately NOT wired into any hook: its
# children already run at pre-commit/pre-push, so hooking it would run them twice.
toolset-status *args:
    @python3 scripts/toolset_status.py {{ args }}

# Install/refresh the standard hook stack in every wom7* repo, including the run-logging wrapper.
# ⚠️ RE-RUN THIS after any `pre-commit install`, a fresh clone, or `pre-commit autoupdate`:
# `.git/hooks/` is NOT versioned, so the wrapper is re-applied by the installer rather than stored.
# `just hooks-logged` reports which repos currently carry it.
hooks-install:
    @python3 scripts/install_hooks.py

# Which repos currently have the run-logging wrapper installed? Answers the question the unversioned
# .git/hooks directory cannot: a repo can silently lose it to a re-install and nothing would say so.
hooks-logged:
    @for r in w0m-api w0m-skills w0m-cf w0m-ext w0m-sec w0m-mlx/w0m-mlx; do \
      f="$r/.git/hooks/pre-commit"; \
      if [ ! -f "$f" ]; then printf "  %-18s ❌ no hook\n" "$r"; \
      elif grep -q "w0m hook-log wrapper" "$f"; then printf "  %-18s ✅ wrapped\n" "$r"; \
      else printf "  %-18s ⚠️  NOT wrapped — run \`just hooks-install\`\n" "$r"; fi; done; \
    for h in pre-commit pre-push; do \
      f="w0m-web/.husky/$h"; \
      if grep -q "hook_log_wrap" "$f" 2>/dev/null; then printf "  %-18s ✅ wrapped (husky %s)\n" "w0m-web" "$h"; \
      else printf "  %-18s ⚠️  NOT wrapped (husky %s)\n" "w0m-web" "$h"; fi; done

# Show the last git-hook run — `just hook-log` for the full output, `just hook-log 5` for the last
# five summaries. Exists because the hooks logged NOTHING: a failure printed to a terminal and
# vanished, so finding WHICH gate blocked a push meant re-running the whole 285-line chain.
# ⚠️ The body is a SCRIPT, not an inline one-liner — the first version was `python3 -c` with escaped
# quotes and died with a SyntaxError on its first run. Tool ladder, as written in CLAUDE.md.
hook-log n="":
    @python3 scripts/hook_log.py {{ n }}

# What is in the repos that NO stack claims (T147 AC3)? The INVERSE of `just discovery`, and that
# is the point: discovery walks the REGISTRY and asks whether each declared thing is real, so it
# can only find what the registry already knows to look at — T149's organising finding verbatim.
# This walks the CODE and asks what nobody declared. First run: 524 uncovered code files against a
# registry reporting fully green, incl. 228 supabase/migrations and packages/ui (the live DS).
# ⚠️ 'uncovered' means NO STACK DECLARES THE PATH — not 'ungated'; a workspace-wide recipe may
# still reach these. Reports only, never gates (AC5). `--all` also lists the prose/asset groups.
coverage-scan *args:
    @python3 scripts/coverage_scan.py {{ args }}

# Prove the coverage scan REFUSES on every empty input (T147 AC6) — its arithmetic is
# covered/total, so an empty registry reports 100% uncovered and an empty corpus reports 0/0, and
# both render as confident numbers. Mutation-checked: reverting `_group` to a path-prefix, or
# deleting the zero-files guard, each turns the suite red.
coverage-scan-test:
    @python3 scripts/coverage_scan_test.py

# Prove the preflight's checks go RED (T147 AC6) — both that a real fault is caught AND that an
# EMPTY input set refuses instead of passing. The second is the one this estate keeps shipping
# without: `0 managed skill(s) match the lockfile ✓` is the shape. Mutation-checked — deleting the
# zero-servers guard makes the suite fail, so the cases are load-bearing, not decorative.
preflight-test:
    @python3 scripts/preflight_test.py

# Hook-layer conformance (T149 AC3 + T150 AC3b) in ONE check, because both describe the same audit
# of the same files. Verifies every declared gate phase is actually wired to a hook that runs the
# `just` recipe (not a raw npx/deno/tsc duplicate), and that exactly one sanctioned forge call site
# exists. Currently RED with 4 real findings — manual until they are resolved, then promote to
# pre-push.
# Type-error RATCHET for the apps that cannot pass `astro check` yet (join 12, job 107 — T149 /
# TECH-DEBT D6). The count may FALL, never RISE. Verify-only: an improvement is reported, and you
# lock it in with `--save`; the check never rewrites the baseline itself. ~26s (join 6.7 + job 19.7).
# An app that reaches 0 belongs in `just typecheck` instead — gated at zero, not ratcheted.
typecheck-ratchet *args:
    @cd w0m-web && python3 project/scripts/typecheck_ratchet.py {{ args }}

hooks-check:
    @python3 scripts/hooks_check.py

# T228 AC6b — what makes a ticket a PARENT. The criterion was a TITLE STRING plus a member table,
# which measured how someone worded a heading rather than whether the relationship exists: T149
# (8 members) and T184 (7) were invisible to both `ticket-graph` and `sync-subissues`.
# 🔴 Dropping to "declares a member table" over-matches — T239's table is `| ticket | issue |
# reason | its own words |`, i.e. tickets closed as not-planned, and a member-count rule adopts
# them as children. RECIPROCITY separates them: one declared member naming the parent back.
# ⚠️ `ticket_graph.py` and `sync_subissues.py` must apply the SAME rule — two consumers disagreeing
# about what a field means is the whole subject of T228.
subissue-parents-test:
    @python3 scripts/tests/test_subissue_parents.py

# T198 AC7 — is the office/capability axis wired, and is it in a state that LIES?
# Measured 2026-08-27: 10 offices, 38 capabilities, 48 grants — and NO table links a person to an
# office, no RLS policy reads the axis, no function reads it. `blueprint.publish` is held by
# design.lead and talent.trainer and is unexercisable, but so are the other 47 grants: it is not a
# policy gap on one verb, it is an axis with no subjects and no readers.
# 🔴 The gate does NOT fire on the inert state, which is declared. It fires on HALF-WIRED — people
# assignable to offices while nothing reads the assignment — because that is the configuration
# indistinguishable from working. Reads the LIVE database.
office-axis-check *args:
    @cd w0m-web && python3 project/scripts/office_axis_check.py {{args}}

# 5 red probes over the classifier — the HALF-WIRED case is the one that must fire.
office-axis-check-test:
    @cd w0m-web && python3 project/scripts/office_axis_check.py --selftest

# T94 AC5 — is `connections` a faithful registry of the two stores it unifies?
# The old tables stay AUTHORITATIVE while their 12 call sites migrate, and two bridge triggers keep
# the registry in step. That has one failure mode and it is silent: the bridge stops firing, the
# registry keeps answering, and every later check measures a stale copy — nothing else notices,
# because every reader is still on the old tables. Compares row by row, not by count.
# 🔴 Token values are compared inside SQL and never selected out.
connections-registry-check *args:
    @cd w0m-web && python3 project/scripts/connections_registry_check.py {{args}}

# T94 AC6 Task 2.2 — test suite and red probe for connections_registry_check
connections-registry-test:
    @cd w0m-web && python3 project/scripts/tests/test_connections_registry_check.py

# Write `just tasks`' derived fields into every ticket's frontmatter, so Obsidian can sort and
# filter on them — `project/tickets/` is inside the w0m-web vault, but Bases reads FRONTMATTER only,
# and AC progress, blockers and the ranking score are all computed. Entry point: project/TICKETS.md
# and project/Tickets.base.
# 🔴 A computed value in a file rots immediately, so this is generate-plus-gate, the same shape as
# state-save/state-check. `--check` fails when any file disagrees with the live queue.
# ⚠️ Keys are namespaced `x_` and the hand-declared `blocked_by` is never touched. Frontmatter is
# edited line by line, never round-tripped through a YAML dumper — that is how tickets.json got
# every non-ASCII character re-encoded once before.
tickets-frontmatter-sync *args:
    @python3 scripts/tickets_frontmatter_sync.py {{args}}

# The freshness gate for the above.
tickets-frontmatter-check:
    @python3 scripts/tickets_frontmatter_sync.py --check

# T94 AC3 — type-check w0m-cf. The `cf` stack declared ONLY a `deploy` command until
# 2026-08-28, so nothing verified its TypeScript: a type error reached production or it did not,
# and no gate could tell you which. Offline and fast (tsc --noEmit, no network, no wrangler).
cf-typecheck:
    @cd w0m-cf && pnpm exec tsc --noEmit -p tsconfig.json && echo "  [OK] cf-typecheck"

# The Connector-interface invariant tests. 🔴 Uses the workers vitest pool, which opens a REMOTE
# connection, so this is `live` and cannot run on a machine without network — unlike cf-typecheck.
cf-test:
    @cd w0m-cf && pnpm exec vitest run

# Full T23 loop: rebuild graph, census debt, lint the lexicon, audit spec drift, refresh dashboard.
# codegraph-sync: incremental re-index of the code knowledge graph (~seconds). Fast enough for
# the pre-push hook; also part of the full knowledge loop.
codegraph-sync:
    @cd w0m-web && codegraph sync

# Full knowledge loop (manual): includes `graph ".."` — whole-monorepo graphify (minutes, 100% CPU).
knowledge: (graph ".") lexicon-lint spec-drift codegraph-sync status-dashboard


# Fast knowledge refresh (used by the post-deploy hook): the quick engines only — NO heavy
# graphify. codegraph-sync (~3s) + lexicon-lint + status-dashboard. Called from the root justfile's
# `_post-deploy-knowledge`; stays here beside `knowledge` because its steps serve the repo hooks.
knowledge-light: codegraph-sync lexicon-lint status-dashboard


# Weekly toolchain watch (T106): has oxc shipped native .astro formatting yet?
# If it has, oxfmt can replace prettier for .astro and we drop a formatter + a plugin.
# Until then prettier + prettier-plugin-astro handles .astro (see w0m-web/.prettierrc.json).
check-oxfmt-astro:
    @python3 "{{ W0M_ROOT }}/w0m-web/project/scripts/check_oxfmt_astro.py"

# Where does symbol/concept A connect to B? (graphify relationship path, w0m-web)
ask-path a b:
    @cd w0m-web && graphify path "{{ a }}" "{{ b }}"

# What breaks if I change X? (reverse traversal)
ask-affected x depth="2":
    @cd w0m-web && graphify affected "{{ x }}" --depth {{ depth }}

# Alias — the SDLC contract names this `check`
check: typecheck


# Static analysis (oxlint) — ADVISORY, by decision 2026-07-22.
#
# The BLOCKING gate is the pre-commit hook, which lints STAGED files: new and touched code must
# be clean, so the backlog cannot grow. This whole-repo run reports that pre-existing backlog
# (174 errors as of 2026-07-22, see TECH-DEBT) and is expected to exit non-zero.
#
# Why it is not blocking yet: clearing 174 today means either editing ~100 files in one pass
# (churn, and most of it is test scaffolding) or disabling `no-unused-vars` (which would lose the
# signal that finds real dead code — it caught an unused import and three dead variables here).
# Ratchet instead: the hook holds the line, the backlog burns down as files are touched.
#
# Convention: prefix a deliberately-unused parameter with `_` (argsIgnorePattern in .oxlintrc.json)
# rather than silencing the rule.
lint:
    @cd w0m-web && pnpm lint

# Unit tests (vitest)
# The JS unit suite alone. Was `just test` until 2026-08-02 — which meant `commands.test` in
# .w0m/sdlc.json ran ONE test while every Python gate suite ran only when named by hand, so the
# verify gate's own instruction produced a green run over ~110 checks that never executed (T160).
test-js:
    @cd w0m-web && ASTRO_TELEMETRY_DISABLED=1 DO_NOT_TRACK=1 pnpm test

# T503 — the deploy chain's order, pinned from the real recipe graph (`just --dump`), with a red probe for the old order.
deploy-chain-order-test:
    @python3 scripts/tests/test_deploy_chain_order.py

# T503 — the prepush tier of the suite registry (selection, validation, cap, raw-log hygiene).
run-suites-prepush-test:
    @python3 scripts/tests/test_run_suites_prepush.py

# T346 AC5 — Corporate verification, SSRF guard, and RFC/SAT blacklist test suite
corporate-verify-test:
    @cd w0m-web && python3 project/scripts/tests/test_corporate_verify.py

# T348 AC5 — Project types taxonomy and @mob mobile apps onboarding test suite
project-types-test:
    @cd w0m-web && python3 project/scripts/tests/test_project_types.py

# T431 — no *.test.ts under apps/*/src/pages (Astro ships every file there as a route).
no-tests-in-pages:
    @cd w0m-web && python3 project/scripts/tests/test_no_tests_in_pages.py

# T135 AC7 — prove the three repo-hygiene gates can FAIL. One harness, three entry points, because
# AC7 names the gates individually and `just docs-check-test` is what someone reaches for after
# touching docs-check. Runs against a throwaway fixture estate via W0M_HYGIENE_ROOT: proving these
# red on the real tree would mean COMMITTING a missing README, a `dotenv-load` in a tracked
# justfile, or a manifest without `private: true`. 19 `*-test` recipes existed and none covered
# these three, so a regression in their ability to fail was invisible — they would go on printing
# ✅ over a clean estate, which is exactly what they print when working.
hygiene-test:
    @python3 scripts/tests/test_repo_hygiene.py

# Aliases so each gate is discoverable by its own name (AC7 asks for these three).
docs-check-test: hygiene-test


secrets-check-test: hygiene-test


license-check-test: hygiene-test


annotations-doctor-test:
    @python3 scripts/tests/test_annotations_doctor.py

overrides-check-test: annotations-doctor-test


# T150 AC3b — prove the forge allowlist FIRES. Runs against a fixture estate via W0M_HOOKS_ROOT,
# because planting a `gh` call in a real hook means committing the violation the check prevents.
hooks-check-test:
    @python3 scripts/tests/test_hooks_check.py

# T131 AC5 — prove sdlc-doctor's versioning check FAILS. It delegates to `version-check` and
# `skills-version-check`, so this tests the WIRING (a failing gate becomes a doctor problem; a
# timeout becomes an explicit UNVERIFIED note, never silence). What those gates DETECT is proven
# by their own red probe, `just version-test` — stated so a green here is not mistaken for a
# proof of version conformance itself.
sdlc-versioning-test:
    @python3 scripts/tests/test_sdlc_versioning.py

# T165 task 1.3 — validate the canonical CV document and every rendered CV surface in one run.
# Two schemas, both required: `jsonresume.schema.json` (interchange) and `w0m-cv.schema.json` (the
# constraints JSON Resume declines to impose — measured, it accepts every x_* field as garbage and
# marks NO field required). The date rule is EXTRACTED from apps/web/src/content.config.ts rather
# than restated, so this cannot become the fifth parser holding its own copy of an anchor.
# Zero rendered files found is a FAILURE, not a pass. Pass --require-canonical once task 2.7 lands.
cv-validate *args:
    @cd w0m-web && python3 project/scripts/cv_validate.py {{ args }}

# T165 task 1.4 — prove cv-validate can FAIL, at the collection layer as well as the comparison
# layer. `state-doctor-test` passed for months while state_doctor.py matched 0 of 155 board rows,
# because it asserted the comparison and never the collection. Runs on fixtures; never mutates
# the real corpus.
cv-validate-test:
    @cd w0m-web && python3 project/scripts/tests/test_cv_validate.py

# T165 Phase 2 — build the canonical project/data/cv/resume.json FROM the corpus (AC1a: imported,
# never hand-authored). Joins the Upwork export to CV roles through the EXPLICIT alias table
# project/data/cv/company-aliases.json — measured 2026-08-06, only 1 of 13 company strings matched
# the export exactly, so fuzzy matching would be the primary path rather than a fallback.
# Conflicts are REPORTED to project/data/cv/conflicts.json, never silently resolved (R3); an owner
# clears one by adding a key to project/data/cv/resolutions.json. Pass --strict to fail on any
# open conflict. Re-runnable: two runs produce byte-identical output.
cv-import *args:
    @cd w0m-web && python3 project/scripts/cv_import.py {{ args }}

# T165 task 2.7/2.3 — prove the importer is idempotent, that it REFUSES to drop a role, and that
# the private CV's internal revision-notes block never reaches the generated document.
cv-import-test:
    @cd w0m-web && python3 project/scripts/tests/test_cv_import.py

# T165 task 3.1 — print the PUBLIC projection of the canonical CV: minus PII, minus every internal
# `x_*` field at any depth. Writes NOTHING, deliberately — task 3.2 says the leak gate must exist
# before any served-path write does, so the generators that write files (3.4/3.5) come after.
cv-public:
    @cd w0m-web && python3 project/scripts/cv_public.py

# T165 task 2.3 — the per-role CLAIMS UNION across every CV document. Not a prose parser: Phase 0.4
# measured 11 claims for one role across 6 documents with 3 living in NO single document, so an
# importer reading one source silently DELETES material. This collects every claim, clusters only
# clear duplicates (biased AGAINST merging — over-splitting is visible, under-splitting deletes),
# and names the claims attested by exactly one document. `--json` writes project/data/cv/claims.json.
cv-claims *args:
    @cd w0m-web && python3 project/scripts/cv_claims.py {{ args }}

# T165 task 2.3 — cross-checks the union against Phase 0.4's independently HAND-derived claim
# matrix: three claims must be private-only and three public-only. Two different methods agreeing
# is evidence; it also asserts no bullet is dropped and no wording lands in two clusters.
cv-claims-test:
    @cd w0m-web && python3 project/scripts/tests/test_cv_claims.py

# T165 task 3.2 / R7 — FAIL-CLOSED gate: no private value may appear on any served surface.
# Scans apps/*/public/** and the content collections, PDFs included (via pdftotext — the served CV
# downloads ARE PDFs, so the likeliest carrier is the one format a text scan skips). Refuses to
# report a pass when it cannot prove one: missing canonical, an absent `x_private` key, zero
# discovered surfaces, or any file it could not read all FAIL.
cv-leak-check:
    @cd w0m-web && python3 project/scripts/cv_public.py --check

# T165 task 3.2 — prove the gate goes RED. Seeds the private value into a fixture served tree in
# four spellings (canonical, digits-only, national, split across lines) and asserts each fails AND
# that a failing run wrote nothing. Never touches the real corpus.
cv-leak-check-test:
    @cd w0m-web && python3 project/scripts/tests/test_cv_public.py

# E2E / browser suite. Delegates to the existing `e2e` recipe (dev-server lifecycle + Gauge).
# Needs secrets — the gate wraps this in `infisical run`.
test-e2e: e2e


# Client-import baseline (T182 Phase 1 / AC1). Reads project/clients-policy.json and diffs every
# declared project's .w0m/sdlc.json against the estate contract, plus its instruction surface,
# skills governance, recipes and agent-memory sizes. READ-ONLY: never writes to a client repo
# (client repos are owner-write-only, T182 Phase 0/AC6). Output is a DIFF, not a judgement — which
# gap matters is the `client` profile (AC2) and its gate (Phase 7, `just discovery --enforce`).
# Hard-fails (exit 2) on registry integrity only: empty/single corpus, ambiguous estate, a missing
# root, or a root that is not the git repo ROOT. `--json` = machine surface, `--quiet` = table only.
client-inventory *args:
    @python3 scripts/client_inventory.py {{ args }}

# Is the published BridgeRoad VM image behind its inputs? (T295 AC5)
#
# Answers one question — would rebuilding produce a DIFFERENT image? — by comparing the guest-agent
# commit, the Packer template hash and the upstream cloud-image ETag against `published.json`.
# It never builds and never pushes, so it is safe to run anywhere.
#
# There is deliberately NO schedule behind this. GitHub Actions is dead on this account (100/100
# startup_failure since 2026-05) and the build is host-bound to Apple Silicon regardless, so a timer
# would rebuild unchanged bits at ~3 GB a run — the schedule-nobody-reads shape. A signal was the
# missing piece, not automation. Exit 0 current · 1 an input moved · 2 nothing published yet, and an
# unreachable upstream reports UNKNOWN rather than current, so offline never reads as an all-clear.
vm-staleness *args:
    @cd ~/Projects/_proj/bridgeroad/vm-seed && python3 staleness.py {{ args }}

# What exceeds the VM image retention policy? (T295 AC6b)
#
# Each published tag is ~3 GB in the registry and ~3 GB again in the local OCI cache once pulled,
# and nothing said who removed either — "all of them, forever" is the answer a system gives when
# nobody writes a different one down. Limits live in image-policy.json -> retention.
#
# 🔴 It NEVER deletes from the registry: that is outward-facing and irreversible, and a consumer
# holding a tag would lose the image under them, so remote pruning stays a human act and this only
# reports. `--apply` prunes the LOCAL cache only, which is re-pullable and therefore cheap to be
# wrong about. An unmeasurable registry counts as a finding, never as clean.
vm-retention *args:
    @cd ~/Projects/_proj/bridgeroad/vm-seed && python3 retention.py {{ args }}

# VM status and guest health supervisor (T296 / ROADMAP §13.11).
# Probes host Tart hypervisor state and guest agent responsiveness via virtio-serial RPC.
vm-status *args:
    @python3 scripts/vm_supervisor.py status {{ args }}

# Regression proof for `vm_supervisor` (T296): unit tests and diagnostic probes.
vm-supervisor-test:
    @python3 scripts/tests/test_vm_supervisor.py

# Is estate-root configuration versioned? (T294 AC4 — the probe that closes D32)
#
# D32 was "@wom is not a repo, so its config is versioned nowhere". Creating the repo and committing
# fifteen files fixes the files that existed that day and notices nothing about the next one — and
# unnoticed accumulation is how the first fifteen happened. This asks the standing question instead:
# is anything at the estate root neither tracked nor deliberately ignored?
#
# Exit 0 clean · 1 undecided files · 2 could not measure. A missing estate repo is exit 2 and reported
# as "D32 has returned in full", never as clean.
estate-config-check *args:
    @python3 scripts/estate_config_versioned.py {{ args }}

# Regression proof for `client-inventory` (T182 AC1): drives it on fixtures and asserts every
# integrity check is observed FAILING — the subdirectory trap (git -C answers about the enclosing
# repo), empty and single-project corpora, zero/two estates, a missing root, a malformed registry —
# plus that an import-directive CLAUDE.md is resolved by content rather than judged by byte count.
client-inventory-test:
    @python3 scripts/tests/test_client_inventory.py

# Active project identity probe (T300 AC2 / AC5): verifies effective git user.name, user.email,
# core.sshCommand, and GitHub CLI identity against project/clients-policy.json declarations.
project-identity-check *args:
    @python3 scripts/project_identity_check.py {{ args }}

# Regression proof for project-identity-check (T300 AC3): red probes for mismatched name, email,
# SSH transport command, gh accounts, unmeasurable absence states, and secret material.
project-identity-test:
    @python3 scripts/tests/test_project_identity.py

# The `client` profile gate (T182 AC2). Re-derives, from source, the profile's central claim:
# every key in project/client-profile.json names a gate whose recipe EXISTS and whose script
# provably READS that key — so a renamed gate or a deleted reader breaks the check instead of
# leaving the profile claiming enforcement it lost. Also asserts required+optional+excluded
# covers the estate contract exactly (no key quietly dropped), and that no required key has a
# fail-open gate. Reports dangling `$schema` refs in declared projects; `--enforce` blocks on them.
client-profile-check *args:
    @python3 scripts/client_profile_check.py {{ args }}

# Regression proof for `client-profile-check` (T182 AC2): every defect it claims to catch is
# observed caught — a key with no gate, a gate naming a missing recipe, a script that does not
# read its key, a required key with a fail-open gate, a contract key in no tier, an empty profile.
client-profile-test:
    @python3 scripts/tests/test_client_profile.py

# The installed-skill CATALOGUE (T182). Lists every agent skill installed across every declared
# project, with the estate's two settings resolved per skill: `managed` (project / excluded /
# unmanaged) and `sandboxed` (is the skill's SHIPPED CODE kept off the host). Recommendation is
# project-managed + sandboxed; deviations are reported and exit 0, `--enforce` blocks. Skills are
# executable instructions loaded into every agent session — a supply-chain surface — and this is
# the estate-wide view that per-repo `just skill check` does not give. Reads the policy path from
# `.w0m/sdlc.json -> skills.policy`, with NO fallback, so the declaration stays load-bearing.
skills-catalogue *args:
    @python3 scripts/skills_catalogue.py {{ args }}

# Regression proof for `skills-catalogue` (T182): asserts the settings are DERIVED not assumed —
# an unmanaged skill is flagged, a skill shipping runnable files without sandboxing is flagged, an
# override suppresses that only with a reason, user-scope skills are surfaced as unmanaged, and
# the catalogue refuses an empty corpus or a missing `.w0m/sdlc.json -> skills` block.
skills-catalogue-test:
    @python3 scripts/tests/test_skills_catalogue.py

# Agent-memory BOUNDS, per declared project (T182 Phase 5 / AC5) — the client-capable half of
# `state_surface`. `state_doctor` enforces that key for w0m only: it renders a managed block out of
# w0m's repo set and ticket queue and takes no --project. This measures what a client actually
# needs — are the agent-maintained memory files inside the bounds the project DECLARES — for every
# project in the registry. 🔴 An undeclared project is a FINDING, not a skip: T177 recurred
# precisely because nothing obliged a client to declare `state_surface`, so T174's retention fix
# had nothing to attach to. Measures only; rotation is lossy and stays deliberate. `--enforce` blocks.
state-bounds *args:
    @python3 scripts/state_bounds.py {{ args }}

# Regression proof for `state-bounds` (T182): asserts undeclared is reported rather than skipped,
# that an over-budget file is caught, that bounds are read from each project's OWN declaration,
# and that an empty candidate set or empty corpus errors instead of reporting health.
state-bounds-test:
    @python3 scripts/tests/test_state_bounds.py

# ONE command that runs every profile gate against a declared client (T182 Phase 7).
# `just client-check artemio` / `just client-check 1945 --json`. The gate list is DERIVED from
# project/client-profile.json — each required key names its own recipe — so the profile and this
# runner cannot drift. A gate the runner does not know how to invoke is a FAILURE, never a skip.
client-check *args:
    @python3 scripts/client_check.py {{ args }}

# T183 AC2–AC11 — Content-based Design System detector & contract gate (`claude-design`, `custom`, `docs`, `none`).
design-system-check *args:
    @cd w0m-web && python3 project/scripts/design_system_check.py {{ args }}

design-system-check-test:
    @cd w0m-web && pytest -q project/scripts/tests/test_t183_design_system_sdlc.py

# T118 AC1–AC6 — Content & blueprint deep-review + DS alignment audit gate.
content-blueprint-audit *args:
    @cd w0m-web && python3 project/scripts/content_blueprint_audit_t118.py {{ args }}

content-blueprint-audit-test:
    @cd w0m-web && pytest -q project/scripts/tests/test_t118_content_blueprint_audit.py

# T266 AC7 — does the first REAL managed client see their own rows, and ONLY their own?
# 🔴 RED ON PURPOSE until T266 AC2 links a person to the Artemio organisation: measured 2026-08-24,
# Artemio has zero rows anywhere in the product database. A probe that has only ever been green
# measures nothing (T198 AC8). Read-only — every actor probe runs inside BEGIN … ROLLBACK.
artemio-tenancy-probe:
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=dev --silent -- python3 project/scripts/artemio_tenancy_probe.py

# T313 AC6 — Artemio delivery roles, hats, and tenancy probe
artemio-roles-probe:
    @cd w0m-web && python3 project/scripts/artemio_roles_probe.py

# T314 AC4 — Aleksei non-admin member & delivery roles (PM, Tech Lead, Dev) verification probe
aleksei-member-probe:
    @cd w0m-web && python3 project/scripts/aleksei_member_probe.py

# AC6/AC11 — license audit + publication safety. Classifies first-party vs VENDORED before
# asserting anything: writing `license: UNLICENSED` into vendored third-party code would
# relicense work we do not own, and this estate contains exactly such a manifest.
# Transitive dependency-license audit (T135 AC6). Reads the licence set from `pnpm licenses list
# --json --prod` per workspace — never a vendored copy, which is stale on the next install — and
# tiers each SPDX expression: GPL/AGPL/SSPL/OSL FAIL outright (this estate is proprietary by owner
# decision); LGPL/MPL/EUPL/CDDL/EPL FAIL unless the package carries a written exemption with a
# reason (AC9); everything else is advisory. An `OR` expression elects its most permissive branch,
# an `AND` binds every term. Policy: `project/deps-policy.json -> licenses`.
# ⚠️ `--prod` measures DEPENDENCY TYPE, not bundle membership — see the policy's `_scope_limit`.
dep-licenses-check:
    @python3 scripts/repo_hygiene.py dep-licenses

# Red probes for `dep-licenses-check` (T135 AC7) — part of the shared hygiene harness.
dep-licenses-check-test: hygiene-test


# Regression proof for the versioning gate (T131, T130-style): drives the real checker over fixture
# policies and asserts exit codes both ways — red on a reintroduced producer, red on an empty scan
# set, red on an unreasoned exemption, red when the producer cannot emit its own format.
version-test:
    @cd w0m-web && python3 project/scripts/tests/test_version_doctor.py

# T232 AC14 — advisory check for index↔body divergence in auto-memory
auto-memory-check *args:
    @python3 scripts/auto_memory_check.py {{ args }}

# T22 AC3 — probe every deployed app's /api/health. ⚠️ The path is `/api/health` on each APP
# domain; `/health` and api.webomage.com both 404/000 (measured 2026-08-02).
health-check *args:
    @python3 scripts/health_check.py {{ args }}

# T33 — enforce openspec/SPEC-AUTHORING-STANDARD.md. Ratchet: the non-conforming count may
# shrink freely, any increase fails. `--verbose` names each offending requirement.
spec-standard-check *args:
    @python3 scripts/spec_standard_check.py {{ args }}

# Annotations & debt markers doctor across all 7 estate repos (T342).
annotations-doctor *args:
    @python3 scripts/annotations_doctor.py {{ args }}

# Overrides & suppressions audit alias for annotations doctor (T342).
overrides-check *args:
    @python3 scripts/annotations_doctor.py {{ args }}

# State lives in Cloudflare R2 (T125 AC6). Terraform's `s3` backend wants AWS-STYLE credentials,
# which R2 issues separately from the CF API token — R2 → Manage R2 API Tokens. They are mapped
# here rather than stored under AWS_* names in the vault, because the vault's existing
# AWS_ACCESS_KEY/AWS_ACCESS_SECRET are real AWS keys for something else and must not be confused
# with these. A missing R2_* pair fails loudly below rather than letting Terraform fall back to
# those AWS keys and produce a baffling 403 against R2.
tf-init *args:
    @cd w0m-api/cloudflare && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- sh -c '\
      test -n "$R2_ACCESS_KEY_ID" && test -n "$R2_SECRET_ACCESS_KEY" || { \
        echo "❌ R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY are not in the vault."; \
        echo "   Create them: Cloudflare dashboard → R2 → Manage R2 API Tokens → Create."; \
        echo "   They are NOT the CF API token, and NOT the AWS_* keys already in the vault."; \
        exit 1; }; \
      AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
        terraform init {{ args }}'

# One-time move of the existing local state into R2. Run AFTER `tf-init` succeeds.
# `-migrate-state` reads the tracked terraform.tfstate and uploads it; only once it is in R2 does
# T125 AC5's untracking become safe, because git stops being the only copy.
# `-force-copy` answers the "copy existing state to the new backend?" prompt, which otherwise
# fails with `Error asking for confirmation: EOF` under any non-interactive runner. It is safe
# ONLY while the destination is empty — it means "copy without asking", not "overwrite whatever
# is there". Re-running this against a populated R2 backend would clobber it, which is why this
# is a one-time recipe and not part of tf-init.
tf-migrate-state:
    @just tf-init -migrate-state -force-copy

# Read-only: what would Terraform change on Cloudflare?
tf-plan:
    @cd w0m-api/cloudflare && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- sh -c '\
      AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
        terraform plan -lock=false'

# Refresh state against reality WITHOUT changing anything (drift detection)
tf-drift:
    @cd w0m-api/cloudflare && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- sh -c '\
      AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
        terraform plan -refresh-only -lock=false'

# ── Supabase auth-settings Terraform (T324) ─────────────────────────────────────────────────
# Declares ONLY auth.site_url + auth.uri_allow_list via the supabase_settings resource — see
# supabase-settings/main.tf for why the provider's partial-update semantics make this safe
# where a full config.toml declare + `supabase config push` was not. State lives in the same
# R2 bucket as cloudflare/ (its own key — see supabase-settings/versions.tf). Needs BOTH the R2
# AWS-style keys (backend state access) and SUPABASE_ACCESS_TOKEN (provider auth).
supabase-settings-init *args:
    @cd w0m-api/supabase-settings && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- sh -c '\
      test -n "$R2_ACCESS_KEY_ID" && test -n "$R2_SECRET_ACCESS_KEY" && test -n "$SUPABASE_ACCESS_TOKEN" || { \
        echo "❌ R2_ACCESS_KEY_ID / R2_SECRET_ACCESS_KEY / SUPABASE_ACCESS_TOKEN are not all in the vault."; \
        exit 1; }; \
      AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
        terraform init {{ args }}'

# Pull the full live auth config into state (read-only against Supabase; writes only to the
# R2-backed .tfstate). Run once, after supabase-settings-init.
supabase-settings-import:
    @cd w0m-api/supabase-settings && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- sh -c '\
      AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
        terraform import supabase_settings.wom7 pqbbjgeapylcengbuvee'

# Read-only: what would Terraform change on the Supabase auth config?
supabase-settings-plan:
    @cd w0m-api/supabase-settings && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- sh -c '\
      AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
        terraform plan -lock=false'

# Refresh state against reality WITHOUT changing anything (T324 AC4 drift check)
supabase-settings-drift:
    @cd w0m-api/supabase-settings && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- sh -c '\
      AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
        terraform plan -refresh-only -lock=false'

# T324 AC4 — unlike supabase-settings-drift's raw `terraform plan -refresh-only` (same
# exit code whether clean, drifted, or errored), this wraps `-detailed-exitcode` and FAILS
# CLOSED on "could not read the config" rather than printing a pass (T242 rule).
supabase-auth-drift-check:
    @cd w0m-api/supabase-settings && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- sh -c '\
      AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
        python3 ../../w0m-web/project/scripts/supabase_auth_drift_check.py'

# LIVE-MUTATING: PATCHes auth.site_url + auth.uri_allow_list on the real Supabase project.
# -auto-approve because this runs non-interactively — the confirmation gate is a human
# reviewing `supabase-settings-plan` BEFORE invoking this, not a terraform y/n prompt.
supabase-settings-apply: (_confirm "supabase-settings-apply")
    @cd w0m-api/supabase-settings && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- sh -c '\
      AWS_ACCESS_KEY_ID="$R2_ACCESS_KEY_ID" AWS_SECRET_ACCESS_KEY="$R2_SECRET_ACCESS_KEY" \
        terraform apply -auto-approve -lock=false'

# Switch the gh CLI back to the w0m account. This machine also hosts Elena's GitHub identity
# (evercred), and the active gh account is a single GLOBAL setting, so it flips as a matter of
# course when work moves between projects. git/ssh are unaffected — those are pinned per-directory
# by the includeIf in ~/.gitconfig. This only fixes the gh API account that ticket-sync uses.
# GH_CONFIG_DIR (exported above) points gh at w0m's dedicated config, so this operates on THAT
# dir — a global flip from evercred can no longer affect it. The switch is an idempotent re-assert;
# the gate then proves it took. `env -u GITHUB_TOKEN` is defensive: a stray token would override
# the keyring and make the switch refuse (dotenv-load was removed in T119 AC2b, so belt-and-
# suspenders). The gate script lives in w0m-api/scripts; the `ls` finds it from either repo root.
# Re-assert w0m's gh identity (casualuser) in the dedicated gh config, then prove it took.
gh-w0m:
    @mkdir -p "$GH_CONFIG_DIR"
    @[ -f "$GH_CONFIG_DIR/hosts.yml" ] || printf 'github.com:\n    git_protocol: ssh\n    users:\n        casualuser:\n    user: casualuser\n' > "$GH_CONFIG_DIR/hosts.yml"
    @env -u GITHUB_TOKEN gh auth switch --hostname github.com --user casualuser
    @env -u GITHUB_TOKEN python3 scripts/check_git_identity.py

# Open the w0m Obsidian vault; optional note path, e.g. `just obsidian docs/VAULT-INDEX.md`
# T186 (2026-08-08): the vault is `w0m-web` — it always carried `.obsidian/`, and the separate
# `wom7md` vault it used to open is DECOMMISSIONED. This recipe pointed at `../wom7md` for the
# rest of that ticket and was simply broken; nothing exercises it, so no gate said so.
obsidian note="":
    @cd w0m-api && python3 scripts/open_vault.py ../w0m-web {{ note }}

# Open a specific client project Obsidian vault (T371 AC3)
obsidian-project project_id note="":
    @cd w0m-api && python3 scripts/open_vault.py {{ project_id }} {{ note }}

# Initialize a standardized Karpathy LLM Wiki project vault (T371 AC2)
project-vault-init project_id *args="":
    @python3 scripts/init_project_vault.py {{ project_id }} {{ args }}

# T210 Phase 4 final step — is it safe to drop `social_integrations.user_id` yet? The answer is a
# property of what is DEPLOYED, not of what is committed, so this checks the live edge-function
# sources rather than the working tree. 🔴 Dropping the column while a deployed caller still writes
# it is the same failure as dropping its unique index was: the connect flow broke instantly.
t210-drop-readiness *args:
    @cd w0m-web && python3 project/scripts/t210_drop_readiness.py {{ args }}

# T134 Phase 3 (AC11) — snapshot credential STATE across stores, never values. Runs HERE rather
# than in a route because apps/cp is on Workers: no filesystem, no subprocesses. Supabase publishes
# SHA-256 digests, so agreement is provable without any secret being read. Report-only unless
# `--write`. ⚠️ An empty corpus FAILS rather than writing a confident empty table.
credential-snapshot *args:
    @cd w0m-web && python3 project/scripts/credential_snapshot.py {{ args }}

# T134 AC11 — prove the credential surface is read-only and leak-free, rather than assert it.
# `routes` fails on ANY non-GET handler on the surface; `leak` fails if a live secret VALUE appears
# in the snapshot the page renders. Runs under infisical because proving no value leaked requires
# knowing the values; without them it FAILS CLOSED rather than reporting a green it cannot support.
credential-probe *args:
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- python3 project/scripts/credential_surface_probe.py {{ args }}

# Prove the gate above goes RED — a gate nobody has seen fail is not a gate. Fixtures only.
credential-probe-test:
    @cd w0m-web && python3 project/scripts/tests/test_credential_surface_probe.py

# T134 task 3.1 — prove the Infisical read credential is read-only, by ATTEMPTING a write. "I set
# the role to read-only" is a claim about a UI, not about the credential. Skips cleanly when no
# token is configured, so it is safe to run before task 3.1 lands.
infisical-token-probe *args:
    @cd w0m-web && infisical run --projectId={{ infisical_project_id }} --env=beta --silent -- ./project/scripts/_infisical_token_probe.sh {{ args }}

# ⚠️ Pinned to a TAG on purpose — personaje0's v4 recipe clones the default branch, which silently
# re-versions the engine under you on every fresh install.
#
# Install the pinned Quartz v5 engine. Idempotent; re-run after changing `quartz_tag`.
quartz-install:
    #!/usr/bin/env bash
    set -euo pipefail
    cd w0m-web
    if [ -d .quartz-engine/.quartz/plugins ] && [ "$(git -C .quartz-engine describe --tags 2>/dev/null || true)" = "{{ quartz_tag }}" ]; then
        echo "✅ Quartz {{ quartz_tag }} already installed in .quartz-engine"
        exit 0
    fi
    rm -rf .quartz-engine
    echo "▶ cloning jackyzha0/quartz @ {{ quartz_tag }} …"
    git clone --depth 1 --branch {{ quartz_tag }} https://github.com/jackyzha0/quartz.git .quartz-engine
    cd .quartz-engine
    echo "▶ npm install …"
    npm install
    # 🔴 NOT `npm run install-plugins`. That script is the LEGACY externalPlugins path: it imports
    # quartz.ts, which pulls in `styles/custom.scss`, which tsx cannot load (ERR_UNKNOWN_FILE_EXTENSION
    # — esbuild handles .scss during a real build, tsx does not). It crashes AFTER cloning ~32 plugins
    # unbuilt, and a later `plugin restore` then regenerates the barrel from only what IT installed,
    # leaving `.quartz/plugins/index.ts` missing exports the components import. The build fails with
    # "No matching export for CustomOgImagesEmitterName", which points at Head.tsx and not at the
    # cause. `plugin restore` on a CLEAN tree installs and builds all 43 at the locked versions.
    echo "▶ quartz plugin restore (43 plugins at quartz.lock.json versions — slow, builds each) …"
    rm -rf .quartz
    node ./quartz/bootstrap-cli.mjs plugin restore
    # Upstream crash: obsidian-flavored-markdown's isTagChar calls String.fromCodePoint on
    # micromark's NEGATIVE line-ending codes, so any tag-shaped token followed by a soft line
    # break (a mermaid hex colour, `Finding #4`, `issue #226`) kills the whole build. Fails loud
    # if upstream changes — see the script for why it must never no-op quietly.
    cd .. && python3 project/scripts/quartz_patch_ofm.py

# Point the engine at OUR config. Separated from install so a clobbered symlink is repairable
# without a re-clone, and so the preflight has something to assert about.
_quartz-link:
    @cd w0m-web/.quartz-engine && ln -sfn ../quartz.config.yaml quartz.config.yaml

# Open the vault. Builds, serves on quartz_port (8099), opens a browser. Ctrl-C to stop.
quartz: quartz-install _quartz-link
    #!/usr/bin/env bash
    set -euo pipefail
    cd w0m-web
    python3 project/scripts/quartz_preflight.py
    if lsof -nP -iTCP:{{ quartz_port }} -sTCP:LISTEN >/dev/null 2>&1; then
        echo "port {{ quartz_port }} is already in use — refusing to build for minutes and then fail to bind:"
        lsof -nP -iTCP:{{ quartz_port }} -sTCP:LISTEN | tail -n +2
        echo "stop it, or run: just quartz_port=<free port> quartz"
        exit 1
    fi
    ( cd .quartz-engine && node ./quartz/bootstrap-cli.mjs build -d .. )
    # Build once, then serve statically — NOT `quartz build --serve`. That forces a watcher which
    # globs **/*.ts from the engine, where v5 keeps 43 plugins WITH their node_modules; chokidar
    # dies of EMFILE after serving a handful of requests. And a watcher is worthless here anyway:
    # a rebuild of this vault takes ~5 minutes. Re-run `just quartz` to pick up edits.
    python3 project/scripts/quartz_serve.py --root .quartz-engine/public --port {{ quartz_port }} --open

# Static build, no server. Output lands inside the gitignored engine tree.
quartz-build: quartz-install _quartz-link
    #!/usr/bin/env bash
    set -euo pipefail
    cd w0m-web
    python3 project/scripts/quartz_preflight.py
    cd .quartz-engine && node ./quartz/bootstrap-cli.mjs build -d ..
    echo "✅ built → w0m-web/.quartz-engine/public"

# Prove the config in effect is ours and report the served corpus. Safe to run any time.
quartz-check:
    @cd w0m-web && python3 project/scripts/quartz_preflight.py

# T93 — Claude-Design sync pipeline & adherence enforcement (ds-diff, ds-bundle, ds-adherence)
ds-diff:
    @cd w0m-web && python3 project/scripts/ds_sync_pipeline.py --diff

ds-bundle:
    @cd w0m-web && python3 project/scripts/ds_sync_pipeline.py --bundle

ds-adherence *args:
    @cd w0m-web && python3 project/scripts/ds_sync_pipeline.py --lint {{ args }}

# T279 / T280 / T351 / T364 — Client Beta Epic regression suite
client-beta-epic-test:
    @python3 scripts/tests/test_client_beta_epic.py

# T55 AC5 — Tailwind @source cross-package purge audit & standing gate
tailwind-source-audit-test:
    @cd w0m-web && python3 -m pytest -q project/scripts/tests/test_t55_tailwind_source_audit.py

# T252 AC4 — CP Agent Workspace simulator SEND regression suite
agent-simulator-test:
    @cd w0m-web && python3 -m pytest -q project/scripts/tests/test_t252_agent_simulator.py

# ── Git Hook Recipes & Commit-Msg T## Gate (T129 / T386) ─────────────────────
deploy-in-flight-check:
    @python3 scripts/deploy_in_flight_check.py

[positional-arguments]
semgrep-staged *files:
    @cd w0m-web && semgrep --config=auto --error --quiet "$@"

[positional-arguments]
lint-staged *files:
    @cd w0m-web && pnpm exec oxlint "$@"

[positional-arguments]
fmt-astro-staged *files:
    @cd w0m-web && pnpm exec prettier --check "$@"

[positional-arguments]
fmt-staged *files:
    @cd w0m-web && pnpm exec oxfmt --write "$@" && git add -- "$@"

[positional-arguments]
guard-test-admin *files:
    @cd w0m-web && scripts/guard-test-admin.sh "$@"

status-dashboard-refresh:
    @cd w0m-web && python3 project/scripts/gen_status_dashboard.py && git add docs/STATUS-DASHBOARD.html

cp-feature-index-refresh:
    @cd w0m-web && python3 project/scripts/cp_feature_index.py && git add docs/CP-FEATURE-INDEX.md

codemap-refresh:
    @cd w0m-web && python3 project/scripts/codemap_gen.py --write && git add docs/CODEMAP.md

# Astro build smoke check for apps/demo (T566 AC4 / T149 AC3)
build-demo:
    @cd w0m-web && pnpm --filter demo build
