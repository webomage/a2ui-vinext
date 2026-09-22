<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-08-15 (LATEST) — **T134 closed (12/12); public assets were uncacheable and now aren't; two dead -->

## ⭐ PICK UP HERE — 2026-08-15 (LATEST) — **T134 closed (12/12); public assets were uncacheable and now aren't; two dead paths found by the credential surface.**

**What shipped**
- **[[T134]] AC11 → ticket COMPLETE.** `just credential-probe` (routes + leak) with a 13-case RED
  proof (`credential-probe-test`, registered in `test-suites.json`), plus the surface it guards:
  `/system/credentials` + `credential-source.ts`. The route gate said *"zero write routes TRUE BUT
  UNTESTED"* until the page existed — now it sees 4 surface routes and passes on **evidence**.
  Every row leaves through `toRenderable()`, so a full SHA-256 never reaches the DOM (asserted).
- **[[T216]] AC1-AC3 — cache headers, verified LIVE.** All 481 public files shipped
  `max-age=0, must-revalidate`; only `/_astro/*` was cached, by the adapter's own injected rule.
  Tiered `_headers` now in web/cp/join/job: fonts `1y immutable` · images `1d + SWR 7d` ·
  og-image `1h` · `llms*.txt` `15m`. Re-probed after deploy — all five paths confirmed.
- **`sync-secrets` no longer writes empty strings.** It interpolated `KEY="$KEY"` in **shell**, so
  an unset var wrote `""` — a present, timestamped secret holding nothing (digest `e3b0c442…`).
  Now delegates to `sync_supabase_secrets.py`, which skips empties **loudly**. `dry` mode added.
- **Research gate now consults DECIDED DEBT.** It scanned board/tickets/specs/code/knowledge but
  never `TECH-DEBT.md` or the `tech_debt` store — so a ticket could duplicate a decided row.

**Filed, queued, unstarted**
- **[[T215]]** `vectorize-vault` throws `GOOGLE_API_KEY not configured` on **every** run; the CF
  Worker holds neither GOOGLE nor GEMINI. ⚠️ The fix is **not** a Google key — the worker already
  binds Workers AI (`"ai"`, *no cost per token*) and the file's `Env` declares an **unused** `AI`.
  **Confirm output dimensionality (forced to 1024 today) BEFORE coding.**
- **[[T217]]** structured technical-discovery interview — the **missing middle** between T16c's
  intake (`stack` is ONE coarse field) and T4's blueprint proposals. The profile↔blueprint **diff
  IS the customization list**, which is what makes the price defensible.

**🔴 OWNER ACTIONS (I am blocked, not deferring)**
1. **CF → Images → Transformations → enable for `webomage.com`** (T216 AC4/AC5). Polish is **Pro+**
   and this zone is **Free Website** (verified via API), so transformations are the ONLY CF image
   path. The API reports `editable: False` for the deploy token — token scope or plan gate, not
   distinguishable without the dashboard, so it is not guessed.
2. **Secrets:** delete `GOOGLE_API_KEY` (legacy; ai-router already falls back to GEMINI, which is
   present + agreed). `HONEYCOMB_API_KEY` has a real value in Infisical that is **not in the sync
   list** and was never pushed. Four `UPWORK_AGENCY_*`/`UPWORK_CLIENT_*` keys hold `""` — owner says
   the agency key was **never granted**.

**Gotcha earned this session**
**Presence is not content.** Six secrets read as "configured" while holding the empty string. A
digest that looks fine is the exact failure mode — compare against `e3b0c442…` (SHA-256 of `""`)
before trusting any "is it set?" signal. Two false greens were also caught inside the new probe
itself: a value-scan that "scanned 21 secrets" that were `PATH`/`HOME`/`LANG`, and a shape walker
applying the wrong whitelist per depth.
