---
id: AgDR-0035
title: "Personal KYC providers (Telegram Gateway OTP + in-estate SAT CSF / CFE-Telmex POA) and profile_identity / profile_contact SSOT cutover"
timestamp: 2026-10-20T18:45:00-05:00
agent: antigravity
model: gemini-2.5-pro
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T528
---

# AgDR-0035 — Personal KYC providers (Telegram Gateway OTP + in-estate SAT CSF / CFE-Telmex POA) and profile_identity / profile_contact SSOT cutover

## Y-statement

> In the context of **completing the personal half of `@wom/kyc` (`T528`, split from `T505` AC7 and AC11)**, facing **(1) the need for a cost-effective, privacy-preserving phone OTP provider and proof-of-address (POA) provider for `public.profile_contact`, and (2) duplicate `curp` and `rfc` columns sitting on `gamification.compliance_profiles` alongside `public.profile_identity`**, we decided **to adopt Telegram Gateway API with SMS fallback for phone OTP, use in-estate `@wom/kyc` SAT CSF QR + CFE/Telmex utility receipt parsing for proof of address, cut over all four `compliance_profiles` readers to read `public.profile_identity` and `public.profile_contact`, drop `curp` and `rfc` from `gamification.compliance_profiles`, and enforce fail-closed payout gating against `public.profile_identity.identity_verified_at`** to achieve **one canonical SSOT for member contact and identity PII, minimal external PII exposure, near-zero verification vendor cost, and automatic payout revocation when a member edits a verified identity fact**, accepting **that non-Telegram phone numbers incur SMS fallback rates (~$0.05/OTP) and that non-MX utility receipts require manual/admin review until LATAM POA parsers land in `T364`**.

## Context

Measured on 2026-10-20 against live Supabase (`--env=beta`) and the estate codebase:
1. **`public.profile_contact` (`20260930130000_t505_profile_contact.sql`, 1 live row)**: Holds `phone`, `address_line1`, `address_line2`, `postal_code`, `city`, `region`, `country_code`, and the service-role-only markers `phone_verified_at` and `address_verified_at`. Trigger `profile_contact_guard()` automatically clears `phone_verified_at` when `phone` changes and `address_verified_at` when any address column changes, unless the marker is updated in the same statement by `service_role`.
2. **`public.profile_identity` (`20260930140000_t505_profile_identity.sql`, 1 live row)**: Holds `legal_given_names`, `legal_family_name`, `legal_second_family_name`, `date_of_birth`, `nationality`, `curp`, `rfc`, `id_document_*`, and the service-role-only marker `identity_verified_at`. Trigger `profile_identity_guard()` automatically clears `identity_verified_at` whenever `legal_*`, `date_of_birth`, `curp`, or `rfc` changes.
3. **`gamification.compliance_profiles` (`20260914210000_t349_w0m_kyc_verified_levels.sql`, 0 live rows)**: Holds duplicate `curp` and `rfc` columns keyed by `user_id` (`auth.users.id`) rather than `profile_id` (`public.profiles.id`), read/written by four surfaces:
   - `wom7web/apps/cp/src/pages/api/admin/kyc-verify.ts`
   - `wom7web/apps/cp/src/components/admin/TreasuryManager.svelte`
   - `wom7api/supabase/functions/gamification-economy/index.ts`
   - `wom7web/project/scripts/t349_kyc_probe.py`
4. **Payout gate gap**: `gamification-economy` checked only `compliance_profiles.kyc_status === 'verified'`. Even if a member edited their `curp` or `rfc` in `profile_identity` (clearing `identity_verified_at`), `compliance_profiles.kyc_status` remained `'verified'` unless `gamification-economy` (and database helper checks) also verify `profile_identity.identity_verified_at IS NOT NULL`.

## Options considered (All Alternatives Preserved for Later Review)

