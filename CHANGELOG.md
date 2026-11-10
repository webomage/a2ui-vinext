# Changelog

_Generated from the `deploy_log` table by `just changelog`. Each heading is one deploy stamp (`YYYY.MM.DD-<unixtimestamp>`)._

## 2026.11.10-1794329001
_First deployed: 2026-11-10 17:46:46.129619+00_

### Features
- **product**: T703 embed advanced services & packages configurator into onboarding wizard with checkout trigger ([T703](file:///.tasks/T703.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `b200f3a` | 2026-11-10 17:46:46.129619+00 |
| demo | `b200f3a` | 2026-11-10 17:45:43.645665+00 |
| me | `b200f3a` | 2026-11-10 17:44:52.6657+00 |
| cp | `b200f3a` | 2026-11-10 17:43:11.237013+00 |
| web | `b200f3a` | 2026-11-10 17:40:49.187786+00 |
| release | `b200f3a` | 2026-11-10 17:38:10.032713+00 |
| api | `b200f3a` | 2026-11-10 17:38:04.122622+00 |

## 2026.11.09-1794282738
_First deployed: 2026-11-10 04:05:08.017486+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `010332c` | 2026-11-10 04:05:08.017486+00 |
| demo | `010332c` | 2026-11-10 04:04:17.236882+00 |
| me | `010332c` | 2026-11-10 04:03:22.198795+00 |
| cp | `010332c` | 2026-11-10 04:00:41.712887+00 |
| web | `010332c` | 2026-11-10 03:58:04.682502+00 |

## 2026.11.09-1794275674
_First deployed: 2026-11-10 02:13:30.248239+00_

### Features
- **security**: complete T689 domain verification providers, agent tabs, and db-drift-check fix ([T689](file:///.tasks/T689.md))
- **T673**: add fork catalog governance, SkillSpector scanner, ontology graph compiler, and AI-DLC harness ([T673](file:///.tasks/T673.md))
- **tools**: record D69 zero svelte type debt and DistroSea integration (T682) ([T682](file:///.tasks/T682.md))
- **infra**: T682 onboard k7kb, SEO/GEO/Security scanner, Enterprise Obs & Same-Host ACP manager ([T682](file:///.tasks/T682.md))
- **kb**: T674 T675 Orca v1.4.253 PR audit, Mac research rescue, local hybrid vector index, and role template tickets ([T674](file:///.tasks/T674.md), [T675](file:///.tasks/T675.md))

### Fixes
- **T673**: route linuxontab-build and linuxontab-test via tracked scripts/linuxontab_serve.py ([T673](file:///.tasks/T673.md))
- **kb**: T674 cast new_labels to np.int32 for mypy strict check ([T674](file:///.tasks/T674.md))
- **T668**: persist and surface tool_chatter/other_trouble in deploy_logged and silence Infisical update chatter ([T668](file:///.tasks/T668.md))
- **T666, T667**: fix crawler-smoke User-Agent 403, clean deploy transcript audit, and close T666/T667 ([T666](file:///.tasks/T666.md), [T667](file:///.tasks/T667.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `fe9b861` | 2026-11-10 02:13:30.248239+00 |
| demo | `fe9b861` | 2026-11-10 02:12:07.687411+00 |
| me | `fe9b861` | 2026-11-10 02:10:52.28641+00 |
| cp | `fe9b861` | 2026-11-10 02:08:10.590095+00 |
| web | `fe9b861` | 2026-11-10 02:04:17.252568+00 |
| release | `fe9b861` | 2026-11-10 01:59:54.717964+00 |
| api | `fe9b861` | 2026-11-10 01:59:46.431972+00 |

## 2026.11.07-1794074188
_First deployed: 2026-11-07 18:34:31.020708+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `19d216f` | 2026-11-07 18:34:31.020708+00 |

## 2026.11.07-1794034239
_First deployed: 2026-11-07 07:09:19.173671+00_

### Features
- **T664,T665**: onboard pandatransfer client, vault, and w0m.xyz tech mailbox ticket ([T664](file:///.tasks/T664.md), [T665](file:///.tasks/T665.md))
- **T658**: add Tinybird surface drift gate, confirm-gated apply, and close T658 ([T658](file:///.tasks/T658.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `8bd523d` | 2026-11-07 07:09:19.173671+00 |
| demo | `8bd523d` | 2026-11-07 07:08:38.887594+00 |
| me | `8bd523d` | 2026-11-07 07:07:54.308718+00 |
| cp | `8bd523d` | 2026-11-07 07:06:25.017974+00 |
| web | `8bd523d` | 2026-11-07 07:04:28.536961+00 |
| release | `8bd523d` | 2026-11-07 07:02:02.916588+00 |
| api | `8bd523d` | 2026-11-07 07:01:56.085996+00 |

## 2026.11.06-1793942553
_First deployed: 2026-11-06 05:36:17.597431+00_

### Fixes
- **infra**: add offline Cloudflare Free-Tier redirect quota gate and self-init supabase-settings-plan (T653) ([T653](file:///.tasks/T653.md))
- **sdlc**: restore clean preflight --fast, incremental graph union refresh, and bounded automation-health gate (T652) ([T652](file:///.tasks/T652.md))
- **T651**: harden GitHub ticket mirror, wire session-complete close sync, and backfill gh_issue ([T651](file:///.tasks/T651.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `9a3fbd8` | 2026-11-06 05:36:17.597431+00 |
| demo | `9a3fbd8` | 2026-11-06 05:35:30.618391+00 |
| me | `9a3fbd8` | 2026-11-06 05:34:21.476582+00 |
| cp | `9a3fbd8` | 2026-11-06 05:32:15.38872+00 |
| web | `9a3fbd8` | 2026-11-06 05:29:43.104815+00 |
| release | `9a3fbd8` | 2026-11-06 05:27:31.151989+00 |
| api | `9a3fbd8` | 2026-11-06 05:27:25.64133+00 |

## 2026.11.05-1793917778
_First deployed: 2026-11-05 22:42:56.48643+00_

### Features
- **portal**: unify me.webomage.com and realign cp.webomage.com org boundary (T646) ([T646](file:///.tasks/T646.md))
- **T620**: audit host, agent, ephemeral & custom-fork tools across estate ([T620](file:///.tasks/T620.md))
- **T644**: close T644 Costa Rica, MX 612/626, and 12-country LATAM KYC/fiscal engine ([T644](file:///.tasks/T644.md))
- **estate**: sync OpenSpec CLI, Orca Gamepad HUD, and solar/mantrabox engagements (T641, T642, T643) ([T641](file:///.tasks/T641.md), [T642](file:///.tasks/T642.md), [T643](file:///.tasks/T643.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `7be5064` | 2026-11-05 22:42:56.48643+00 |
| demo | `7be5064` | 2026-11-05 22:42:13.094138+00 |
| me | `7be5064` | 2026-11-05 22:41:25.460332+00 |
| cp | `7be5064` | 2026-11-05 22:39:08.149032+00 |
| web | `7be5064` | 2026-11-05 22:36:40.276731+00 |
| release | `7be5064` | 2026-11-05 22:33:53.279989+00 |
| api | `7be5064` | 2026-11-05 22:33:47.366578+00 |

## 2026.11.04-1793824626
_First deployed: 2026-11-04 21:03:51.604516+00_

### Features
- **orca**: stage *top & Docker TUI monitor launcher + HP monitor tooling (T638) ([T638](file:///.tasks/T638.md))

### Fixes
- **deploy**: repair T638 DoD, gate dod-check in prepush, and retry Wrangler 100312 (T639) ([T638](file:///.tasks/T638.md), [T639](file:///.tasks/T639.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `1ced624` | 2026-11-04 21:03:51.604516+00 |
| demo | `1ced624` | 2026-11-04 21:03:00.269457+00 |
| job | `1ced624` | 2026-11-04 21:02:06.233559+00 |
| join | `1ced624` | 2026-11-04 21:00:36.950206+00 |
| cp | `1ced624` | 2026-11-04 20:59:21.010303+00 |
| web | `1ced624` | 2026-11-04 20:57:09.777908+00 |
| release | `1ced624` | 2026-11-04 20:54:38.370331+00 |
| api | `1ced624` | 2026-11-04 20:54:32.791941+00 |

## 2026.11.04-1793813884
_First deployed: 2026-11-04 17:56:02.340792+00_

### Features
- **orca,prs**: batch T635 edge arrows, 4-tap Alt+M, smooth resize & v1.4.249-w0m.2 ([T635](file:///.tasks/T635.md))
- **estate**: audit 7 vault sources and separate tech, client, and public guides (T634) ([T634](file:///.tasks/T634.md))
- **T628, T629, T630, T631, T632**: ship AgDR-0055, vault/todos/audit features, and SuperPM w0m co-owner role ([T628](file:///.tasks/T628.md), [T629](file:///.tasks/T629.md), [T630](file:///.tasks/T630.md), [T631](file:///.tasks/T631.md), [T632](file:///.tasks/T632.md))
- **prs,rules**: add short just pr-open/orca-apply aliases and permanent multiline copy-paste rule (T621) ([T621](file:///.tasks/T621.md))
- **estate**: close T622, T623, T624 with social trace cli, toolchain policy, lessons, and state ([T622](file:///.tasks/T622.md), [T623](file:///.tasks/T623.md), [T624](file:///.tasks/T624.md))
- **orca**: triple-tap Enter PR branch, Live Input backload, subagent modes & Floating category (T621) ([T621](file:///.tasks/T621.md))
- **T619**: implement self-healing webomage/orca overlay release feed ([T619](file:///.tasks/T619.md))
- **prs**: register Bodhi/Moksha forks and 9 prepared upstream PR proposals (T618) ([T618](file:///.tasks/T618.md))

### Fixes
- **estate**: close T637 codemap-refresh hook and prepush gate ([T637](file:///.tasks/T637.md))
- **estate**: close T633 deploy-all worker-env-check and vitest regressions ([T633](file:///.tasks/T633.md))
- **T627**: replace Bash orca-overlay-update with Python CLI and clean up webomage Actions ([T627](file:///.tasks/T627.md))
- **estate**: close T625 deploy-all suite regressions and record lesson ([T625](file:///.tasks/T625.md))

| Service | Commit | Deployed at |
|---|---|---|
| web | `576e27e` | 2026-11-04 17:56:02.340792+00 |
| release | `576e27e` | 2026-11-04 17:53:00.861227+00 |
| api | `576e27e` | 2026-11-04 17:52:55.046228+00 |

## 2026.11.03-1793721135
_First deployed: 2026-11-03 16:18:47.998331+00_

### Features
- **sdlc**: verify completed tickets/specs and restore offline suites (T616) ([T616](file:///.tasks/T616.md))
- **prs**: add post-rebase obsolete PR management, cgroup-safe session closer, and archive wrap-up (T615) ([T615](file:///.tasks/T615.md))
- **sdlc**: complete T613/T614 session wrap-up, lessons, reports, and drift recipes (T613, T614) ([T613](file:///.tasks/T613.md), [T614](file:///.tasks/T614.md))

### Fixes
- **T617**: update tasks_render line pointer in emoji-policy.json ([T617](file:///.tasks/T617.md))
- **T617**: align tasks_render row status claim check with tasks_bounds ([T617](file:///.tasks/T617.md))
- **T617**: separate hermetic release lockfile installs from worktree symlinks ([T617](file:///.tasks/T617.md))
- **T612**: complete Obsidian per-engagement vault launch guard and record lesson ([T612](file:///.tasks/T612.md))
- **deps**: enforce workspace package import linkage and add tools-install CLI bootstrap (T611) ([T611](file:///.tasks/T611.md))
- **prs**: paginate PR audits hitting gh pr list 100-item GraphQL cap (T610) ([T610](file:///.tasks/T610.md))
- **prs**: parallelize GitHub PR delta precheck and harden Orca CLI resolution (T610) ([T610](file:///.tasks/T610.md))
- **agents**: add multi-agent provider resolver and close T609 (T609) ([T609](file:///.tasks/T609.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `429fd73` | 2026-11-03 16:18:47.998331+00 |
| demo | `429fd73` | 2026-11-03 16:17:33.214538+00 |
| job | `429fd73` | 2026-11-03 16:16:07.677293+00 |
| join | `429fd73` | 2026-11-03 16:14:43.632117+00 |
| cp | `429fd73` | 2026-11-03 16:13:39.618018+00 |
| web | `429fd73` | 2026-11-03 16:11:28.595401+00 |
| release | `429fd73` | 2026-11-03 16:08:55.910025+00 |
| api | `429fd73` | 2026-11-03 16:08:49.9691+00 |

## 2026.11.02-1793646360
_First deployed: 2026-11-02 19:41:59.671737+00_

### Features
- **estate**: split T604 into atomic T605/T606/T607 tickets and register T608 Orca upstream PR proposals (T604, T605, T606, T607, T608) ([T604](file:///.tasks/T604.md), [T605](file:///.tasks/T605.md), [T606](file:///.tasks/T606.md), [T607](file:///.tasks/T607.md), [T608](file:///.tasks/T608.md))
- **estate**: close T602, T603, T604 — debt hygiene, mobile-first UI & CF/k7 audit ordering ([T602](file:///.tasks/T602.md), [T603](file:///.tasks/T603.md), [T604](file:///.tasks/T604.md))
- **orca**: make linux-host standalone primary control plane (T596) ([T596](file:///.tasks/T596.md))

### Fixes
- **prs**: match gh pr list --head without org prefix for ALREADY_OPEN detection and track #37510/#37511 (T608) ([T608](file:///.tasks/T608.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `59cf18c` | 2026-11-02 19:41:59.671737+00 |
| api | `59cf18c` | 2026-11-02 19:41:53.179405+00 |

## 2026.11.01-1793550372
_First deployed: 2026-11-01 16:34:29.240784+00_

### Features
- **mlx**: port canonical MLX Gemma 4 + oMLX schemas and register mlx-rs/mlx-lm PR proposals (T601) ([T601](file:///.tasks/T601.md))
- **mlx**: complete T14, T82, and T83 with webomage/mlx-rs fork and Gemma 4 port (T14, T82, T83) ([T14](file:///.tasks/T14.md), [T82](file:///.tasks/T82.md), [T83](file:///.tasks/T83.md))
- **sdlc**: complete T487 visual golden local stack SSOT, baseline check, and diff gate (T487) ([T487](file:///.tasks/T487.md))
- **tooling**: complete paused backlog tasks T152, T153, T179, T180, T181, T343, T368 ([T152](file:///.tasks/T152.md), [T153](file:///.tasks/T153.md), [T179](file:///.tasks/T179.md), [T180](file:///.tasks/T180.md), [T181](file:///.tasks/T181.md), [T343](file:///.tasks/T343.md), [T368](file:///.tasks/T368.md))
- **prs**: prepare 9 upstream PR proposals, submit gate, and worktree monitor (T593) ([T593](file:///.tasks/T593.md))
- **e2e,oci**: Gauge fail-fast + parallel E2E, multi-engine OCI sandboxes, and service+version probes (T480) ([T480](file:///.tasks/T480.md))
- **automation**: Orca AutomationService sync, N=1/N=3 cohort runner, and capability red-probe (T171) ([T171](file:///.tasks/T171.md))
- **cli**: worktree session targeting, Orca GitHub Tasks auth sync, and T597 completion (T597) ([T597](file:///.tasks/T597.md))
- **tools**: add private cross-host workload state persistence and w0m-prs Orca task/automation sync (T599) ([T599](file:///.tasks/T599.md))
- **cli,catalog**: add w0m track, w0m automation prechecks, and sync Backstage catalog (T597, T598, T171) ([T597](file:///.tasks/T597.md), [T598](file:///.tasks/T598.md), [T171](file:///.tasks/T171.md))
- **tools**: add w0m catalog subcommand and platform entity alignment to AX report (T597, T598) ([T597](file:///.tasks/T597.md), [T598](file:///.tasks/T598.md))
- **tools**: add unified w0m CLI and Orca multi-host AX specs (T597, T598) ([T597](file:///.tasks/T597.md), [T598](file:///.tasks/T598.md))
- **tools**: add multi-host Orca instance and agent session orchestration (T596) ([T596](file:///.tasks/T596.md))
- **T595**: standardize on webomage/tap with continuous beta branch tap-sync (AgDR-0052) ([T595](file:///.tasks/T595.md))
- **T569,T596,T597**: complete T569 Apple Silicon Metal benchmarks and file P1 Orca tickets ([T569](file:///.tasks/T569.md), [T596](file:///.tasks/T596.md), [T597](file:///.tasks/T597.md))
- **T595**: standardize toolchain on brew with LTS floor and latest comparison (AgDR-0052) ([T595](file:///.tasks/T595.md))

### Fixes
- **scripts**: resolve rustup wasm32 cargo and isolate crate check (T595) ([T595](file:///.tasks/T595.md))
- **tools**: govern missing host CLIs and verify/auto-provision workspace .bin tools (T595) ([T595](file:///.tasks/T595.md))
- **tasks**: record T600 CP project hat switcher & ContextSwitcher fixes (T600) ([T600](file:///.tasks/T600.md))
- **sdlc**: align stale Gauge specs, update spec-reality retired reporting, and close T486 (T486) ([T486](file:///.tasks/T486.md))
- **prs**: support --no-dry-run and idempotent open-PR detection in prs-submit (T593) ([T593](file:///.tasks/T593.md))
- **deploy**: exclude harmless Gauge/WebGL audit trouble and record release-to-release deltas (T523) ([T523](file:///.tasks/T523.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `09f8383` | 2026-11-01 16:34:29.240784+00 |
| demo | `09f8383` | 2026-11-01 16:34:13.779886+00 |
| job | `09f8383` | 2026-11-01 16:33:46.508722+00 |
| join | `09f8383` | 2026-11-01 16:33:10.25929+00 |
| cp | `09f8383` | 2026-11-01 16:32:38.64733+00 |
| web | `09f8383` | 2026-11-01 16:31:49.830811+00 |
| release | `09f8383` | 2026-11-01 16:30:24.686661+00 |
| api | `09f8383` | 2026-11-01 16:30:19.691649+00 |

## 2026.10.31-1793464869
_First deployed: 2026-10-31 18:16:44.686083+00_

### Features
- **vault**: enable vault assets/ in clients-policy and sync R2 SVG diagrams (T594) ([T594](file:///.tasks/T594.md))
- **estate**: add graphify preset and mergeable retry to w0m-prs, sync firecrawl skill, and track T593 (T343, T531, T593) ([T593](file:///.tasks/T593.md), [T343](file:///.tasks/T343.md), [T531](file:///.tasks/T531.md))
- **estate**: activate ast-grep guardrails, align graphify MCP v2 policy, and close T588-T592 (T588, T589, T590, T591, T592) ([T588](file:///.tasks/T588.md), [T592](file:///.tasks/T592.md), [T589](file:///.tasks/T589.md), [T590](file:///.tasks/T590.md), [T591](file:///.tasks/T591.md))
- **tasks**: complete T587 per-profile shared primary CV links (T587) ([T587](file:///.tasks/T587.md))
- **prs**: add prs-digest, prs-rising, prs-features, and prs-vote CLI commands (T586) ([T586](file:///.tasks/T586.md))
- **vault**: declare w0m knowledge_hub in clients-policy and sync eg-w0m to R2 (T585) ([T585](file:///.tasks/T585.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `0ba5a88` | 2026-10-31 18:16:44.686083+00 |
| demo | `0ba5a88` | 2026-10-31 18:15:26.61044+00 |
| job | `0ba5a88` | 2026-10-31 18:14:08.080164+00 |
| join | `0ba5a88` | 2026-10-31 18:11:36.836543+00 |
| cp | `0ba5a88` | 2026-10-31 18:09:38.879461+00 |
| web | `0ba5a88` | 2026-10-31 18:05:41.753415+00 |
| release | `0ba5a88` | 2026-10-31 18:02:15.841431+00 |
| api | `0ba5a88` | 2026-10-31 18:02:10.392296+00 |

## 2026.10.29-1793314887
_First deployed: 2026-10-29 23:13:41.079873+00_

### Features
- **security**: add asterisk password masking for Linux sudo confirm and mobile terminal input (T584) ([T584](file:///.tasks/T584.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `37aa9ec` | 2026-10-29 23:13:41.079873+00 |

## 2026.10.29-1793312271
_First deployed: 2026-10-29 22:25:35.577607+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `aa146a1` | 2026-10-29 22:25:35.577607+00 |
| cp | `aa146a1` | 2026-10-29 22:24:20.748254+00 |

## 2026.10.29-1793288100
_First deployed: 2026-10-29 15:55:43.138096+00_

### Features
- **root**: add mobile-sync-user-guide scaffolding and close T583 (T583) ([T583](file:///.tasks/T583.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `956cda5` | 2026-10-29 15:55:43.138096+00 |
| demo | `956cda5` | 2026-10-29 15:54:51.860739+00 |
| job | `956cda5` | 2026-10-29 15:54:01.639529+00 |
| join | `956cda5` | 2026-10-29 15:52:37.717883+00 |
| cp | `956cda5` | 2026-10-29 15:51:25.905757+00 |
| web | `956cda5` | 2026-10-29 15:47:13.421212+00 |

## 2026.10.29-1793276295
_First deployed: 2026-10-29 12:32:38.325101+00_

### Features
- **root**: add --push-ios-ext R2 uploader and close T582 (T582) ([T582](file:///.tasks/T582.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `e724a80` | 2026-10-29 12:32:38.325101+00 |
| demo | `e724a80` | 2026-10-29 12:31:47.30494+00 |
| job | `e724a80` | 2026-10-29 12:30:53.207467+00 |
| join | `e724a80` | 2026-10-29 12:29:11.060199+00 |
| cp | `e724a80` | 2026-10-29 12:27:51.24364+00 |
| web | `e724a80` | 2026-10-29 12:25:17.83229+00 |

## 2026.10.28-1793225231
_First deployed: 2026-10-28 22:34:03.603021+00_

### Features
- **estate**: per-engagement R2 vault sync CLI and T580/T581 tracking (T580, T581) ([T580](file:///.tasks/T580.md), [T581](file:///.tasks/T581.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `c674fb2` | 2026-10-28 22:34:03.603021+00 |
| demo | `c674fb2` | 2026-10-28 22:33:17.188939+00 |
| job | `c674fb2` | 2026-10-28 22:32:19.705019+00 |
| join | `c674fb2` | 2026-10-28 22:30:47.827062+00 |
| cp | `c674fb2` | 2026-10-28 22:29:38.607763+00 |
| web | `c674fb2` | 2026-10-28 22:27:27.343428+00 |
| release | `c674fb2` | 2026-10-28 22:25:00.191906+00 |
| api | `c674fb2` | 2026-10-28 22:24:54.423701+00 |

## 2026.10.28-1793208728
_First deployed: 2026-10-28 20:00:09.666705+00_

### Features
- **sdlc**: add T579 CP API parity & roles-verify / e2e-roles-local targets (T579) ([T579](file:///.tasks/T579.md))
- **cp**: complete T578 CP mobile UI responsiveness and unclip sidebar popovers ([T578](file:///.tasks/T578.md))
- **security**: complete T70 and T28, advance T504 AC4/AC6 with AgDR-0051, and record lessons (T70, T28, T504, T17) ([T70](file:///.tasks/T70.md), [T28](file:///.tasks/T28.md), [T504](file:///.tasks/T504.md), [T17](file:///.tasks/T17.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `b0cc91f` | 2026-10-28 20:00:09.666705+00 |
| demo | `b0cc91f` | 2026-10-28 19:59:15.29867+00 |
| job | `b0cc91f` | 2026-10-28 19:58:19.48542+00 |
| join | `b0cc91f` | 2026-10-28 19:56:39.828902+00 |
| cp | `b0cc91f` | 2026-10-28 19:55:04.912757+00 |
| web | `b0cc91f` | 2026-10-28 19:52:44.391894+00 |
| release | `b0cc91f` | 2026-10-28 19:50:11.08663+00 |
| api | `b0cc91f` | 2026-10-28 19:50:05.339197+00 |

## 2026.10.26-1793061488
_First deployed: 2026-10-27 00:56:14.610129+00_

### Features
- **estate**: complete T226, T508, T522, T521, T128, T132, T512, T109, T84, and T106 ([T226](file:///.tasks/T226.md), [T508](file:///.tasks/T508.md), [T522](file:///.tasks/T522.md), [T521](file:///.tasks/T521.md), [T128](file:///.tasks/T128.md), [T132](file:///.tasks/T132.md), [T512](file:///.tasks/T512.md), [T109](file:///.tasks/T109.md), [T84](file:///.tasks/T84.md), [T106](file:///.tasks/T106.md))
- **cp**: record T577 Upwork sidebar category, editable CV title, and WorkHistory layout fix ([T577](file:///.tasks/T577.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `a3bc2f0` | 2026-10-27 00:56:14.610129+00 |
| demo | `a3bc2f0` | 2026-10-27 00:55:02.996996+00 |
| job | `a3bc2f0` | 2026-10-27 00:54:01.055202+00 |
| join | `a3bc2f0` | 2026-10-27 00:52:21.915045+00 |
| cp | `a3bc2f0` | 2026-10-27 00:51:10.758961+00 |
| web | `a3bc2f0` | 2026-10-27 00:48:56.117687+00 |

## 2026.10.26-1793049239
_First deployed: 2026-10-26 21:26:52.515061+00_

### Features
- **sdlc**: built-artifact local gate recipes, canonical 3-level epic tags, and ticket spec disposition (T227, T355, T565) ([T227](file:///.tasks/T227.md), [T355](file:///.tasks/T355.md), [T565](file:///.tasks/T565.md))
- **connectors**: record T576 Telegram and Threads channel/group discovery ([T576](file:///.tasks/T576.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `b31793f` | 2026-10-26 21:26:52.515061+00 |
| demo | `b31793f` | 2026-10-26 21:26:04.328103+00 |
| job | `b31793f` | 2026-10-26 21:25:14.378455+00 |
| join | `b31793f` | 2026-10-26 21:23:57.862234+00 |
| cp | `b31793f` | 2026-10-26 21:22:53.553316+00 |
| web | `b31793f` | 2026-10-26 21:20:49.053766+00 |
| release | `b31793f` | 2026-10-26 21:18:25.119167+00 |
| api | `b31793f` | 2026-10-26 21:18:19.811186+00 |

## 2026.10.26-1793036162
_First deployed: 2026-10-26 17:56:20.996155+00_

### Features
- **connectors**: register Threads provider, TG/Threads job sources, and close T575 ([T575](file:///.tasks/T575.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `1d863b0` | 2026-10-26 17:56:20.996155+00 |
| demo | `1d863b0` | 2026-10-26 17:55:13.828633+00 |
| job | `1d863b0` | 2026-10-26 17:54:10.198573+00 |
| join | `1d863b0` | 2026-10-26 17:52:26.585537+00 |
| cp | `1d863b0` | 2026-10-26 17:51:05.699914+00 |
| web | `1d863b0` | 2026-10-26 17:48:02.508663+00 |
| release | `1d863b0` | 2026-10-26 17:44:47.857436+00 |
| api | `1d863b0` | 2026-10-26 17:44:40.957429+00 |

## 2026.10.26-1793021763
_First deployed: 2026-10-26 14:14:21.487201+00_

### Features
- **hooks**: auto-scale run-typecheck concurrency and V8 heap by host RAM (T573, T509) ([T573](file:///.tasks/T573.md), [T509](file:///.tasks/T509.md))
- **sdlc**: complete T509 L2 root-first layout cutover and AgDR-0050 (T509) ([T509](file:///.tasks/T509.md))

### Fixes
- **scripts**: resolve w0m-* repo prefixes in estate_search --repo (T509) ([T509](file:///.tasks/T509.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `ef1dce9` | 2026-10-26 14:14:21.487201+00 |
| demo | `ef1dce9` | 2026-10-26 14:13:35.787471+00 |
| job | `ef1dce9` | 2026-10-26 14:12:44.541706+00 |
| join | `ef1dce9` | 2026-10-26 14:11:27.144629+00 |
| cp | `ef1dce9` | 2026-10-26 14:10:19.87324+00 |
| web | `ef1dce9` | 2026-10-26 14:08:09.967104+00 |
| release | `ef1dce9` | 2026-10-26 14:05:38.387056+00 |
| api | `ef1dce9` | 2026-10-26 14:05:32.174517+00 |

## 2026.10.25-1792983664
_First deployed: 2026-10-26 03:17:33.810524+00_

### Features
- **estate**: complete T571 portal sidebar & side switcher and T509 root search/mypy/pre-push (T571, T509) ([T571](file:///.tasks/T571.md), [T509](file:///.tasks/T509.md))
- **estate**: complete Wave 1 Phase 1 tickets (T136, T271, T273, T365, T454, T475) ([T136](file:///.tasks/T136.md), [T271](file:///.tasks/T271.md), [T273](file:///.tasks/T273.md), [T365](file:///.tasks/T365.md), [T454](file:///.tasks/T454.md), [T475](file:///.tasks/T475.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `1f1a9f8` | 2026-10-26 03:17:33.810524+00 |
| demo | `1f1a9f8` | 2026-10-26 03:16:49.28044+00 |
| job | `1f1a9f8` | 2026-10-26 03:16:00.436633+00 |
| join | `1f1a9f8` | 2026-10-26 03:14:46.749692+00 |
| cp | `1f1a9f8` | 2026-10-26 03:13:42.000226+00 |
| web | `1f1a9f8` | 2026-10-26 03:11:41.096059+00 |
| release | `1f1a9f8` | 2026-10-26 03:09:20.938302+00 |
| api | `1f1a9f8` | 2026-10-26 03:09:15.325787+00 |

## 2026.10.23-1792798998
_First deployed: 2026-10-23 23:52:39.980812+00_

### Features
- **tools**: prepare upstream Graphify-Labs/graphify PR for global status, sync, and commit provenance (T570) ([T570](file:///.tasks/T570.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `323c89a` | 2026-10-23 23:52:39.980812+00 |
| cp | `323c89a` | 2026-10-23 23:51:51.752851+00 |
| web | `323c89a` | 2026-10-23 23:49:48.74264+00 |

## 2026.10.23-1792786764
_First deployed: 2026-10-23 20:38:08.946115+00_

### Features
- **estate**: land 4-identity selector, stale-path probe, remote CI, and autonomous queue (T306, T164, T234, T259, T384, T387, T400, T509) ([T306](file:///.tasks/T306.md), [T164](file:///.tasks/T164.md), [T234](file:///.tasks/T234.md), [T259](file:///.tasks/T259.md), [T384](file:///.tasks/T384.md), [T387](file:///.tasks/T387.md), [T400](file:///.tasks/T400.md), [T509](file:///.tasks/T509.md))
- **estate**: close 13 Area 5 & Area 6 tickets, record AgDR-0046, and split T569 (T500, T57, T88, T11, T10, T462, T9, T434, T569, T184, T37, T66, T143, T490) ([T569](file:///.tasks/T569.md), [T500](file:///.tasks/T500.md), [T57](file:///.tasks/T57.md), [T88](file:///.tasks/T88.md), [T11](file:///.tasks/T11.md), [T10](file:///.tasks/T10.md), [T462](file:///.tasks/T462.md), [T9](file:///.tasks/T9.md), [T434](file:///.tasks/T434.md), [T184](file:///.tasks/T184.md), [T37](file:///.tasks/T37.md), [T66](file:///.tasks/T66.md), [T143](file:///.tasks/T143.md), [T490](file:///.tasks/T490.md))
- **tools**: add just eli5 T* plain-English ticket explainer CLI (T568) ([T568](file:///.tasks/T568.md))

### Fixes
- **clients**: point bridgeroad and evercred roots to ../../!proj in clients-policy.json (T385) ([T385](file:///.tasks/T385.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `0f60c25` | 2026-10-23 20:38:08.946115+00 |
| demo | `0f60c25` | 2026-10-23 20:37:15.777594+00 |
| job | `0f60c25` | 2026-10-23 20:36:13.788682+00 |
| join | `0f60c25` | 2026-10-23 20:34:17.115834+00 |
| cp | `0f60c25` | 2026-10-23 20:32:54.750093+00 |
| web | `0f60c25` | 2026-10-23 20:29:44.048935+00 |
| release | `0f60c25` | 2026-10-23 20:26:24.361201+00 |
| api | `0f60c25` | 2026-10-23 20:26:17.105667+00 |

## 2026.10.22-1792728937
_First deployed: 2026-10-23 04:41:09.323079+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `619f671` | 2026-10-23 04:41:09.323079+00 |

## 2026.10.22-1792719973
_First deployed: 2026-10-23 02:00:07.053834+00_

### Features
- **estate**: add W0M_ROOT fail-closed resolver, AgDR-0041, and close T274/T340/T427/T437/T438 (T274, T340, T427, T437, T438) ([T274](file:///.tasks/T274.md), [T340](file:///.tasks/T340.md), [T427](file:///.tasks/T427.md), [T437](file:///.tasks/T437.md), [T438](file:///.tasks/T438.md))
- **decisions,tasks**: record AgDR-0038/AgDR-0039 and close T36, T220, T550, T98 (T36, T220, T550, T98) ([T36](file:///.tasks/T36.md), [T220](file:///.tasks/T220.md), [T550](file:///.tasks/T550.md), [T98](file:///.tasks/T98.md))
- **sdlc**: close Track 2 gate integrity, hook runner, svelte typecheck, and multi-agent landing tickets (T104, T129, T278, T386, T408, T527, T531) ([T104](file:///.tasks/T104.md), [T129](file:///.tasks/T129.md), [T278](file:///.tasks/T278.md), [T386](file:///.tasks/T386.md), [T408](file:///.tasks/T408.md), [T527](file:///.tasks/T527.md), [T531](file:///.tasks/T531.md))
- **sdlc**: close Wave 1 Track 2 tickets and harden audit/debt/suite gates (T43, T225, T241, T276, T328, T331, T385, T549) ([T43](file:///.tasks/T43.md), [T225](file:///.tasks/T225.md), [T241](file:///.tasks/T241.md), [T276](file:///.tasks/T276.md), [T328](file:///.tasks/T328.md), [T331](file:///.tasks/T331.md), [T385](file:///.tasks/T385.md), [T549](file:///.tasks/T549.md))
- **T6,T61,T290,T305,T306**: cloud compute governance, 4-identity selector, and ticket tracking ([T6](file:///.tasks/T6.md), [T61](file:///.tasks/T61.md), [T290](file:///.tasks/T290.md), [T305](file:///.tasks/T305.md), [T306](file:///.tasks/T306.md))
- **governance**: close Area 7A client governance, non-vacuous deps & boundary tickets (T264, T298, T302, T308, T316) ([T264](file:///.tasks/T264.md), [T298](file:///.tasks/T298.md), [T302](file:///.tasks/T302.md), [T308](file:///.tasks/T308.md), [T316](file:///.tasks/T316.md))

### Fixes
- **deps**: close T566 @astrojs/cloudflare 14.3.4 linkage & preflight/pre-push gates (T566) ([T566](file:///.tasks/T566.md))
- **tasks**: add space before YAML comment on status: done in T116 & T293 (T333) ([T116](file:///.tasks/T116.md), [T293](file:///.tasks/T293.md), [T333](file:///.tasks/T333.md))
- **infisical,typing**: resolve .infisical.yaml link lookup and type json.loads (T429, T448) ([T429](file:///.tasks/T429.md), [T448](file:///.tasks/T448.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `edbd553` | 2026-10-23 02:00:07.053834+00 |

## 2026.10.22-1792676871
_First deployed: 2026-10-22 14:01:26.618232+00_

### Features
- **sdlc**: complete Track 4 Wave 2 — spec policy, consumer skill gate, lessons check, eli5 default tier & OpenCode config (T152, T177, T178, T179, T180, T185, T245, T270, T368, T565) ([T152](file:///.tasks/T152.md), [T177](file:///.tasks/T177.md), [T178](file:///.tasks/T178.md), [T179](file:///.tasks/T179.md), [T180](file:///.tasks/T180.md), [T185](file:///.tasks/T185.md), [T245](file:///.tasks/T245.md), [T270](file:///.tasks/T270.md), [T368](file:///.tasks/T368.md), [T565](file:///.tasks/T565.md))
- **sdlc**: complete Track 4 Wave 1 — branch hygiene, delivery record, Serena reconciliation & tickets (T148, T158, T172, T176, T193, T212, T269, T339, T548, T552) ([T148](file:///.tasks/T148.md), [T158](file:///.tasks/T158.md), [T172](file:///.tasks/T172.md), [T176](file:///.tasks/T176.md), [T193](file:///.tasks/T193.md), [T212](file:///.tasks/T212.md), [T269](file:///.tasks/T269.md), [T339](file:///.tasks/T339.md), [T548](file:///.tasks/T548.md), [T552](file:///.tasks/T552.md))
- **T429**: auto-upgrade infisical on update banner and bump tools known_good (T112) ([T429](file:///.tasks/T429.md), [T112](file:///.tasks/T112.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `411f850` | 2026-10-22 14:01:26.618232+00 |

## 2026.10.21-1792633374
_First deployed: 2026-10-22 01:55:09.194303+00_

### Features
- **sdlc**: complete Gauge migration, obsidian-skills survey/catalog, and awesome-repositories MCP (T24, T26, T142) ([T24](file:///.tasks/T24.md), [T26](file:///.tasks/T26.md), [T142](file:///.tasks/T142.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `e3f7219` | 2026-10-22 01:55:09.194303+00 |

## 2026.10.21-1792620789
_First deployed: 2026-10-21 22:21:58.110663+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `54a87a3` | 2026-10-21 22:21:58.110663+00 |

## 2026.10.21-1792617301
_First deployed: 2026-10-21 21:26:13.07356+00_

### Features
- **sdlc**: declare design_system contract and complete T183 + T118 ([T183](file:///.tasks/T183.md), [T118](file:///.tasks/T118.md))
- **sdlc**: close Track D tickets (T99, T114, T219, T333) and wire standing audit probes ([T99](file:///.tasks/T99.md), [T114](file:///.tasks/T114.md), [T219](file:///.tasks/T219.md), [T333](file:///.tasks/T333.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `1df175c` | 2026-10-21 21:26:13.07356+00 |

## 2026.10.21-1792595362
_First deployed: 2026-10-21 15:20:59.887169+00_

### Features
- **sdlc,dora**: Backstage catalog, DORA 5/Core 4 cockpit, AgDR-0036, and close T448, T64, T432, T292, T59, T51, T141, T144 ([T448](file:///.tasks/T448.md), [T64](file:///.tasks/T64.md), [T432](file:///.tasks/T432.md), [T292](file:///.tasks/T292.md), [T59](file:///.tasks/T59.md), [T51](file:///.tasks/T51.md), [T141](file:///.tasks/T141.md), [T144](file:///.tasks/T144.md))
- **sdlc**: close T506, T520, T525, T534 with reports and state refresh ([T506](file:///.tasks/T506.md), [T520](file:///.tasks/T520.md), [T525](file:///.tasks/T525.md), [T534](file:///.tasks/T534.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `6c7d3d0` | 2026-10-21 15:20:59.887169+00 |

## 2026.10.20-1792556546
_First deployed: 2026-10-21 04:32:06.003839+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `6d11a82` | 2026-10-21 04:32:06.003839+00 |

## 2026.10.20-1792552492
_First deployed: 2026-10-21 03:26:07.475201+00_

### Features
- **T272**: declare client project external services & cost attribution and record T271 comparison ([T272](file:///.tasks/T272.md), [T271](file:///.tasks/T271.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `24881df` | 2026-10-21 03:26:07.475201+00 |

## 2026.10.20-1792549859
_First deployed: 2026-10-21 02:42:35.728739+00_

### Features
- **kyc**: record AgDR-0035 and mark T528 AC1-AC4 complete (T528) ([T528](file:///.tasks/T528.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `a0801e2` | 2026-10-21 02:42:35.728739+00 |

## 2026.10.20-1792536207
_First deployed: 2026-10-20 23:17:13.35776+00_

### Features
- **connectors**: record AgDR-0034, expand services-policy oauth_providers, and close T442 (T442) ([T442](file:///.tasks/T442.md))
- **sdlc**: add T564 virtual agent_id & cross-worktree ticket claim/tagging system (T564) ([T564](file:///.tasks/T564.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `cedbec4` | 2026-10-20 23:17:13.35776+00 |

## 2026.10.20-1792525002
_First deployed: 2026-10-20 20:32:53.690066+00_

### Features
- **sdlc**: close T337 air-gapped sandbox audit runner and cloud compliance binder ([T337](file:///.tasks/T337.md))

### Fixes
- **graph,deps**: update .mcp.json Linux paths, forward graph-health, and bump hono floor (T25) ([T25](file:///.tasks/T25.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `f002cf6` | 2026-10-20 20:32:53.690066+00 |

## 2026.10.20-1792477624
_First deployed: 2026-10-20 06:37:53.964338+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `aef50be` | 2026-10-20 06:37:53.964338+00 |

## 2026.10.20-1792472683
_First deployed: 2026-10-20 05:16:11.907087+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `b4a2f3b` | 2026-10-20 05:16:11.907087+00 |

## 2026.10.19-1792461838
_First deployed: 2026-10-20 02:14:27.171156+00_

### Features
- **sdlc**: close T510, T513 & T560, record AgDR-0033, and queue T561-T563 Outreach Vault (T510, T513, T560, T561, T562, T563) ([T510](file:///.tasks/T510.md), [T513](file:///.tasks/T513.md), [T560](file:///.tasks/T560.md), [T561](file:///.tasks/T561.md), [T563](file:///.tasks/T563.md), [T562](file:///.tasks/T562.md))
- **T74,T257,T301,T477,T546**: close 5 in-progress tooling tickets and promote verified tools ([T74](file:///.tasks/T74.md), [T257](file:///.tasks/T257.md), [T301](file:///.tasks/T301.md), [T477](file:///.tasks/T477.md), [T546](file:///.tasks/T546.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `27c8df0` | 2026-10-20 02:14:27.171156+00 |

## 2026.10.19-1792441744
_First deployed: 2026-10-19 20:41:47.414238+00_

### Features
- **tasks,prepush**: close T458 roots-epic, complete T510 U4.2/U5.1, and add prepush step progress bar (T458, T510, T375) ([T458](file:///.tasks/T458.md), [T510](file:///.tasks/T510.md), [T375](file:///.tasks/T375.md))
- **sdlc**: close T357, mark ROADMAP §33 Client Alfa complete, and advance current_plan to §34 Client Beta (T357, T335) ([T357](file:///.tasks/T357.md), [T335](file:///.tasks/T335.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `e749599` | 2026-10-19 20:41:47.414238+00 |

## 2026.10.19-1792425309
_First deployed: 2026-10-19 16:06:15.540905+00_

### Features
- **client-alfa**: rebalance client-alfa and client-beta epics and close T263, T217, T338, T3, T5 (T263, T217, T338, T3, T5) ([T263](file:///.tasks/T263.md), [T217](file:///.tasks/T217.md), [T338](file:///.tasks/T338.md), [T3](file:///.tasks/T3.md), [T5](file:///.tasks/T5.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `7b6bde7` | 2026-10-19 16:06:15.540905+00 |

## 2026.10.19-1792392441
_First deployed: 2026-10-19 06:53:53.312806+00_

### Features
- **tasks**: complete T455 member OSS & PRs board and T468 Upwork contracts/messages fixes (T455, T468) ([T455](file:///.tasks/T455.md), [T468](file:///.tasks/T468.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `33b71c7` | 2026-10-19 06:53:53.312806+00 |

## 2026.10.19-1792387706
_First deployed: 2026-10-19 05:37:53.1395+00_

### Features
- **policy**: declare job_board_sources in services-policy.json (T134, T213) ([T134](file:///.tasks/T134.md), [T213](file:///.tasks/T213.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `4bbae93` | 2026-10-19 05:37:53.1395+00 |

## 2026.10.18-1792382940
_First deployed: 2026-10-19 04:22:29.49173+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `8be63b0` | 2026-10-19 04:22:29.49173+00 |

## 2026.10.18-1792373024
_First deployed: 2026-10-19 01:55:41.417412+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `e6a2c5d` | 2026-10-19 01:55:41.417412+00 |

## 2026.10.18-1792361625
_First deployed: 2026-10-18 22:44:30.50859+00_

### Features
- **T555,T543**: record Resume Studio tech chips editor and /me/work assigned projects & project management ([T555](file:///.tasks/T555.md), [T543](file:///.tasks/T543.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `e588d82` | 2026-10-18 22:44:30.50859+00 |

## 2026.10.18-1792357477
_First deployed: 2026-10-18 21:14:17.887988+00_

### Features
- **T555,T556,T557,T558**: complete Harness2 integration, Resume Studio print/period-expansion, and webomage org fork rule ([T555](file:///.tasks/T555.md), [T556](file:///.tasks/T556.md), [T557](file:///.tasks/T557.md), [T558](file:///.tasks/T558.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `be1ccf1` | 2026-10-18 21:14:17.887988+00 |

## 2026.10.18-1792352123
_First deployed: 2026-10-18 19:51:22.17206+00_

### Features
- **ai**: wire Jev image processing recipes and track T558 (T558) ([T558](file:///.tasks/T558.md))
- **tasks**: add P0 tickets T556 (Orca + Harness2) and T557 (Mobile Orca camera capture) ([T556](file:///.tasks/T556.md), [T557](file:///.tasks/T557.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `d29c259` | 2026-10-18 19:51:22.17206+00 |

## 2026.10.18-1792334573
_First deployed: 2026-10-18 15:06:01.739134+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `370dfc9` | 2026-10-18 15:06:01.739134+00 |

## 2026.10.18-1792331184
_First deployed: 2026-10-18 14:01:37.638842+00_

### Features
- **T503**: add critical/medium/full test levels, parallel suite runner, and sync ticket frontmatter ([T503](file:///.tasks/T503.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `25f2e1e` | 2026-10-18 14:01:37.638842+00 |

## 2026.10.17-1792276587
_First deployed: 2026-10-18 00:07:10.218792+00_

### Features
- **T555**: complete Resume Studio, sync ticket frontmatter, and Linux host posture fixes ([T555](file:///.tasks/T555.md))
- **hygiene**: exempt Linux platform binaries and ignore cross-platform unused exemptions (T135) ([T135](file:///.tasks/T135.md))

### Fixes
- **T555**: disable goldens in _deploy-gates to prevent host halt during deploy ([T555](file:///.tasks/T555.md))
- **T555**: support Linux host estate path in w0m_prs fork resolution ([T555](file:///.tasks/T555.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `d0bf862` | 2026-10-18 00:07:10.218792+00 |

## 2026.10.07-1791355037
_First deployed: 2026-10-07 07:03:39.188305+00_

### Features
- **T546**: tools-weekly proposes known_good bumps, tools-promote lands them from an agent tree ([T546](file:///.tasks/T546.md))
- **T532**: root forwarder for e2e-sandbox-guard-test ([T532](file:///.tasks/T532.md))
- **T541**: single-use step consumption, --clear action, and deploy teardown consent cleanup ([T541](file:///.tasks/T541.md))
- **T531**: just agent-tree, agent-tree-list, agent-tree-land, agent-tree-remove; AC6 half done ([T531](file:///.tasks/T531.md))
- **T542**: scripts/check_db_host.py: the preflight resolves the database host the way psql does; T542 filed ([T542](file:///.tasks/T542.md))
- **T539**: split T537: the owner's laptop MCP sync gets a database loader; the per-member server connector is on hold (Upwork refuses an https redirect) ([T539](file:///.tasks/T539.md), [T537](file:///.tasks/T537.md))
- **T537**: Upwork on the official MCP with per-member OAuth; the API connection is deprecated and hidden, not deleted (Hero Epic stage 2) ([T537](file:///.tasks/T537.md))

### Fixes
- **deploy**: re-render the board (T532 done, T545-T548 rows), recipes resolve for the registered tools-upgrade suite, record the deploy findings in T503 ([T532](file:///.tasks/T532.md), [T545](file:///.tasks/T545.md), [T548](file:///.tasks/T548.md), [T503](file:///.tasks/T503.md))
- **emoji**: restore md_headings_estate baseline to 230; the 225 lowering was read from the live tree and failed the release-shaped test tier

| Service | Commit | Deployed at |
|---|---|---|
| release | `16f9885` | 2026-10-07 07:03:39.188305+00 |

## 2026.10.02-1790927707
_First deployed: 2026-10-02 08:08:00.976014+00_

### Features
- **governance**: define base roles and per-service capability switches in clients policy (T299) ([T299](file:///.tasks/T299.md))

### Fixes
- **state**: STATE.md ticket links pointed into a scratch directory; lesson on derived files generated in a scratch copy

| Service | Commit | Deployed at |
|---|---|---|
| release | `7ea7aab` | 2026-10-02 08:08:00.976014+00 |

## 2026.10.01-1790882082
_First deployed: 2026-10-01 19:32:36.158393+00_

### Features
- **profile**: declarative profile connection policy and resolver integration (T366) ([T366](file:///.tasks/T366.md))
- **specs**: regex fix for table params in spec reality check; progress T237 and T458 ([T237](file:///.tasks/T237.md), [T458](file:///.tasks/T458.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `71b5ec7` | 2026-10-01 19:32:36.158393+00 |

## 2026.10.01-1790865449
_First deployed: 2026-10-01 14:50:35.118397+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `468de50` | 2026-10-01 14:50:35.118397+00 |

## 2026.10.01-1790863675
_First deployed: 2026-10-01 14:24:12.066436+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `90cdec9` | 2026-10-01 14:24:12.066436+00 |

## 2026.10.01-1790853122
_First deployed: 2026-10-01 11:29:05.373807+00_

### Features
- **T521,T523**: record mmd-validate sandbox decision (catalogue test 13/18 to 15/18), add golden-run browser errors ticket, record live vault and stable-sync results ([T521](file:///.tasks/T521.md), [T523](file:///.tasks/T523.md))
- **T77**: elevate spec_drift_gate with structured recommendations and graduate orphan-change to HARD gate ([T77](file:///.tasks/T77.md))
- **sdlc**: elevate decisions and lessons registers to workspace root (T392) ([T392](file:///.tasks/T392.md))
- **T481**: release worktree retention: keep 5 newest plus newest deployed; declare keep_worktrees in sdlc.json ([T481](file:///.tasks/T481.md))
- **T481**: declare release.e2e_before_deploy (off); infisical auto-update ceiling patch to minor; T509 stale deploy-rule note ([T481](file:///.tasks/T481.md), [T509](file:///.tasks/T509.md))

### Fixes
- **security**: add wom-tinybird-token rule and track T515 progress ([T515](file:///.tasks/T515.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `52bee57` | 2026-10-01 11:29:05.373807+00 |

## 2026.09.30-1790816882
_First deployed: 2026-10-01 01:23:05.149902+00_

### Fixes
- **T414**: disable completed evercred, classify release, milestones and lessons_surface for half-managed, fix sync_github generator path ([T414](file:///.tasks/T414.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `c3fb64f` | 2026-10-01 01:23:05.149902+00 |

## 2026.09.30-1790800772
_First deployed: 2026-09-30 20:56:39.839019+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `bccac94` | 2026-09-30 20:56:39.839019+00 |

## 2026.09.30-1790787699
_First deployed: 2026-09-30 17:26:01.367963+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `0943aac` | 2026-09-30 17:26:01.367963+00 |

## 2026.09.30-1790784566
_First deployed: 2026-09-30 16:24:50.142404+00_

### Fixes
- **T503**: deploy gates run before db-migrate, prepush ratchet tier and pre-flight, ticket AC check at commit, lesson ([T503](file:///.tasks/T503.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `de8addc` | 2026-09-30 16:24:50.142404+00 |

## 2026.09.29-1790727494
_First deployed: 2026-09-30 00:34:12.207499+00_

### Features
- root cp-feature-index forwarders
- **client-beta**: organize client-facing work as the Client Beta epic (§34), 18 tickets moved; name-refs history heuristic
- name-refs inventory + gate, and the rename lesson (11 surfaces)

| Service | Commit | Deployed at |
|---|---|---|
| release | `65dd993` | 2026-09-30 00:34:12.207499+00 |

## 2026.09.29-1790702495
_First deployed: 2026-09-29 17:35:45.634417+00_

### Features
- **T430**: umbrella pre-commit hook fails when a commit leaves wom7web/docs/DECISIONS.md stale ([T430](file:///.tasks/T430.md))
- **T453**: root route-policy-live forwarders; probe baseline note ([T453](file:///.tasks/T453.md))
- **T335**: validated current_plan setter (plan-set), hand-edit gate in tasks plan --check; stamp §19 plan ([T335](file:///.tasks/T335.md))
- **T453**: steps 1-4 done (AC1, AC2, AC5, AC7); root route-policy-check forwarder ([T453](file:///.tasks/T453.md))

### Fixes
- **T488**: root forwarders for resumes-upload[-live]; upload skips rows already stored without a source ([T488](file:///.tasks/T488.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `c987e9c` | 2026-09-29 17:35:45.634417+00 |

## 2026.09.29-1790670292
_First deployed: 2026-09-29 08:39:04.031412+00_

### Features
- **skills**: multi-agent transcript harvester, validation gate, and sleep harness (T482) ([T482](file:///.tasks/T482.md))
- **sdlc**: configure release e2e_gate, add stable Justfile recipes, and complete T481 (T481) ([T481](file:///.tasks/T481.md))

### Fixes
- **policy**: add resumes-upload-live step to confirm-policy and save plan progress report
- **T473**: deploy-functions verifies every function updated and retries only the stale ones ([T473](file:///.tasks/T473.md))
- **T473**: repair the gates that failed release 2026.09.28-1790648128 ([T473](file:///.tasks/T473.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `405659f` | 2026-09-29 08:39:04.031412+00 |

## 2026.09.28-1790639135
_First deployed: 2026-09-29 00:00:11.544929+00_

### Features
- **infra**: purge Hostinger MCP configurations and residue (T483) ([T483](file:///.tasks/T483.md))
- **T482**: implement w0m sleep harness, multi-agent harvester, and tests (#482) ([T482](file:///.tasks/T482.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `fd0184e` | 2026-09-29 00:00:11.544929+00 |

## 2026.09.28-1790582373
_First deployed: 2026-09-28 08:13:26.876266+00_

### Features
- **T477**: stop emoji/license scans walking node_modules; file pre-push parallel ticket ([T477](file:///.tasks/T477.md))
- **T471**: complete cross-device confirmation gate and sync queue ([T471](file:///.tasks/T471.md))
- **T473**: deploy chain skips unchanged apps (W0M_RELEASE_APPS), per-app APP_VERSION, release-apps registry; T474 closed ([T473](file:///.tasks/T473.md), [T474](file:///.tasks/T474.md))
- **T473**: just deploy / deploy-all ship a tagged release from an isolated worktree by default; deploy-local / deploy-all-local force the working tree; release-* recipes; T469/T470/T472 closed (their session's completion notes included, status values fixed) ([T473](file:///.tasks/T473.md), [T469](file:///.tasks/T469.md), [T470](file:///.tasks/T470.md), [T472](file:///.tasks/T472.md))

### Fixes
- **T473**: update emoji ratchet baseline, ignore _ext symlink, and fallback forks dir ([T473](file:///.tasks/T473.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `5994f4f` | 2026-09-28 08:13:26.876266+00 |

## 2026.09.27-1790522929
_First deployed: 2026-09-27 15:46:17.416789+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `48bfd8b` | 2026-09-27 15:46:17.416789+00 |

## 2026.09.26-1790474969
_First deployed: 2026-09-27 02:25:03.527757+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f1ad0d1` | 2026-09-27 02:25:03.527757+00 |

## 2026.09.26-1790452856
_First deployed: 2026-09-26 20:16:07.581789+00_

### Features
- **tasks**: implement orca obsidian ofm engine (T464) ([T464](file:///.tasks/T464.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `323a155` | 2026-09-26 20:16:07.581789+00 |

## 2026.09.26-1790438594
_First deployed: 2026-09-26 16:18:14.097698+00_

### Features
- **T452**: resolve one fixed background, simplify slide UI, and update records ([T452](file:///.tasks/T452.md))
- **T449**: orchestrate full local stack with *.w0m.local SSL proxy and host validation ([T449](file:///.tasks/T449.md))
- **T436**: public-safe automated changelog generation and disclosure guardrail gate ([T436](file:///.tasks/T436.md))
- **sdlc**: synthesize PICK UP HERE from ticket Status notes and add concurrency test (T428) ([T428](file:///.tasks/T428.md))
- **T425**: implement just land local merge queue and single committer to beta ([T425](file:///.tasks/T425.md))
- **T211**: ticket diagram co-location, GitHub sync, and zero-width browser viewer ([T211](file:///.tasks/T211.md))

### Fixes
- **T435**: wire _confirm into deploy-workers/deploy-functions, describe new steps, record the agent rule-enforcement audit ([T435](file:///.tasks/T435.md))
- **T425**: handle PermissionError in is_pid_alive, case-insensitive report glob, auto-ticket detect ([T425](file:///.tasks/T425.md))
- **tickets**: resolve schema lint errors in T190, T240, T354, T396, T418 ([T190](file:///.tasks/T190.md), [T240](file:///.tasks/T240.md), [T354](file:///.tasks/T354.md), [T396](file:///.tasks/T396.md), [T418](file:///.tasks/T418.md))
- **T431,T428,T426**: state-brief + in-flight tickets at session start; three silent deploy-all regressions ([T431](file:///.tasks/T431.md), [T428](file:///.tasks/T428.md), [T426](file:///.tasks/T426.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `6600586` | 2026-09-26 16:18:14.097698+00 |

## 2026.09.24-1790226662
_First deployed: 2026-09-24 05:25:26.816412+00_

### Features
- **T431**: top-level `just deploy-function <name…>` helper, confirm-gated ([T431](file:///.tasks/T431.md))
- **T422**: add automated test and recipe for React-free design system and token parity ([T422](file:///.tasks/T422.md))
- **T165**: satisfy AC4-AC8 and update tracking ([T165](file:///.tasks/T165.md))
- **deploy**: elevate deployment machinery, scripts, recipes, and logs to workspace root (T421) ([T421](file:///.tasks/T421.md))
- **T420**: register ds-check gate and update ticket tracking ([T420](file:///.tasks/T420.md))
- **T417**: add review feedback and comments inspection column to w0m-prs ([T417](file:///.tasks/T417.md))
- **T416**: add Area column to HOT, SDLC, and EPIC tables in tasks_query ([T416](file:///.tasks/T416.md))
- **T415**: add area mode to tasks_query and register T415 ([T415](file:///.tasks/T415.md))
- **T406**: elevate estate search to root workspace and close ticket ([T406](file:///.tasks/T406.md))
- **T262**: archive public-assets-to-r2, enforce human-only db-migrate/deploy rules, fix ticket_audit .tasks/ resolution ([T262](file:///.tasks/T262.md))
- **T413**: build hints log analyzer and automated remediation ([T413](file:///.tasks/T413.md))
- **T53**: mark T53 done across tracking surfaces ([T53](file:///.tasks/T53.md))
- **T412**: elevate governance config, root task board, and core tools to workspace root ([T412](file:///.tasks/T412.md))
- **T411**: establish root .tasks/ queue, tasks-render, and worktree-agent orchestrator ([T411](file:///.tasks/T411.md))
- **T409**: forward rename-audit & decommission recipes and realign wom7open -> wom7pr ([T409](file:///.tasks/T409.md))

### Fixes
- **T431**: root pnpm builds run from wom7web, so deploy-web can find astro ([T431](file:///.tasks/T431.md), [T421](file:///.tasks/T421.md))
- **T431**: acknowledge the historical deploy-client-api / deploy-agent-consultant citations ([T431](file:///.tasks/T431.md), [T198](file:///.tasks/T198.md), [T246](file:///.tasks/T246.md), [T249](file:///.tasks/T249.md))
- **T431**: root justfile exports W0M_DB_MIGRATIONS so deploy-function can parse config.toml ([T431](file:///.tasks/T431.md))
- **T430**: estate-side of the elevation-fallout repair ([T430](file:///.tasks/T430.md))
- **T429**: check-infisical names the real cause; root justfile passes an explicit Infisical project id ([T429](file:///.tasks/T429.md), [T421](file:///.tasks/T421.md))
- **audit**: point spec_drift_gate path to workspace scripts directory
- **sdlc**: point sdlc_doctor to workspace root scripts directory

| Service | Commit | Deployed at |
|---|---|---|
| release | `b8f0de0` | 2026-09-24 05:25:26.816412+00 |

## 2026.09.19-1789869801
_First deployed: 2026-09-20 02:20:02.943086+00_

### Features
- **sdlc**: forward npx-audit recipes in root justfile (T398) ([T398](file:///.tasks/T398.md))
- **sdlc**: forward ticket-recycle recipes in root justfile (T397) ([T397](file:///.tasks/T397.md))
- **skills**: retire root .opencode/skills symlinks and forward ticket-dups recipes (T403) ([T403](file:///.tasks/T403.md))
- **workspace**: update repository and governance references to wom7func (T393) ([T393](file:///.tasks/T393.md))
- **workspace**: establish root package manifest and version management forwarders (T391) ([T391](file:///.tasks/T391.md))
- **tooling**: add just forwarders for crg and graphify dashboards and update agent rules (T388) ([T388](file:///.tasks/T388.md))
- **T370**: delegate default recipe to general info overview ([T370](file:///.tasks/T370.md))
- **just**: forward prs-open and prs-test recipes to wom7web (T369) ([T369](file:///.tasks/T369.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `cdbf5b9` | 2026-09-20 02:20:02.943086+00 |

## 2026.09.12-1789267479
_First deployed: 2026-09-13 02:57:06.784781+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `1858dc8` | 2026-09-13 02:57:06.784781+00 |

## 2026.09.12-1789246682
_First deployed: 2026-09-12 21:10:41.670645+00_

### Features
- **T345**: forward w0m-prs tool from workspace root justfile ([T345](file:///.tasks/T345.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `526df17` | 2026-09-12 21:10:41.670645+00 |

## 2026.09.11-1789185003
_First deployed: 2026-09-12 04:01:33.682502+00_

### Features
- **vm**: add vm management and guest agent install recipes to justfile
- **workspace**: add root forwarder justfile and sync w0m-tasks with EPIC board (T232) ([T232](file:///.tasks/T232.md))
- **governance**: install estate-level w0m skills and multi-agent surfaces at workspace root (T232) ([T232](file:///.tasks/T232.md))

### Fixes
- **skills**: sync corrected fact-checker skill at the estate root (T331) ([T331](file:///.tasks/T331.md))
- **skills**: update w0m-lessons and w0m-state-load to current canonical (T232) ([T232](file:///.tasks/T232.md))

| Service | Commit | Deployed at |
|---|---|---|
| release | `bca29f5` | 2026-09-12 04:01:33.682502+00 |

## 2026.09.06-1788737454
_First deployed: 2026-09-06 23:41:56.038816+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `2a0536f` | 2026-09-06 23:41:56.038816+00 |

## 2026.09.06-1788727367
_First deployed: 2026-09-06 20:53:57.106309+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `2a0536f` | 2026-09-06 20:53:57.106309+00 |

## 2026.09.04-cp-t311
_First deployed: 2026-09-04 18:42:12.936395+00_

### Features
- **estate**: name the _in and _msg trays, and track the conventions not the contents

### Fixes
- **estate**: `/_in/*` not `/_in/` — a negation inside an ignored directory never matches
- **estate**: move nested-repo exclusions out of .gitignore — they broke osv estate-wide

| Service | Commit | Deployed at |
|---|---|---|
| release | `1d853d0` | 2026-09-04 18:42:12.936395+00 |

## 2026.08.26-1787770059
_First deployed: 2026-08-26 18:56:37.048956+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f9cbfeb` | 2026-08-26 18:56:37.048956+00 |

## 2026.08.26-1787760232
_First deployed: 2026-08-26 16:12:53.215373+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `21e6663` | 2026-08-26 16:12:53.215373+00 |

## 2026.08.25-1787717995
_First deployed: 2026-08-26 04:29:07.987956+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `908a58a` | 2026-08-26 04:29:07.987956+00 |

## 2026.08.23-1787537684
_First deployed: 2026-08-24 02:22:49.390324+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `9719077` | 2026-08-24 02:22:49.390324+00 |

## 2026.08.16-1786891220
_First deployed: 2026-08-16 14:48:21.272493+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `b844b3f` | 2026-08-16 14:48:21.272493+00 |

## 2026.08.16-1786888602
_First deployed: 2026-08-16 14:04:31.626152+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `83099dc` | 2026-08-16 14:04:31.626152+00 |

## 2026.08.16-1786887270
_First deployed: 2026-08-16 13:50:54.217111+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `83099dc` | 2026-08-16 13:50:54.217111+00 |

## 2026.08.16-1786881321
_First deployed: 2026-08-16 12:15:22.21781+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `83099dc` | 2026-08-16 12:15:22.21781+00 |

## 2026.08.16-1786874640
_First deployed: 2026-08-16 10:44:46.656359+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `83099dc` | 2026-08-16 10:44:46.656359+00 |

## 2026.08.16-1786871191
_First deployed: 2026-08-16 09:18:11.044956+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `83099dc` | 2026-08-16 09:18:11.044956+00 |

## 2026.08.16-1786868190
_First deployed: 2026-08-16 08:35:41.769541+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `83099dc` | 2026-08-16 08:35:41.769541+00 |

## 2026.08.15-1786825777
_First deployed: 2026-08-15 20:36:04.611248+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `5196087` | 2026-08-15 20:36:04.611248+00 |

## 2026.08.14-1786767541
_First deployed: 2026-08-15 04:22:38.109226+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `003c33f` | 2026-08-15 04:22:38.109226+00 |

## 2026.08.14-1786766604
_First deployed: 2026-08-15 04:07:13.22921+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `003c33f` | 2026-08-15 04:07:13.22921+00 |

## 2026.08.14-1786764093
_First deployed: 2026-08-15 03:25:31.64843+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `748e619` | 2026-08-15 03:25:31.64843+00 |

## 2026.08.13-1786646256
_First deployed: 2026-08-13 19:01:16.898748+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `3455402` | 2026-08-13 19:01:16.898748+00 |

## 2026.08.10-1786387039
_First deployed: 2026-08-10 18:42:27.256191+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `7049f57` | 2026-08-10 18:42:27.256191+00 |

## 2026.07.19-1784493481
_First deployed: 2026-07-19 20:41:45.779201+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `5f1b16d` | 2026-07-19 20:41:45.779201+00 |

## 2026.07.18-1784436966
_First deployed: 2026-07-19 04:59:41.273772+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `5084c05` | 2026-07-19 04:59:41.273772+00 |

## 2026.07.18-1784408734
_First deployed: 2026-07-18 21:09:17.323115+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `5084c05` | 2026-07-18 21:09:17.323115+00 |

## 2026.07.18-1784358677
_First deployed: 2026-07-18 07:14:46.262242+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `0233660` | 2026-07-18 07:14:46.262242+00 |

## 2026.07.16-1784233940
_First deployed: 2026-07-16 20:32:22.750104+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `5003809` | 2026-07-16 20:32:22.750104+00 |

## 2026.07.15-1784096598
_First deployed: 2026-07-15 06:26:50.553764+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `61711d9` | 2026-07-15 06:26:50.553764+00 |

## 2026.07.15-1784094912
_First deployed: 2026-07-15 05:58:57.232057+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `e0fb3fc` | 2026-07-15 05:58:57.232057+00 |

## 2026.07.14-1784042992
_First deployed: 2026-07-14 15:33:24.262831+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `7ef843a` | 2026-07-14 15:33:24.262831+00 |

## 2026.07.14-1784034824
_First deployed: 2026-07-14 13:17:00.633339+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-14 13:17:00.633339+00 |

## 2026.07.14-1784024918
_First deployed: 2026-07-14 10:38:01.133724+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-14 10:38:01.133724+00 |

## 2026.07.14-1784023684
_First deployed: 2026-07-14 10:11:25.628424+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-14 10:11:25.628424+00 |

## 2026.07.14-1784015986
_First deployed: 2026-07-14 08:04:09.873307+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-14 08:04:09.873307+00 |

## 2026.07.14-1784013240
_First deployed: 2026-07-14 07:17:33.91804+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-14 07:17:33.91804+00 |

## 2026.07.14-1784011116
_First deployed: 2026-07-14 06:41:46.313103+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-14 06:41:46.313103+00 |

## 2026.07.14-1784010313
_First deployed: 2026-07-14 06:28:27.029608+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-14 06:28:27.029608+00 |

## 2026.07.14-1784008052
_First deployed: 2026-07-14 05:50:41.401957+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-14 05:50:41.401957+00 |

## 2026.07.14-1784007541
_First deployed: 2026-07-14 05:42:55.639242+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-14 05:42:55.639242+00 |

## 2026.07.14-1784006437
_First deployed: 2026-07-14 05:23:49.303039+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-14 05:23:49.303039+00 |

## 2026.07.13-1784003582
_First deployed: 2026-07-14 04:36:29.168884+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-14 04:36:29.168884+00 |

## 2026.07.13-1783979199
_First deployed: 2026-07-13 21:49:58.972097+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-13 21:49:58.972097+00 |

## 2026.07.13-1783978127
_First deployed: 2026-07-13 21:32:23.714363+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `f670915` | 2026-07-13 21:32:23.714363+00 |

## 2026.07.10-1783720961
_First deployed: 2026-07-10 22:02:43.772694+00_

| Service | Commit | Deployed at |
|---|---|---|
| release | `cdc2071` | 2026-07-10 22:02:43.772694+00 |

