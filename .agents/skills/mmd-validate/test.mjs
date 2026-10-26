#!/usr/bin/env node
// T195 AC7 — the red probe mmd-validate shipped without.
//
// This gate runs on every commit (.pre-commit-config.yaml -> mmd-validate) and had, until
// 2026-08-13: no test, no `just` recipe, and no entry in project/test-suites.json. It was
// therefore invisible to `just suites-drift` — which enumerates justfile recipes — no matter how
// the matcher was widened. It is one of 10 of 11 pre-commit entries that bypass `just` entirely.
//
// 🔴 The case that matters most is PROSE-MENTION (below). On 2026-08-10 an unanchored fence regex
// made a documented mention of ```mermaid inside an inline code span open a phantom diagram that
// ran to the next real fence, so docs/00-MOC-FLOWS-AND-DIAGRAMS.md reported its 3 valid diagrams
// as 4, one bogus, and blocked a legitimate commit. The regex was fixed the same day; this file is
// the proof it stays fixed.
//
// Run: `just mmd-validate-test`
import { execFileSync } from "node:child_process";
import { cpSync, mkdirSync, mkdtempSync, rmSync, symlinkSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { fileURLToPath } from "node:url";

const HERE = fileURLToPath(new URL(".", import.meta.url));
const VALIDATE = join(HERE, "validate.mjs");
const TMP = mkdtempSync(join(tmpdir(), "mmd-probe-"));
const failures = [];

function run(...files) {
  try {
    return { rc: 0, out: execFileSync("node", [VALIDATE, ...files], { encoding: "utf8" }) };
  } catch (e) {
    return { rc: e.status ?? 1, out: String(e.stdout ?? "") + String(e.stderr ?? "") };
  }
}

function runWithOpts(args, opts = {}) {
  try {
    return { rc: 0, out: execFileSync("node", args, { encoding: "utf8", ...opts }) };
  } catch (e) {
    return { rc: e.status ?? 1, out: String(e.stdout ?? "") + String(e.stderr ?? "") };
  }
}

function write(name, body) {
  const p = join(TMP, name);
  writeFileSync(p, body);
  return p;
}

function check(label, ok, detail = "") {
  console.log(`  ${ok ? "✅" : "❌"} ${label}`);
  if (!ok) failures.push(`${label}${detail ? ` — ${detail}` : ""}`);
}

const VALID = "graph TD\n  A[Start] --> B[End]";
const INVALID = "graph TD\n  A[Start] -->< B]]]";

// ⚠️ Vacuity guard FIRST. validate.mjs exits 2 with a missing runtime dependencies message when
// jsdom/mermaid are not installed.
const probe = run(write("valid.mmd", VALID));
if (probe.rc === 2 || probe.out.includes("missing runtime dependencies")) {
  console.error("❌ mmd-validate deps are not installed — this probe cannot run.");
  console.error(`   Run \`cd ${HERE} && npm install\`, then re-run.`);
  process.exit(2);
}

console.log("\n── the gate goes green on valid input ──");
check("a valid .mmd passes", probe.rc === 0, probe.out.trim());

let r = run(write("valid.md", `# Doc\n\n\`\`\`mermaid\n${VALID}\n\`\`\`\n`));
check("a valid fence in .md passes", r.rc === 0, r.out.trim());
check("...and reports exactly 1 diagram", /\b1 diagram\(s\) valid/.test(r.out), r.out.trim());

console.log("\n── and RED on invalid input (a gate that cannot fail is not a gate) ──");
r = run(write("bad.mmd", INVALID));
check("an invalid .mmd fails", r.rc === 1, r.out.trim());

r = run(write("bad.md", `# Doc\n\n\`\`\`mermaid\n${INVALID}\n\`\`\`\n`));
check("an invalid fence in .md fails", r.rc === 1, r.out.trim());

console.log("\n── 🔴 the 2026-08-10 regression: a PROSE MENTION is not a diagram ──");
// Exactly the shape in CLAUDE.md and docs/VAULT-INDEX.md: the fence syntax named inside an inline
// code span, followed by real diagrams. The unanchored regex treated the mention as an opening
// fence and swallowed the prose between it and the next real fence.
const prose = [
  "# How we document diagrams",
  "",
  "Write diagrams in a `` ```mermaid `` fence, like this:",
  "",
  "Some prose with a --- horizontal rule that is NOT a diagram.",
  "",
  "```mermaid",
  VALID,
  "```",
  "",
  "More prose.",
  "",
  "```mermaid",
  "sequenceDiagram\n  Alice->>Bob: Hi",
  "```",
  "",
].join("\n");
r = run(write("prose.md", prose));
check("a prose mention of the fence syntax does not fail the file", r.rc === 0, r.out.trim());
check(
  "...and exactly 2 diagrams are counted, not 3",
  /\b2 diagram\(s\) valid/.test(r.out),
  r.out.trim(),
);

console.log("\n── counting stays honest at the edges ──");
r = run(write("none.md", "# No diagrams here\n\nJust prose.\n"));
check(
  "a file with no fences passes with 0 diagrams",
  r.rc === 0 && /\b0 diagram\(s\)/.test(r.out),
  r.out.trim(),
);

r = run(write("indented.md", "Text\n\n   ```mermaid\n" + VALID + "\n   ```\n"));
check(
  "a fence indented ≤3 spaces is still found (CommonMark)",
  /\b1 diagram\(s\) valid/.test(r.out),
  r.out.trim(),
);

r = run(write("empty.mmd", "   \n"));
check("an empty .mmd yields 0 diagrams rather than a parse error", r.rc === 0, r.out.trim());

console.log("\n── T521 AC4/AC5/AC6: portable client-project invocation & missing-deps failure ──");
const missingDeps = runWithOpts([VALIDATE, write("valid.mmd", VALID)], {
  env: { ...process.env, MMD_VALIDATE_FORCE_MISSING_DEPS: "1" },
});
check(
  "missing jsdom/mermaid exits non-zero (rc=2) with actionable install command",
  missingDeps.rc === 2 &&
    missingDeps.out.includes("missing runtime dependencies") &&
    missingDeps.out.includes("npm install"),
  missingDeps.out.trim(),
);

// Build a scratch client-shaped project under tmpdir() with no w0m* or wom7* in its path.
const clientRoot = mkdtempSync(join(tmpdir(), "client-proj-"));
try {
  check(
    "scratch client project path contains no w0m* or wom7* parent segment",
    !/w0m|wom7/i.test(clientRoot),
    clientRoot,
  );
  const clientSkillDir = join(clientRoot, ".agents", "skills", "mmd-validate");
  mkdirSync(clientSkillDir, { recursive: true });
  cpSync(VALIDATE, join(clientSkillDir, "validate.mjs"));
  cpSync(join(HERE, "package.json"), join(clientSkillDir, "package.json"));
  symlinkSync(join(HERE, "node_modules"), join(clientSkillDir, "node_modules"));

  const docsDir = join(clientRoot, "docs");
  mkdirSync(docsDir, { recursive: true });
  writeFileSync(join(docsDir, "ok.mmd"), VALID + "\n");
  writeFileSync(join(docsDir, "broken.mmd"), INVALID + "\n");
  writeFileSync(join(docsDir, "spec.md"), `# Client Spec\n\n\`\`\`mermaid\n${INVALID}\n\`\`\`\n`);

  // Run from clientRoot using the portable installed path `.agents/skills/mmd-validate/validate.mjs --root .`
  const redClient = runWithOpts([".agents/skills/mmd-validate/validate.mjs", "--root", "."], {
    cwd: clientRoot,
  });
  check(
    "portable invocation in client project fails (rc=1) when 1 .mmd and 1 .md fence are broken",
    redClient.rc === 1 && /\b2\/3 diagram\(s\) invalid/.test(redClient.out),
    redClient.out.trim(),
  );
  check(
    "portable failure output names both broken.mmd and spec.md#mermaid[0]",
    redClient.out.includes("broken.mmd") && redClient.out.includes("spec.md#mermaid[0]"),
    redClient.out.trim(),
  );

  // Fix both broken files and re-run from clientRoot
  writeFileSync(join(docsDir, "broken.mmd"), "sequenceDiagram\n  Client->>API: ping\n");
  writeFileSync(join(docsDir, "spec.md"), `# Client Spec\n\n\`\`\`mermaid\n${VALID}\n\`\`\`\n`);
  const greenClient = runWithOpts([".agents/skills/mmd-validate/validate.mjs", "--root", "."], {
    cwd: clientRoot,
  });
  check(
    "portable invocation in client project exits 0 (3/3 valid) once broken diagrams are fixed",
    greenClient.rc === 0 && /\b3 diagram\(s\) valid/.test(greenClient.out),
    greenClient.out.trim(),
  );
} finally {
  rmSync(clientRoot, { recursive: true, force: true });
  rmSync(TMP, { recursive: true, force: true });
}

console.log();
if (failures.length) {
  console.error(`❌ ${failures.length} failure(s):`);
  for (const f of failures) console.error(`   · ${f}`);
  process.exit(1);
}
console.log("✅ mmd-validate: all checks passed");
