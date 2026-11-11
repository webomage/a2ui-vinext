# T723 — Collapse Public `/services` and `/solutions` to 1-Click Fast Register + Direct Package Checkout

- **Ticket:** `T723`
- **Date:** `2026-11-11`
- **Repos:** `@wom`, `w0m-web`
- **Status:** Completed & Verified (`AC1`–`AC3`)

---

## 1. Conversion & Single-Responsibility Split (`public` vs `/o/[org]`)

```mermaid
flowchart LR
    A["Public /services & /solutions Cards"] -->|"Checkout Package"| B["Step 2: 1-Click OAuth or Work Email"]
    A -->|"Fast Register"| B
    B -->|"Stripe Checkout or OAuth SSO"| C["Authenticated /o/org Onboarding Wizard"]
    C --> D["Detailed Source/Target Infra, Workloads & Timeline"]
```

| Surface | Responsibility After `T723` |
|---|---|
| **Public `/services` & `/solutions`** (`ServiceActionOrderConfigurator.svelte`, `SolutionsGrid.astro`, `ServicesDetailed.astro`) | **Zero pre-signup Step-2 infrastructure questionnaire.** Each catalog card presents two crisp actions (`Checkout ($X)` and `Fast Register`) that scroll straight to **1-Click OAuth SSO (`Google`, `GitHub`, `LinkedIn`)** or **Work Email + optional Domain/Repo -> Direct Stripe Checkout / Magic Link**. |
| **Post-Signup `/o/[org]` Client Portal** (`ClientDashboard.svelte`, `cp-onboarding-service-wizard`) | **Exclusive home of the detailed Source/Target Infra, Involved Workloads, and Cutover Timeline selector**, pre-seeded via `buildFastOAuthRegisterUrl` / `buildOnboardingWizardPortalUrl` (`?onboarding=wizard&service=...`). |

---

## 2. Bugs & Friction Removed

1. Removed ~225 lines of duplicated pre-signup infrastructure chip selectors (`service-order-step-infra`, `service-order-source-infra`, `service-order-target-infra`, `service-order-workloads`, `service-order-timeline`, `service-order-scope-notes`, `service-order-skip-infra-btn`) from public `ServiceActionOrderConfigurator.svelte`.
2. Reduced each public catalog card from 4 competing buttons (`Order Package`, `Order By Request`, `Checkout & Launch Wizard`, `Skip Details & Fast Register`) to 2 clear actions (`Checkout ($X) →` and `Fast Register →`).
3. Fixed the `($${activeService.packagePriceUsd})` double-dollar string bug in `ServiceActionOrderConfigurator.svelte` (`$2,400` instead of `$$2400`).