All options evaluated across the `T528` KYC provider questions and the `/me/profile` UX & architecture questions are preserved below for future review, cost comparison, or phase-2 adoption (e.g., `T364` LATAM KYC expansion or Resume Studio vault consolidation).

### 1. Phone OTP Provider (`profile_contact.phone_verified_at`)

| Option | Unit Cost | Data Sent to Provider | Pros | Cons / Trade-offs | Status |
|---|---|---|---|---|---|
| **Option A (Recommended): Telegram Gateway API + SMS fallback** | **~$0.01 / Telegram OTP** (~$0.05 / SMS fallback) | Only normalized E.164 phone number (`profile_contact.phone`) + 6-digit OTP code. Zero name, email, or profile ID. | 5x cheaper than traditional SMS; native fit for w0m's Telegram-connected guild workflow; automatic SMS fallback when number is not on Telegram. | Requires Telegram Gateway token in Infisical (`TELEGRAM_GATEWAY_TOKEN`) and SMS fallback configuration. | **Selected (2026-10-20)** |
| **Option B: Supabase Auth Phone OTP (Twilio Verify / MessageBird)** | **~$0.05 / OTP** | E.164 phone number (`profile_contact.phone`) + OTP channel (`sms` / `whatsapp`). | Built-in Supabase Auth hook support; single vendor dashboard if Twilio is already used. | 5x higher baseline cost per check; separate Twilio Verify account overhead. | **Preserved for later review** (if unified Supabase Auth phone-factor login is needed) |
| **Option C: AWS End User Messaging / SNS SMS** | **~$0.03–$0.06 / SMS** | E.164 phone number (`profile_contact.phone`) + SMS body. | Consolidates billing onto existing AWS account. | 10DLC / country sender-ID registration overhead; lower LATAM delivery reliability without WhatsApp/Telegram channel. | **Preserved for later review** (if AWS enterprise credits cover SMS spend) |

### 2. Proof-of-Address Provider (`profile_contact.address_verified_at`)

| Option | Unit Cost | Data Sent to Provider | Pros | Cons / Trade-offs | Status |
|---|---|---|---|---|---|
| **Option A (Recommended): Official MX SAT CSF QR + CFE/Telmex utility receipt parser in `@wom/kyc`** | **$0.00 / check** | **SAT CSF QR**: only the SAT QR URL (`siat.sat.gob.mx/app/qr/...`, SSRF-guarded). **CFE/Telmex receipt**: 0 bytes leave the estate (parsed locally in `@wom/kyc` against `profile_contact`). | Zero vendor fee; zero PII shared with third-party KYC SaaS; reuses `@wom/kyc`'s SSRF-hardened `verifySatCsfQr` plus deterministic postal-code/address matching against `profile_contact`. | Scoped to MX documents (SAT CSF, CFE, Telmex) until `T364` adds LATAM utility parsers. | **Selected (2026-10-20)** |
| **Option B: Stripe Identity Address / Document Verification** | **~$1.50 / check** | Member legal name, postal address (`profile_contact`), and uploaded utility/government document image. | Hosted UI across 30+ countries; handles non-MX passports and utility bills out of the box. | High per-check fee ($1.50); exports high-sensitivity member PII and document scans to a third party. | **Preserved for later review** (candidate fallback for non-MX / international members in `T364`) |
| **Option C: MetaMap / Truora LATAM POA API** | **~$1.00–$2.00 / check** | Member legal name, CURP/RFC, postal address, and utility document. | Broad LATAM utility & tax registry coverage (CO, BR, CL, PE, AR). | Monthly minimums and per-check cost; externalizes sensitive identity/address PII. | **Preserved for later review** (evaluate against in-estate adapters when `T364` starts) |

### 3. `/me/profile` UX & Resume Studio Integration Options (Preserved for Later Review)

During the `T528` `/me/profile` review (2026-10-20), four UX & architectural questions were evaluated. The selected option for each was shipped immediately, and all alternative options are preserved here for future review:

