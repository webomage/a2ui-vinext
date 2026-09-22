<!-- Rotated out of STATE.md by `just state-rotate` (T174). Content is VERBATIM. -->
<!-- Archived section: ## ⭐ PICK UP HERE — 2026-09-02 — **a VM that shipped unable to build, two "read-only" guarantees that were not, and a co -->

## ⭐ PICK UP HERE — 2026-09-02 — **a VM that shipped unable to build, two "read-only" guarantees that were not, and a compression win that costs more than it saves.**

**The BridgeRoad VM is ready for work.** `cd _proj/bridgeroad/vm-seed && python3 vm.py pull | start | up`
serves the client's stack at **HTTP 200** on the guest IP:8888. Published image:
`ghcr.io/casualuser/w0m-bridgeroad:2026.09.02-1788381805`, first one carrying Orca headless.

🔴 **The image shipped green and could not build anything, and the gate is why.** `docker compose
build` died in `apt-get` with *"Temporary failure resolving"* while the guest itself resolved fine.
Docker hands containers the vmnet gateway — measured, the one resolver they cannot use — while public
resolvers answer from a container and not from the guest. `daemon.json` now pins container DNS, plus
`default-network-opts` because `mtu` covers **only docker0**; every bridge BuildKit and compose create
was still born at 1500. **The gate ran `docker run hello-world`**, which uses a prebuilt image on
docker0 and touches **no DNS**, so it stayed green while the half the workflow uses was broken. It now
resolves from a fresh container FIRST — BuildKit persists its own `resolv.conf` and a
`systemctl restart docker` does not regenerate it, so the build gate alone passed from cache while
DNS was broken.

🔴 **Two read-only guarantees turned out to be promises.** The client's tree was shared WITHOUT tart's
`:ro` and mounted `-o ro` in the guest — a guest mount option is advisory, and one
`mount -o remount,rw` as root wrote through it, with the file appearing on the **host** inside the
client's workspace. That is what [[T265]] AC8 forbids. Share-level `:ro` is host-enforced and now
used. Separately `provision.py` decided VM existence with `if name in tart_list_stdout`, a **substring
match**: `"bridgeroad"` reported as existing while no VM of that name did.

**Shares are now `repo` (host-enforced ro) + `work` (rw, on the HOST).** `work` outlives the guest —
`vm.py pull --replace` destroys that disk, and so does a crash. `vm.py workspace` prepares the
read-write clone there, on the host **where the engagement git identity lives**; cloning inside the
guest would commit as the wrong person into someone else's history. Origin points at the client's real
remote, so delivery is a normal `git push`. ⚠️ Multiple tart shares must each be NAMED and appear as
SUBDIRECTORIES of one tag — hence `/mnt/w0m/repo`, not the old `/mnt/bridgemvp`.

**[[T303]] closed 5/5** — a rebuild used to destroy the VM you work in and exit 0 (it happened, to a box
serving the client's stack). The artefact and the working VM are now separate names in
`image-policy.json`, and `vm.py pull` makes the working VM a clone of the **published** image, so we
use the artefact by the consumer's own path. **[[T301]] AC1+AC2 done** — five of six policy schemas were
decorative; `clients-policy.schema.json` validated the live file with **0 errors** while its `tiers`
half caught **none** of five mutations. **[[T302]] filed** — gates for client projects do not run in the
w0m workspace.

**ZeroClaw compression is ON with the local model** (`custom.omlx`), and **measured**:
`python3 project/scripts/zc_compression_measure.py --turns 9 --reps 2`. Result over 2 reps — per-call
context **−4.7%**, but completion tokens **+7.3×** and wall time **1.7×**, so **total prompt tokens went
UP by 942**. Compression fired in only **1 of 2** ON reps, so treat it as indicative. 🔑 Counting reads
`~/.omlx/logs/server.log`, NOT `stats.json` — that file is flushed lazily and one curl moved its
counter 67 → 85, holding 17 requests from an earlier run. **Do not adopt Compresr Context Gateway**:
its `claude_code.yaml` uses the same `ANTHROPIC_BASE_URL` redirect blamed for Headroom's regression,
`"lazy tool"` has 0 hits in the repo, and `fast_setup.yaml` defaults to sending content to
`api.compresr.ai`. Orca does not compress at all — it passes agent env through.

**Also landed after the block above was written:** [[T304]] filed AND closed the same day ·
[[T305]] filed — a Claude Code **cloud environment named `w0m`** holds repo access and is declared by
nothing (`.w0m/sdlc.json` has no cloud/compute/sandbox key at all); measured `casualuser/w0m` created
`2026-09-02T12:10:34Z` with **0 clones**, and the App-installation endpoints are **unmeasured (403/401)**,
not zero · python bytecode untracked from the estate repo.

🔴 **Blocked, needs the owner:**

✅ **RESOLVED the same evening — [[T304]] is DONE 5/5, and the fix shipped.** The gate now tells a
credential failure apart from a security finding: `run_sql` classifies **credentials / connection /
query**, could-not-measure exits **3** while RED stays **1**, and the hook branches — both still
block, only the words change. 🔑 The bug was narrower than filed: the probe loop has been guarded
since [[T242]]; what was unguarded is `build()`, which resolves live ids with a `run_sql` **before any
probe runs**, so the process died at setup one layer beneath that machinery. New gate
`just authz-unavailable-test` (9 offline probes over verbatim field captures). ⚠️ Owner-side half
that made the session usable again: the vault backend was `auto` (system keyring), which a TTY-less
hook cannot read — `infisical vault set file`, then `infisical login` into the org owning project
`87a1718d-…`. If pushes start failing that way again, that is the first thing to check.

- **The client's `docker-compose.yml` carries a committed `SUPABASE_SERVICE_ROLE_KEY`** (`sb_secret_*`,
  the RLS-bypassing class the June audit flagged). It is in **their** repo; nothing was changed.
  Reporting it to the client is an owner call.
- **The stack has no Supabase.** It expects `host.docker.internal:54321/54322`; the server boots and
  serves but every DB-backed request fails. `vm.py up` prints this every run.
- **Orca session state lives on the guest disk** (`~/.orca`, `~/.config/orca`), so `pull --replace`
  loses an in-flight session. Code survives; the session does not. Moving it onto the `work` share is
  the remaining piece of the session-loss fix.
- One registry tag is over the retention limit (`2026.09.01-1788324569`, ~3 GB). Registry deletion is
  deliberately owner-only.
