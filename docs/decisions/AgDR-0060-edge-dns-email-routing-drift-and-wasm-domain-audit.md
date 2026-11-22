---
id: AgDR-0060
title: "Edge DNS & Email Routing Architecture, Automated Terraform Drift Detection with Telegram Alerts, and Client WASM DoH Perimeter Auditing"
timestamp: 2026-11-21T20:15:00Z
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T787
---

# AgDR-0060 — Edge DNS, Email Routing Architecture, Terraform Drift Telegram Alerts, and Client WASM DoH Perimeter Auditing

## Y-statement

> In the context of **managing edge DNS records, Cloudflare Email Routing, and domain security perimeters across first-party zones (`webomage.com` and `w0m.xyz`) and client connected/audited domains while operating at `$0/mo` infrastructure cost ([[AgDR-0055]], [[AgDR-0003]])**, facing **dual-SSOT conflicts between Terraform declarations and Cloudflare Email Routing internal MX locks, Pages-era domain leftovers pointing at deleted projects, and unmanaged DNS drift (such as duplicate SPF records causing RFC 7208 PermErrors and breaking mail delivery)**, we decided **to (1) enforce a strict Single-SPF invariant across all domains, (2) retire legacy `cloudflare_pages_domain` resources in favor of Wrangler Workers Custom Domains and untrack locked Email Routing MX records from Terraform management, (3) implement automated Terraform drift detection (`scripts/tf_drift_check.py`, `just tf-drift-check`, `just tf-drift-alert`) dispatching instant Telegram alerts to Aleksei (`TELEGRAM_ADMIN_ID: 275104413`) via `@webomage_bot`, and (4) provide zero-server client connected domain DNS drift monitoring (`domain-drift.ts`) running in WASM / browser sandbox via Cloudflare DoH in TabLinux**, to achieve **tamper-evident infrastructure synchronization, zero email delivery disruption, and free-tier client domain verification without backend server load**, accepting **relegation of MX management on Email Routing zones to Cloudflare's internal controller and requiring Infisical secret injection (`R2_*` mapped to `AWS_*`) for Terraform execution**.

## Context

1. **Email Routing & DNS Reality on `w0m.xyz` vs `webomage.com` (T664, T671, T786):**
   - `webomage.com` MX points to Google Workspace (`smtp.google.com`), with outbound sending via Amazon SES / Resend (`v=spf1 include:_spf.google.com include:amazonses.com ~all`). Enabling Cloudflare Email Routing on `webomage.com` would overwrite Google Workspace MX records and disrupt primary mailbox delivery.
   - `w0m.xyz` is dedicated to short-links (`redirects.tf`) and per-client `<slug>@w0m.xyz` technical mailing lists routed to the `wom7func` Email Worker (`w0m-cf/src/lib/email-routing.ts`).
   - When Email Routing is enabled on `w0m.xyz`, Cloudflare automatically provisions and locks `route1.mx.cloudflare.net`, `route2.mx.cloudflare.net`, and `route3.mx.cloudflare.net`. Declaring individual `cloudflare_record` MX entries in Terraform triggers API error 1046 (`This record is managed by Email Routing. Disable Email Routing to modify/remove this record`).
2. **Duplicate SPF Record Outage Risk (RFC 7208 Section 3.2):**
   - An out-of-band edit created a secondary `v=spf1` TXT record on `w0m.xyz`. Under RFC 7208, multiple SPF records trigger a permanent evaluation error (`PermError`). Cloudflare Email Routing immediately locked and refused to activate with `Multiple SPF records exist (2026)`.
   - Single-SPF invariant is mandatory: exactly one consolidated `v=spf1` TXT record may exist per domain apex.
3. **Retired Pages Domains:**
   - Previous Terraform declarations included `cloudflare_pages_domain.webomage_root`, `www_webomage`, and `beta_webomage` pointing to the legacy `webomage` Pages project. That Pages project was decommissioned when production web apps were migrated to Astro SSR on Cloudflare Workers Custom Domains (`custom_domain: true` in `wrangler.jsonc`, [[AgDR-0056]]).
