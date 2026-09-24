# Research: Bug Bounty Participation, Program Catalogs & w0m's Own Disclosure Posture

**Date:** 2026-09-23
**Author:** Claude Code (Opus 5.5), web research + estate check
**Status:** Adopted 2026-09-23 as **T433** (`.tasks/T433.md`); §9 below is the original ticket draft
**Diagram:** [`2026-09-23-t433-research-bug-bounty-participation-and-listings.mmd`](2026-09-23-t433-research-bug-bounty-participation-and-listings.mmd)
**Related:** `wom7sec` (audit toolchain, T111), `wom7sec/SECURITY.md`,
`wom7web/openspec/changes/2026-09-11-multi-tier-audit-and-secure-sandboxes/` (task 1.3 checks `security.txt`)

> Sources were gathered on 2026-09-23 and are cited inline. Bounty programs change their
> terms often; re-check each program's policy page before acting on anything below.

---

## 1. Executive summary

1. **Participation can work for w0m as R&D, reputation, and marketing, but not as a revenue line.**
   Earnings follow a power law. HackerOne paid **$81M** in the year to mid-2025, but **$21.6M** of it came
   from just 10 programs. Even in 2019 the top 1% of hunters earned only about $34k a year.
   Budget it as time-boxed skill-building for `wom7sec`.
2. **Working with agents is allowed; letting them hunt unattended is not.** HackerOne: *"Hackbots must not
   operate in a fully autonomous manner"*, and the human operator answers for every report.
   Bugcrowd suspends accounts after 10 consecutive invalid AI reports and bans submission farming
   permanently. This fits w0m's existing human-gate philosophy, but it has to be written down as an
   explicit rule before the first report goes out.
3. **HackerOne has an account type made for w0m's shape.** A **Researcher Business Account** is one
   legal entity with several authorised users, explicitly *"including AI-agent setups"*, and
   files a corporate tax form. Support has to grant it (no self-service), and it is not
   for a sole researcher who forms an entity only to receive their own rewards.
4. **Open-source bounty money is drying up in 2026.** curl ended its bounty (2026-01-31), HackerOne's
   Internet Bug Bounty is paused (2026-03-27), Code4rena shut down (2026-05-13), GitHub cut public tiers
   to a flat $250–$10k (2026-07-27), and Google OSS VRP now asks for an OSS-Fuzz reproduction or a merged patch.
   The cause is the same everywhere: a flood of AI-generated reports. **Paid programs from commercial vendors on
   w0m's own stack (Cloudflare, Anthropic, GitHub, Vercel/Svelte) are the realistic targets.**
5. **w0m's own house comes first, and it is cheap.** w0m publishes no `security.txt` on any
   property. `wom7sec/SECURITY.md` is the only disclosure channel. w0m's own planned audit tool
   (openspec 2026-09-11, task 1.3) would flag w0m's sites for this. Fix: publish `security.txt`, add
   disclose.io safe-harbor terms, list in diodb, and optionally open HackerOne's **free** Essential VDP.
   **Do not run a paid bounty**: at w0m's size it attracts AI noise, as curl and IBB found.

---

## 2. Estate facts (checked 2026-09-23)

| Fact | Evidence |
|---|---|
| No `security.txt` anywhere in the estate | `just search -F "security.txt"` → only hit is the openspec audit *checking* for it |
| Disclosure channel = `wom7sec/SECURITY.md` → `aleksei@webomage.com` | chosen deliberately over an unproven `security@` alias; states 3-day ack / 10-day assessment |
| No bug-bounty / HackerOne / Bugcrowd mentions in any repo | `just search "bug.?bount"`: 0 hits |
| wom7sec `src/` + `specs/` still empty | `SECURITY.md` "Early-stage" note; T111 build deferred |
| Public apps: `web`, `cp`, `job`, `join`, `demo` (Astro on CF Workers) | `wom7web/apps/` |

---

## 3. Platforms for hunters

