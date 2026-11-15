# Vinext + Cloudflare Workers A2UI v1.0 Starter

Minimal Next.js App Router + React Server Components starter powered by `cloudflare/vinext` (`workerd` + Vite) and `@webomage/a2ui-vinext`.

## Endpoints

- `GET /` — React 19 RSC initial surface prepared with `prepareA2uiRscSurface()` (server-side secret stripping before serialization) + `"use client"` `<A2uiVinextSurface />`.
- `GET /api/a2ui/capabilities` — Emits `a2uiRendererCapabilities["1.0"]` per the A2UI v1.0 schema.
- `GET /api/a2ui/stream` — Streams validated `A2UI Express` SSE events via `createA2uiSseResponse()`.
- `POST /api/a2ui/action` — Receives canonical `renderer_to_agent` v1.0 `action` payloads.

## Local Development

```bash
pnpm install
pnpm dev
```
