# @webomage/a2ui-vinext

Edge-native **A2UI v1.0 / v0.9.1 / v0.8** React 19 RSC renderer, fail-closed catalog validator, Vite SSR/HMR plugin, and Cloudflare Workers (`workerd`) SSE/JSONL streaming adapter built for [`cloudflare/vinext`](https://github.com/cloudflare/vinext).

## Supported Protocol & Catalog Coverage

- **Protocol Versions:** `v1.0` (canonical), `v0.9.1`, `v0.9`, `v0.8` (envelope normalization)
- **Catalog:** All **18 official A2UI v1.0 Basic Catalog components**:
  - Layout & Structure: `Row`, `Column`, `List` (static + `template` iteration), `Card`, `Tabs`, `Modal`, `Divider`
  - Display & Media: `Text`, `Image`, `Icon`, `Video`, `AudioPlayer`
  - Inputs & Actions: `Button`, `TextField`, `CheckBox`, `ChoicePicker`, `Slider`, `DateTimeInput`
- **Capabilities Discovery:** Emits `a2uiRendererCapabilities["1.0"]` compatible with `@a2ui/web_core` and A2UI conformance suites.
- **Security Controls:** Fail-closed catalog/component validation, prototype-pollution key rejection, `javascript:`/`vbscript:`/`data:` URL blocking, zero `dangerouslySetInnerHTML`, and automatic stripping of secret-shaped keys (`apiKey`, `token`, `secret`, `password`, `authorization`, `service_role`) prior to RSC client boundary serialization or edge egress.

## Installation

```bash
pnpm add @webomage/a2ui-vinext @a2ui/web_core react react-dom zod
```

## Quick Start (`cloudflare/vinext`)

1. Register `vinextA2uiPlugin()` in `vite.config.ts` alongside `vinext()` and `@cloudflare/vite-plugin`.
2. Prepare initial surfaces cleanly in React Server Components via `prepareA2uiRscSurface()` from `@webomage/a2ui-vinext/server`.
3. Render interactively inside a `"use client"` boundary via `<A2uiVinextSurface />` from `@webomage/a2ui-vinext/client`.
4. Stream edge AI JSONL/SSE envelopes in `worker/index.ts` via `createA2uiSseResponse()` or `createA2uiJsonlResponse()` from `@webomage/a2ui-vinext/workers`.

See [`examples/vinext-cloudflare-worker/`](examples/vinext-cloudflare-worker/README.md) for a complete runnable worker configuration (`wrangler.jsonc`, `vite.config.ts`, App Router RSC page, and `/api/a2ui/stream` endpoint), and the [live Cloudflare Workers demo](https://a2ui.w0m.workers.dev/).

## Development & Tests

```bash
pnpm install
pnpm run build
pnpm run typecheck
pnpm test
```

## License

Apache-2.0
