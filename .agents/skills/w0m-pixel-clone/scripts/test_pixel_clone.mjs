#!/usr/bin/env node
/**
 * test_pixel_clone.mjs — End-to-end and unit probe suite for `w0m-pixel-clone` (T132 AC1–AC7).
 *
 * Run: `node w0m-skills/skills/w0m-pixel-clone/scripts/test_pixel_clone.mjs`
 */

import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { join } from "node:path";
import {
  BREAKPOINTS,
  checkAuthorization,
  compareVisualFidelity,
  emitSvelteAstro,
  extractTokens,
  parseStructure,
  runCli,
  validateCaptureInputs,
  writeOutlineArtifact,
} from "./pixel_clone.mjs";

const failures = [];
function check(label, ok, detail = "") {
  console.log(`  ${ok ? "[PASS]" : "[FAIL]"} ${label}`);
  if (!ok) failures.push(`${label}${detail ? ` — ${detail}` : ""}`);
}

console.log("\n── Stage 0 (AC7): Legal / ToS authorization guardrail ──");
{
  const firstParty = checkAuthorization({ url: "https://cp.webomage.com/pricing" });
  check(
    "first-party webomage.com domain is authorized without brand sanitization",
    firstParty.authorized === true && firstParty.sanitizeBrand === false,
  );

  const thirdPartyBlocked = checkAuthorization({
    url: "https://unauthorized-competitor.example.com/landing",
    confirmAuthorized: false,
  });
  check(
    "RED: unauthorized third-party domain without --confirm-authorized is refused",
    thirdPartyBlocked.authorized === false &&
      /not in the first-party\/client allowlist/i.test(thirdPartyBlocked.error || ""),
  );

  const thirdPartyStudy = checkAuthorization({
    url: "https://unauthorized-competitor.example.com/landing",
    confirmAuthorized: true,
  });
  check(
    "third-party domain with --confirm-authorized enables mandatory brand/copy sanitization",
    thirdPartyStudy.authorized === true &&
      thirdPartyStudy.sanitizeBrand === true &&
      Boolean(thirdPartyStudy.warning),
  );
}

console.log("\n── Stage 1 (AC1): Multi-source capture contract & 3 breakpoints ──");
{
  const empty = validateCaptureInputs({});
  check("RED: missing all capture inputs is refused", empty.valid === false);

  const validCombo = validateCaptureInputs({
    url: "http://localhost:4321",
    screenshots: "mobile.png,tablet.png,desktop.png",
    dom: "fixture.html",
    css: "fixture.css",
  });
  check(
    "accepts URL + screenshots + DOM/CSS and exposes 375/768/1440 breakpoints",
    validCombo.valid === true &&
      BREAKPOINTS.map((b) => b.width).join(",") === "375,768,1440" &&
      validCombo.sources.screenshots.length === 3,
  );
}

console.log("\n── Stage 2 (AC2): Structural & section parser + auditable outline.md ──");
const SAMPLE_HTML = `
  <header>
    <strong>AcmeCloud</strong>
    <nav>
      <a href="/overview">Overview</a>
      <a href="/features">Features</a>
      <a href="/pricing">Pricing</a>
    </nav>
  </header>
  <section class="hero">
    <h1>Deploy Edge Workflows Faster</h1>
    <p>Zero-config observability and instant rollbacks across regions.</p>
    <button>Start Trial</button>
  </section>
  <section class="features">
    <article class="card"><h3>Instant Routing</h3><p>Sub-millisecond global dispatch.</p></article>
    <article class="card"><h3>Live Traces</h3><p>Streaming tail logs at the edge.</p></article>
  </section>
  <footer>© 2026 AcmeCloud Inc.</footer>
`;

const SAMPLE_CSS = `
  :root {
    --brand: #3b82f6;
    --bg: #0f172a;
    --surface: #1e293b;
    --text: #f8fafc;
  }
  body {
    font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
    border-radius: 0.875rem;
    gap: 1.25rem;
  }
`;

