# Role Scoring Rubric, JD Decoding & Evidence Provenance

Load this guide when decoding a raw job description or contract brief, calculating the `0-100` role fit score, verifying claims against candidate evidence, or triaging red flags.

## 1. Normalized Opportunity Brief Schema

Parse every raw posting into five standardized blocks before scoring:

1. **Role & Organization:** Exact title, company/client name, product domain, team/funding stage, engagement model (`Full-Time`, `Contract`, `Fractional`, `Fixed-Scope`).
2. **Must-Have Requirements:** Non-negotiable languages, frameworks, infrastructure platforms, compliance/security constraints, and production scale expectations.
3. **Nice-to-Have Signals:** Secondary tooling, domain overlap, open-source leadership, or architecture mentorship bonus items.
4. **Commercials & Logistics:** Published salary/hourly/retainer band, equity structure, payment reliability signals (e.g., marketplace verified spend or funded stage), timezone overlap hours, and location/entity rules.
5. **Ambiguities & Red Flags:** Unlisted compensation, contradictory or bloated stack expectations, unpaid production deliverables, or missing engineering leadership context.

## 2. Deterministic Weighted Scoring Rubric (`0-100`)

Evaluate each sub-criterion independently so the composite score is reproducible and explainable:

| Dimension | Max Weight | Sub-Criteria & Point Allocation |
|---|---:|---|
| **Core Stack & Architecture Fit** | **35** | Primary language/runtime match (`0-15`) · Cloud/edge/data platform match (`0-10`) · Production reliability/security scope (`0-10`) |
| **Domain & Ownership Level** | **20** | Seniority alignment (`0-10`, IC/Staff/Founding/Fractional) · System design & technical ownership autonomy (`0-10`) |
| **Compensation & Commercial Terms** | **20** | Meets or exceeds candidate rate/salary floor (`0-10`) · Clarity of budget, duration, retainer/equity terms, and payment trust (`0-10`) |
| **Timezone, Location & Async Cadence** | **15** | Overlap hours compatibility (`0-10`) · Remote flexibility & entity/visa/tax compatibility (`0-5`) |
| **Product Signal & Engineering Health** | **10** | Realistic single-role scope vs multi-department wishlist (`0-5`) · Engineering rigor, testing, and clear problem definition (`0-5`) |

### Triage Buckets & Required Action

- **Priority Apply (`80-100`):** High stack, ownership, and commercial fit. Proceed immediately to evidence mapping, tailored resume variant generation, and custom outreach/proposal drafting.
- **Selective / Clarify (`65-79`):** Viable core alignment with `1-2` unresolved parameters (e.g., undisclosed rate band, ambiguous overlap hours, or one secondary stack gap). Draft concise clarifying questions before spending deep customization effort.
- **Pass / Archive (`<65`):** Material core mismatch, below-floor compensation, incompatible on-site/timezone mandate, or severe red flags. Log one-line pass reason in the pipeline tracker and do not draft materials.

## 3. Candidate Evidence & Fact Provenance Matrix

Every capability claim in tailored resumes, cover notes, or technical proposals MUST trace back to verified candidate history:

| JD Requirement | Classification | Verified Candidate Source | Honest Framing / Bridge Strategy |
|---|---|---|---|
| Edge runtime routing & Workers | `Direct Production Match` | Verified CV / Shipped repo X (architecture, throughput/scale) | Lead with exact shipped system and concrete outcome |
| Postgres RLS & multi-tenant auth | `Direct Production Match` | Verified production schema migrations & test suites | Cite specific isolation model and verified test coverage |
| Kubernetes / Helm cluster ops | `Adjacent / Transferable Match` | Containerized CI/CD + IaC / Terraform edge deployment | State exact bridge and production container experience transparently |
| Embedded Rust firmware | `True Gap` | None in candidate history | Flag explicitly to user; omit from mastery claims or note ramp-up plan |

### Truthfulness Guardrails

- **Immutable Facts:** Employers, titles, employment dates, degree/certification status, customer names, and production metrics remain strictly grounded in user-verified records.
- **Gap Disclosure:** Classify missing must-haves as `True Gap` in the evaluation summary before drafting materials so the candidate decides consciously whether to apply or address ramp-up upfront.

## 4. Red-Flag & Risk Taxonomy

Deduct points under `Product Signal & Engineering Health` and `Compensation & Commercial Terms` when any of these appear:

| Signal | Severity | Impact & Guidance |
|---|---|---|
| **Multi-Department Wishlist** | Medium | Posting demands Staff Backend + Mobile + ML + DevOps + Design in one IC role; cap Engineering Health at `<= 2/10` unless scope clarifies core focus |
| **Unpaid Production Work** | High | Request for multi-day feature build or bespoke proprietary audit prior to paid contract/interview; flag explicitly for candidate rejection or paid-trial counterproposal |
| **Undisclosed / Wide Bait Band** | Low-Med | Range >50% spread or completely omitted; route to `Selective / Clarify` and confirm budget ceiling early |
| **Stale / Reposted Req (>60d)** | Low-Med | Repeatedly reposted role across multiple months; verify active headcount before investing deep tailoring time |
| **Contradictory Stack Constraints** | Medium | Requires conflicting seniority years (e.g., 8 years in a 3-year framework) or mismatched client-side/backend buzzwords; signal non-technical brief filtering |
