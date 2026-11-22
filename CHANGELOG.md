# Changelog

## 0.1.1 - 2026-11-22

- Upgraded `zod` dependency to `^4.6.7` across package manifests and examples.
- Added canonical A2UI v1.0 `@path` and `@call` expression resolution support.
- Excluded `examples/**/node_modules/` and build caches from npm tarball via `.npmignore`, reducing published package footprint from 1.3 MB to ~45 KB.
- Replaced deprecated `h3` `Text` variant in starter example with standard `h2`/`h4` headings.

## 0.1.0 - 2026-11-15

- Initial release of `@webomage/a2ui-vinext` (Apache-2.0).
- Implemented all 18 A2UI v1.0 Basic Catalog components under a `"use client"` React 19 surface boundary (`A2uiVinextSurface`).
- Added `@a2ui/web_core/v1_0`-backed capability negotiation (`buildA2uiRendererCapabilities`), fail-closed Zod v4 catalog validation (`validateA2uiVinextEnvelope`), and server-side secret stripping (`prepareA2uiRscSurface`, `bindServerDataModel`).
- Added Cloudflare Workers (`workerd`) Web Streams adapters (`createA2uiJsonlTransformStream`, `createA2uiSseTransformStream`, `createA2uiSseResponse`, `createA2uiJsonlResponse`) and Vite/Vinext plugin (`vinextA2uiPlugin`).
- Added runnable `examples/vinext-cloudflare-worker` starter and protocol conformance tests.
