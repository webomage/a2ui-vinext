---
id: AgDR-0059
title: "Mexico and Global SaaS Commercial, Fiscal (SAT CFDI 4.0 / 0% IVA Export), Payment Rail, and Regulatory Compliance Architecture"
timestamp: 2026-11-20T22:15:00Z
agent: antigravity
model: gemini-4-argon
trigger: user-prompt
status: accepted
superseded_by:
supersedes:
ticket: T783
---

# AgDR-0059 — Mexico and Global SaaS Commercial, Fiscal (SAT CFDI 4.0 / 0% IVA Export), Payment Rail, and Regulatory Compliance Architecture

## Y-statement

> In the context of **operating Webomage (`webomage.com`, `cp.webomage.com`, `me.webomage.com`) from Mexico (Playa del Carmen, Quintana Roo, C.P. 77710) as an automated SaaS, security audit, and AI-assisted software engineering business serving domestic Mexican (`MXN`) and international B2B/B2C (`USD`) clients (`[[T351]]`, `[[T373]]`, `[[T781]]`, `[[AgDR-0055]]`)**, facing **intersecting Mexican SAT fiscal rules (`RESICO` 3.5M MXN cap and shareholder incompatibility under LISR Art. 113-E, mandatory CFDI 4.0 electronic invoicing, LIVA Art. 29 Fracc. IV 0% vs. 16% IVA export evidentiary rules, CFF Art. 20 Banxico DOF `FIX` exchange-rate requirements), post-INAI data privacy oversight by the Secretaría Anticorrupción y Buen Gobierno (`SABG` under the March 20, 2025 DOF LFPDPPP reform), PROFECO recurring billing transparency (`LFPC Art. 76 Bis`), and global VAT/sales-tax obligations**, we decided **to adopt a hybrid direct payment and fiscal automation architecture: (1) Direct Stripe Checkout (`tax_id_collection.enabled = true`, `tos_policy_version` metadata) for foreign B2B and card payments + Mercado Pago / direct STP SPEI (`0%` fee) for domestic Mexican payments, (2) automated CFDI 4.0 stamping via Facturapi PAC using Banxico SIE `SF43718` (`FIX T-1`) exchange rates (`16% IVA` domestic; `0% IVA` export with `RFC: XEXX010101000`, `UsoCFDI: S01`, `ObjetoImp: 02` strictly when paid from a foreign financial institution), (3) full public legal and Spanish *Aviso de Privacidad Integral* (`SABG`) compliance with unchecked opt-in consent (`[[T781]]`), and (4) threshold-triggered Merchant of Record (`Paddle` / `Polar`) or Stripe Tax activation only when launching self-serve B2C digital subscriptions into zero-threshold EU/UK VAT jurisdictions**, to achieve **compliant, low-take-rate (`0%` SPEI / `2.9%–3.6%` Stripe vs. `5%+` MoR), zero-idle-cost (`$0/mo` base per `[[AgDR-0055]]`) global and Mexican commercial operations**, accepting **the responsibility to maintain a valid SAT CSD (`.cer`/`.key`) for automated PAC stamping, forbid domestic SPEI rails on 0%-IVA export invoices, and enforce a hard 3.0M MXN alert before the 3.5M MXN RESICO transition ceiling**.

## Context

1. **Measured Codebase & Legal Baseline (`2026-11-20`, `[[T781]]`, `[[T782]]`):**
   - `w0m-web/apps/web/src/pages/` now serves the complete public legal suite (`/terms`, `/privacy`, `/refunds`, `/cancellation` 301, `/dpa`, `/sla`, `/cookies`, and Spanish `/aviso-de-privacidad` designating **SABG** under the March 20, 2025 DOF LFPDPPP reform).
   - Every public intake and checkout drawer (`ServiceActionOrderConfigurator.svelte`, `SecurityAuditWidget.svelte`, `BlueprintOrderFlow.svelte`, `AuditPricing.svelte`) initializes consent unchecked (`$state(false)`) and records `tosPolicyVersion` (`"2026-11-20"`) and `tosAcceptedAt` via `POST /api/security-audit`.
   - `w0m-api/supabase/functions/_shared/stripe-billing.ts` and `stripe-checkout/index.ts` collect buyer tax IDs (`tax_id_collection: { enabled: true }`, with `customer_update: { name: "auto", address: "auto" }` on customer-backed subscriptions), render legal terms links via `custom_text.submit.message`, and attach `metadata.tos_policy_version`.
   - `w0m-api/supabase/functions/_shared/mexican-payments.ts` (`L9`) and `mercadopago-checkout/index.ts` (`L100`) implement CLABE check-digit validation (`validateClabe`), FNV-1a 7-digit SPEI numeric reference generation, and Mercado Pago preference creation (`card`, `oxxo`, `spei`), but currently use a static fallback constant `DEFAULT_USD_TO_MXN_RATE = 19.5`.
