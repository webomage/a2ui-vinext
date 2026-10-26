#!/usr/bin/env node
// mmd-validate — headless Mermaid validation. NO browser / NO playwright / NO chromium.
// Engine: mermaid.parse() over a jsdom DOM shim → deterministic syntax validation that runs
// locally, in CI, and (under Node) server-side. A parse failure is the real "won't render" cause.
//
// Validates BOTH:
//   • standalone .mmd files (the preferred external source of truth), and
//   • ```mermaid fenced blocks embedded in .md / .mdx (docs & specs).
//
// Usage:
//   node validate.mjs [file ...]     # validate the given .mmd/.md/.mdx (git hook passes staged files)
//   node validate.mjs --root <dir>   # recurse <dir> for *.mmd/*.md/*.mdx (default: cwd)
// Exit 0 = all valid; exit 1 = one or more invalid; exit 2 = missing runtime deps (mermaid/jsdom).
//
// No bash: discovery uses a pure-node recursive walk. Deps (mermaid, jsdom) are dynamically
// imported; if missing, validate.mjs fails fast with an actionable install command.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const SKILL_DIR = dirname(fileURLToPath(import.meta.url));
const EXT = /\.(mmd|md|mdx)$/;

// Pure-node recursive walk (no shell) — includes dot-dirs like openspec; skips node_modules/dist/.git.
function findFiles(dir) {
  const out = [];
  let ents;
  try {
    ents = readdirSync(dir, { withFileTypes: true });
  } catch {
    return out;
  }
  for (const ent of ents) {
    if (ent.name === "node_modules" || ent.name === "dist" || ent.name === ".git") continue;
    const p = join(dir, ent.name);
    if (ent.isDirectory()) out.push(...findFiles(p));
    else if (EXT.test(ent.name)) out.push(p);
  }
  return out;
}

// Extract the diagram source(s) from a file: whole file for .mmd; each ```mermaid fence for .md/.mdx.
function extractDiagrams(file, text) {
  if (file.endsWith(".mmd")) return text.trim() ? [{ src: text.trim(), label: file }] : [];
  const out = [];
  // Fences must START A LINE (CommonMark allows ≤3 spaces of indent). The old pattern had no
  // anchor, so a PROSE MENTION of the fence syntax — ```` ```mermaid ```` inside an inline code
  // span, which is how CLAUDE.md and docs/VAULT-INDEX.md document the convention — opened a
  // phantom diagram that ran to the next real fence and reported the intervening markdown as an
  // invalid diagram. Found 2026-08-10 when docs/00-MOC-FLOWS-AND-DIAGRAMS.md failed pre-commit
  // on "diagrams beginning with --- are not valid": the ONE line documenting mermaid usage made
  // the file's 3 valid diagrams read as 4, one bogus. A validator that miscounts what it found
  // is the measurement trap this estate keeps hitting — the tool commits the defect it hunts.
  const re = /^[ \t]{0,3}```mermaid[^\n]*\n([\s\S]*?)^[ \t]{0,3}```/gm;
  let m,
    i = 0;
  while ((m = re.exec(text)) !== null) {
    const src = m[1].trim();
    if (src) out.push({ src, label: `${file}#mermaid[${i}]` });
    i++;
  }
  return out;
}

// Deps guard: set jsdom globals BEFORE importing mermaid (mermaid wires DOMPurify at import time).
let mermaid;
try {
  if (process.env.MMD_VALIDATE_FORCE_MISSING_DEPS === "1") {
    throw new Error("forced missing runtime dependencies");
  }
  const { JSDOM } = await import("jsdom");
  const dom = new JSDOM("<!DOCTYPE html><body></body>", { pretendToBeVisual: true });
  globalThis.window = dom.window;
  globalThis.document = dom.window.document;
  globalThis.DOMParser = dom.window.DOMParser;
  mermaid = (await import("mermaid")).default;
} catch {
  console.error(
    `✗ mmd-validate: missing runtime dependencies (mermaid, jsdom).\n` +
      `  Install them in the skill directory:\n` +
      `    cd ${SKILL_DIR} && npm install\n` +
      `  Or add "mermaid" and "jsdom" to your project's devDependencies.`,
  );
  process.exit(2);
}
mermaid.initialize({ startOnLoad: false, securityLevel: "loose" });

const args = process.argv.slice(2);
const rootIdx = args.indexOf("--root");
const root = rootIdx >= 0 ? args[rootIdx + 1] : ".";
let files = args.filter((a, i) => !a.startsWith("--") && !(rootIdx >= 0 && i === rootIdx + 1));
if (files.length === 0) files = findFiles(root.replace(/\/$/, ""));

let diagrams = 0;
const bad = [];
for (const f of files) {
  let text = "";
  try {
    text = readFileSync(f, "utf8");
  } catch {
    continue;
  }
  for (const d of extractDiagrams(f, text)) {
    diagrams++;
    try {
      await mermaid.parse(d.src);
    } catch (e) {
      bad.push([
        d.label,
        String(e?.message ?? e)
          .split("\n")[0]
          .slice(0, 120),
      ]);
    }
  }
}

if (bad.length) {
  console.error(`✗ mmd-validate: ${bad.length}/${diagrams} diagram(s) invalid`);
  for (const [l, m] of bad) console.error(`  ✗ ${l}\n      ${m}`);
  process.exit(1);
}
console.log(`✓ mmd-validate: ${diagrams} diagram(s) valid across ${files.length} file(s)`);
