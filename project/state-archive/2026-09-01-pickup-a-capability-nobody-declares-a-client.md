<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-09-01 — **a capability nobody declares, a client repo we wrote into, and a silent MTU black hol -->

## ⭐ PICK UP HERE — 2026-09-01 — **a capability nobody declares, a client repo we wrote into, and a silent MTU black hole.**

**[[T294]] filed — workspace mode is built, proven by ten probes, and declared by NOBODY.** [[T268]]
closed 7/7 with schema + inventory support for a `root` + `repos` workspace, red-tested against a
subdirectory root. Measured today: **all five registered projects are `simple`, w0m included**, whose
`root` is `wom7web` — so the estate's own seven-repo shape is invisible to its own registry. The cost
landed the same week: an AGY registration of BridgeRoad used the simple shape on a non-repo root and
`just client-inventory` hard-failed **exit 2 for the whole estate**. Owner direction: the workspace
level becomes a repo we own — bare **`w0m`** for the estate (our own project, the whole wom/webomage
stack), **`w0m-<slug>`** per client. That is the only shape where one-level-up, inside-a-declared-repo,
git-tracked and not-in-the-client-repo all hold at once. Closes **D32**. AC5 is load-bearing.

🔴 **Our governance config had been written INTO the client's git repo, and is now out.**
`.w0m/{sdlc,skills}.json` landed in `_proj/bridgeroad/BridgeMvp/` — `github.com/BridgeRoad/bridgeroad-app`,
a third-party org — untracked and unignored on `dev`, carrying our Infisical invocation
(`--env=beta`, the live env), `gh_account: casualuser`, and a roles block naming one person in five
positions. Removed; `.w0m/` added to that clone's `.git/info/exclude` (local-only, never pushed, and
it does not touch Elena's ability to push her own work). The BridgeRoad registration is **held** until
T294/[[T265]] AC1 defines the tier, preserved verbatim at `project/clients/bridgeroad/`.

**The `bridgeroad` micro VM is real: Ubuntu 26.04 LTS arm64, 2 CPU / 4 GB / 20 GB (3.0 GB actual),
shell-only, Docker CE 29.7.2 + Compose v5.5.0 verified end to end.** 🔴 **Read
`project/clients/bridgeroad/vm-seed/README.md` before touching any Tart guest on this machine** — six
traps, and the sixth explains the other five. The host runs seven `utun` interfaces with MTUs as low
as 1000 and ICMP is filtered, so path-MTU discovery black-holes: at the default 1500 the TCP handshake
and DNS succeed while **every HTTP payload silently vanishes**. `apt-get update` hung 14 minutes with
no output; `curl` returned nothing rather than failing. Same URL, only MTU changed — 1500 hangs, 1400
hangs, **1280 returns 200 in 0.74s**. Pin it on the link *and* in `/etc/docker/daemon.json`, because
Docker's bridge defaults to 1500 and reproduces it inside containers. ⚠️ Do not diagnose with ping:
ICMP is filtered, so every size reports DROPPED and tells you nothing.

⚠️ **`tart ip` is not trustworthy here** — it reads the MAC-based lease while these images DHCP with a
client-id, so it reported `.13` while the guest was on `.15`, then `.16`. Read `/var/db/dhcpd_leases`.

**Two security floors raised**, both found by pre-commit rather than by anyone looking:
`postcss-selector-parser` ≥7.1.3 (Medium) and, exposed by refreshing that lockfile,
`browserslist` ≥4.28.7 (**High 7.5**) which the stale resolution had been hiding.


**`just quartz`** — the Obsidian vault as a browsable local site, Quartz v5 pinned at `v5.0.0`.
951 of 3,683 markdown files serve. The corpus boundary is DERIVED, not invented: `.obsidian/app.json`
already declares what the vault is, and Quartz honours `.gitignore` natively, so the two compose.
Three upstream defects are worked around and documented where they bite — the worst is
`obsidian-flavored-markdown`'s `isTagChar`, which calls `String.fromCodePoint` on micromark's
NEGATIVE line-ending codes, so a mermaid hex colour or an `issue #226` reference kills the whole
build with an error that names `Head.tsx`.

**`just decommission-check`** — the tombstone log had 5 entries nothing read; the audit checked 2
hardcoded terms, only one of which matched a tombstone. `openrouter` was checked while appearing
nowhere in the log. Each tombstone now carries an `absent` block. **D15 closed as a consequence**:
a gate must read a versioned file, so the log moved into wom7web and the repo chose itself.

**`just ignore-audit`** — 540 tracked-but-ignored files estate-wide. git cannot un-track a file by
adding a pattern later, so a rule written after the fact is silently inert and invisible from both
sides. 🔴 The find that justifies it: **wom7ext's `extension/icons/*.png` are declared in
`manifest.json` and were matched by `*.png`** — delete and re-add one and `git add` skips it
silently. Also: no repo ignored `*.key`, only wom7api ignored `*.pem`, wom7mlx had no `.env` rule.

**The CV had fallen back to the hand-written experience section** (regression `0f741646`, 08-29).
It led with VXG Inc — a role that ENDED Feb 2026 — with no ongoing engagement at all. 2,667 → 1,158
words, 28 nested engagements flattened to 10. Restored and verified BYTE-IDENTICAL to what
`just cv-experience` generates. 🔴 **`just cv-validate` reported "no problems" for two days and was
right to**: `CV_GLOBS` covers 10 content-collection pages and the broken file was not among them.
**A corpus gap, not a rule gap** — the shape this estate keeps finding. Now widened, with
`PROSE_SURFACES` declaring per document whether it must carry a current role.

**`just cv-gallery`** — 7 CV documents × 6 PDF templates = 42, plus an index. No CV PDF here was
actually single-page (all twelve were A4 at 2–11 pages), so `single-page` is that idea implemented
rather than assumed.

⚠️ **`aleksei-tcelishchev-cv-upwork.md` is NOT defective** — I flagged it and was wrong. Canonical's
only ongoing entry is Webomage, the *consultancy*, not an Upwork contract, so an Upwork-scoped
document has nothing current to show. Requiring one would push someone to invent an engagement.

✅ **`OPENROUTER_KEY` was removed from Supabase 2026-08-31** — verified against the live store (zero
occurrences, non-vacuous query, count 90 → 89) and `credential-snapshot.json` regenerated.
🔴 **OWNER ACTION REMAINS: revoke it at OpenRouter.** Removing our copy is not revocation — the key
is still valid there, and revocation is forward-looking anyway: it does not remove what they already
logged, which is the reason it was rejected.
📌 Same class, unaddressed: `LITELLM_*` and `HATCHET_CLIENT_TOKEN` (T196 measured it LIVE, `exp` 2126).

📌 Also open: the **CP panel for w0m members to manage their own CV** is ticket-shaped and unstarted
— it needs multi-tenant CV data and server-side PDF, and the CF path already exists
(`wom7cfworkers` binds `BROWSER` and `document-generator.ts` already calls `page.pdf()`). Cloudflare
Browser Rendering **is** the Gotenberg equivalent; nothing needs deploying.

---
