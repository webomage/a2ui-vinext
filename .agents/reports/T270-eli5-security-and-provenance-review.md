# T270 — `eli5` Skill Security, Upstream Provenance & Candidate Comparison Review

- **Ticket:** [[T270]] (`Adopt the community eli5 skill into the default project skill set`)
- **Date:** 2026-10-21
- **Scope:** AC1, AC2, AC3, AC4, AC6, AC8, AC9, AC10
- **Related Governance:** [[T127]] (fully-qualified skill provenance & lockfile), [[T135]] (resolve by content diff, never by name), [[T177]] (propagation beyond estate boundary), [[T182]] (skills catalogue & client portability), [[T183]] (Design System boundary)

---

## 1. Executive Summary

Two distinct community skills publish under the bare name `eli5`:

1. **`anthropics/claude-plugins-community@eli5`** (author: Thariq Shihipar, MIT) — a 321-byte pure-prose marketplace plugin that generates standalone HTML visual explainers (*"big visuals and few words"*).
2. **`DreambigOu/ELI5`** (author: Andrew Ou / `DreambigOu`, MIT) — a standalone GitHub repository containing a 7,965-byte audience-adaptive prose skill (`skills/eli5/SKILL.md`) **plus** an executable Python evaluation harness (`eli5-workspace/run-evals.py` and `eli5-workspace/test_run_evals.py`, 22,823 bytes of Python).

Per **[[T135]]** (*resolve by content diff, never by name*), these two artefacts are unrelated works sharing a name and **must never both be installed as `eli5`**. Following the security audit, provenance verification, and weighted comparison below:

- We **adopt a single governed canonical `eli5` skill** in `wom7skills/skills/eli5/SKILL.md` (`provider: w0m-native`, `portable: true`) that combines standalone visual HTML explainer output with audience-adaptive calibration in **100% pure prose (zero executable surface)** and includes the mandatory **[[T183]]** Design System boundary note.
- We **reject installing `DreambigOu/ELI5`'s `eli5-workspace/` Python evaluation harness**, preserving `ships_executable: 0` for `eli5`.
- We **explicitly discount** `DreambigOu/ELI5`'s self-reported `83.3% vs 41.6%` pass-rate figure as an unverified vendor claim over a 3-prompt self-authored rubric (AC10).
- We extend `project/policies/skills-policy.json` (and `skills-policy.schema.json` + `skills_catalogue.py`) with an explicit **`"defaults"`** tier for unconditional, stack-independent project skills (`eli5`, `feynman`), rather than fabricating a fake `detect:` rule in `stacks-policy.json` (AC3).

---

## 2. AC1 — Content-Hashed Security Review of `anthropics/claude-plugins-community@eli5`

### 2.1 Pinned File Inventory & SHA-256 Digests

Inspected at `anthropics/claude-plugins-community` commit `f4c9452f5ca091f1be7064d9faab1b001ea21645` (vendored directory `./eli5`):

| File Path | Size (Bytes) | Git Blob SHA-1 | Content SHA-256 Digest |
|---|---:|---|---|
| `eli5/README.md` | 197 | `b0dbc035cda6de4cc86c9758a7956b7da7140a1e` | `2b4f2ce086e003fcfee1075fe1cf0e86253d9ac21d477f881b39a7f3e7957ffe` |
| `eli5/.claude-plugin/plugin.json` | 280 | `32f0a009096fb0a239cb8a57a33e8c068804a4f3` | `6745ff91dd0ae7fea5fb51ef933390313a677da04aaa4d7a05052942777be11f` |
| `eli5/skills/eli5/SKILL.md` | 321 | `d59eb05f3b0790b2259a29d7a474f0bc479893d7` | `3bb95cd13852051c5a1862e8b94da1de7cfba7415d418ab0ca4d762527d1b9a5` |

### 2.2 Verbatim Inspected Contents