2. **Statutory & Fiscal Constraints Verified (`[[T783]]` Dossier):**
   - **LISR Art. 113-E (`RESICO` Persona Física, Régimen `626`):** Provides a `1.0%–2.5%` effective ISR rate up to `3,500,000 MXN/year` collected cash, but **strictly prohibits** the individual from being a shareholder or partner in any Mexican or foreign corporation (*persona moral*).
   - **LIVA Art. 29 Fracc. IV & RLIVA Art. 61 (`0% IVA` IT/Software Export):** Zero-rated `0% IVA` (`Tasa 0.000000`, `ObjetoImp: 02`) applies to software, cloud, and data-processing services utilized abroad by a foreign resident without a permanent establishment in Mexico **only** when payment originates from a foreign financial institution.
   - **CFF Art. 20 (Exchange Rate on Foreign-Currency CFDIs):** USD invoices must use the Banxico `FIX` rate published in the DOF on the business day prior to payment (`SF43718`), not a hardcoded constant.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **O1 — Full Merchant of Record (`Paddle` / `Polar`) for 100% of revenue** | MoR handles global B2C VAT remittance and buyer invoicing outside Mexico. | Charges `5% + $0.50` even on $2,500–$15,000 B2B engineering contracts; MoR AUPs routinely restrict cybersecurity scanning services; still requires issuing a Mexican export CFDI 4.0 for each monthly MoR settlement payout; discards `stripe-checkout` and `mercadopago-checkout`. | **Rejected** |
| **O2 — Unautomated Direct Stripe + Manual SAT Portal Invoicing** | Zero PAC API cost; lowest raw payment processing fees. | Violates CFF Art. 29/29-A timely CFDI issuance rules at scale; leaves `DEFAULT_USD_TO_MXN_RATE = 19.5` drifting from Banxico DOF `FIX`; risks 16% IVA reclassification if export CFDIs omit `XEXX010101000` / `S01` / `0% IVA` (`ObjetoImp: 02`). | **Rejected** |
| **O3 — Hybrid Split: Direct Stripe (`tax_id_collection`) + Mercado Pago / STP SPEI + Facturapi CFDI 4.0 PAC + Banxico SIE `SF43718` KV Cache + Triggered MoR/Stripe Tax for Global B2C SaaS** | Preserves `0%` SPEI and `2.9%–3.6%` direct Stripe fees on B2B & Mexican transactions; automates SAT CFDI 4.0 domestic (`16% IVA`) and export (`0% IVA`) stamping with R2 archival (`[[AgDR-0055]]`); captures B2B VAT/RFC IDs for reverse-charge; isolates MoR cost strictly to future self-serve global B2C SaaS tiers. | Requires SAT CSD (`.cer`/`.key`) provisioning in Facturapi, Banxico SIE `SF43718` daily KV sync, and strict rail separation so foreign 0%-IVA export clients never pay via domestic Mexican SPEI. | **Accepted (`[[T783]]`)** |

## Decision

1. **Fiscal & Entity Discipline (Pillar 1):**
   - While operating under `RESICO Persona Física (626)`, maintain **zero equity ownership** in any Mexican or foreign *persona moral* (`LISR Art. 113-E Fracc. I`) and monitor trailing 12-month collected revenue in `cp.webomage.com` with a `3,000,000 MXN` warning threshold (`85.7%` of the `3,500,000 MXN` cap).
   - Ensure `WOM_SPEI_BENEFICIARY` and issuer RFC/regime configuration match the active SAT `Constancia de Situación Fiscal` before enabling live PAC stamping.