#### 3a. Personal Information (`PersonalInformation.svelte`) Collapse Behavior
- **Option 1 (Selected — 2026-10-20)**: **Collapsed by default with a 1-line verification summary strip** (shows Phone, Address, Identity verification pills + location/phone preview + `Edit / Expand ▼` toggle button).
- **Option 2 (Preserved for later review)**: **Auto-collapse only when all 3 verifications (Phone, Address, Identity) are verified**, remaining expanded if any fields are incomplete or unverified.
- **Option 3 (Preserved for later review)**: **Separate sub-accordions** so Contact (phone/address/links) and Identity (legal name/CURP/RFC/ID doc) expand and collapse independently inside the panel.

#### 3b. Verified Credentials Bug (`VerifiedCredentials.svelte`) & Character Sheet (`CharacterSheet.svelte`)
- **Option 1 (Selected — 2026-10-20)**: **Fix `me.id` `ReferenceError` in `VerifiedCredentials.svelte`** (resolve `profileId` / `auth.getUser()` cleanly and render empty state when 0 rows exist) **and pass real member name to `CharacterSheet.svelte`** instead of hardcoded `"Guild Member"`.
- **Option 2 (Preserved for later review)**: **Fix the bug AND make `VerifiedCredentials` & `CharacterSheet` collapsible when empty** so 0-XP / 0-certificate profiles stay ultra-compact.
- **Option 3 (Preserved for later review)**: **Hide `CharacterSheet` and `VerifiedCredentials` on `/me/profile`** and move them exclusively to the Gamification / Guild tab.

#### 3c. Stored Resumes (`ResumeParser.svelte`) & Resume Studio (`job.webomage.com/me/resume`) Connection
- **Option 1 (Selected — 2026-10-20)**: **Unified Resume Studio Vault manager** — group files into `Uploaded PDFs` vs `Studio Exports`, add `Primary PDF` badge + `Set Primary`, signed-URL `Preview`, `Delete`, `Re-parse`, and direct `Open in Resume Studio ↗` link; keep the file list collapsed by default behind a summary bar.
- **Option 2 (Preserved for later review)**: **Compact Vault Selector on `/me/profile`** — show only the currently active Primary Resume + 1-click `Manage Vault in Resume Studio` modal/redirect, moving all file management into `job.webomage.com/me/resume`.
- **Option 3 (Preserved for later review)**: **Keep full list on `/me/profile` but add batch cleanup (`Delete all duplicates`)** to prune repeated `Resume-Aleksei-Tcelishchev-*.pdf` exports in one click.

#### 3d. Career & Project Experience (`ProfileExperience.svelte`) Display & Upwork Contract Curation
- **Option 1 (Selected — 2026-10-20)**: **Decode HTML entities (`&nbsp;`), replace `"DELETED"` with `"Upwork Client (Archived)"`, add source filter tabs (`All` / `Core Career` / `Upwork Contracts`), and cap initial view to top 5 entries** with `"Show all N entries ▼"` toggle + `"Work History ↗"` and `"Curate in Resume Studio ↗"` links.
- **Option 2 (Preserved for later review)**: **Group all Upwork contracts into a single collapsible `"Upwork Freelance Portfolio (N contracts)"` summary card** on `/me/profile` so only major multi-month roles appear at the top level.
- **Option 3 (Preserved for later review)**: **Keep only summary metrics on `/me/profile`** (total years, role count, Upwork contract count, top skills) and move the full CRUD experience list exclusively to `job.webomage.com/me/work`.

## Decision

1. **Phone OTP Provider (`T528` AC1/AC2)**:
   - Use **Telegram Gateway API + SMS fallback** for phone verification in `@wom/kyc`.
   - **Cost**: ~$0.01 per verification via Telegram Gateway (`gateway.telegram.org`), ~$0.05 per SMS fallback.
   - **Data boundary**: The provider receives exclusively the member's E.164 phone number read from `public.profile_contact.phone` (and the ephemeral 6-digit verification code / TTL). It never receives `profile_id`, `user_id`, legal name, email, address, CURP, or RFC.