**`eli5/README.md` (197 bytes):**
```markdown
# eli5

Explain any topic like I'm 5.

```
/eli5 how does DNS work
```

Produces a HTML artifact with big pictures and very few words that explains the topic to someone who knows nothing about it.
```

**`eli5/.claude-plugin/plugin.json` (280 bytes):**
```json
{
  "name": "eli5",
  "version": "1.0.0",
  "description": "Explain any topic like I'm 5: a dead-simple HTML picture explainer with big visuals and few words. Use /eli5 <topic>.",
  "author": {
    "name": "Thariq Shihipar"
  },
  "license": "MIT",
  "keywords": ["explain", "eli5", "learning", "explainer", "html"]
}
```

**`eli5/skills/eli5/SKILL.md` (321 bytes):**
```markdown
---
name: eli5
description: Explain a topic like I'm a 5 year old. Use when the user types /eli5 <topic> or asks for a dead-simple picture explainer of how something works.
---

# eli5

Explain like I'm someone who knows nothing about this topic, using a HTML artifact with big pictures and few words.

Topic: $ARGUMENTS
```

### 2.3 Security Surface Verdict (`anthropics/claude-plugins-community@eli5`)

| Vector | Measured Finding | Status |
|---|---|---|
| **Executable Surface** | `0` scripts or binaries (no `.sh`, `.py`, `.mjs`, `.js`, `.ts`, or `+x` files). | PASS (`0` exec) |
| **Network Egress** | `0` URLs, `curl`, `wget`, `fetch`, or external endpoints in prose or metadata. | PASS (`0` egress) |
| **Filesystem Writes** | `0` host file write instructions outside emitting an HTML explainer artifact when requested. | PASS |
| **Credential Access** | `0` references to `.env`, `~/.ssh`, `~/.aws`, `~/.gnupg`, `id_rsa`, tokens, or secrets. | PASS |
| **Prompt Injection / Gate Bypass** | `0` findings under `wom7skills/skill_audit.ts` (5 prose rules). | PASS |

---

## 3. AC2 — Upstream Provenance to `[[T127]]` Standard

| Attribute | Recorded Value |
|---|---|
| **Fully-Qualified Identifier** | `anthropics/claude-plugins-community@eli5` |
| **Marketplace Repository** | `https://github.com/anthropics/claude-plugins-community` |
| **Pinned Commit SHA** | `f4c9452f5ca091f1be7064d9faab1b001ea21645` (committed 2026-08-21) |
| **Marketplace Source Path** | `"source": "./eli5"` (vendored directly inside the marketplace monorepo; no independent upstream repo) |
| **Declared Licence** | `MIT` (in `eli5/.claude-plugin/plugin.json`) |
| **Author vs. Host Distinction** | **Author:** Thariq Shihipar (individual contributor). **Host:** `anthropics/claude-plugins-community`. Anthropic hosting the community marketplace directory is **not** Anthropic authoring or maintaining the skill. |
| **Who Can Change It & Reachability** | Maintainers with write access to `anthropics/claude-plugins-community` can merge PRs modifying `./eli5`. Because `./eli5` is vendored inside the monorepo, the repository `HEAD` moves whenever *any* community plugin in the catalogue changes. By governing `eli5` in `wom7skills/skills/eli5/SKILL.md` and locking its SHA-256 integrity in `.w0m/skills.lock.json`, upstream marketplace commits **cannot** reach `w0m` or client sessions without an explicit canonical edit, version stamp, and lockfile update. |

---

## 4. AC8 — Repo-Standard Audit of Second Candidate (`DreambigOu/ELI5`)

### 4.1 Repository Identity & Maintenance Signal

