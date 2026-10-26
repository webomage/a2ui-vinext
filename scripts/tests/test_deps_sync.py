#!/usr/bin/env python3
"""T140 — Unit tests for `deps_sync.py` range parsing, upper-bound enforcement, and lockfile ceiling checks.

Verifies:
  - AC1: `parse_range(spec)` parses `>=x.y.z`, `>=x.y.z <a.b.c`, and `>=x.y.z <a` (`(a, 0, 0)`),
         returning `upper = None` when no `<` is present.
  - AC2: `--check` (`evaluate_policy`) fails when a floor has `upper` and a repo entry omits `<...`
         or specifies a looser `<...` (`> upper`).
  - AC3: `--apply` propagates the full floor string (both bounds), so bumping `"undici": ">=7.29.1 <8"`
         -> `">=7.30.0 <8"` writes `">=7.30.0 <8"` and never strips `<8`.
  - AC4: `deps-policy.json` has `_ceiling_audit_t140` covering every floor and pins `"undici": ">=7.29.1 <8"`.
  - AC5: `lockfile_max` / `evaluate_policy` fails when `pnpm-lock.yaml` resolves a version `>= upper`.
  - AC6: Covers the exact `undici`-vs-`jsdom` shape across `wom7web`/`wom7ext` (`<8`) and `wom7api`/`wom7func` (`>=8.11.2`).
  - AC7: `vitest.config.ts` pins `passWithNoTests: false` so 0 collected test files cannot pass.
"""

from __future__ import annotations

import json
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parents[1]
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

import deps_sync  # noqa: E402


