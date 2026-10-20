---
state: living
author: w0m-in-tray
dropped: 2026-10-20
reason: "Generated disposition board (`just in-sync`) showing what is new vs adopted, declined, or living."
---

# `_in` Disposition Ledger (`INDEX.md`)

> **Generated mechanically by `just in-sync` (`wom7web/project/scripts/in_tray.py`).**
> Do not hand-edit this file; update YAML front-matter on dropped `.md` files or `_in/ledger.json`, then run `just in-sync`.

## Summary

| State | Count | Policy |
|---|---:|---|
| `new` | 0 | Must be triaged (`just in-triage`) within **7 days** |
| `living` | 4 | Permanent tray infrastructure (`README.md`, `INDEX.md`, `ledger.json`, `active-work.json`) |
| `adopted` | 29 | Moved out of `_in/` into a ticket (`[[T###]]`), OpenSpec change, `docs/reports/`, or `client-projects/` |
| `declined` | 0 | Evaluated and declined with a recorded reason |

## New Drops (`state: new`)

_No untriaged `new` items currently in `_in/`._

## Living Files (`state: living`)

| File | Author | Dropped | Purpose |
|---|---|---|---|
| `README.md` | `owner` | `2026-09-02` | Permanent drop protocol and untrusted-input notice for the `_in/` tray. |
| `INDEX.md` | `w0m-in-tray` | `2026-10-20` | Generated disposition board (`just in-sync`) showing what is new vs adopted, declined, or living. |
| `ledger.json` | `w0m-in-tray` | `2026-10-20` | Machine-readable disposition ledger backing `_in/INDEX.md` and `just in-check`. |
| `active-work.json` | `agent-claim` | `2026-09-03` | Living coordination claim file (T274 / T426) read by `active-work-heads-up`; never moved out. |

## Adopted Items (`state: adopted`)

