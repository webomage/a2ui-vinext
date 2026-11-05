# Security & Vulnerability Disclosure Policy — Webomage (`w0m` Estate)

**Canonical Public Policy URL:** `https://webomage.com/security`
**Repository Mirror:** [`w0m-sec/SECURITY.md`](../w0m-sec/SECURITY.md)
**Governance Record:** [`AgDR-0047`](decisions/AgDR-0047-vulnerability-disclosure-and-bug-bounty-hunting-governance.md) (`T433`)
**RFC 9116 `security.txt`:** Published at `/.well-known/security.txt` on every public Webomage property (`webomage.com`, `cp.webomage.com`, `me.webomage.com`, `demo.webomage.com`) and validated by `w0m-sec/scripts/check_security_txt.py`.
**Safe Harbor Standard:** [disclose.io Core Terms (`dioterms`) — Full Safe Harbor](https://github.com/disclose/dioterms).

---

## 1. Reporting a Vulnerability

**Email [`security@webomage.com`](mailto:security@webomage.com) or [`aleksei@webomage.com`](mailto:aleksei@webomage.com).** Put `SECURITY` in the subject line.

Please include:

- **What the issue is**, and which property, repository, file, or endpoint it affects;
- **How to reproduce it** (minimal step-by-step proof-of-concept);
- **What an attacker gains** (realistic security impact and affected tenant/user boundary);
- **Whether you have disclosed it anywhere else**.

**Do not open a public GitHub issue for a security problem**, and **never include a live secret or credential literal in a report** — redact the value and describe where and how it was exposed.

## 2. What to Expect (Response Targets)

| Stage | Target SLA |
|---|---|
| **Acknowledgement** | Within **3 business days** |
| **Initial triage & severity assessment** | Within **10 business days** |
| **Fix or documented mitigation** | Tracked as a prioritized `T##` ticket, severity-ordered |
| **Coordinated disclosure** | Mutually agreed after remediation (default ≤ 90 days) |

Webomage operates a self-hosted **Vulnerability Disclosure Program (VDP)** with **Full Safe Harbor** and public researcher acknowledgement (upon request). Per [`AgDR-0047`](decisions/AgDR-0047-vulnerability-disclosure-and-bug-bounty-hunting-governance.md), Webomage does not run a standing paid bug bounty program at its current stage.

## 3. Estate-Wide Scope

### In Scope (First-Party Webomage Properties & Repositories)

1. **Public Web Applications (`w0m-web/apps/*`)**:
   - `https://webomage.com` (`apps/web`)
   - `https://cp.webomage.com` (`apps/cp`)
   - `https://me.webomage.com` (`apps/me`)
   - `https://demo.webomage.com` (`apps/demo`)
2. **Backend APIs, Supabase Edge Functions & Cloudflare Workers (`w0m-api`, `w0m-cf`)**
3. **Browser Extensions (`w0m-ext`)**
4. **Security Toolchain, Agent Skills & Inference Subsystems (`w0m-sec`, `w0m-skills`, `w0m-mlx`)**

### Out of Scope

- **Client-owned domains, repositories, and third-party workspaces** declared in `project/policies/clients-policy.json` (except `role: "w0m"`).
- **Unverified automated scanner or LLM/hackbot output** without demonstrated security impact and human-verified reproduction.
- **Volumetric Denial of Service (DoS / DDoS)** or rate-limit flooding.
- **Social engineering, phishing, or physical attacks**.
- **Findings requiring an already-compromised host or stolen session/credential**.

## 4. Legal Posture — disclose.io Full Safe Harbor (`dioterms`)

> **Safe Harbor Statement (`dioterms` Full Safe Harbor)**
>
> When conducting vulnerability research according to this policy, we consider this research conducted under this policy to be:
>
> - **Authorized concerning any applicable anti-hacking laws**, and we will not initiate or support legal action against you for accidental, good-faith violations of this policy;
> - **Authorized concerning any relevant anti-circumvention laws**, and we will not bring a claim against you for circumvention of technology controls;
> - **Exempt from restrictions in our Terms of Service (ToS) and/or Acceptable Use Policy (AUP)** that would interfere with conducting security research, and we waive those restrictions on a limited basis; and
> - **Lawful, helpful to the overall security of the Internet, and conducted in good faith.**
>
> You are expected, as always, to comply with all applicable laws. If legal action is initiated by a third party against you and you have complied with this policy, we will take steps to make it known that your actions were conducted in compliance with this policy.
>
> If at any time you have concerns or are uncertain whether your security research is consistent with this policy, please inquire through [`security@webomage.com`](mailto:security@webomage.com) before going any further.
