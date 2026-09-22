<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0p. 🆕 OWNER ASK 2026-07-25 (late) — README + standard human-facing files, enforced by SDLC. GROUNDED, unbuilt. -->

### 0p. 🆕 OWNER ASK 2026-07-25 (late) — README + standard human-facing files, enforced by SDLC. GROUNDED, unbuilt.

> *"we have to have README.md and other human used standard files in repos all checked enforced by sdlc"*

**Not ticketed.** Current state **measured 2026-07-25 — do not re-derive:**

| Repo | README | lines | other standard files |
|---|---|---|---|
| `wom7web` | ✅ | 58 | AGENTS.md · CLAUDE.md |
| `wom7api` | ✅ | 53 | CHANGELOG.md · CLAUDE.md |
| `wom7cfworkers` | ✅ | 77 | .editorconfig · CLAUDE.md |
| `wom7ext` | ✅ | 336 | CLAUDE.md |
| `wom7skills` | ⚠️ | **16** (stub) | CLAUDE.md |
| `wom7md` | 🔴 **NONE** | — | — |
| `wom7mlx/wom7mlx` | 🔴 **NONE** | — | AGENTS.md · CLAUDE.md |

**Across all 7 repos: zero `LICENSE`, zero `CONTRIBUTING.md`, zero `SECURITY.md`, zero
`CODE_OF_CONDUCT.md`; one `.editorconfig`; one `CHANGELOG.md`.**

⚠️ **The design trap to avoid, and it is the whole difficulty of this ask:** a file-exists check is a
**vacuous gate** — `wom7skills`' 16-line README would pass it while telling a human nothing, and this
project has now hit the vacuous-gate failure mode three separate times (T127's empty manifest printing
`0 managed … ✓`, T130's `enforce_raw`, and the wom7md hook that did not exist). Enforcement needs a
*substantive* bar (required sections? minimum length? a "what is this / how do I run it / where are the
docs" triple?), and that bar is a **decision the owner should make**, not one to infer.

Also decide: which files are **universal** vs **per-stack** (a `LICENSE` choice is a business decision,
not a lint), and whether `wom7md`'s exemptions apply. **Build this with §0n gaps 2–4** — same
mechanism (`.pre-commit-config.yaml` + a `just` recipe + a `stacks-policy.json` role + `sdlc-doctor`),
same repos, one pass.
