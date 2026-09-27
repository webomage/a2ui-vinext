# Changelog

_Generated from the `deploy_log` table by `just changelog`. Each heading is one deploy stamp (`YYYY.MM.DD-<unixtimestamp>`)._

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