| Attribute | Measured Value |
|---|---|
| **Repository URL** | `https://github.com/DreambigOu/ELI5` |
| **Pinned Commit SHA** | `a766623b062331fdde53467001379b4ddf3acc2f` (2026-03-18T03:35:19Z) |
| **Git Tree SHA** | `b1429f66ead33785ba6cca68adc98aabe2879711` |
| **Author** | Andrew Ou (`DreambigOu`, `dreambig.ou@gmail.com`) |
| **Licence** | `MIT` (`LICENSE`, 1,056 bytes) |
| **Commit History & Bus Factor** | **10 commits total, 1 author (Bus Factor = 1)**, 0 open issues, 0 PRs. The 258 GitHub stars and 9 forks are a popularity signal, not a maintenance or review signal. |

### 4.2 Full Recursive File Inventory & SHA-256 Digests (`DreambigOu/ELI5`)

| File Path | Size (Bytes) | Git Blob SHA-1 | Content SHA-256 Digest | Surface Class |
|---|---:|---|---|---|
| `LICENSE` | 1,056 | `14fac913ccf80234b1848540089a3bbcb6e5283d` | `1126322e2cc8d165adc4c792eeb195717de2bcc7b39be1ce77959d78e87ef685` | Legal notice |
| `README.md` | 5,180 | `041914a3c611ae2869637c413a442c5c4dd5a1c3` | `67cf8d9493f36059ce8861f19df00d0c3c06a606b9c7137e8fc991c4dc2f3964` | Documentation |
| `skills/eli5/SKILL.md` | 7,965 | `b0644b6cbc4839749aeecf0b340074be9e88f475` | `a671efd44a818aee7dbe4ea2ec634079401c3f578c08cb634c2b6181ced2dbe9` | Prose skill |
| `eli5-workspace/eval-results.md` | 4,863 | `38bbc55e7a5eb7f1e4514b99c0109f01a2137ba0` | `d8f8c6a53ddc86b56453081d8022984b9d70e75f15823505f4a700861ff8e2ee` | Eval doc |
| `eli5-workspace/eval-workflow.md` | 3,677 | `35c21722f7787fd87f7136629167eb498b76e54e` | `d3d95f4fad9fc365ea32068ea13220e908a101700318f1a33ac02e678806bdb1` | Eval doc |
| `eli5-workspace/evals.json` | 1,853 | `02d063934342b78279e04cf03b3d01c28d3fda5b` | `754f6a809ed904d1cb91f755914b0bac87a0998e066c87452f72d6f2a6a5a615` | Eval fixture |
| `eli5-workspace/run-evals.py` | 10,038 | `62ac3550dc8b80bb95dbb7630dd389f174f37690` | `7ba67193fd039fe3aea76463d5f6fb3e68562089bc8b50e141f16bb535519681` | **Executable Python** |
| `eli5-workspace/test_run_evals.py` | 12,785 | `9299dacdd0b01600746f433ecaf1a1083a4f22be` | `c597d400a6c804486dddab87be947e89cfea82c4c139be18492c3e9f6bfe1a4f` | **Executable Python** |

### 4.3 Why AC1's "Zero Executable Surface" Finding Does NOT Transfer to `DreambigOu/ELI5`

Unlike `anthropics/claude-plugins-community@eli5` (which is 321 bytes of pure prose), `DreambigOu/ELI5` ships **22,823 bytes of executable Python** in `eli5-workspace/`:

1. **Host Subprocess Execution:** `eli5-workspace/run-evals.py` (lines 61–67) executes `subprocess.run(["claude", "-p", prompt, "--output-format", "text"])` directly on the host machine for every test configuration and again for every LLM-as-judge grading pass.
2. **Host Filesystem Reads & Writes:** `run-evals.py` reads `~/.claude/skills/eli5/SKILL.md` (`DEFAULT_SKILL = Path.home() / ".claude" / "skills" / "eli5" / "SKILL.md"`) and writes `iteration-N/` directories containing `outputs/response.md`, `timing.json`, `grading.txt`, `grading.json`, `summary.txt`, and `config.json`.
3. **Supply-Chain Policy Impact:** Under `project/policies/skills-policy.json → detect_executable` (`.py` suffix), vendoring `DreambigOu/ELI5` as a repo unit would flag `eli5` as shipping runnable code (`ships_executable`), requiring a host-execution override in `skills-policy.json` for a skill that needs zero runtime code.