| Platform | Model | Payout | Org / team support | Notes for w0m |
|---|---|---|---|---|
| **HackerOne** | public and private (invite) | bank, PayPal, crypto (BTC/USDC, needs ID check); about 7–10 days; W-9/W-8BEN/W-8BEN-E | ✅ **Researcher Business Account** ([docs](https://docs.hackerone.com/en/articles/14289683-researcher-business-accounts)): the owner re-verifies ID every 12 months and the account files a corporate tax form | Biggest catalog; hosts **Cloudflare, Supabase, GitHub, Anthropic, Mozilla web, Vercel OSS** |
| **Bugcrowd** | public and private | bank, PayPal, some BTC | ⚠️ per-report collaboration, up to 10 people, split fixed at submit; non-US corporate tax-form path exists | New accounts limited to **5 pending** reports; hosts **OpenAI** ($100k max) |
| **Intigriti** (BE) | public and private | wire, PayPal, Payoneer, UPI; ID check | ⚠️ self-billing invoice to a company name + VAT number; multi-user accounts unverified | EU-friendly invoicing; MSRC's named payout provider |
| **YesWeHack** (FR) | public and private | bank only, in the verified person's name (MangoPay ID check before any report) | ⚠️ company bank account needs company verification via support | Runs FireBounty directory |
| **Synack Red Team** | vetted, application-only | missions $25–50+, vulnerabilities $500 to several thousand dollars (2023 data) | ❌ individuals only; background check + interview | Steady but gated |
| **Immunefi / HackenProof / Sherlock / Cantina** | web3 bounties and audit contests | crypto (mostly USDC) | Sherlock allows teams on one wallet | Outside w0m's stack. **Skip** unless w0m moves into smart contracts |
| **huntr** (AI/ML OSS) | now Palo Alto (Prisma AIRS) | — | — | Moving to timed challenges; some pages say "sunsetting". **Don't invest** |
| **Open Bug Bounty** | non-profit, no payouts | — | — | Mostly XSS; no money and little reputation value |
| **Standoff 365** | Positive Technologies (RU) | rewards go to Russian sole traders or self-employed people | — | ⛔ **Avoid**: Positive Technologies is on US sanctions lists |

Sources: HackerOne [payments](https://docs.hackerone.com/en/articles/8395720-payment-preferences) · [tax](https://docs.hackerone.com/en/articles/8395744-tax-forms);
Bugcrowd [payments](https://docs.bugcrowd.com/researchers/payments/frequently-asked-questions-payment-methods/) · [collab](https://docs.bugcrowd.com/researchers/reporting-managing-submissions/reporting-a-bug/submission-collaboration/) · [limit](https://docs.bugcrowd.com/researchers/reporting-managing-submissions/reporting-a-bug/submissions-limit/);
Intigriti [payouts](https://kb.intigriti.com/en/articles/3379502-payout-methods) · [invoicing](https://kb.intigriti.com/en/articles/8489725-invoice-generation-self-billing);
YesWeHack [KYC](https://helpcenter.yeswehack.io/en/articles/376519-kyc-verifications-strong-customer-authentication-sca);
[Synack](https://www.synack.com/red-team/); [Code4rena shutdown](https://www.theblock.co/news/regulation/2026-05-13-immufefi-absorb-code4rena-bug-bounty-customers-shutdown-decision-401179);
[Sherlock](https://docs.sherlock.xyz/audits/watsons/meeting-the-payout-criteria); [huntr](https://huntr.com/); [Open Bug Bounty](https://www.openbugbounty.org/faq/);
[Standoff 365](https://bugbounty.standoff365.com/en-US/programs/standoff-365/).

**Recommendation: start on HackerOne.** It hosts most of w0m's stack vendors and has the only formal
company-with-agents account type. Start on individual accounts, because Business Accounts are granted by
Support and a track record helps. Apply to convert once there are valid reports. Treat Intigriti as a
second, EU-invoicing channel.

---

## 4. Vendor programs aligned with w0m's stack

These are the programs where w0m's day-to-day expertise gives a real edge.

| Vendor | Where | Paid? | Rules that matter | w0m fit |
|---|---|---|---|---|
| **Cloudflare** | [H1](https://hackerone.com/cloudflare) | ✅ CVSS bands, VIP tier, occasional Workers bonus campaigns ([blog](https://blog.cloudflare.com/cisa-pledge-commitment-bug-bounty-vip/)) | scan only from authorised IPs; customers off-limits | ⭐⭐⭐ Workers, Workflows, DO, KV: w0m runs all of these in production |
| **Supabase** | [H1](https://hackerone.com/supabase) | VDP (no confirmed reward table) | send `X-SUPABASE-VDP: <handle>` header; **no DoS, flooding, cross-tenant testing, or unverified scanner output** ([guide](https://supabase.com/docs/guides/security/security-testing)) | ⭐⭐⭐ for knowledge, ⭐ for money. w0m's RLS/definer/grants history (T39, T69, T206) is exactly this attack surface |
| **Anthropic** | [H1](https://hackerone.com/anthropic) (public since 2026-05-07) | ✅ security bounty; model-safety bounty is by application with an NDA ([info](https://support.claude.com/en/articles/12119250-model-safety-bug-bounty-program)) | jailbreaks out of scope on the security program | ⭐⭐ w0m uses Claude Code and MCP heavily |
| **OpenAI** | [Bugcrowd](https://bugcrowd.com/engagements/openai-safety) | ✅ up to $100k | separate safety program | ⭐⭐ |
| **GitHub** | H1 | ✅ flat $250/$2k/$5k/$10k from 2026-07-27; VIP up to $30k+ ([blog](https://github.blog/security/next-chapter-restructuring-githubs-bug-bounty-program/)) | about 4 initial reports while below the signal threshold | ⭐⭐ Actions, gh, and apps |
| **Svelte (via Vercel OSS)** | H1 (Vercel) | ✅ via Vercel program ([policy](https://github.com/sveltejs/svelte/security/policy)) | reports made via GitHub are not bounty-eligible | ⭐⭐⭐ `@webomage/ui` is Svelte |
| **Astro / Vite** | GitHub private advisories | ❌ no bounty ([astro](https://github.com/withastro/astro/blob/main/SECURITY.md), [vite](https://github.com/vitejs/vite/security/policy)) | — | Credit only; overlaps with the `wom7pr` upstream-contribution work |
| **Google** | [bughunters.google.com](https://bughunters.google.com) | ✅ ($17.1M in 2025) | Chrome Extensions VRP covers **Google-made extensions only** | ⭐ wom7ext expertise doesn't transfer to it directly |
| **Mozilla** | H1 (web) / own (Firefox client, up to $20k) | ✅ | bugs in third-party add-ons generally not rewarded | ⭐ |
| **Apple** | own ([ASB](https://security.apple.com/blog/apple-security-bounty-evolved/)) | ✅ up to $2M; "Target Flags" | — | ⭐ long shot; the MLX/Virtualization.framework work is adjacent |
| **Microsoft** | own MSRC portal ([FAQ](https://www.microsoft.com/en-us/msrc/faqs-bounty)); payouts via Intigriti | ✅ | — | ⭐ |

---

## 5. Catalogs and machine-readable listings

Three feeds can be ingested with licences that allow it. All were pulled and inspected on 2026-09-23.

| Source | Licence | Shape | Size today | Use for w0m |
|---|---|---|---|---|
| **[arkadiyt/bounty-targets-data](https://github.com/arkadiyt/bounty-targets-data)** | **MIT** | `data/<platform>.json` + `domains.txt` / `wildcards.txt`; refreshed about every 30 min (last push 2026-09-22) | H1 451 · Bugcrowd 279 · Intigriti 146 · YWH 58 | ⭐ **primary scope feed**; H1 JSON has `targets`, `offers_bounties`, `allows_bounty_splitting` |
| **[disclose/diodb](https://github.com/disclose/diodb)** | **CC0** | `program-list.json` + SQLite + schema | 2,425 programs | ⭐ **safe-harbor filter**: `safe_harbor` = full/partial/none, `offers_bounty` |
| **[Chaos / ProjectDiscovery](https://github.com/projectdiscovery/public-bugbounty-programs)** | list: MIT; **Chaos data terms not found** | `chaos-data.projectdiscovery.io/index.json`, per-program subdomain zips | 790 programs | ⚠️ use the MIT list only; don't ingest Chaos subdomain data into anything w0m ships until its terms are confirmed |
| Platform researcher APIs | per-account ToS | H1 Hacker API ([docs](https://api.hackerone.com/hacker-resources/)), [Intigriti API](https://kb.intigriti.com/en/articles/8529303-intigriti-researcher-api), [YWH API](https://api.yeswehack.com/doc) | only programs you can access | Authoritative scope for enrolled programs; **always re-read scope here before testing** |
| FireBounty, bugbountydirectory.com | no feed / licence | HTML | — | browsing only |

**Scope trap:** a wildcard in a feed can still have excluded subdomains in the program policy. The feed tells
you where to look; the program page is what authorises testing.

**Estate fit:** a small `wom7sec` intake command could join bounty-targets-data (scope) with diodb
(safe harbor), filter to programs that are paid, have **full** safe harbor, and match w0m's stack (Cloudflare,
Supabase, Astro/Svelte, extensions), and write a ranked JSONL shortlist. The shortlist is for reading only. Nothing
scans automatically from it (see §6).

---

## 6. Rules for agent-assisted hunting (non-negotiable)

What the platforms say:

- **HackerOne [Code of Conduct](https://www.hackerone.com/policies/code-of-conduct):** AI is "permitted and encouraged". Banned: high volumes
  of low-signal reports, unverified or hallucinated claims, repeatedly inflated severity, and *fully autonomous hackbots*. Program
  limits on automation and request rates apply. Penalties escalate to a 12-month ban, then permanent.
- **HackerOne triage ([2026-05-29](https://www.hackerone.com/blog/ai-driven-report-volume-insights-and-actions)):** report volume more than doubled since February. "Hai" agents
  deduplicate and escalate; TriageOne separates trusted researchers from new accounts running only automated tools.
- **Bugcrowd ([2026-03-10](https://www.bugcrowd.com/blog/bugcrowd-policy-changes-to-address-ai-slop-submissions/)):** submission farming gets a permanent ban; 10+ consecutive invalid AI reports
  can bring a 30-day suspension; 10+ invalid reports in total trigger ID verification; automated grabbing of common findings at launch is banned.
- **Program level:** Brave closes AI-looking reports as spam and bans after 2; Supabase and Cloudflare forbid
  unverified scanner output and flooding.
- **The wider trend:** [curl](https://daniel.haxx.se/blog/2026/01/26/the-end-of-the-curl-bug-bounty/) (valid reports fell below 5% in 2025), [IBB pause](https://www.csoonline.com/article/4154216/internet-bug-bounty-program-hits-pause-on-payouts-2.html),
  [Google OSS VRP](https://bughunters.google.com/blog/ossvrp-rule-updates-2026). **A bad reputation with the platforms is the main
  risk of an agent-heavy approach, and it's hard to undo.**

**Proposed w0m hunting rules** (to become an AgDR if adopted):

1. **Agents propose; a human reproduces and submits.** No agent has platform credentials or can submit anything.
   Every report is reproduced by hand, from a clean browser, by the named human.
2. **Scope is checked against the platform API at test time.** A feed cache is not enough. Out of scope means not
   authorised, and nothing is "probably fine".
3. **Rate limits and required headers are in the tooling config**, e.g. per-program RPS caps and Supabase's
   `X-SUPABASE-VDP`, and a missing value fails closed (w0m's no-silent-fallback rule applies here too).
4. **Scanner output is never a report.** A report includes impact, a minimal reproduction, and a severity the author would defend.
5. **Validity ratio is tracked.** Pause the whole programme if valid reports drop below 50% over the last 10.
6. **Client assets are never bounty targets**, even if the client runs a public program. Client security
   work is a separate, contracted engagement. Findings stay out of the public KB until disclosed (KB content policy).
7. **Secrets come from Infisical, never from files.** Platform API tokens live in Infisical like every other credential.

---

## 7. Legal and safe harbor

- **Only test assets in scope of a program you are enrolled in.** Anything else has no authorisation.
- **disclose.io "Full Safe Harbor"** ([dioterms](https://github.com/disclose/dioterms)) covers anti-hacking law (CFAA/CMA), anti-circumvention
  law (DMCA), a waiver of the organisation's terms of service, and an acknowledgement of good faith. A plain "we won't sue" is only "Partial". Prefer
  programs with `safe_harbor: full` in diodb.
- **HackerOne [Gold Standard Safe Harbor](https://docs.hackerone.com/en/articles/8494525-gold-standard-safe-harbor-statement):** good-faith research is treated as authorised, but third-party
  infrastructure can never be covered. An **AI-research variant** was added in [January 2026](https://www.helpnetsecurity.com/2026/01/20/hackerone-good-faith-ai-research-safe-harbor-framework/).
- **US:** the 2022 DOJ policy not to charge good-faith research under the CFAA is guidance to prosecutors, not law; civil
  suits are still possible ([WSGR](https://www.wsgr.com/en/insights/doj-acknowledges-limits-to-the-cfaa-but-questions-and-possible-civil-liability-remain-for-security-researchers-and-others.html)).
- **UK:** there is still no Computer Misuse Act defence for researchers ([Computer Weekly](https://www.computerweekly.com/news/366649543/Peers-propose-report-into-Computer-Misuse-Act-reform)).
- **Tax and entity:** a Business Account files a corporate tax form (W-8BEN-E if the entity is non-US). Which entity
  and jurisdiction w0m would use is **an owner decision this research does not make**.

---

## 8. w0m's own disclosure posture (Phase 0: do this regardless)

| Step | Cost | Detail |
|---|---|---|
| Publish `/.well-known/security.txt` on every public app ([RFC 9116](https://www.rfc-editor.org/rfc/rfc9116)) | ~1h | Required: `Contact: mailto:aleksei@webomage.com`, `Expires` (≤1y). Optional: `Policy` (→ SECURITY.md or a `/security` page), `Canonical`, `Preferred-Languages`. **Needs a renewal check**: an expired `Expires` is itself a finding, and a `just` recipe or preflight check could catch it |
| Upgrade `SECURITY.md` → estate-wide policy with **dioterms full safe-harbor** text | ~2h | Currently scoped to wom7sec only; public apps + extensions need to be in scope |
| List in **diodb** by PR | ~30m | Makes w0m visible in the same catalogs described in §5 |
| Optional: **HackerOne Essential VDP** (free since Sept 2024, [PR](https://www.hackerone.com/press-release/hackerone-launches-free-vdps-support-compliance-mandates)) | free (paid triage extra) | Gives a proper inbox and compliance attestations, which helps agency sales. Intigriti and YesWeHack VDPs are quote-only |
| ❌ Paid bounty | — | Not at this size; curl and IBB show it attracts noise faster than a small team can triage |

This also works as a sales asset. "We run a public VDP with full safe harbor" is a credible line in a proposal, and
the same `security.txt` + policy bundle can be sold to clients as part of the planned multi-tier audit
(openspec 2026-09-11).

---

## 9. Proposed ticket (for intake)

**Title:** Bug-bounty programme: own disclosure posture (Phase 0) and a time-boxed hunting pilot on stack-vendor programs
**Prio:** P2 · **Repos:** sec, web · **Type:** research → task

- **AC1:** `security.txt` is live on all public apps with a valid `Expires`, and an expiry check fails closed ≥30 days before expiry.
- **AC2:** An estate-wide security policy with dioterms full-safe-harbor text is published and linked from `security.txt`; w0m is listed in diodb.
- **AC3:** An owner decision on HackerOne Essential VDP (adopt or decline, with the reason) is recorded in `docs/DECISIONS.md`.
- **AC4:** The agent-assisted hunting rules (§6) are recorded as an AgDR before any submission.
- **AC5:** A `wom7sec` intake command joins bounty-targets-data (MIT) and diodb (CC0) into a ranked JSONL shortlist (paid + full safe harbor + stack match); it is read-only with no scanning.
- **AC6:** The pilot is time-boxed (proposed: 4h/week × 8 weeks) on ≤3 programs (proposed: Cloudflare, Vercel/Svelte, Supabase VDP), with a written go/no-go review: valid ratio, hours, payouts, and what `wom7sec` gained.

**Owner decisions needed:** which legal entity and jurisdiction receives payouts; the pilot time budget; whether to apply for an H1 Business Account after the pilot.

---

## 10. Could not verify

- Median bounty or time-to-first-bounty in any official report. The "~40% never paid" and "90% earn nothing" figures come from blogs only.
- Bugcrowd's total 2025 payouts.
- Current Cloudflare and Supabase reward tables (the pages need JavaScript to load).
- Whether Intigriti or YesWeHack support multi-user company accounts the way HackerOne does.
- Chaos data terms of use; huntr's current AI policy and how far its move to challenges has gone.
- Sanctions exposure for Standoff 365 payouts (moot: recommendation is to avoid it).
- Anthropic's model-safety reward maximum (sources say $15k, $25k, or $35k).