{
  const parsed = parseStructure(SAMPLE_HTML, {
    hostname: "localhost",
    sanitizeBrand: false,
  });
  const kinds = parsed.sections.map((s) => s.kind);
  check(
    "normalizes HTML into header, hero, cards, footer sections",
    kinds.join(",") === "header,hero,cards,footer",
    kinds.join(","),
  );

  const tmp = mkdtempSync(join(tmpdir(), "pixel-clone-outline-"));
  try {
    const written = writeOutlineArtifact(tmp, parsed);
    check(
      "writes docs/research/<hostname>/outline.md on disk",
      existsSync(written.absPath) &&
        written.relPath === join("docs", "research", "localhost", "outline.md"),
    );
    const md = readFileSync(written.absPath, "utf8");
    check(
      "outline.md records all 4 section kinds and interactive states",
      md.includes("`header`") &&
        md.includes("`hero`") &&
        md.includes("`cards`") &&
        md.includes("`footer`") &&
        md.includes("`hover`"),
    );
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

console.log("\n── Stage 3 (AC3): Design token extractor & RGB triplet rule ──");
{
  const tokenSheet = extractTokens(SAMPLE_CSS);
  check(
    "extracts --brand and --brand-rgb triplet (59, 130, 246 for #3b82f6)",
    tokenSheet.tokens["--brand"] === "#3b82f6" &&
      tokenSheet.tokens["--brand-rgb"] === "59, 130, 246",
    JSON.stringify(tokenSheet.tokens),
  );
  check(
    "zero raw #hex inside rgba(...) in generated token sheet",
    !/rgba\(\s*#/i.test(tokenSheet.cssText) &&
      !/rgba\(\s*var\(--(?:brand|bg|surface|text)\)/i.test(tokenSheet.cssText) &&
      tokenSheet.cssText.includes("rgba(var(--brand-rgb), 0.16)"),
  );
}

console.log("\n── Stage 4 (AC4): Svelte 5 runes + Astro emitter (@webomage/ui conformance) ──");
{
  const structure = parseStructure(SAMPLE_HTML, { hostname: "localhost" });
  const tokenSheet = extractTokens(SAMPLE_CSS);
  const emitted = emitSvelteAstro(structure, tokenSheet);

  check(
    "Svelte 5 component uses $props(), $state(), $derived() runes",
    emitted.svelteCode.includes("$props()") &&
      emitted.svelteCode.includes("$state(") &&
      emitted.svelteCode.includes("$derived("),
  );
  check(
    "Svelte 5 component imports @webomage/ui primitives (Button, Card, Badge, Input, Select, PageHeader)",
    emitted.svelteCode.includes('from "@webomage/ui"') &&
      emitted.svelteCode.includes("<Button") &&
      emitted.svelteCode.includes("<Card>"),
  );
  check(
    "Svelte 5 component contains zero raw <button>/<input>/<select>, zero #hex, and zero inline style=",
    !/<(?:button|input|select)\b/.test(emitted.svelteCode) &&
      !/#[0-9a-fA-F]{3,6}\b/.test(emitted.svelteCode) &&
      !/\bstyle=/.test(emitted.svelteCode),
  );
}

console.log("\n── Stage 5 (AC5): Closed visual-diff verification comparator (<= 2% mismatch) ──");
{
  const ref = Array.from({ length: 400 }, () => 120);
  const candPass = [...ref];
  // Perturb 1 pixel out of 100 (1.0% <= 2.0%)
  candPass[0] = 250;
  const passRes = compareVisualFidelity({
    threshold: 0.02,
    breakpoints: [
      { name: "mobile", referencePixels: ref, candidatePixels: candPass },
      { name: "tablet", referencePixels: ref, candidatePixels: candPass },
      { name: "desktop", referencePixels: ref, candidatePixels: candPass },
    ],
  });
  check(
    "GREEN: visual diff <= 0.02 (1.0% mismatch) passes across all 3 breakpoints",
    passRes.passed === true && passRes.maxMismatchRatio === 0.01,
  );

  const candFail = [...ref];
  // Perturb 5 pixels out of 100 (5.0% > 2.0%)
  for (let i = 0; i < 5 * 4; i += 4) candFail[i] = 250;
  const failRes = compareVisualFidelity({
    threshold: 0.02,
    breakpoints: [
      { name: "mobile", referencePixels: ref, candidatePixels: candPass },
      { name: "desktop", referencePixels: ref, candidatePixels: candFail, region: "hero" },
    ],
  });
  check(
    "RED: visual diff > 0.02 (5.0% mismatch) fails and names breakpoint + region",
    failRes.passed === false &&
      failRes.failingRegions.length === 1 &&
      failRes.failingRegions[0].breakpoint === "desktop" &&
      failRes.failingRegions[0].region === "hero",
  );
}

console.log("\n── CLI End-to-End Integration Test ──");
{
  const tmp = mkdtempSync(join(tmpdir(), "pixel-clone-cli-"));
  try {
    const domFile = join(tmp, "sample.html");
    const cssFile = join(tmp, "sample.css");
    const diffPassFile = join(tmp, "diff-pass.json");
    const diffFailFile = join(tmp, "diff-fail.json");
    writeFileSync(domFile, SAMPLE_HTML);
    writeFileSync(cssFile, SAMPLE_CSS);
    writeFileSync(
      diffPassFile,
      JSON.stringify({
        threshold: 0.02,
        breakpoints: [
          { name: "mobile", mismatchRatio: 0.008 },
          { name: "tablet", mismatchRatio: 0.011 },
          { name: "desktop", mismatchRatio: 0.015 },
        ],
      }),
    );
    writeFileSync(
      diffFailFile,
      JSON.stringify({
        threshold: 0.02,
        breakpoints: [
          { name: "mobile", mismatchRatio: 0.008 },
          { name: "desktop", mismatchRatio: 0.045, region: "cards" },
        ],
      }),
    );

    const rcUnauthorized = runCli([
      "--url",
      "https://thirdparty.example.org",
      "--dom",
      domFile,
      "--out-dir",
      tmp,
    ]);
    check("CLI exits 2 when third-party URL lacks --confirm-authorized", rcUnauthorized === 2);

    const rcPass = runCli([
      "--url",
      "http://localhost:4321/landing",
      "--dom",
      domFile,
      "--css",
      cssFile,
      "--verify-diff",
      diffPassFile,
      "--out-dir",
      tmp,
    ]);
    check(
      "CLI exits 0 and emits outline.md + CloneSection.svelte + index.astro + tokens.css",
      rcPass === 0 &&
        existsSync(join(tmp, "docs/research/localhost/outline.md")) &&
        existsSync(join(tmp, "src/components/CloneSection.svelte")) &&
        existsSync(join(tmp, "src/pages/index.astro")) &&
        existsSync(join(tmp, "src/styles/tokens.css")),
    );

    const rcFailDiff = runCli([
      "--url",
      "http://localhost:4321/landing",
      "--dom",
      domFile,
      "--css",
      cssFile,
      "--verify-diff",
      diffFailFile,
      "--out-dir",
      tmp,
    ]);
    check("CLI exits 1 when visual diff exceeds 0.02 threshold", rcFailDiff === 1);
  } finally {
    rmSync(tmp, { recursive: true, force: true });
  }
}

console.log();
if (failures.length) {
  console.error(`❌ ${failures.length} failure(s):`);
  for (const f of failures) console.error(`   · ${f}`);
  process.exit(1);
}
console.log("✅ w0m-pixel-clone: all checks passed");
