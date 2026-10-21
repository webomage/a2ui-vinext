# `.incidents/` — Structured Delivery Incident Ledger (`T432` AC4)

Version-controlled incident records powering the **Failed Deployment Recovery Time** (formerly MTTR) and **Change Fail Rate** metrics in `just dora` (`scripts/dora_metrics.py`).

## Conventions

- Every incident is stored as `.incidents/INC-YYYY-MM-DD-NNN.json` and validated against [`.incidents/incident.schema.json`](incident.schema.json).
- Required lifecycle fields:
  - `id`: `INC-YYYY-MM-DD-NNN`
  - `detected_at`: ISO-8601 UTC timestamp when the failed deploy or service degradation began
  - `recovered_at`: ISO-8601 UTC timestamp when service or pipeline health was restored (`null` while open)
  - `cause_deploy_version`: release version or commit that introduced the failure
  - `resolution_deploy_version`: release version or commit that restored service
  - `severity`: `sev1` · `sev2` · `sev3`
  - `status`: `open` · `resolved`
  - `affected_services`: array of affected services (`release`, `api`, `web`, `cp`, `join`, `job`, `demo`, `db`)
  - `tickets`: linked remediation tickets (`T###`)
- When logging a remediation or rollback deploy via `scripts/log_deploy.py`, pass `--trigger incident --incident-ref INC-YYYY-MM-DD-NNN` (or set `W0M_DEPLOY_TRIGGER=incident W0M_DEPLOY_INCIDENT_REF=INC-...`).