| File | Author | Dropped | Adopted To |
|---|---|---|---|
| `Lahore_Prospect_Proposal_2026-06.md` | `owner` | `2026-09-02` | client-projects/lahore-prospect (client-projects tier; excluded from public KB per KB content policy) |
| `orca` | `owner` | `2026-09-02` | [[T377]] · [[T409]] · [[T423]] · wom7pr/orca |
| `2026-09-03-projects-inventory-audit.md` | `antigravity` | `2026-09-03` | [[T308]] · wom7web/docs/reports/PROJECTS_CATALOG_AND_CLEANUP_AUDIT_2026.md |
| `2026-09-04-agent-parity-skills-tools-and-d32-p0-report.md` | `antigravity` | `2026-09-04` | [[T312]] · wom7web/docs/reports/2026-09-04-agent-parity-skills-tools-and-d32-p0-report.md |
| `2026-09-05-project-roles-hats-offices-and-resource-access-architecture.md` | `antigravity` | `2026-09-05` | [[T319]] · [[T313]] · [[T315]] |
| `2026-09-06-login-logout-role-change-audit-and-suggested-actions.md` | `antigravity` | `2026-09-06` | [[T320]] · [[T159]] · wom7web/docs/reports/2026-09-06-login-logout-session-audit.md |
| `2026-09-07-client-registration-and-projects-readiness-measured.md` | `claude` | `2026-09-07` | [[T328]] · wom7web/docs/reports/2026-09-07-client-registration-and-projects-readiness-measured.md |
| `2026-09-09-proposal-w0m-slim-vm-universal-sandboxing.md` | `antigravity` | `2026-09-09` | [[T296]] · [[T297]] · wom7web/docs/reports/2026-09-09-proposal-w0m-slim-vm-universal-sandboxing.md |
| `2026-09-11-analysis-orca-vs-zeroclaw-unification.md` | `antigravity` | `2026-09-11` | [[AgDR-0012]] · [[T180]] · wom7web/docs/reports/2026-09-11-analysis-orca-vs-zeroclaw-unification.md |
| `2026-09-11-proposal-unified-one-button-platform-connectors.md` | `antigravity` | `2026-09-11` | [[T94]] · [[T442]] · wom7web/docs/reports/2026-09-11-proposal-unified-one-button-platform-connectors.md |
| `2026-09-11-proposal-w0m-resource-governance.md` | `antigravity` | `2026-09-11` | [[T343]] · wom7web/openspec/changes/2026-09-11-resource-governance |
| `2026-09-11-research-ios-app-store-sandbox-audit.md` | `antigravity` | `2026-09-11` | [[T336]] · [[T337]] · wom7web/docs/reports/2026-09-11-research-ios-app-store-sandbox-audit.md |
| `2026-09-11-spec-w0m-fullsize-orca-zeroclaw-and-rebranding-research.md` | `antigravity` | `2026-09-11` | [[AgDR-0012]] · [[T180]] · wom7web/docs/reports/2026-09-11-spec-w0m-fullsize-orca-zeroclaw-and-rebranding-research.md |
| `2026-09-11-strategy-unified-w0m-ecosystem-orca-rebranding.md` | `antigravity` | `2026-09-11` | [[AgDR-0012]] · [[T345]] · wom7web/docs/reports/2026-09-11-strategy-unified-w0m-ecosystem-orca-rebranding.md |
| `2026-09-15-artemio-delivery-report.md` | `agent-delivery` | `2026-09-15` | [[T357]] · client-projects/artemio (_arch/artemio_reports_2026-09-15/) |
| `w0m_agent_integration.md` | `antigravity` | `2026-09-16` | [[T367]] · wom7web/openspec/changes/archive/2026-09-17-2026-09-16-siri-shortcuts-zeroclaw-orca/proposal.md |
| `2026-09-17-claude-obsidian-project-vaults-cp-embedding.md` | `claude` | `2026-09-17` | [[T370]] · wom7web/docs/reports/2026-09-17-claude-obsidian-project-vaults-cp-embedding.md |
| `2026-09-21-audit-design-system-vs-shipping-code-and-update-proposal.md` | `antigravity` | `2026-09-21` | [[T420]] · wom7web/openspec/changes/archive/2026-09-22-design-system-reconciliation/proposal.md |
| `2026-09-22-t165-member-resume-web-tool-architecture.md` | `claude` | `2026-09-22` | [[T165]] · .agents/reports/2026-09-22-t165-member-resume-web-tool-architecture.md |
| `2026-09-22-t420-design-system-reconciliation-brief.md` | `claude` | `2026-09-22` | [[T420]] · .agents/reports/2026-09-22-t420-design-system-reconciliation-brief.md |
| `2026-09-23-recheck-design-system-post-t420-and-react-free-component-plan.md` | `antigravity` | `2026-09-23` | [[T422]] · wom7web/openspec/changes/archive/2026-09-23-2026-09-23-design-system-react-elimination-and-tokens-ssot/proposal.md |
| `2026-09-23-cowork-research-parallel-agents-isolation-and-merge.md` | `claude` | `2026-09-23` | [[T423]] · .agents/reports/2026-09-23-cowork-research-parallel-agents-isolation-and-merge.md |
| `2026-09-23-parallel-agents-isolation-and-merge-proposal.md` | `claude` | `2026-09-23` | [[T423]] · [[T424]] · [[T425]] · [[T426]] · .agents/reports/2026-09-23-parallel-agents-isolation-and-merge-proposal.md |
| `2026-09-23-t432-research-dora-space-devex-for-w0m.md` | `claude` | `2026-09-23` | [[T432]] · .agents/reports/2026-09-23-t432-research-dora-space-devex-for-w0m.md |
| `2026-09-23-t433-research-bug-bounty-participation-and-listings.md` | `claude` | `2026-09-23` | [[T433]] · .agents/reports/2026-09-23-t433-research-bug-bounty-participation-and-listings.md |
| `2026-09-24-agent-rule-enforcement-audit.md` | `claude` | `2026-09-24` | [[T434]] · .agents/reports/2026-09-24-agent-rule-enforcement-audit.md |
| `2026-09-24-t211-ticket-diagram-sync.md` | `claude` | `2026-09-24` | [[T211]] · .agents/reports/2026-09-24-t211-ticket-diagram-sync.md |
| `2026-09-24-t435-deploy-confirmation-gate-test-and-agent-refusal-report.md` | `antigravity` | `2026-09-24` | [[T435]] · .agents/reports/2026-09-24-t435-deploy-confirmation-gate-test-and-agent-refusal-report.md |
| `2026-09-25-client-org-model-review-T439.md` | `claude` | `2026-09-25` | [[T439]] · .agents/reports/2026-09-25-client-org-model-review-T439.md |

## Declined Items (`state: declined`)

_No declined items._
