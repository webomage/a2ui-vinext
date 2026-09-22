<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0e. 🆕 FILED 2026-07-25 — T131: the w0m version schema is enforced NOWHERE -->

### 0e. 🆕 FILED 2026-07-25 — T131: the w0m version schema is enforced NOWHERE

`project/tickets/T131.md` (queued, **not started**, no GH issue yet — ticket-sync runs on push).
Owner ask mid-session: *do w0m skills/tools carry the required `YYYY.MM.DD-<unixtimestamp>` schema?
Apply it, verify it on doctor, and check what else should call it.* **Answer: no.** Audit is written
into the ticket — measured, do not re-derive:

- **THREE competing formats coexist.** The standard is produced at **`wom7api/justfile:15`**
  (`deploy_version := \`date +%Y.%m.%d-%s\``) and consumed by 7 `deploy-*` recipes + `_log-deploy`.
  A **second, non-conforming** format lives in **`wom7api/scripts/bump_version.js`**
  (`vYYYY.MM.DD-HHMMSS` — `v` prefix, local HHMMSS not a unix timestamp) and is **fully orphaned,
  zero callers**. A third is ad-hoc semver in `package.json` + skill `metadata.version`.
- **Skills are the biggest gap (the owner's first point).** Of the **27** canonical skills in
  `wom7skills/skills`, **16 carry NO version at all** — including `w0m` itself,
  `security-guardrails`, `w0m-mcp-builder` (renamed from `mcp-builder` by R4), `rbac-auditor` and every persona — and the 10 `w0m-sdlc-*`
  carry a hand-set two-component `"1.0"`/`"2.0"`. The only 3-part version belongs to an *imported*
  skill, so it is upstream's. **w0m's own skills are the unversioned ones** while all 49 external
  skills carry versions.
- **`just build` does not stamp at all** — it is a bare `pnpm run build`.
- **No live spec:** the standard exists only in the **archived** change
  `openspec/changes/archive/release-versioning/`; its deltas were never synced into `openspec/specs/`
  (unlike T130's, which landed in `sdlc_toolchain`). AC7 backfills it.
- 🔴 **Hard constraint, needs an owner call:** `2026.07.25-1784986544` is **NOT valid semver** — the
  grammar forbids leading zeroes in numeric identifiers, so the zero-padded `07` is illegal, and
  npm/pnpm require semver in `package.json`. **Proposed: `package.json` is EXEMPT**, schema governs
  deploy stamps + build artifacts + skills. The alternative (drop zero-padding everywhere) would
  change the existing deploy format and all recorded history.
- **Owner also framed it per-stack** ("different soft stacks determined by our tools") → T131 should
  read T130's `project/stacks-policy.json` and declare a **per-stack version carrier**, the same way
  `discovery` reads it for tools. `stacks-policy.json` currently has **no** versioning notion
  (verified: zero `version` keys beyond dependency floors).
- **A working reference implementation already exists** — see §0f. 1945 implemented this end-to-end
  (declared schema + one producer + stamped build/deploy + a gate proven red on 5 classes). Read
  `1945/.w0m/scripts/version_check.py` before writing w0m's version; it is the shape to port.
