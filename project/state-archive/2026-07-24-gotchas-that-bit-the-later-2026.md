<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ### 🔴 Gotchas that BIT the LATER 2026-07-24 session (read these first) -->

### 🔴 Gotchas that BIT the LATER 2026-07-24 session (read these first)

- **`just test` (vitest) has been DEAD since 2026-07-09** — `Cannot find module
  'undici/lib/handler/wrap-handler.js'`: the `undici >=7.28.0` floor resolves to **8.7.0**, which
  dropped the path `jsdom@29` needs. **Do not claim "tests pass" for anything in that window.**
  Proven pre-existing via `git log -S` on the lockfile (`fc78a91f`). It stayed invisible because
  **pre-push gates on `astro check` + audit and never runs `pnpm test`**. Now dated in **TECH-DEBT
  D7** (fix is a real tradeoff: pin undici 7.x vs bump/patch jsdom vs scope an override to jsdom's
  undici — and put the suite behind a gate or it rots again).
- **`UnicodeDecodeError` is a `ValueError`, NOT an `OSError`.** Any file-scanning tool with
  `except OSError` around `read_text()` dies on the first binary/non-UTF-8 file = denial-of-gate.
  Route every read through one helper catching both (see `project/scripts/discovery.py:read_text`).
- **Ticket-sync will NOT close your GH issue.** The pre-push background sync wrote an empty log, and
  foreground `just sync-tickets` **exceeds 5 minutes** (full board). At archive time close the one
  issue directly: `GH_CONFIG_DIR=~/.config/gh-w0m gh issue close <n> --repo casualuser/webomage.com
  --reason completed --comment "…"`, then verify `--json state`.
- **GREP `TECH-DEBT.md` BEFORE FILING A ROW.** I filed D24 as a duplicate of the existing **D7** and
  had to withdraw it at the archive gate. Search the register first, then enrich the existing row.
- **`openspec archive` prepends TODAY's date to an already-dated change name** → double-dated dirs
  (`2026-07-25-2026-07-24-…`). 4 archived changes now look like this; it's consistent — don't
  "fix" one in isolation.
- **`gitleaks detect` on the whole repo exceeds 2 minutes** — scope it:
  `gitleaks detect --log-opts="<base>^..HEAD"`.
- **`timeout` on this machine is a Python script, not GNU timeout** — `timeout 180 <cmd>` fails with
  `ModuleNotFoundError: No module named 'examples'`. Use the tool's own timeout or the Bash tool's.
- **Safe to know:** `just --justfile <any> --summary` does **not** execute backtick assignments
  (verified with a `touch` probe) — parsing an untrusted justfile is safe; running a recipe is not.
