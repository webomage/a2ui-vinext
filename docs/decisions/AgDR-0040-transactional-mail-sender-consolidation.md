---
id: AgDR-0040
title: "3-Channel Outbound Mail Architecture (Supabase Auth, Google Workspace SMTP, Resend Free Tier) & Apex SPF/DMARC"
timestamp: 2026-10-22T20:15:00-05:00
agent: antigravity
model: claude-opus-4-6
trigger: user-prompt
status: executed
superseded_by:
supersedes:
ticket: T326
---

# AgDR-0040 — 3-Channel Outbound Mail Architecture (Supabase Auth, Google Workspace SMTP, Resend Free Tier) & Apex SPF/DMARC

## Y-statement

> In the context of **outbound email across `webomage.com` (`Supabase Auth` ceremonies, 1:1 platform/transactional messages, internal admin alerts, and user notifications/digests)**, facing **missing apex SPF (`webomage.com`), missing DMARC (`_dmarc.webomage.com`), and an uncodified split between Google Workspace SMTP (`SMTP_USER@webomage.com`) and Resend (`no-reply@webomage.com`, signed by `resend._domainkey.webomage.com`)**, we decided **to codify a 3-channel outbound mail architecture — (1) Supabase Auth for self-service auth ceremonies, (2) Google Workspace SMTP (`sendTransactionalSmtpMail`) for 1:1 platform transactions & internal admin alerts, and (3) Resend Free Tier (`sendNotificationResendMail`) for automated user notifications, visitor/applicant auto-replies, and weekly digests — backed by apex SPF (`v=spf1 include:_spf.google.com include:amazonses.com ~all`) and DMARC (`p=none; rua=mailto:dmarc@webomage.com`) in Cloudflare Terraform (`wom7api/cloudflare/records.tf`)** to achieve **1:1 human reply-ability and Workspace `Sent` auditability for platform transactions while preserving Resend's 100/day free-tier quota and DKIM-signed `no-reply@webomage.com` branding for user notifications**, accepting **that both `_spf.google.com` and `amazonses.com` remain authorized in apex SPF and each edge function call must explicitly choose `sendTransactionalSmtpMail` or `sendNotificationResendMail` with zero silent cross-channel fallback**.

## Context

1. `webomage.com` had **no apex `v=spf1` TXT record** and **no `_dmarc.webomage.com` TXT record** (`[[T326]]`).
2. Both senders are live and provisioned in Infisical (`beta`):
   - **Google Workspace SMTP (`smtp.gmail.com`, `SMTP_USER@webomage.com`)**: real `@webomage.com` mailbox where replies land in the inbox and sent messages are recorded in the Workspace `Sent` folder (up to 2,000 messages/day).
   - **Resend API (`RESEND_API_KEY`, `RESEND_FROM_EMAIL=no-reply@webomage.com`)**: DKIM-signed via `resend._domainkey.webomage.com` with `send.webomage.com` SES return-path, ~50ms HTTP POST, Free Tier (100 emails/day, 3,000/month).
3. Sending internal admin alerts (`CONTACT_NOTIFY_EMAIL`) through Resend would waste 50% of the Resend free-tier quota on internal copies, whereas sending public visitor auto-replies or newsletters through Gmail SMTP would expose `SMTP_USER` and clutter the Workspace `Sent` folder.

## Decision: 3-Channel Assignment Matrix

| Channel | Helper / API | Sender Identity | Assigned Flows |
|---|---|---|---|
| **1. Auth Ceremonies** | `supabase.auth.*` (`signInWithOtp`, `resetPasswordForEmail`) | Supabase Auth mailer | Self-service OTP login, password reset (`apps/cp/src/pages/api/auth/reset-request.ts`, `apps/web/src/pages/api/auth/reset-request.ts`), email verification. |
| **2. Transactional & Platform (`transactional`)** | `sendTransactionalSmtpMail` (`wom7api/supabase/functions/_shared/transactional-mail.ts`) | Google Workspace `SMTP_USER@webomage.com` (`spf=pass` via `include:_spf.google.com`) | • `client-register`: B2B client portal provisioning & magic link<br>• `admin-invite-candidate`: 1:1 candidate technical interview invitation<br>• `contact-submit` (admin alert to `CONTACT_NOTIFY_EMAIL`)<br>• `apply-submit` (admin alert + signed resume link to `CONTACT_NOTIFY_EMAIL`) |
| **3. Notifications & User Messages (`notification`)** | `sendNotificationResendMail` (`wom7api/supabase/functions/_shared/transactional-mail.ts`) | Resend `<no-reply@webomage.com>` (`dkim=pass` via `resend._domainkey` + `spf=pass` via `include:amazonses.com`) | • `contact-submit` (visitor auto-reply receipt)<br>• `apply-submit` (applicant auto-reply receipt)<br>• `weekly-digest` (subscriber newsletter broadcast) |

## Consequences

- **Positive**:
  - Every B2B client portal invite (`client-register`) and candidate interview invite (`admin-invite-candidate`) is logged in Google Workspace `Sent` and supports direct human reply.
  - Internal admin alerts (`contact-submit`, `apply-submit`) stay inside Google Workspace SMTP and never consume Resend's 100/day free-tier quota.
  - External visitor/applicant auto-replies and `weekly-digest` broadcasts dispatch via fast HTTP POST from DKIM-signed `no-reply@webomage.com`.
  - Enforced mechanically by `wom7web/project/scripts/mail_auth_check.py`.
- **Negative**:
  - Live DNS resolution of the new apex SPF and `_dmarc` TXT records requires a human-confirmed `terraform apply` on `wom7api/cloudflare/`.

## What this does NOT decide

- Does not escalate DMARC policy from `p=none` to `p=quarantine` or `p=reject` until initial aggregate reports at `dmarc@webomage.com` are reviewed.
