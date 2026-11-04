# T626 — Fix `/me/account` `403 Forbidden` Proxy APIs, First-Factor `/api/me/mfa` Enrollment & Explicit CP API Coverage

- **Date:** `2026-11-03`
- **Ticket:** [`T626`](../../.tasks/T626.md)
- **Spec:** [`openspec/specs/profile-auth-mfa-pat/spec.md`](../../w0m-web/openspec/specs/profile-auth-mfa-pat/spec.md)
- **Agent:** `agy:cp-me-account-apis`

---

## 1. Root Cause Summary

| Surface / Endpoint | Live Symptom on `cp.webomage.com/me/account` | Root Cause | Resolution (`T626`) |
| :--- | :--- | :--- | :--- |
| `/api/me/mfa`, `/api/me/tokens`, `/api/me/identities` (+ `/api/profile/self-accounting-kyc`, `/api/project/release-approval`, `/api/payments/mercadopago-checkout`) | Red `⚠ Forbidden` alert inside **Multi-Factor Authentication** and **Personal Access Tokens** for non-`admin` hats (`TECH-LEAD`, `member`, `client`) | Omitted from `ME_APIS` in `w0m-web/apps/cp/src/lib/cp-routes.ts`; fell into the trailing `{ test: () => true, subject: "admin-console" }` catch-all, which masked `route-inventory.spec.ts` (`UNDECLARED`) while `middleware.ts` returned `403 {"error": "Forbidden"}`. | Added all 6 member/client proxy endpoints to `ME_APIS` (`subject: "profile"`). |
| `/api/payments/mercadopago-webhook`, `/api/webhooks/linkedin`, `/api/sync/vault`, `/api/board/*` | Blocked by cookie-auth `admin-console` catch-all (`401`/`403`) | Self-authenticating HMAC webhook and Bearer-token Chrome extension sync routes were unlisted in `cp-routes.ts`. | Declared `PUBLIC_SELF_AUTH_APIS` + `isBoardApi` (`subject: "public"`) and `ADMIN_CONSOLE_APIS` + `isPostsApi` (`subject: "admin-console"`), enforced by `isExplicitCpApi()`. |
| `GET`/`POST /api/me/mfa` for unenrolled elevated users (`admin`/`manager`) | `403 MFA_REQUIRED` deadlock when enrolling the very first 2FA factor at `/me/account?mfa_required=1` | `isMfaExemptRoute` exempted `/me/account` HTML page, but `evaluateMfaRequirement` (`w0m-web/packages/lib/src/auth/mfa-policy.ts`) still required `aal2` on `/api/me/mfa` even when `!hasEnrolledFactor` (`nextLevel !== "aal2"`). | Allowed `/api/me/mfa` at `aal1` strictly when `!hasEnrolledFactor`, while continuing to enforce `403 MFA_REQUIRED` at `aal1` whenever `hasEnrolledFactor === true`. |
| `PersonalAccessTokens.svelte` & `ConnectedIdentities.svelte` at `aal1` in elevated hat | Raw red `⚠ MFA_REQUIRED` banner before first factor is enrolled | Panels treated `403 {"error": "MFA_REQUIRED"}` as a red failure string instead of an actionable AAL2 lock state. | Rendered calm amber AAL2 guidance notice on `403 MFA_REQUIRED` and dispatched `w0m:mfa-verified` from `MfaEnrollment.svelte` so both panels auto-unlock upon 2FA verification. |

---

## 2. Verification Matrix

- **Vitest (`w0m-web`)**: `7/7` test files, `180/180` tests passing:
  - `apps/cp/src/lib/__tests__/cp-routes.test.ts` (`55/55`, including exhaustive `apps/cp/src/pages/api/**` disk-parity ratchet via `isExplicitCpApi` + red mutation probe)
  - `packages/lib/src/auth/mfa-policy.spec.ts` (`60/60`, including `T626 AC3` unenrolled vs enrolled `/api/me/mfa` probes)
  - `packages/lib/src/auth/middleware.spec.ts` (`17/17`, including `TECH-LEAD` end-to-end `/api/me/mfa` + `/api/me/tokens` AAL1/AAL2 lifecycle probe)
  - `packages/lib/src/auth/route-inventory.spec.ts` (`21/21`)
  - `packages/lib/src/auth/route-policy.spec.ts` (`17/17`)
  - `apps/cp/src/components/profile/__tests__/MeAccountPage.test.ts` (`5/5`)
  - `apps/cp/src/components/auth/__tests__/HttpOnlyAccountIslands.test.ts` (`5/5`)
- **Static & Policy Gates**:
  - `oxlint`: `0` warnings, `0` errors across touched TypeScript files
  - `oxfmt --check`: all 8 touched TypeScript/Svelte files formatted cleanly
  - `python3 project/scripts/cp_nav_policy_test.py --enforce`: exit `0`
  - `python3 project/scripts/supabase_surface_drift_check.py`: `0` findings across `926` files