2. **CFDI 4.0 & 0% vs. 16% IVA Rules (Pillar 2):**
   - **Domestic Mexican Clients (`MXN` or Mexican resident):** Issue CFDI 4.0 against the buyer's validated 12/13-character RFC (`DomicilioFiscalReceptor`, `RegimenFiscalReceptor`, `UsoCFDI: G03`) with **16% IVA** (`ObjetoImp: 02`, `TasaOCuota: 0.160000`). Unclaimed B2C domestic receipts roll into the month-end *CFDI Global* (`RFC: XAXX010101000`, `RegimenFiscalReceptor: 616`, `UsoCFDI: S01`).
   - **Foreign Export Clients (`USD`, non-MX resident, foreign payment method):** Issue CFDI 4.0 with `Rfc: XEXX010101000`, `RegimenFiscalReceptor: 616`, `UsoCFDI: S01`, `Exportacion: 01`, `NumRegIdTrib` + `ResidenciaFiscal` (from Stripe `customer_details.tax_ids`), and **0% IVA** (`ObjetoImp: 02`, `Impuesto: 002`, `TipoFactor: Tasa`, `TasaOCuota: 0.000000`) under `LIVA Art. 29 Fracc. IV`. Never offer domestic Mexican SPEI (`rail = "spei_direct"`) on a 0%-IVA export invoice.
   - **Archival (`[[AgDR-0055]]`):** Store stamped CFDI `.xml` and `.pdf` blobs in Cloudflare R2 (`VAULT_R2`) and store only compact metadata (`cfdi_uuid`, `r2_xml_key`, `r2_pdf_key`, `tipo_cambio_dof`) in Supabase Postgres `invoices`.
3. **Global Tax, Privacy (`SABG`), PROFECO & FX Automation (Pillars 3–7):**
   - **Legal & Privacy (`SABG`):** Keep `/terms`, `/privacy`, `/refunds`, `/cancellation`, `/dpa`, `/sla`, `/cookies`, and `/aviso-de-privacidad` (`SABG`) live on `webomage.com` and linked in all footers and unchecked intake consent checkboxes (`tosPolicyVersion` + `tosAcceptedAt`, `[[T781]]`).
   - **Banxico SIE `SF43718` FX Rate:** Cache the daily Banxico DOF `FIX` USD/MXN rate in Cloudflare KV via `w0m-cf` cron and consume it in `mercadopago-checkout` and CFDI 4.0 `TipoCambio` generation, keeping `DEFAULT_USD_TO_MXN_RATE` strictly as an offline fail-safe.
   - **PROFECO & Chargebacks:** Send 7-day pre-renewal reminders on `invoice.upcoming` with direct Click-to-Cancel links (`LFPC Art. 76 Bis`), and assemble Stripe dispute evidence automatically from `tosPolicyVersion`, `tosAcceptedAt`, `visitorFingerprint`, and `*_audit_log` delivery timestamps.

## Consequences

- **Positive:**
  - Locks in the lowest legal tax and payment take-rate for Mexican and cross-border B2B operations (`1%–2.5%` RESICO ISR + `0%` IVA on verified exports + `0%` STP SPEI / `2.9%–3.6%` direct Stripe) while preserving 16% Mexican expense IVA recovery (`ObjetoImp: 02` zero-rating).
  - Reconciles Mexican post-INAI privacy law (`SABG`, DOF March 20, 2025), PROFECO `LFPC Art. 76 Bis`, GDPR Art. 28 (`DPA` + Subprocessor Register), and CCPA in a single auditable consent and billing pipeline (`[[T781]]`).
  - Honors `[[AgDR-0055]]` Free-Tier-First resource allocation by keeping CFDI XML/PDF storage in Cloudflare R2 (`$0` egress), Banxico FX caching in Cloudflare KV, and compact invoice/consent metadata in Supabase Postgres.
- **Negative / Trade-offs:**
  - Requires active operator custody and renewal (every 4 years) of SAT `e.firma` (FIEL) and *Certificado de Sello Digital* (`CSD`) `.cer`/`.key` credentials for PAC stamping.
  - Prohibits combining `RESICO Persona Física (626)` with corporate equity ownership (`S.A.S.` / `S.A.P.I.` / US C-Corp) by the same individual taxpayer (`LISR Art. 113-E Fracc. I`).

## What this does NOT decide

- **Not Formal Legal or CPA Advice:** This AgDR codifies technical and architectural compliance rules for the `@wom` software estate; formal tax filings, monthly SAT provisional declarations, and corporate formation acts remain the purview of the owner and a licensed Mexican *Contador Público Certificado* (CPC).
- **No Premature Paid MoR / Insurance Commitment:** Does not enable paid Stripe Tax (`0.5%`), a Merchant of Record (`Paddle`/`Polar`), or commercial Tech E&O insurance until the quantitative revenue or B2C tier triggers in the [[T783]] dossier are crossed and confirmed by the owner.
