# Resume Tailoring, Technical Proposals & Outreach Playbook

Load this guide for opportunities scoring `>= 65` when producing role-specific resumes, ATS keyword alignment checks, contract proposals, or hiring-manager outreach notes.

## 1. Non-Destructive Resume Variant Rules

- **Preserve Canonical Master Profile:** Never overwrite the user's master CV, base facts file, or canonical portfolio record. Emit each tailored version as a dedicated role-scoped output (e.g., `applications/<org>-<role>/resume.md`).
- **Role-Specific Focus:** Re-order existing verified experience blocks and project highlights to foreground direct matches for the target JD without changing employment dates, titles, or factual scope.
- **No Unrequested PII Bloat:** Omit street addresses, government identifiers, birth dates, and private reference lists unless explicitly requested by the user.

### Tailored Document Structure

1. **Targeted Headline (1 line):** Align the candidate's real verified discipline with the role's primary problem domain.
2. **Executive Summary (3-4 lines):** State years of domain delivery, core technical architecture focus, and 1-2 concrete verified outcomes matching the posting.
3. **ATS Keyword Hygiene Section:** Use exact canonical technology terms confirmed in the candidate's background (for example `TypeScript`, `PostgreSQL`, `Rust`, `Cloudflare Workers`, `Playwright`) in standard, parser-friendly Markdown/PDF sections. Avoid hidden text, white-font blocks, or ungrounded buzzword injection.
4. **Impact Bullets (`Problem -> Architecture/Action -> Measured Result`):**
   - **Formula:** `[Context/Bottleneck] -> [Architectural Choice & Implementation] -> [Verified Outcome / Metric]`.
   - **Example Pattern:** *"Eliminated multi-tenant query latency spikes across 40k daily webhook events by partitioning Postgres tables with covering indexes and moving signature validation to edge isolates, cutting p95 latency from 420ms to 38ms."*

## 2. Cover Letter & Contract Proposal Framework (`120-200` Words)

Keep cold outreach, ATS cover notes, and marketplace proposals crisp, scannable, and strictly within `4-5` concise sentences (`120-200` words total):

1. **Sentence 1 — Specific Technical Bottleneck Hook:** Reference the exact engineering challenge or architectural milestone stated in the job brief (never generic flattery).
2. **Sentence 2 — Comparable System Proof:** Cite 1-2 directly comparable systems built in verified history with concrete scale or reliability outcomes.
3. **Sentence 3 — Concrete First-Week / Milestone Plan:** Outline the immediate diagnostic, architecture check, or deliverable you would execute first to de-risk their roadmap.
4. **Sentence 4 — Honest Scope / Adjacent Bridge (if applicable):** Confirm availability/timezone alignment or transparently frame how adjacent production skills cover a secondary requirement.
5. **Sentence 5 — Clear Low-Friction CTA:** Propose a focused 15-20 minute technical call or clarification on acceptance criteria.

### Cold-Outreach Compensation Rule

- Do **not** volunteer unsolicited salary demands or rigid rate ultimatums inside initial cover letters; state compensation only when an application form, screening question, or marketplace bid field explicitly requires a rate/salary figure (in which case use the user's verified range).
- **Avoid Generic AI Cliches:** Exclude filler openings (`"I am thrilled to apply"`, `"passionate rockstar"`, `"fast-paced synergy"`). Ground every sentence in tangible systems, failure modes, and deliverables.

## 3. Channel-Specific Templates

### A. Contract / Marketplace Proposal Template (Upwork, Contra, Fractional)

```markdown
Saw your brief on [specific bottleneck/deliverable] — the main risk in similar [domain/stack] builds is typically [concrete technical failure mode, e.g., webhook idempotency / cold-start latency / schema drift].

In a recent production system ([Verified Project Reference]), I designed and shipped [architecture summary], achieving [verified measurable outcome]. For week one here, I would audit [specific integration/surface], lock down [test/schema contract], and deliver [tangible Milestone 1 artifact] before scaling further.

Available for [overlap window] in [timezone] at [user-confirmed rate if bid field requires it]. Happy to share relevant code architecture notes or walk through [specific screening question] on a brief call.
```

### B. Direct Founder / Hiring Manager Note (`60-100` Words)

```markdown
Subject: [Role Title] — [Specific Technical Problem]

Hi [Name], noticed [Organization] is hiring a [Role] to tackle [specific roadmap item from JD or engineering post]. I recently built [comparable production system] using [exact overlapping stack], solving [measurable constraint].

If helpful, I mapped two quick observations on [relevant technical area] against your public docs. Open to a 15-minute engineering chat this week?
```

### C. Selective / Clarify Pre-Application Note (`65-79` Rubric Score)

Use when core stack alignment is strong (`>= 26/35`) but compensation, overlap hours, or role scope needs verification before full customization:

- Ask at most `2-3` direct, answerable questions (e.g., published compensation range, required synchronous hours, primary ownership scope between competing systems).
