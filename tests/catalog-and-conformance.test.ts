import { basicCatalog, Schemas } from "@a2ui/web_core/v1_0";
import { describe, expect, it } from "vitest";
import {
  A2UI_BASIC_CATALOG_ID,
  BASIC_CATALOG_V1_COMPONENTS,
  buildA2uiRendererCapabilities,
  createVinextMessageProcessor,
  hasPrototypePollutionKey,
  isSafeUrl,
  redactSensitiveDataModel,
  validateA2uiVinextEnvelope,
} from "../src/catalog.js";
import { createRendererActionEvent } from "../src/server/index.js";

describe("@webomage/a2ui-vinext catalog & A2UI conformance", () => {
  it("matches all 18 official @a2ui/web_core v1 Basic Catalog components 1-for-1", () => {
    const coreComponentNames = [...basicCatalog.components.keys()];
    expect(BASIC_CATALOG_V1_COMPONENTS).toHaveLength(18);
    expect(new Set(BASIC_CATALOG_V1_COMPONENTS)).toEqual(new Set(coreComponentNames));
    expect(Schemas.A2uiMessageSchemaRaw.$id).toBe(
      "https://a2ui.org/specification/v1_0/agent_to_renderer.json",
    );
  });

  it("emits spec-compliant a2uiRendererCapabilities across v1.0, v0.9, and v0.8", () => {
    const caps = buildA2uiRendererCapabilities({
      versions: ["1.0", "v0.9", "v0.8"],
      additionalCatalogIds: ["https://webomage.com/a2ui/vinext/catalog/v1"],
    });
    expect(caps.a2uiRendererCapabilities["1.0"].supportedCatalogIds).toContain(
      A2UI_BASIC_CATALOG_ID,
    );
    expect(caps.a2uiRendererCapabilities["1.0"].supportedCatalogIds).toContain(
      "https://webomage.com/a2ui/vinext/catalog/v1",
    );
    expect(caps.a2uiRendererCapabilities["v0.9"]).toBeDefined();
    expect(caps.a2uiRendererCapabilities["v0.8"]).toBeDefined();

    const processor = createVinextMessageProcessor({ version: "1.0" });
    expect(processor.catalogs.length).toBe(1);
  });

  it("validates a complete v1.0 surface exercising all 18 Basic Catalog components", () => {
    const result = validateA2uiVinextEnvelope([
      {
        version: "1.0",
        createSurface: {
          surfaceId: "all-18",
          catalogId: A2UI_BASIC_CATALOG_ID,
          dataModel: {
            title: "All 18 Basic Components",
            query: "workers",
            checked: true,
            choice: ["a"],
            sliderVal: 40,
            dueDate: "2026-12-01",
            secretApiKey: "must-not-leak",
          },
          components: [
            { id: "root", component: "Card", child: "col" },
            {
              id: "col",
              component: "Column",
              children: [
                "heading",
                "row",
                "list",
                "tabs",
                "modal",
                "divider",
                "tf",
                "cb",
                "cp",
                "sl",
                "dt",
                "vid",
                "aud",
                "btn",
              ],
            },
            { id: "heading", component: "Text", variant: "h2", text: { path: "/title" } },
            { id: "row", component: "Row", children: ["icon", "img"] },
            { id: "icon", component: "Icon", name: "check" },
            {
              id: "img",
              component: "Image",
              url: "https://webomage.com/logo.png",
              description: "Logo",
            },
            { id: "list", component: "List", children: ["listTxt"] },
            { id: "listTxt", component: "Text", text: "List entry" },
            { id: "tabs", component: "Tabs", tabs: [{ title: "Tab A", child: "tabChild" }] },
            { id: "tabChild", component: "Text", text: "Inside Tab" },
            { id: "modal", component: "Modal", trigger: "modalTrigger", content: "modalBody" },
            { id: "modalTrigger", component: "Text", text: "Open Details" },
            { id: "modalBody", component: "Text", text: "Modal Details" },
            { id: "divider", component: "Divider", axis: "horizontal" },
            { id: "tf", component: "TextField", label: "Query", value: { path: "/query" } },
            { id: "cb", component: "CheckBox", label: "Agree", value: { path: "/checked" } },
            {
              id: "cp",
              component: "ChoicePicker",
              label: "Option",
              value: { path: "/choice" },
              options: [{ label: "Option A", value: "a" }],
            },
            {
              id: "sl",
              component: "Slider",
              label: "Scale",
              min: 0,
              max: 100,
              value: { path: "/sliderVal" },
            },
            {
              id: "dt",
              component: "DateTimeInput",
              label: "Target Date",
              value: { path: "/dueDate" },
              enableDate: true,
            },
            { id: "vid", component: "Video", url: "https://webomage.com/demo.mp4" },
            {
              id: "aud",
              component: "AudioPlayer",
              url: "https://webomage.com/demo.mp3",
              description: "Audio clip",
            },
            {
              id: "btn",
              component: "Button",
              variant: "primary",
              child: "btnTxt",
              action: { event: { name: "submit_form", context: { q: { path: "/query" } } } },
            },
            { id: "btnTxt", component: "Text", text: "Submit" },
          ],
        },
      },
    ]);

    expect(result.ok).toBe(true);
    expect(result.issues).toEqual([]);
    expect(result.redactedKeyCount).toBe(1);
    const surface = result.surfaces["all-18"];
    expect(surface).toBeDefined();
    expect(surface.dataModel.secretApiKey).toBeUndefined();
    expect(Object.keys(surface.components)).toHaveLength(23);
  });

  it("normalizes v0.8 and v0.9.1 envelopes while supporting updateDataModel and deleteSurface", () => {
    const v08 = validateA2uiVinextEnvelope([
      { beginRendering: { surfaceId: "legacy", root: "r" } },
      {
        surfaceUpdate: {
          surfaceId: "legacy",
          components: [
            { id: "r", component: { Column: { children: ["t"] } } },
            { id: "t", component: { Text: { text: { path: "/greeting" } } } },
          ],
        },
      },
      { dataModelUpdate: { surfaceId: "legacy", path: "/greeting", contents: "Hello from v0.8" } },
    ]);
    expect(v08.ok).toBe(true);
    expect(v08.surfaces.legacy.dataModel.greeting).toBe("Hello from v0.8");
    expect(v08.surfaces.legacy.components.t.component).toBe("Text");

    const deleted = validateA2uiVinextEnvelope(
      [{ version: "1.0", deleteSurface: { surfaceId: "legacy" } }],
      { existingSurfaces: v08.surfaces },
    );
    expect(deleted.ok).toBe(true);
    expect(deleted.surfaces.legacy).toBeUndefined();
  });

  it("fails closed on unallowlisted components, prototype pollution, unsafe URLs, and secret keys", () => {
    expect(isSafeUrl("javascript:alert(1)")).toBe(false);
    expect(isSafeUrl("vbscript:msgbox(1)")).toBe(false);
    expect(isSafeUrl("data:text/html,<script>alert(1)</script>")).toBe(false);
    expect(isSafeUrl("https://webomage.com/assets/hero.webp")).toBe(true);
    expect(isSafeUrl("/api/a2ui/stream")).toBe(true);

    const polluted = JSON.parse('{"version":"1.0","__proto__":{"polluted":true}}');
    expect(hasPrototypePollutionKey(polluted)).toBe(true);
    const protoResult = validateA2uiVinextEnvelope(polluted);
    expect(protoResult.ok).toBe(false);
    expect(protoResult.issues[0].code).toBe("PROTOTYPE_POLLUTION");

    const badComponent = validateA2uiVinextEnvelope({
      version: "1.0",
      createSurface: {
        surfaceId: "xss",
        components: [{ id: "bad", component: "Script", text: "alert(1)" }],
      },
    });
    expect(badComponent.ok).toBe(false);
    expect(badComponent.issues.some((i) => i.code === "UNALLOWED_COMPONENT")).toBe(true);

    const badUrl = validateA2uiVinextEnvelope({
      version: "1.0",
      createSurface: {
        surfaceId: "xss-url",
        components: [{ id: "img1", component: "Image", url: "javascript:alert(1)" }],
      },
    });
    expect(badUrl.ok).toBe(false);
    expect(badUrl.issues.some((i) => i.code === "UNSAFE_URL")).toBe(true);

    const badCatalog = validateA2uiVinextEnvelope({
      version: "1.0",
      createSurface: { surfaceId: "bad-cat", catalogId: "https://evil.example/cat.json" },
    });
    expect(badCatalog.ok).toBe(false);
    expect(badCatalog.issues[0].code).toBe("UNALLOWED_CATALOG");

    const cleaned = redactSensitiveDataModel({
      name: "Ada",
      token: "tok_123",
      nested: { service_role: "priv", count: 2 },
    }) as Record<string, unknown>;
    expect(cleaned.name).toBe("Ada");
    expect(cleaned.token).toBeUndefined();
    expect((cleaned.nested as Record<string, unknown>).service_role).toBeUndefined();

    const actionEvt = createRendererActionEvent({
      name: "save",
      surfaceId: "s1",
      sourceComponentId: "b1",
      context: { ok: true, apiKey: "secret-should-strip" },
    });
    expect(actionEvt.version).toBe("1.0");
    expect(actionEvt.action.context.ok).toBe(true);
    expect(actionEvt.action.context.apiKey).toBeUndefined();
  });
});