2. **Proof-of-Address Provider (`T528` AC1/AC2)**:
   - Use **Official MX SAT Constancia de Situación Fiscal (CSF) QR + CFE/Telmex utility receipt parser in `@wom/kyc`**.
   - **Cost**: $0.00 vendor fee.
   - **Data boundary**:
     - For **SAT CSF QR**: Only the official `https://siat.sat.gob.mx/app/qr/...` URL is queried (enforced by `validateSatQrUrl` SSRF guard); the returned fiscal location/postal code is matched in-estate against `public.profile_contact` (`postal_code`, `city`, `region`, `country_code`, `address_line1`).
     - For **CFE / Telmex / MX POA text/receipt verification**: Parsed 100% in-estate within `@wom/kyc` against `public.profile_contact` (`address_line1`, `postal_code`, `city`, `region`, `country_code`) — zero external network calls and zero PII transmitted outside the estate.
3. **SSOT Cutover & Schema Cleanup (`T528` AC2/AC3/AC4)**:
   - `public.profile_contact` is the sole store of member phone and postal address; `phone_verified_at` and `address_verified_at` are written exclusively by KYC (`service_role`).
   - `public.profile_identity` is the sole store of member `curp`, `rfc`, legal name, and birth date; `identity_verified_at` is written exclusively by KYC (`service_role`).
   - Drop `curp` and `rfc` from `gamification.compliance_profiles` via forward migration (`AgDR-0025`, no compatibility shim).
   - Update all four readers (`apps/cp/src/pages/api/admin/kyc-verify.ts`, `TreasuryManager.svelte`, `wom7api/supabase/functions/gamification-economy/index.ts`, and `wom7web/project/scripts/t349_kyc_probe.py`) to read `public.profile_identity` and `public.profile_contact` keyed by `profile_id`.
   - Enforce fail-closed payout gating in both Postgres (`gamification.is_member_kyc_payout_eligible(uuid)`) and `gamification-economy`: a member with no `profile_identity` row, no valid `curp`/`rfc`, or `identity_verified_at IS NULL` (including after editing a verified fact, which triggers `profile_identity_guard()` to clear `identity_verified_at`) is refused payout (`403`).

## Consequences

- **Positive**:
  - Eliminates dual SSOT for `curp` and `rfc` between `gamification.compliance_profiles` and `public.profile_identity`.
  - Connects `T505`'s self-invalidating verification triggers (`profile_identity_guard`, `profile_contact_guard`) directly to compliance and treasury payout gating: if a verified member alters their CURP, RFC, legal name, or birth date, `identity_verified_at` is cleared in the database and payouts immediately fail closed until re-verified.
  - Keeps member PII inside the estate ($0 POA check via SAT CSF QR + CFE/Telmex parser; E.164 phone-only payload for Telegram Gateway OTP).
- **Negative**:
  - Admin KYC verification (`TreasuryManager.svelte` / `/api/admin/kyc-verify`) now requires the member to have saved their `public.profile_identity` record first (failing closed with 422 if missing, rather than letting an admin type an unanchored CURP/RFC into `compliance_profiles`).
  - Non-Mexican proof-of-address documents remain gated on `T364` (LATAM KYC expansion).

## What this does NOT decide

- Column-level encryption of `public.profile_identity` (`T505` Open Question 5) — `profile_identity` remains protected by owner-only RLS, column-level write grants, and platform disk encryption.
- Hardware biometric anchoring (`WebAuthn` / `Touch ID` binding to KYC scorecards), which is tracked separately in `T475`.
- Multi-country LATAM registry adapters (CR, PA, BR, CO, AR, CL, PE), which are tracked in `T364`.
