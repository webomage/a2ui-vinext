<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 0u. 🆕 OWNER QUESTION 2026-07-25 (late) — should the SDLC audit package/lib licenses? **ANSWER: yes. Grounded, unbuil -->

### 0u. 🆕 OWNER QUESTION 2026-07-25 (late) — should the SDLC audit package/lib licenses? **ANSWER: yes. Grounded, unbuilt.**

> *"should we do audit for license type of used packages/libs in repos in sdlc ?"*

**Recommendation: yes — and build it in the same pass as §0n gaps 2–4 and §0p.** All three are the
same mechanism (a `just` recipe + a `stacks-policy.json` role + a pre-commit hook + `sdlc-doctor`)
across the same repos; doing them separately means three passes over identical plumbing.

**Why the marginal cost is low:** `deps-policy.json` already exists as the natural policy home (keys:
`repos`/`toolchain`/`lockstep`/`floors`/`exceptions`/`aligned_advisory` — a `licenses` block fits
beside `floors`), `just deps-check` already runs cross-repo in pre-push, and **osv-scanner is already
installed in every repo's hook stack** and its SBOM output carries license data.

**Measured 2026-07-25 — do not re-derive:**
- **Zero license tooling exists** — nothing in either justfile, nothing in `deps-policy.json`, no hook.
- 🔴 **No repo declares a `license` field** in `package.json` (wom7web, wom7api, wom7cfworkers, wom7ext
  — all absent).
- 🔴 ~~**`wom7api` and `wom7ext` are not marked `private: true`** (wom7web and wom7cfworkers are).~~
  An unlicensed, non-private package is one `npm publish` away from being published by accident.
  🔴 **PARTLY WRONG — corrected 2026-07-25 (late night).** `wom7ext/extension/package.json` **does**
  carry `private: true`; the offender is the unnamed **repo-root** `wom7ext/package.json` (same
  wrong-level read as §0n gap 3 above). Re-measured across **all seven** manifests in the estate:
  **`private` is absent on exactly two — `wom7api` and `wom7ext` (root)** — and **`license` is absent
  on all seven**, so that half of the finding *understated* the gap.
  ⚠️ **`deps-policy.json` tracks only four of the seven manifests** — it has no entry for
  `wom7ext/package.json`, `wom7ext/extension-ff/package.json`, or `wom7skills/package.json`. Any gate
  must **discover** manifests, not read that list, or it repeats this miss.

**Two w0m-specific reasons this matters more here than in a typical repo:**
1. **Vendored *content* is a license surface that dependency scanning cannot see.** [[T127]] vendors
   **~50 external agent skills** from GitHub, now with pinned provenance — and at least one
   (`mcp-builder`, byte-identical to `anthropics/skills`) explicitly declares `license: LICENSE.txt`,
   **a file our copy does not include** (§0a: it was vendored `SKILL.md`-only, 1 of 10 upstream files).
   A `package.json`-only audit would report a clean bill of health over all of it.
2. **`wom7mlx` vendors 13 upstream ML repos** (`mlx`, `mlx-lm`, `mlx-rs`, `candle`, `mlx-vlm`, …) as
   independent clones. Same blind spot, much larger.

**The real exposure** is copyleft (GPL/AGPL) reaching a shipped commercial bundle — not permissive-license
bookkeeping. Scope the gate to that: fail on copyleft in anything shipped, advisory elsewhere.

⚠️ **Same vacuous-gate trap as §0p:** a check that reads only *declared* license fields is worthless.
It has to cover **transitive** dependencies **and** the vendored trees, or it will pass while the actual
risk sits in `.agents/skills/` and `wom7mlx/`.
