#!/usr/bin/env python3
"""Test Design System React Elimination & Token SSOT Consolidation (T422).

Verifies:
1. Zero React/JSX artifacts in all design-system/components/**/*.prompt.md files:
   - No ```jsx or ```tsx code fences (must use ```svelte or ```astro)
   - No className attributes (must use class)
   - No JSX comment blocks {/* ... */}
   - No React imports or hook references (useState, etc.)
2. Zero React types in all design-system/components/**/*.d.ts files:
   - No imports from "react" or 'react'
   - No ReactNode, JSX.Element, or React.* namespace references
   - No className properties (must use class)
3. Token SSOT parity between design-system/tokens/*.css and packages/ui/src/tokens.css:
   - 100% of design-system tokens must exist in packages/ui/src/tokens.css (zero dropped tokens)
   - Specific check for --tracking-widest restoration (AC3)
4. Target Component Registry (TARGET-COMPONENT-REGISTRY-2026-09-10.md) integrity:
   - Zero references to deleted *.jsx files in table source columns
   - All cited component prompt specs, d.ts typings, and local Astro/Svelte files resolve on disk
"""

from __future__ import annotations

import re
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
WEB_ROOT = ROOT / "wom7web"
DS_ROOT = WEB_ROOT / "design-system"
COMPONENTS_DIR = DS_ROOT / "components"


