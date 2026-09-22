<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0m. 🆕 OWNER ASK 2026-07-25 (evening) — enforce Infisical for secrets in w0m skills + tools. **Owner said FILE AND BU -->

### 0m. 🆕 OWNER ASK 2026-07-25 (evening) — enforce Infisical for secrets in w0m skills + tools. **Owner said FILE AND BUILD.** Unstarted.

> *"we have to enforce in w0m skills and tools usage infisical for secrets sync"*

**Not yet ticketed.** Partial grounding done — do not re-derive:
- The **contract already exists but is only half-enforced.** `.w0m/sdlc.json → toolchain` declares
  `commands_via: just` / `secrets_via: infisical`, both `required: true` in `tools-policy.json`, and
  `just sdlc-doctor` verifies the *interfaces are present*. It does **not** verify that a skill or a
  tool actually takes its secrets from Infisical.
- **Only 2 of the 27 canonical skills mention `infisical` at all** — `w0m/w0m-deploy/SKILL.md` and
  `w0m-sdlc-start/SKILL.md`. So the standard is documented in CLAUDE.md and in two skills, and is
  otherwise unenforced across the skill corpus.
- `toolchain.exempt` currently excuses `wom7md`, `wom7skills`, `wom7ext`, `wom7sec` — the last two
  with the explicit note *"add `.infisical.json` when it grows a deploy/secret surface"*, which is a
  standing condition nobody re-checks.
- Related lever that already exists: `just discovery --enforce` gates declared-command drift, and
  **`enforce_raw` is still `false`** ([[T130]]) — flipping it is blocked on one raw call in
  `.husky/pre-push:25`.
- Likely shape: a gate that fails when tracked automation reads a secret from a file/`.env` instead
  of `infisical run`, plus a skills-corpus rule. Pairs naturally with **[[T131]]** (which also wants
  a per-stack policy read) and with §0n below.