class TestDepsSyncUpperBounds(unittest.TestCase):
    def test_ac1_parse_range_supports_lower_and_upper_bounds(self) -> None:
        self.assertEqual(deps_sync.parse_range(">=7.29.1"), ((7, 29, 1), None))
        self.assertEqual(deps_sync.parse_range(">=7.29.1 <8"), ((7, 29, 1), (8, 0, 0)))
        self.assertEqual(deps_sync.parse_range(">=7.29.1 <8.0.0"), ((7, 29, 1), (8, 0, 0)))
        self.assertEqual(deps_sync.parse_range(">=3.3.17 <4"), ((3, 3, 17), (4, 0, 0)))
        self.assertEqual(deps_sync.parse_range(">=14.3.1 <15.2.0"), ((14, 3, 1), (15, 2, 0)))
        self.assertEqual(deps_sync.semver(">=7.29.1 <8"), (7, 29, 1))

    def test_ac2_check_enforces_upper_bound_honoured_missing_or_looser(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for name, spec in (
                ("repo_ok", ">=7.29.1 <8"),
                ("repo_missing_upper", ">=7.29.1"),
                ("repo_looser_upper", ">=7.29.1 <9"),
            ):
                rdir = root / name
                rdir.mkdir()
                (rdir / "package.json").write_text(
                    json.dumps({"pnpm": {"overrides": {"undici": spec}}}),
                    encoding="utf-8",
                )
                (rdir / "pnpm-lock.yaml").write_text(
                    "packages:\n  undici@7.30.0:\n    resolution: {integrity: sha512-xyz}\n",
                    encoding="utf-8",
                )

            policy = {
                "repos": {
                    "repo_ok": "repo_ok/package.json",
                    "repo_missing_upper": "repo_missing_upper/package.json",
                    "repo_looser_upper": "repo_looser_upper/package.json",
                },
                "floors": {"undici": ">=7.29.1 <8"},
            }
            repos = {k: root / v for k, v in policy["repos"].items()}
            pkgs = {k: deps_sync.load(p)[0] for k, p in repos.items()}

            hard, _, edits = deps_sync.evaluate_policy(policy, repos, pkgs)
            self.assertEqual(len(hard), 2)
            self.assertTrue(any("repo_missing_upper" in h and "missing upper bound" in h for h in hard))
            self.assertTrue(any("repo_looser_upper" in h and "looser than policy ceiling" in h for h in hard))
            self.assertNotIn("repo_ok", edits)
            self.assertEqual(edits["repo_missing_upper"]["undici"], ">=7.29.1 <8")
            self.assertEqual(edits["repo_looser_upper"]["undici"], ">=7.29.1 <8")

    def test_ac3_apply_propagates_full_floor_preserving_upper_bound(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            rdir = root / "wom7web"
            rdir.mkdir()
            (rdir / "package.json").write_text(
                json.dumps({"pnpm": {"overrides": {"undici": ">=7.29.1 <8"}}}),
                encoding="utf-8",
            )
            (rdir / "pnpm-lock.yaml").write_text(
                "packages:\n  undici@7.30.0:\n    resolution: {integrity: sha512-xyz}\n",
                encoding="utf-8",
            )

            # Bump canonical floor from >=7.29.1 <8 to >=7.30.0 <8
            policy = {
                "repos": {"wom7web": "wom7web/package.json"},
                "floors": {"undici": ">=7.30.0 <8"},
            }
            repos = {"wom7web": rdir / "package.json"}
            pkgs = {"wom7web": deps_sync.load(repos["wom7web"])[0]}

            hard, _, edits = deps_sync.evaluate_policy(policy, repos, pkgs)
            self.assertEqual(len(hard), 1)
            self.assertEqual(edits["wom7web"]["undici"], ">=7.30.0 <8")

    def test_ac5_and_ac6_lockfile_resolution_at_or_above_upper_fails_and_undici_jsdom_shape(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            # wom7web declares ">=7.29.1 <8", but lockfile drifted to undici@8.7.0 (the jsdom@29 failure mode)
            web_dir = root / "wom7web"
            web_dir.mkdir()
            (web_dir / "package.json").write_text(
                json.dumps({"pnpm": {"overrides": {"undici": ">=7.29.1 <8"}}}),
                encoding="utf-8",
            )
            (web_dir / "pnpm-lock.yaml").write_text(
                "packages:\n  undici@8.7.0:\n    resolution: {integrity: sha512-bad}\n",
                encoding="utf-8",
            )

            # wom7api is exempted onto >=8.11.2 via repo_floors + exceptions
            api_dir = root / "wom7api"
            api_dir.mkdir()
            (api_dir / "package.json").write_text(
                json.dumps({"pnpm": {"overrides": {"undici": ">=8.11.2"}}}),
                encoding="utf-8",
            )
            (api_dir / "pnpm-lock.yaml").write_text(
                "packages:\n  undici@8.11.2:\n    resolution: {integrity: sha512-ok}\n",
                encoding="utf-8",
            )

            repo_map = {"wom7web": "wom7web/package.json", "wom7api": "wom7api/package.json"}
            policy: dict[str, object] = {
                "repos": repo_map,
                "floors": {"undici": ">=7.29.1 <8"},
                "repo_floors": {"undici": {"wom7api": ">=8.11.2"}},
                "exceptions": {
                    "undici": "wom7web pins >=7.29.1 <8 for jsdom@29 compatibility; wom7api runs >=8.11.2 without jsdom."
                },
            }
            repos = {k: root / v for k, v in repo_map.items()}
            pkgs = {k: deps_sync.load(p)[0] for k, p in repos.items()}

            hard, _, _ = deps_sync.evaluate_policy(policy, repos, pkgs)
            self.assertEqual(len(hard), 1)
            self.assertIn("wom7web lockfile resolves 8.7.0 (>= upper ceiling <8.0.0", hard[0])

    def test_ac4_and_ac7_live_policy_and_vitest_no_tests_guard(self) -> None:
        policy, _ = deps_sync.load(deps_sync.POLICY)
        floors = {k: v for k, v in policy["floors"].items() if not k.startswith("_")}
        audit = policy["floors"].get("_ceiling_audit_t140", {})
        self.assertEqual(set(floors.keys()), set(audit.keys()))
        self.assertEqual(floors["undici"], ">=7.29.1 <8")
        self.assertEqual(deps_sync.main(), 0)

        vitest_cfg = (deps_sync.ROOT / "wom7web" / "vitest.config.ts").read_text(encoding="utf-8")
        self.assertIn("passWithNoTests: false", vitest_cfg)
        self.assertNotIn("passWithNoTests: true", vitest_cfg)

    def test_t566_astro_adapter_exports_catches_missing_begin_content_entry_collection(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web_dir = Path(tmp)
            astro_dir = web_dir / "node_modules" / "astro"
            (astro_dir / "dist" / "core" / "app" / "entrypoints").mkdir(parents=True)
            (astro_dir / "package.json").write_text(
                json.dumps(
                    {
                        "name": "astro",
                        "version": "7.3.3",
                        "exports": {"./app": "./dist/core/app/entrypoints/index.js"},
                    }
                ),
                encoding="utf-8",
            )
            (astro_dir / "dist" / "core" / "app" / "entrypoints" / "index.js").write_text(
                "export { App, renderForPrerender };\n",
                encoding="utf-8",
            )

            cf_dir = web_dir / "node_modules" / "@astrojs" / "cloudflare"
            (cf_dir / "dist" / "utils").mkdir(parents=True)
            (cf_dir / "package.json").write_text(
                json.dumps(
                    {
                        "name": "@astrojs/cloudflare",
                        "version": "14.2.1",
                        "peerDependencies": {"astro": "^7.0.0"},
                    }
                ),
                encoding="utf-8",
            )
            (cf_dir / "dist" / "utils" / "prerender.js").write_text(
                'import { beginContentEntryCollection, endContentEntryCollection } from "astro/app";\n',
                encoding="utf-8",
            )

            errs = deps_sync.check_astro_adapter_exports(web_dir)
            self.assertEqual(len(errs), 2)
            self.assertTrue(any("beginContentEntryCollection" in e for e in errs))
            self.assertTrue(any("endContentEntryCollection" in e for e in errs))

            # Upgrading @astrojs/cloudflare to import renderForPrerender resolves the linkage error
            (cf_dir / "dist" / "utils" / "prerender.js").write_text(
                'import { renderForPrerender } from "astro/app";\n',
                encoding="utf-8",
            )
            self.assertEqual(deps_sync.check_astro_adapter_exports(web_dir), [])

    def test_t566_node_engines_catches_unsupported_host_node(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            web_dir = Path(tmp)
            (web_dir / "package.json").write_text(json.dumps({"name": "wom7web"}), encoding="utf-8")
            astro_dir = web_dir / "node_modules" / "astro"
            astro_dir.mkdir(parents=True)
            (astro_dir / "package.json").write_text(
                json.dumps(
                    {
                        "name": "astro",
                        "version": "7.4.2",
                        "engines": {"node": ">=22.23.4"},
                    }
                ),
                encoding="utf-8",
            )
            repos = {"wom7web": web_dir / "package.json"}
            errs = deps_sync.check_node_engines(repos, host_node_version=(22, 23, 3))
            self.assertEqual(len(errs), 1)
            self.assertIn("astro@7.4.2 requires node '>=22.23.4', but host node is 22.23.3", errs[0])
            self.assertEqual(deps_sync.check_node_engines(repos, host_node_version=(22, 23, 4)), [])

    def test_t56_ac1_workspace_enumeration_and_summary_scope(self) -> None:
        policy, _ = deps_sync.load(deps_sync.POLICY)
        repos = {name: deps_sync.ROOT / rel for name, rel in policy["repos"].items()}
        pkgs = {name: deps_sync.load(path)[0] for name, path in repos.items() if path.exists()}
        ws_pkgs = deps_sync.discover_workspace_packages(repos, pkgs)
        ws_keys = [ws_key for ws_key, _, _, _ in ws_pkgs]
        self.assertEqual(len(ws_pkgs), 19)
        for expected_key in (
            "wom7web",
            "wom7web/apps/web",
            "wom7web/apps/cp",
            "wom7web/apps/join",
            "wom7web/apps/job",
            "wom7web/apps/demo",
            "wom7web/packages/lib",
            "wom7api",
            "wom7func",
            "wom7ext/extension",
            "wom7skills",
        ):
            self.assertIn(expected_key, ws_keys)

        hard, warn, _, report = deps_sync.evaluate_policy_detailed(policy, repos, pkgs)
        self.assertEqual(hard, [])
        summary = deps_sync.format_summary(policy, pkgs, warn, report)
        self.assertIn("(19 package.json across 5 repos)", summary)

    def test_t56_ac2_ac3_ac4_dynamic_minor_lag_and_intra_repo_workspace_exceptions(self) -> None:
        self.assertEqual(deps_sync.compute_minor_lag("^2.87.1", "^2.110.7"), 23)
        self.assertEqual(deps_sync.compute_minor_lag("2.98.0", "2.110.7"), 12)
        self.assertEqual(deps_sync.compute_minor_lag("^2.110.7", "^2.110.7"), 0)

        # Hardcoded 'minors behind' in policy lagging is rejected by check_policy_integrity (AC3)
        bad_policy = {
            "aligned_advisory": {
                "@supabase/supabase-js": {
                    "target": "^2.110.7",
                    "lagging": {
                        "wom7ext/extension": "^2.87.1 — 23 minors behind; bump needs test"
                    },
                }
            }
        }
        problems = deps_sync.check_policy_integrity(bad_policy)
        self.assertTrue(any("hardcodes 'N minors behind'" in p for p in problems))

        # Intra-repo workspace key (`wom7web/apps/join`) in `lagging` excuses that workspace
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_dir = root / "wom7web"
            join_dir = web_dir / "apps" / "join"
            join_dir.mkdir(parents=True)
            (web_dir / "package.json").write_text(
                json.dumps({"devDependencies": {"@supabase/supabase-js": "^2.110.7"}}),
                encoding="utf-8",
            )
            (join_dir / "package.json").write_text(
                json.dumps({"dependencies": {"@supabase/supabase-js": "^2.99.2"}}),
                encoding="utf-8",
            )
            (web_dir / "pnpm-lock.yaml").write_text(
                "packages:\n  '@supabase/supabase-js@2.110.7':\n    resolution: {integrity: sha512-ok}\n",
                encoding="utf-8",
            )
            policy = {
                "repos": {"wom7web": "wom7web/package.json"},
                "aligned_advisory": {
                    "@supabase/supabase-js": {
                        "target": "^2.110.7",
                        "resolved_target": "2.110.7",
                        "lagging": {
                            "wom7web/apps/join": {
                                "declared": "^2.99.2",
                                "installed": "2.110.7",
                                "reason": "Scoped intra-repo exception for join app verification",
                                "recheck_by": "2026-12-01",
                            }
                        },
                    }
                },
            }
            repos = {"wom7web": web_dir / "package.json"}
            pkgs = {"wom7web": deps_sync.load(repos["wom7web"])[0]}
            hard, warn, _, _ = deps_sync.evaluate_policy_detailed(policy, repos, pkgs)
            self.assertEqual(hard, [])
            self.assertEqual(len(warn), 1)
            self.assertIn("wom7web/apps/join @ ^2.99.2 (11 minors behind target ^2.110.7", warn[0])

    def test_t56_ac5_ac6_red_then_green_workspace_drift_and_lockfile_spread(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_dir = root / "wom7web"
            join_dir = web_dir / "apps" / "join"
            lib_dir = web_dir / "packages" / "lib"
            api_dir = root / "wom7api"
            join_dir.mkdir(parents=True)
            lib_dir.mkdir(parents=True)
            api_dir.mkdir(parents=True)

            (web_dir / "package.json").write_text(
                json.dumps(
                    {
                        "pnpm": {"overrides": {"hono": ">=4.13.11"}},
                        "devDependencies": {"@supabase/supabase-js": "^2.110.7"},
                    }
                ),
                encoding="utf-8",
            )
            (join_dir / "package.json").write_text(
                json.dumps({"dependencies": {"@supabase/supabase-js": "^2.99.2"}}),
                encoding="utf-8",
            )
            (lib_dir / "package.json").write_text(
                json.dumps({"dependencies": {"@supabase/supabase-js": "^2.90.1"}}),
                encoding="utf-8",
            )
            (web_dir / "pnpm-lock.yaml").write_text(
                "packages:\n"
                "  hono@4.13.13:\n"
                "  '@supabase/supabase-js@2.105.1':\n"
                "  '@supabase/supabase-js@2.110.7':\n",
                encoding="utf-8",
            )
            (api_dir / "package.json").write_text(
                json.dumps(
                    {
                        "pnpm": {"overrides": {"hono": ">=4.13.11"}},
                        "dependencies": {"@supabase/supabase-js": "^2.110.7"},
                    }
                ),
                encoding="utf-8",
            )
            (api_dir / "pnpm-lock.yaml").write_text(
                "packages:\n  hono@4.13.11:\n  '@supabase/supabase-js@2.110.7':\n",
                encoding="utf-8",
            )

            repo_map_t56 = {"wom7web": "wom7web/package.json", "wom7api": "wom7api/package.json"}
            policy: dict[str, object] = {
                "repos": repo_map_t56,
                "lockstep": {
                    "hono": {"version": ">=4.13.11", "repos": ["wom7web", "wom7api"]},
                },
                "aligned_advisory": {
                    "@supabase/supabase-js": {
                        "target": "^2.110.7",
                        "resolved_target": "2.110.7",
                        "lagging": {},
                    }
                },
            }
            repos = {k: root / v for k, v in repo_map_t56.items()}
            pkgs = {k: deps_sync.load(p)[0] for k, p in repos.items()}

            # RED: catches workspace specifier drift, 2 resolved supabase-js versions in wom7web,
            # and lockstep lockfile skew for hono (4.13.13 vs 4.13.11)
            hard, _, _, _ = deps_sync.evaluate_policy_detailed(policy, repos, pkgs)
            self.assertTrue(any("wom7web/apps/join declares '^2.99.2'" in h for h in hard))
            self.assertTrue(any("wom7web/packages/lib declares '^2.90.1'" in h for h in hard))
            self.assertTrue(any("wom7web pnpm-lock.yaml resolves 2 versions ['2.105.1', '2.110.7']" in h for h in hard))
            self.assertTrue(any("lockstep-lockfile hono: repos resolve multiple versions" in h for h in hard))

            # GREEN: aligning workspace specifiers and lockfiles clears all violations
            (join_dir / "package.json").write_text(
                json.dumps({"dependencies": {"@supabase/supabase-js": "^2.110.7"}}),
                encoding="utf-8",
            )
            (lib_dir / "package.json").write_text(
                json.dumps({"dependencies": {"@supabase/supabase-js": "^2.110.7"}}),
                encoding="utf-8",
            )
            (web_dir / "pnpm-lock.yaml").write_text(
                "packages:\n  hono@4.13.13:\n  '@supabase/supabase-js@2.110.7':\n",
                encoding="utf-8",
            )
            (api_dir / "pnpm-lock.yaml").write_text(
                "packages:\n  hono@4.13.13:\n  '@supabase/supabase-js@2.110.7':\n",
                encoding="utf-8",
            )
            hard_after, _, _, _ = deps_sync.evaluate_policy_detailed(policy, repos, pkgs)
            self.assertEqual(hard_after, [])

    def test_t113_ac1_ac2_ac5_runtime_alignment_check(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            web_dir = root / "wom7web"
            app_web = web_dir / "apps" / "web"
            api_dir = root / "wom7api"
            app_web.mkdir(parents=True)
            api_dir.mkdir(parents=True)

            (root / ".nvmrc").write_text("22.23.3\n", encoding="utf-8")
            (web_dir / ".nvmrc").write_text("20.11.0\n", encoding="utf-8")
            (web_dir / "package.json").write_text(
                json.dumps({"engines": {"node": ">=22.23.3 <23", "pnpm": ">=10.32.0"}}),
                encoding="utf-8",
            )
            (api_dir / "package.json").write_text(json.dumps({}), encoding="utf-8")
            (app_web / "wrangler.jsonc").write_text(
                '// comment\n{"compatibility_date": "2024-11-18", "compatibility_flags": ["nodejs_compat"]}\n',
                encoding="utf-8",
            )
            (api_dir / "wrangler.jsonc").write_text(
                '{"compatibility_date": "2026-05-06", "compatibility_flags": []}\n',
                encoding="utf-8",
            )

            policy = {
                "runtime": {
                    "nvmrc": "22.23.3",
                    "nvmrc_files": [".nvmrc", "wom7web/.nvmrc"],
                    "engines": {"node": ">=22.23.3 <23", "pnpm": ">=10.32.0"},
                    "engines_repos": ["wom7web", "wom7api"],
                    "compatibility_date": "2026-05-06",
                    "required_compatibility_flags": ["nodejs_compat"],
                    "wrangler_configs": ["wom7web/apps/web/wrangler.jsonc", "wom7api/wrangler.jsonc"],
                }
            }
            repos = {
                "wom7web": web_dir / "package.json",
                "wom7api": api_dir / "package.json",
            }
            pkgs = {k: deps_sync.load(p)[0] for k, p in repos.items()}

            errs = deps_sync.check_runtime_alignment(policy, repos, pkgs, estate_root=root)
            self.assertTrue(any("wom7web/.nvmrc has '20.11.0'" in e for e in errs))
            self.assertTrue(any("engines.node: wom7api has None" in e for e in errs))
            self.assertTrue(any("wom7web/apps/web/wrangler.jsonc has '2024-11-18'" in e for e in errs))
            self.assertTrue(any("wom7api/wrangler.jsonc missing 'nodejs_compat'" in e for e in errs))

            # Fix all 4 runtime surfaces and verify 0 errors
            (web_dir / ".nvmrc").write_text("22.23.3\n", encoding="utf-8")
            (api_dir / "package.json").write_text(
                json.dumps({"engines": {"node": ">=22.23.3 <23", "pnpm": ">=10.32.0"}}),
                encoding="utf-8",
            )
            (app_web / "wrangler.jsonc").write_text(
                '{"compatibility_date": "2026-05-06", "compatibility_flags": ["nodejs_compat"]}\n',
                encoding="utf-8",
            )
            (api_dir / "wrangler.jsonc").write_text(
                '{"compatibility_date": "2026-05-06", "compatibility_flags": ["nodejs_compat"]}\n',
                encoding="utf-8",
            )
            pkgs = {k: deps_sync.load(p)[0] for k, p in repos.items()}
            self.assertEqual(deps_sync.check_runtime_alignment(policy, repos, pkgs, estate_root=root), [])


if __name__ == "__main__":
    unittest.main()