---

## 5. AC10 — Explicit Discount of Upstream's Self-Reported `83.3% vs 41.6%` Eval

`DreambigOu/ELI5/README.md` and `eli5-workspace/eval-results.md` report an **`83.3%` pass rate with the skill (10/12 assertions) versus `41.6%` baseline without the skill (5/12 assertions)**.

Inspection of `eli5-workspace/evals.json` and `eli5-workspace/run-evals.py` establishes why this figure must be **discounted and never repeated as a w0m measurement**:

1. **Tiny, Author-Defined Sample (`N = 3` prompts, `12` binary assertions):** The entire benchmark consists of 3 prompts (`explain-db-index-age5`, `explain-codebase-manager`, `explain-git-merge-5th-grader`) with 4 assertions each, run once (`iteration-1`). A single assertion flip moves the score by `8.3%`.
2. **Rubric Circularity:** Assertions in `evals.json` test formatting rules that the author's `SKILL.md` explicitly instructs (for example, test 2 asserts *"Contains no code blocks or inline code formatting — purely prose"* and *"Response is under 500 words"* for a manager explanation, penalizing baseline responses that include a short directory tree).
3. **Unpinned Non-Deterministic Judge:** `grade_response()` invokes `claude -p "You are a strict grader..."` with no model pin, no temperature=0 setting, and no human calibration baseline.

**Decision (AC10):** The `83.3% vs 41.6%` figure is **formally discounted as an unverified vendor rubric claim**. It is documented here for audit completeness and must never be cited as empirical justification in `w0m` documentation.

---

## 6. AC9 — Weighted Candidate Comparison & Name-Collision Resolution

Per **[[T135]]** and **[[T182]] AC4**, two skills must never be installed under the same `eli5` name. We evaluate four options across five weighted architectural criteria:

| Criterion | Weight | Option A: Raw `anthropics/claude-plugins-community@eli5` (321 B only) | Option B: Raw `DreambigOu/ELI5` Repo (with `eli5-workspace/*.py`) | Option C: Install Both Under Separate Names (`eli5-html` + `eli5-audience`) | Option D (Recommended): Unified `w0m-native` `eli5` in `wom7skills/skills/eli5/SKILL.md` (Pure Prose, Zero Exec) |
|---|---:|---|---|---|---|
| **1. Zero Executable Surface & Supply-Chain Safety** | **30%** | 5/5 — 0 scripts, 0 network, 0 host exec | 2/5 — ships 22.8 KB Python (`run-evals.py`) invoking `claude -p` on host | 2/5 — if `DreambigOu/ELI5` is vendored raw, still carries Python eval surface | **5/5** — 100% pure Markdown prose (`ships_executable: []`); excludes `eli5-workspace/*.py` |
| **2. Project Default Utility (Explaining w0m & Client Systems)** | **25%** | 3/5 — emits HTML picture explainers, but lacks audience calibration (manager, engineer, client, 5th grader) | 4/5 — strong audience calibration tables, but lacks the `/eli5` visual HTML explainer workflow | 3/5 — splits one user intent ("explain this clearly") across two slash triggers | **5/5** — supports both audience-calibrated explanation (Age/Role/Education) and standalone visual HTML explainer artifacts |
| **3. Governance & Provenance Fit (`[[T127]]` / `[[T131]]`)** | **20%** | 3/5 — marketplace monorepo commit moves on unrelated plugin edits; no version stamp | 3/5 — bus factor 1 (10 commits, 1 author) | 2/5 — doubles manifest/lockfile/survey maintenance | **5/5** — governed in `wom7skills/skills-registry.json`, stamped by `version.ts`, locked in `.w0m/skills.lock.json`, attribution in `NOTICE.md` |
| **4. Client Portability (`[[T182]]` / `[[T177]]`)** | **15%** | 4/5 — portable prose, but no [[T183]] DS boundary note | 3/5 — `run-evals.py` hardcodes `~/.claude/skills/eli5/SKILL.md` | 3/5 — cognitive overhead in client repos | **5/5** — zero w0m-bound path markers; classified `portable` in `portability.jsonc`; propagates cleanly via `just skills-install-generic` |
| **5. Design System Boundary Clarity (`[[T183]]`)** | **10%** | 2/5 — silent on why HTML artifacts bypass `@webomage/ui` | 3/5 — prose-only output by default | 2/5 — inconsistent output contracts | **5/5** — carries explicit one-line `[[T183]]` DS boundary note in `SKILL.md` |
| **Weighted Total** | **100%** | **3.65 / 5.00** | **2.95 / 5.00** | **2.40 / 5.00** | **5.00 / 5.00** |

