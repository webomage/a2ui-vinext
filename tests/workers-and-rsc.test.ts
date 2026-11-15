import { describe, expect, it } from "vitest";
import { A2UI_BASIC_CATALOG_ID } from "../src/catalog.js";
import { bindServerDataModel, prepareA2uiRscSurface } from "../src/server/index.js";
import { A2UI_VINEXT_VIRTUAL_ID, vinextA2uiPlugin } from "../src/vite/index.js";
import {
  createA2uiJsonlResponse,
  createA2uiSseResponse,
  parseA2uiExpressChunk,
} from "../src/workers/index.js";
import { handleA2uiWorkerRequest } from "../examples/vinext-cloudflare-worker/worker/index.js";

describe("@webomage/a2ui-vinext RSC server, workerd streams, and Vite plugin", () => {
  it("strips server secrets cleanly across bindServerDataModel and prepareA2uiRscSurface", () => {
    const bound = bindServerDataModel(
      { orgName: "Acme", bearerToken: "secret-bearer" },
      { plan: "pro", authorization: "Bearer hidden", password: "nope" },
    );
    expect(bound.redactedKeyCount).toBe(3);
    expect(bound.dataModel).toEqual({ orgName: "Acme", plan: "pro" });

    const prepared = prepareA2uiRscSurface([
      {
        version: "1.0",
        createSurface: {
          surfaceId: "rsc-1",
          catalogId: A2UI_BASIC_CATALOG_ID,
          dataModel: { title: "Hello RSC", apiKey: "sk-hidden" },
          components: [{ id: "root", component: "Text", text: { path: "/title" } }],
        },
      },
    ]);
    expect(prepared.ok).toBe(true);
    expect(prepared.surface?.dataModel.title).toBe("Hello RSC");
    expect(prepared.surface?.dataModel.apiKey).toBeUndefined();
  });

  it("streams validated SSE and JSONL envelopes while blocking oversized or unsafe chunks", async () => {
    const oversized = parseA2uiExpressChunk(`{"x":"${"a".repeat(200)}"}`, { maxLineBytes: 64 });
    expect(oversized.ok).toBe(false);
    expect((oversized.messages[0].error as Record<string, unknown>).code).toBe("VALIDATION_FAILED");

    const malformed = parseA2uiExpressChunk("{broken json");
    expect(malformed.ok).toBe(false);

    const sseResponse = createA2uiSseResponse([
      {
        version: "1.0",
        createSurface: {
          surfaceId: "sse-1",
          dataModel: { msg: "Streamed cleanly", token: "strip-me" },
          components: [{ id: "root", component: "Text", text: { path: "/msg" } }],
        },
      },
      '{"version":"1.0","createSurface":{"surfaceId":"bad","components":[{"id":"x","component":"Script"}]}}',
    ]);
    expect(sseResponse.headers.get("Content-Type")).toContain("text/event-stream");
    expect(sseResponse.headers.get("Cache-Control")).toBe("no-store, no-transform");
    expect(sseResponse.headers.get("X-Content-Type-Options")).toBe("nosniff");

    const bodyText = await sseResponse.text();
    expect(bodyText).toContain("event: a2ui");
    expect(bodyText).toContain("Streamed cleanly");
    expect(bodyText).not.toContain("strip-me");
    expect(bodyText).toContain("VALIDATION_FAILED");

    const ndjsonResponse = createA2uiJsonlResponse([
      {
        version: "1.0",
        createSurface: {
          surfaceId: "nd-1",
          components: [{ id: "root", component: "Text", text: "NDJSON line" }],
        },
      },
    ]);
    expect(ndjsonResponse.headers.get("Content-Type")).toContain("application/x-ndjson");
    const ndText = await ndjsonResponse.text();
    expect(ndText.trim().startsWith("{")).toBe(true);
  });

  it("exposes virtual catalog metadata and fail-closed HMR validation in vinextA2uiPlugin", async () => {
    const plugin = vinextA2uiPlugin();
    expect(plugin.name).toBe("webomage:a2ui-vinext");
    const resolved = plugin.resolveId?.(A2UI_VINEXT_VIRTUAL_ID);
    expect(resolved).toBe(`\0${A2UI_VINEXT_VIRTUAL_ID}`);
    const loaded = plugin.load?.(resolved!);
    expect(loaded).toContain("a2uiRendererCapabilities");
    expect(loaded).toContain("AudioPlayer");

    await expect(
      plugin.handleHotUpdate?.({
        file: "surface.a2ui.json",
        read: async () =>
          JSON.stringify({
            version: "1.0",
            createSurface: {
              surfaceId: "hmr-bad",
              components: [{ id: "x", component: "RawHtml" }],
            },
          }),
      }),
    ).rejects.toThrow(/A2UI fixture validation failed/);

    const hmrOk = await plugin.handleHotUpdate?.({
      file: "surface.a2ui.json",
      read: async () =>
        JSON.stringify({
          version: "1.0",
          createSurface: {
            surfaceId: "hmr-ok",
            components: [{ id: "x", component: "Text", text: "Valid HMR" }],
          },
        }),
    });
    expect(hmrOk).toBeUndefined();
  });

  it("serves capabilities, SSE stream, and v1.0 action routes from the example Worker handler", async () => {
    const capRes = await handleA2uiWorkerRequest(
      new Request("https://example.workers.dev/api/a2ui/capabilities"),
      {},
    );
    expect(capRes.status).toBe(200);
    const capsJson = (await capRes.json()) as { a2uiRendererCapabilities: Record<string, unknown> };
    expect(capsJson.a2uiRendererCapabilities["1.0"]).toBeDefined();

    const streamRes = await handleA2uiWorkerRequest(
      new Request("https://example.workers.dev/api/a2ui/stream?prompt=Verify+edge"),
      {},
    );
    expect(streamRes.status).toBe(200);
    const streamBody = await streamRes.text();
    expect(streamBody).toContain("Verify edge");
    expect(streamBody).not.toContain("server-only-redacted-before-egress");

    const actionRes = await handleA2uiWorkerRequest(
      new Request("https://example.workers.dev/api/a2ui/action", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          version: "1.0",
          action: {
            name: "deploy_worker_config",
            surfaceId: "vinext-edge-demo",
            sourceComponentId: "launchBtn",
            timestamp: "2026-11-15T00:00:00Z",
            context: { replicas: 3 },
          },
        }),
      }),
      {},
    );
    expect(actionRes.status).toBe(200);
  });
});