class TestDesignSystemReactFree(unittest.TestCase):
    """Test suite asserting complete elimination of React from the DS spec layer and Token SSOT."""

    def test_ds_prompts_react_free(self):
        """AC1: All .prompt.md files must be completely free of React / JSX syntax."""
        prompt_files = list(COMPONENTS_DIR.glob("**/*.prompt.md"))
        self.assertGreaterEqual(
            len(prompt_files), 21, f"Expected at least 21 .prompt.md files, found {len(prompt_files)}"
        )

        banned_patterns = [
            (r"```jsx\b", "JSX code fence (```jsx)"),
            (r"```tsx\b", "TSX code fence (```tsx)"),
            (r"\bclassName=", "React className attribute (use class=)"),
            (r"\{/\*.*?\*/\}", "JSX comment block ({/* ... */})"),
            (r'from\s+["\']react["\']', "React import statement"),
            (r"\bReact\.[A-Za-z]+", "React namespace usage (e.g. React.useState)"),
            (r"\bReactNode\b", "ReactNode type reference"),
            (r"\bhtmlFor=", "React htmlFor attribute (use for=)"),
        ]

        violations = []
        for pf in prompt_files:
            rel_path = pf.relative_to(WEB_ROOT)
            content = pf.read_text(encoding="utf-8")
            for pattern, desc in banned_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    violations.append(f"{rel_path}: {desc} (count: {len(matches)})")

        self.assertEqual(
            violations,
            [],
            f"Found React artifacts in design-system .prompt.md files:\n" + "\n".join(violations),
        )

    def test_ds_dts_react_free(self):
        """AC2: All .d.ts files must use Svelte 5 / native TypeScript types, free of React."""
        dts_files = list(COMPONENTS_DIR.glob("**/*.d.ts"))
        self.assertGreaterEqual(
            len(dts_files), 17, f"Expected at least 17 .d.ts files, found {len(dts_files)}"
        )

        banned_patterns = [
            (r'from\s+["\']react["\']', "React import"),
            (r'import\s+React\b', "React default import"),
            (r"\bReactNode\b", "ReactNode type reference"),
            (r"\bReact\.", "React namespace qualifier"),
            (r"\bJSX\.Element\b", "JSX.Element type reference"),
            (r"\bclassName\?:", "className prop (use class?:)"),
        ]

        violations = []
        for df in dts_files:
            rel_path = df.relative_to(WEB_ROOT)
            content = df.read_text(encoding="utf-8")
            for pattern, desc in banned_patterns:
                matches = re.findall(pattern, content)
                if matches:
                    violations.append(f"{rel_path}: {desc} (count: {len(matches)})")

        self.assertEqual(
            violations,
            [],
            f"Found React types in design-system .d.ts files:\n" + "\n".join(violations),
        )

    def test_tokens_ssot_parity(self):
        """AC3 & AC4: Shipping packages/ui/src/tokens.css must contain 100% of design-system tokens."""
        tokens_dir = DS_ROOT / "tokens"
        self.assertTrue(tokens_dir.is_dir(), f"Missing design-system/tokens directory: {tokens_dir}")

        ds_tokens: set[str] = set()
        for css_file in tokens_dir.glob("*.css"):
            for line in css_file.read_text(encoding="utf-8").splitlines():
                matches = re.findall(r"(--[a-zA-Z0-9_-]+)\s*:", line)
                ds_tokens.update(matches)

        self.assertGreater(
            len(ds_tokens), 150, f"Expected >150 DS tokens, found {len(ds_tokens)}"
        )

        pkg_tokens_file = WEB_ROOT / "packages/ui/src/tokens.css"
        self.assertTrue(
            pkg_tokens_file.is_file(), f"Missing package tokens file: {pkg_tokens_file}"
        )

        pkg_tokens: set[str] = set()
        for line in pkg_tokens_file.read_text(encoding="utf-8").splitlines():
            matches = re.findall(r"(--[a-zA-Z0-9_-]+)\s*:", line)
            pkg_tokens.update(matches)

        missing_from_package = ds_tokens - pkg_tokens
        self.assertEqual(
            missing_from_package,
            set(),
            f"Tokens in design-system/tokens/*.css missing from packages/ui/src/tokens.css: {sorted(missing_from_package)}",
        )

        # AC3 specific check: --tracking-widest must be present
        self.assertIn(
            "--tracking-widest",
            pkg_tokens,
            "--tracking-widest is missing from packages/ui/src/tokens.css (AC3)",
        )

    def test_target_component_registry_resolves(self):
        """AC5: All component paths in TARGET-COMPONENT-REGISTRY-2026-09-10.md must resolve on disk."""
        registry_file = DS_ROOT / "TARGET-COMPONENT-REGISTRY-2026-09-10.md"
        self.assertTrue(registry_file.is_file(), f"Missing registry file: {registry_file}")

        content = registry_file.read_text(encoding="utf-8")

        # Must not contain references to deleted *.jsx components
        banned_jsx_refs = re.findall(r"`components/[^`]+\.jsx`", content)
        self.assertEqual(
            banned_jsx_refs,
            [],
            f"Found references to deleted .jsx files in registry: {banned_jsx_refs}",
        )

        # Explicit canonical paths that must exist on disk
        canonical_paths = [
            # Table 1: DS sources (under design-system/)
            "design-system/components/core/Badge.prompt.md",
            "design-system/components/core/Button.prompt.md",
            "design-system/components/core/Card.prompt.md",
            "design-system/components/core/Checkbox.prompt.md",
            "design-system/components/overlay/Dialog.prompt.md",
            "design-system/components/core/Input.prompt.md",
            "design-system/components/core/Label.prompt.md",
            "design-system/components/overlay/Select.prompt.md",
            "design-system/components/core/Separator.prompt.md",
            "design-system/components/data/Table.prompt.md",
            # Table 1: Runtime targets (under packages/ui/src/lib/components/)
            "packages/ui/src/lib/components/ui/badge/badge.svelte",
            "packages/ui/src/lib/components/ui/button/button.svelte",
            "packages/ui/src/lib/components/ui/checkbox/checkbox.svelte",
            "packages/ui/src/lib/components/ui/input/input.svelte",
            "packages/ui/src/lib/components/ui/label/label.svelte",
            "packages/ui/src/lib/components/ui/separator/separator.svelte",
            # Table 2: Canonical brand/domain DS sources
            "design-system/components/brand/BlueprintCard.prompt.md",
            "design-system/components/brand/ComplexityBadge.prompt.md",
            "design-system/components/brand/SegmentBadge.prompt.md",
            "design-system/components/brand/TechIcon.prompt.md",
            "design-system/components/brand/GlassCard.prompt.md",
            "design-system/components/brand/StatusDot.prompt.md",
            "design-system/components/domain/QuickViewModal.prompt.md",
            # Table 2: Duplicated local Astro/Svelte implementations
            "apps/web/src/components/BlueprintCard.astro",
            "apps/cp/src/components/BlueprintCard.astro",
            "apps/web/src/components/ComplexityBadge.astro",
            "apps/cp/src/components/ComplexityBadge.astro",
            "apps/web/src/components/SegmentBadge.astro",
            "apps/cp/src/components/SegmentBadge.astro",
            "apps/web/src/components/TechIconGrid.astro",
            "apps/web/src/components/QuickViewModal.svelte",
            "apps/web/src/components/QuickViewModal.astro",
            "apps/cp/src/components/QuickViewModal.astro",
        ]

        missing = []
        for rel in canonical_paths:
            full = WEB_ROOT / rel
            if not full.exists():
                missing.append(rel)

        self.assertEqual(
            missing,
            [],
            f"Canonical paths in registry do not exist on disk:\n" + "\n".join(missing),
        )


if __name__ == "__main__":
    unittest.main()
