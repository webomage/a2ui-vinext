# Resume Studio vs `Aleksei_CV_2026_Public.pdf` — what we can replicate (T555 AC2 evidence)

Measured 2026-10-07, read-only. Reference: `apps/cp/public/cv/Aleksei_CV_2026_Public.pdf` (6 pages, A4, WeasyPrint, Inter; the four copies on disk and in the repo are byte-identical). Studio output: the real `synthesizeResume` + `renderResumeMarkdown` run on the owner's live data (29 curated facts, 135 highlights), the way `ResumeStudio.svelte` loads it.

## Verdict

**Experience content: 75% of the reference's 84 bullets are reproducible today (63/84). 100% (84/84) are reproducible once the database is brought to the canonical file.** Every one of the 84 bullets exists word for word in `project/data/cv/resume.json`; the database holds 135 of the canonical 206 highlights, and the 71 missing include the 21 the PDF uses. That is a loader gap, not a data gap.
**Structure: about half.** The Studio has no concept of four of the PDF's ten parts (Executive Summary text, Core Competencies, Accreditations, Open-source) and does not load Education. It cannot produce the PDF's umbrella layout (Webomage with its 22 client engagements nested) or the "Earlier Employment" block with bullets.
**Look:** the Studio offers a Markdown download and the browser's print dialog. The PDF is a WeasyPrint render in Inter with its own stylesheet. Not the same artifact, and nothing generates it from the database.

## Part by part

| # | Part of the PDF | Studio today | Replicable? | Needs |
|---|---|---|---|---|
| 1 | Header: name, headline "Principal Software Engineer & DevOps Architect", location with UTC note, email, site, LinkedIn, GitHub, Upwork | Name, email, links: yes. Headline comes from the chosen target role ("Senior DevOps Engineer & Cloud Infrastructure Architect"), not the profile's. Location "Playa del Carmen, Mexico" (PDF: Quintana Roo, UTC-5, Remote Worldwide). Upwork link is `upwork.com/freelancers/casualuser`, the PDF prints `upwork.webomage.com` | Mostly | A profile headline field; location text; decide which Upwork URL |
| 2 | Executive Summary: paragraph plus three bold-lead bullets (Upwork, ACS, technical mastery) | **Absent.** `profiles.description` is NULL for the owner, so no "## Summary" is printed | Yes after AC3 | Approved summary text in canonical and DB (owner decision recorded: 2026 wording with canonical numbers). Multi-line summary needs a check that the bullets render |
| 3 | Core Competencies & Technical Skills: 7 groups | **Absent.** Skills are derived from `profile_experience.skills`; the 95 Upwork rows have none and `profile_skills` has 0 rows | Partly | The PDF's 7 groups are NOT in `resume.json` (it has 5 different groups). Owner decision: 2026 groups, evidenced items only; the nine unevidenced terms stay out |
| 4 | Professional Experience: Webomage umbrella (5 headline bullets) plus "22 engagements, most recent first" nested | Flat list of 29 positions. Webomage shows 12 of its 15 bullets, and they are a mix of its own and client-derived ones. Artemio is listed above Webomage because it is current | Not the layout | A "client engagement under an umbrella" relation, or a per-variant order and nesting. Per-variant bullet selection (the PDF uses 3 of 15 for Webomage) |
| 5 | Earlier Employment: explanatory paragraph plus 8 roles, each with bullets | Only in Compact mode, as one-line entries without bullets. In Full mode they are ordinary positions | No | Section break by an "employment kind" flag plus the paragraph; keep bullets |
| 6 | Professional Accreditations: ACS, IELTS, Upwork Top Rated Plus | **Absent.** Certificates are never loaded from anywhere | Partly | `resume.json` has ACS and MCP only. IELTS and Top Rated Plus are not canonical. ACS reference number A-438949 must never appear publicly. Owner will supply the ACS and IELTS dates |
| 7 | Open-source contributions: 6 entries (tart-guest-agent PR #62, FIDO2 PR #48, Serverless PR #245, IcedCoffeeScript, Lambda gist, Ansible playbooks) | **No such section in the renderer.** `resume.json` carries a single "Open Source" project entry | No | Renderer section plus data (6 entries) plus claims check |
| 8 | Education: Saint Petersburg State University of Aerospace Instrumentation, Engineer's degree | **Not loaded** (`education` is always empty) | **Blocked by a data conflict** | `resume.json` says North-Western State Correspondence Technical University (1998–2003) and Lyceum of Information Technologies (1993–1998). The PDF's university appears only in `docs/backend/branding/*Master.md` and the PDF. One is wrong or they are two different things: owner must say which |
| 9 | Dates and per-job location | "2026-04-01 — Present", no location. PDF: "Apr 2026 – Present" and "Playa del Carmen, MX / Remote" | Yes | Formatter change; the database already holds `location` |
| 10 | Typography and PDF file | Markdown or browser print | No | A server-side render path (the PDF's pipeline is WeasyPrint) if the Studio is to produce the file itself |

## Defects found on the way (not in the PDF's parts)

1. **No privacy mode produces the PDF.** Studio has `full` (names, phone, street address: the private CV) and `masked`/`public` (employer names masked as `A*** q*** c***`). The public PDF names its clients but has no phone or address. A "named employers, no private contact" mode does not exist.
2. **Featured Projects loads the platform's `projects` table** (`select … from projects limit 10`, 7 rows today incl. a demo and other clients' work), not the member's own projects. The PDF has no such section; if it printed it would list rows that are not the owner's.
3. **Highlight caps.** Full keeps at most 12 bullets per employer; TokensFarm (15) and EventCartel (13) lose some. The PDF shows 3 per client entry.
4. **Public CV is hand-written.** `cv_public.py` is a leak gate, not a generator; the PDF comes from `docs/backend/branding/…_Public.md`, so nothing keeps it in step with `resume.json`.

## Reproduction

Bullets compared after normalising markup and dashes, match at ≥ 0.9 similarity. Generated with `synthesizeResume`/`renderResumeMarkdown` from `packages/lib/src/resume/synthesis.ts` on the rows of `profile_cv_facts` for the owner (`full` and `compact`, role `devops`, privacy `public`, date order). Facts per employer in the DB versus used by the PDF: Webomage 15/5, TokensFarm 15/3, EventCartel 13/3, Inovus 7/3, Featherglass 6/3.

## Questions for the owner (weighted)

1. **Education**: which is correct, SUAI (PDF) or North-Western correspondence university plus Lyceum (canonical)? Blocks part 8. Cost: one reply. Risk if wrong: a false credential on a public CV.
2. **Public privacy mode** (defect 1): add "named employers, no phone/address". Recommended yes; small change, unblocks the whole comparison.
3. **Umbrella layout** (part 4): model Webomage's clients as nested entries (recommended) versus keeping a flat list with a per-variant exclusion list (already planned in T555). Nested is closer to the PDF, flat is cheaper.
4. **PDF file**: should the Studio produce the PDF (server render, larger) or keep Markdown plus print (today)? Recommended: keep print for now and compare after the structure work.
