# T458 S6 — engagement review lists (measured 2026-09-27, read-only, live)

**Ticket:** [[T458]] step S6 (AgDR-0028 decisions 1–2: orgs connect only through engagements; contracts and projects
belong to an engagement). Nothing written; these lists are for the owner to confirm before the S6 migration.

**Source:** `public.contracts`: 98 rows, 0 soft-deleted, 94 `upwork` (all `CLOSED`) + 4 `direct`, **78 distinct client
names**; 4 carry a `client_id`, 3 a `project_id`. `public.projects`: 7.

## List A — the 78 historical client names → companies

S6 creates one company per client name and one engagement `webomage.eg-<id>.<company>` per contract group, contractor
`webomage`. The owner confirms or corrects each group below.

**Already companies (4, reuse the existing org):** `Artemio, quiero comer!` → `artemio-quiero-comer`; `BridgeRoad` →
`bridgeroad`; `Inovus Investments Inc.` → `inovus-investments-inc`; `Northwind Studio` → `demo` (the demo fixture:
recommend **excluding** it from history, it is reseeded).

**Probably the same company as an existing org (confirm):** `Renowned Marketing LLC` → `kayse-renowned-marketing-llc`
(that org's client record says company "Renowned Marketing LLC").

**Not a client at all (decide):**

| Name | Contracts | Recommendation |
|---|---|---|
| `DELETED` | 2 | Upwork's placeholder for a deleted client account: one company `upwork-deleted-client`, or two anonymous ones |
| `Healthcare` | 1 | looks like a category, not a name: keep as recorded unless the owner knows the client |
| `Elena Kushnareva` | 1 | a person; confirm it is not Elena (operator member) before making it a client |

**Looks like a person, not a company (21, by name only; the owner may reclassify):** A Adach, Alexander De Ridder, Antras Erelis, Artem Vostrikov, Ben Israel, Brooks Patton (2), Chris Otieno (2), Edward Bishop, Elena Kushnareva, Emil B (2), Evgeny Pogrebnyak, Floyd D (4), Henrique Souza, Igor Tarasov, Ivan Spiridonov, Jesse Leimgruber, michael bell, Michael Colin, Roland Wagner (5), Sufian A, Victor Gartvich.
A historical client has no account here, and AgDR-0027 personal orgs belong to registered persons, so the
recommendation is a **company named after the person**, claimable later through the directory (decision 9).

**Several contracts from one client:** EventCartel.com (7), Roland Wagner (5), Floyd D (4), Agency Entertainment &
Marketing S.L (2), Brooks Patton (2), Chris Otieno (2), Dabble Lab (2), Emil B (2), Market Republic Technologies Ltd.
(2). One company each, and **one engagement per contract** (AgDR-0028 as accepted, except contracts already on a
project).

**Companies, one each (50):** ACQhq, LLC, Agency Entertainment & Marketing S.L (2), Ambitechstrous, AMZ Tracker, Appinux, Auxility Software Development Agency, BlockVest Movement, BTR LTD, creative suburbs, Dabble Lab (2), Data Sleek LLC, DcentraLab Ltd, Digital Kickstart, EDA, Elevate 360, Engineering Simplicity, ETLA, The Research Institute of the Finnish Economy, EventCartel.com (7), FirstLine Corporation Pty Ltd, Fovea.cc, Friends Of CNM, FunnelEnvy, gTeam FZ LLC, Hekwerk, Honeylove, Idera, Kaizen, Lotus Interworks Inc., Market Republic Technologies Ltd. (2), Medical Business Consulting Ltd, MYM Inc., New Zealand Fighter, Newport Capital LLC, Openmart, Inc., PassiveBolt, Inc., PME Solution, Qbix Inc., Romantic Robot LTD, SafeBytes Software Inc., SafeMotos, Scale AI, Scribely, The Comm Network, Travel Co, Upstock, Viewmyact, VNC AG, VXG Inc, W AI, WOWITO LTD.

Totals: 5 existing or matched + 2 to decide + 21 person-named + 50 companies
= 78 names.

## List B — projects and their contracts

| Project | Client org | Contracts linked | Proposed engagement |
|---|---|---|---|
| `artemio-quiero-comer` | artemio-quiero-comer | 1 (direct, active) | `webomage.eg-<id>.artemio-quiero-comer`, with that contract |
| `bridgeroad-mvp` | bridgeroad | 1 (direct, active) | `webomage.eg-<id>.bridgeroad`, with that contract |
| `marketing-site-rebuild-demo` | — (demo reseed left `client_org_id` empty) | 1 (demo) | the demo's engagement with `demo`; fix `seed-demo` to set the client org |
| `kayse-ai` | kayse-renowned-marketing-llc | 0 | **match:** Renowned Marketing LLC, "Engineering Manager / Director of Engineering", Upwork 39317728, from 2024-12-24 |
| `theorql` | inovus-investments-inc | 0 | **match:** Inovus Investments Inc., "AI-Startup Seeking Back End Developer…", Upwork 40687618, from 2025-05-26 |
| `featherglass` | featherglass | 0 | **no contract matches** by client name or title: owner names it, or the project gets an engagement with no contract |
| `meetocean-ai` | meetocean-ai | 0 | **no contract matches**: same |

Candidates by date if Featherglass or Meetocean.ai were billed under another client name (Upwork contracts started
since 2025-06): Ben Israel "Server Dev Ops Consulting and Admin" (2025-06-30), VXG Inc "DevOps Engineer for AWS and K3s
Automation" (2025-11-11), Scribely "AWS Audio Description Automation" (2026-01-24), Sufian A "60 minute consultation"
(2026-02-13), Jesse Leimgruber "Build Voice AI Abilities…" (2026-02-20).

## Also found

- **The platform project is missing.** AgDR-0028 decision 11's worked example is `webomage.eg-<id>.webomage`, "the w0m
  platform project", but no project for the platform exists among the 7. S6 creates its engagement; whether it also
  gets a `projects` row is the owner's call (recommend yes, so hats and milestones have a home).
- `seed-demo` creates the demo project with `client_id` but no `client_org_id`, so `/o/demo` would not list it as the
  client's project. Small fix, bundled with S6.

## Questions (weighted)

| # | Question | Recommendation | Weight |
|---|---|---|---|
| Q1 | Persons among historical clients | companies named after the person, claimable later | Keeps personal orgs for registered people only; no accounts invented |
| Q2 | `DELETED` (2 contracts) | one company `upwork-deleted-client` | Honest record; two anonymous companies add noise |
| Q3 | `Renowned Marketing LLC` = Kayse's org? | yes, merge | Avoids a duplicate company for one client |
| Q4 | Featherglass, Meetocean.ai | owner names the contract, or an engagement without one | Only the owner knows how they were billed |
| Q5 | Exclude the demo `Northwind Studio` contract from history | yes | Fixture, reseeded on demand |
| Q6 | Platform project row | yes, `w0m` project in engagement `webomage.eg-<id>.webomage` | Gives the 8 delivery hats a real project in S7 |
