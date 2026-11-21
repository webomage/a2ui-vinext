import {
  A2UI_BASIC_CATALOG_ID,
  buildA2uiRendererCapabilities,
} from "@webomage/a2ui-vinext/catalog";
import { createA2uiSseResponse } from "@webomage/a2ui-vinext/workers";

export interface ExampleWorkerEnv {
  ASSETS?: { fetch: (request: Request) => Promise<Response> };
  AI?: {
    run: (
      model: string,
      input: Record<string, unknown>,
    ) => Promise<ReadableStream<Uint8Array> | Record<string, unknown>>;
  };
}

export function buildDemoAgentMessages(
  promptText = "Deploy edge AI surface",
): Array<Record<string, unknown>> {
  return [
    {
      version: "1.0",
      createSurface: {
        surfaceId: "vinext-edge-demo",
        catalogId: A2UI_BASIC_CATALOG_ID,
        dataModel: {
          title: "Cloudflare Workers + Vinext A2UI v1.0",
          prompt: promptText,
          replicas: 3,
          autoScale: true,
          region: ["iad"],
          token: "server-only-redacted-before-egress",
        },
        components: [
          { id: "root", component: "Card", child: "layout" },
          {
            id: "layout",
            component: "Column",
            children: [
              "heading",
              "summary",
              "replicasSlider",
              "scaleCheck",
              "regionPicker",
              "launchBtn",
            ],
          },
          { id: "heading", component: "Text", variant: "body", text: { "@path": "/title" } },
          { id: "summary", component: "Text", variant: "body", text: { "@path": "/prompt" } },
          {
            id: "replicasSlider",
            component: "Slider",
            label: "Edge Replicas",
            min: 1,
            max: 16,
            steps: 15,
            value: { "@path": "/replicas" },
          },
          {
            id: "scaleCheck",
            component: "CheckBox",
            label: "Enable smart placement",
            value: { "@path": "/autoScale" },
          },
          {
            id: "regionPicker",
            component: "ChoicePicker",
            label: "Primary Region",
            variant: "mutuallyExclusive",
            value: { "@path": "/region" },
            options: [
              { label: "US East (iad)", value: "iad" },
              { label: "EU West (fra)", value: "fra" },
              { label: "APAC (sin)", value: "sin" },
            ],
          },
          {
            id: "launchBtn",
            component: "Button",
            variant: "primary",
            child: "launchLabel",
            action: {
              event: {
                name: "deploy_worker_config",
                context: {
                  replicas: { "@path": "/replicas" },
                  autoScale: { "@path": "/autoScale" },
                  region: { "@path": "/region" },
                },
              },
            },
          },
          { id: "launchLabel", component: "Text", text: "Apply Edge Config" },
        ],
      },
    },
  ];
}

export interface WorkerExecutionContext {
  waitUntil: (promise: Promise<unknown>) => void;
  passThroughOnException?: () => void;
}

export async function handleA2uiWorkerRequest(
  request: Request,
  env: ExampleWorkerEnv,
  vinextFetch?: (
    request: Request,
    env: ExampleWorkerEnv,
    ctx: WorkerExecutionContext,
  ) => Promise<Response>,
  ctx?: WorkerExecutionContext,
): Promise<Response> {
  const url = new URL(request.url);

  if (url.pathname === "/api/a2ui/capabilities") {
    return Response.json(buildA2uiRendererCapabilities({ versions: ["1.0", "v0.9"] }), {
      headers: { "Cache-Control": "no-store" },
    });
  }

  if (url.pathname === "/api/a2ui/stream") {
    const prompt = url.searchParams.get("prompt") ?? "Edge deployment assistant";
    if (env.AI && url.searchParams.get("liveAi") === "1") {
      try {
        const aiResult = await env.AI.run("@cf/meta/llama-3.1-8b-instruct", {
          stream: true,
          messages: [
            {
              role: "system",
              content:
                "Emit newline-delimited A2UI v1.0 JSON envelopes for Basic Catalog components only.",
            },
            { role: "user", content: prompt },
          ],
        });
        if (aiResult instanceof ReadableStream) {
          return createA2uiSseResponse(aiResult);
        }
      } catch {
        // Fall back to deterministic sample stream when local AI binding is absent
      }
    }
    return createA2uiSseResponse(buildDemoAgentMessages(prompt));
  }

  if (url.pathname === "/api/a2ui/action" && request.method === "POST") {
    const payload = (await request.json().catch(() => null)) as Record<string, unknown> | null;
    if (!payload || payload.version !== "1.0" || typeof payload.action !== "object") {
      return Response.json(
        { ok: false, error: "Expected A2UI v1.0 action envelope" },
        { status: 400 },
      );
    }
    return Response.json(
      { ok: true, received: payload.action },
      { headers: { "Cache-Control": "no-store" } },
    );
  }

  if (vinextFetch && ctx) {
    return vinextFetch(request, env, ctx);
  }
  return Response.json({ ok: true, service: "@webomage/a2ui-vinext" });
}

export default {
  async fetch(
    request: Request,
    env: ExampleWorkerEnv,
    ctx: WorkerExecutionContext,
  ): Promise<Response> {
    const mod = (await import("vinext/server/fetch-handler")) as {
      default: {
        fetch: (req: Request, e: ExampleWorkerEnv, c: WorkerExecutionContext) => Promise<Response>;
      };
    };
    return handleA2uiWorkerRequest(request, env, mod.default.fetch, ctx);
  },
};