### Why Option D Wins and Why Raw `DreambigOu/ELI5` Lost

1. **Zero Executable Surface Preserved:** By authoring and governing `wom7skills/skills/eli5/SKILL.md` as a pure-prose `w0m-native` skill (attributing both MIT upstreams in `skills-registry.json` and `NOTICE.md`) and **excluding `eli5-workspace/`**, the estate keeps its `ships_executable` count at exactly `2` (`w0m:webapp-testing` and `artemio:idea-refine`, plus `mmd-validate` overrides).
2. **No Name Collision (`[[T135]]`):** Exactly one skill resolves under `eli5` across `wom7skills`, `.agents/skills/eli5`, `.w0m/skills.json`, and `.w0m/skills.lock.json`.
3. **Solves Both Owner Use Cases:** Supports `/eli5 <topic>` standalone visual HTML explainers (from Thariq Shihipar's `anthropics/claude-plugins-community@eli5`) **and** audience-calibrated explanations for kids, managers, directors, engineers, and non-technical stakeholders (from Andrew Ou's `DreambigOu/ELI5`), while recording the **[[T183]]** Design System boundary in one line.

---

## 7. AC3, AC4, AC6 & AC7 — Governance Architecture & Propagation Record

1. **AC3 — Unconditional Default Tier (`project/policies/skills-policy.json`):**
   - Added top-level `"defaults"` object to `project/policies/skills-policy.json` and `project/policies/skills-policy.schema.json`.
   - Declares `eli5` and `feynman` as stack-independent, unconditional default project skills (`portable: true`), validated by `wom7web/project/scripts/skills_catalogue.py` without any fabricated `detect: dep:<name>` rule.
2. **AC4 — Plugin-to-Governed-Skill Relationship:**
   - Rather than leaving `eli5` as an unversioned marketplace plugin in `~/.claude/plugins/` or hiding it in `exclude`, `eli5` is promoted into the canonical `wom7skills/skills/eli5/SKILL.md` store, declared in `.w0m/skills.json` (`w0m` root and `wom7web`), and integrity-hashed in `.w0m/skills.lock.json`.
3. **AC6 — Design System Boundary Note (`[[T183]]`):**
   - Recorded directly in `wom7skills/skills/eli5/SKILL.md`:
     > **Design System boundary ([[T183]]):** HTML explainer artifacts generated by `eli5` are standalone, self-contained visual explainers and intentionally do not import `@webomage/ui` (`packages/ui`) runtime components.
4. **AC7 — Propagation to Estate & Client Projects (`[[T177]]` / `[[T182]]`):**
   - **Estate repos (`w0m`, `wom7web`):** Propagated via `just skills-sync` (`tsx skills.ts`) into `.agents/skills/eli5/SKILL.md` and `wom7web/.agents/skills/eli5/SKILL.md`, and marked `bootstrap: true` in `wom7skills/skills-registry.json`.
   - **Client / managed projects:** Classified under `portable` in `wom7skills/portability.jsonc` (`35` portable skills, `0` w0m-bound markers tripped) and verified against a real managed project via `just skills-install-generic <target> --dry-run`.