4. **Free-Tier-First Client Domain Auditing (TabLinux / WASM):**
   - Clients connecting custom domains to Webomage require passive DNS, SPF, DMARC, DNSSEC, and ownership challenge audits. Running these audits on backend servers or edge workers consumes daily CPU and subrequest quotas. Cloudflare DoH (`https://cloudflare-dns.com/dns-query` `Accept: application/dns-json`) allows the entire audit to execute client-side in WebAssembly inside the TabLinux browser console (`apps/cp` Crew Toolkit) at `$0` server compute cost.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **O1 — Manual Cloudflare Dashboard Management** | No Terraform setup or provider version quirks. | Zero version control, untracked drift, high human error risk, duplicate records go unnoticed until mail fails. | **Rejected** |
| **O2 — Blind Terraform Re-apply Over Managed Objects** | Single tool for all DNS. | Fails closed on Cloudflare Email Routing locks (Error 1046) and provider bug #3397 on rule updates. | **Rejected** |
| **O3 — Hybrid Declarative Edge DNS + Automated Drift Alerting + WASM DoH Client Scanner** | Declarative state for all owned records, graceful delegation of Cloudflare-managed MX records, automated drift detection with Telegram alerts, and client-side WASM auditing at $0 server cost. | Requires mapping R2 keys to AWS-style environment variables for Terraform S3 backend and keeping rule names aligned to prevent provider update bugs. | **Accepted ([[T787]])** |

## Decision

1. **Single-SPF Invariant:**
   - No domain under `@wom` management shall publish more than one `v=spf1` TXT record. All authorized mail gateways (Google, Cloudflare, SES, Resend) must be consolidated into a single string ending with `~all` (softfail) or `-all` (fail).
2. **Resource Boundary:**
   - `cloudflare_pages_domain` resources are officially retired; edge hostnames (`webomage.com`, `cp.webomage.com`, `me.webomage.com`, `demo.webomage.com`) are owned exclusively by Wrangler Workers Custom Domains.
   - On zones with Email Routing (`w0m.xyz`), MX records (`route1/2/3.mx.cloudflare.net`) are managed exclusively by Cloudflare Email Routing and untracked from Terraform state.
   - `cloudflare_email_routing_rule` resources must maintain exact metadata parity (e.g. `name = "PandaTransfer Tech Mailing List (T664)"`, `priority = 0`) to prevent Cloudflare provider #3397 update failures.
3. **Automated Terraform Drift Detection & Telegram Alerting:**
   - `scripts/tf_drift_check.py` executes `terraform plan -detailed-exitcode -lock=false`.
   - On exit code `2` (drift detected), it parses planned additions, modifications, and deletions, and dispatches a structured Markdown alert to Aleksei (`TELEGRAM_ADMIN_ID: 275104413`) via `@webomage_bot` (`TELEGRAM_BOT_TOKEN`).
   - Exposed via `just tf-drift-check` (dry-run check) and `just tf-drift-alert` (live Telegram alerting).
4. **Client Domain Drift & Security Auditor in WASM (TabLinux):**
   - Implemented in `w0m-web/packages/lib/src/security/domain-drift.ts` and registered as module `domain-drift` in `TABLINUX_CREW_MODULES`.
   - Executes parallel DoH queries (`TXT`, `_dmarc`, `_w0m-verify`, `MX`, `DNSKEY`) using Cloudflare's public DNS-over-HTTPS JSON API.
   - Computes deterministic score (0–100), letter grade (`A`–`F`), and actionable remediations directly inside the client's browser console with zero backend compute overhead.

## Consequences

- **Positive:**
  - Zero chance of undetected infrastructure drift or accidental SPF duplication breaking production mail.
  - Operator receives actionable Telegram push notifications the instant out-of-band edits occur.
  - Clean `terraform plan` output with zero legacy Pages or locked MX clashes.
  - Client domain audits run infinitely at `$0` recurring cost in browser WASM.
- **Negative:**
  - Automated alerting requires valid `TELEGRAM_BOT_TOKEN` in Infisical `beta` vault.
  - Email Routing MX records on `w0m.xyz` are managed through Cloudflare's internal service rather than explicit Terraform resources.

## References

- Ticket: `[[T787]]`
- RFC 7208: *Sender Policy Framework (SPF) for Authorizing Use of Domains in Email, Section 3.2 (Multiple SPF Records)*
- RFC 7489: *Domain-based Message Authentication, Reporting, and Conformance (DMARC)*
- Prior Decisions: `[[AgDR-0055]]` (Free-Tier-First Architecture), `[[AgDR-0056]]` (Workers Custom Domains), `[[AgDR-0059]]` (Email Routing & DKIM)
