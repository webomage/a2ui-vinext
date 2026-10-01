---
id: AgDR-0031
title: "Tinybird token literal remediation, process injection, and gitleaks scanner hardening"
timestamp: 2026-09-30T22:30:00Z
agent: antigravity
model: gemini-2.5-pro
trigger: audit
status: accepted
superseded_by:
supersedes:
ticket: T515
---

# AgDR-0031 — Tinybird token literal remediation, process injection, and gitleaks scanner hardening

## Y-statement

> In the context of **a legacy admin JWT token literal committed in `wom7api/scripts/init_tinybird_schemas.py` that went undetected by static analysis scanners**, facing **unrestricted administrative access to analytics pipelines and quarantine queues**, we decided **to revoke and rotate the token via Tinybird CLI, inject it strictly via Infisical process injection, and harden `.gitleaks.toml` across all 7 estate repositories with a dedicated `wom-tinybird-token` rule**, to achieve **zero token literals in the codebase, fail-closed environment validation, and automated pre-commit detection of Tinybird secrets**, accepting **the operational overhead of synchronizing gitleaks configurations estate-wide**.

## Context

On 2026-09-30, an audit identified a literal Tinybird JWT admin token committed in `wom7api/scripts/init_tinybird_schemas.py` (committed 4 months prior in a private upstream repository).
Standard Gitleaks scanner rules missed the token because standard JWT patterns do not cover Tinybird's `p.ey...` format without explicit prefixes.

## Options considered

| Option | Pros | Cons | Verdict |
|---|---|---|---|
| **Rotate token only** | Fast | Re-leaks possible; script still contains patterns; scanner blind spot remains | Rejected |
| **Rotate token + Infisical injection + Custom gitleaks pattern across all 7 estate repos** | Complete remediation: revoked live, injected safely, scanner catches future occurrences | Touches `.gitleaks.toml` across all 7 repos | **Accepted** |
| **Delete init script** | Eliminates code surface | Schema initialization capability lost | Rejected |

## Decision

1. **Immediate Revocation & Rotation:** Owner rotated tokens via `tb --cloud token refresh` and stored the new workspace admin token in Infisical as `TINYBIRD_TOKEN`. Old token verified returning HTTP 403 Forbidden.
2. **Environment Variable Injection:** `init_tinybird_schemas.py` reads `TINYBIRD_ADMIN_TOKEN` / `TINYBIRD_TOKEN` from `os.environ` and fails closed (exit code 1) when absent.
3. **Estate Scanner Hardening:** Added `wom-tinybird-token` detection regex `\bp\.ey[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b` across all seven `.gitleaks.toml` files in the estate.
4. **Offline Test Proof:** Added regression unit tests proving discrimination and red-fixture detection.

## Consequences

- Zero credentials in code; Infisical process injection enforced.
- Gitleaks detects any leaked Tinybird token pre-commit across all repos.
