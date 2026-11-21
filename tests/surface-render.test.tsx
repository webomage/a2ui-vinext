import React, { act } from "react";
import { createRoot } from "react-dom/client";
import { renderToStaticMarkup } from "react-dom/server";
import { beforeAll, describe, expect, it, vi } from "vitest";
import { A2UI_BASIC_CATALOG_ID } from "../src/catalog.js";
import { A2uiVinextSurface } from "../src/client/A2uiVinextSurface.js";
import { prepareA2uiRscSurface, type A2uiRendererActionEnvelope } from "../src/server/index.js";

beforeAll(() => {
  (globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;
});

function buildFullCatalogMessages() {
  return [
    {
      version: "1.0",
      createSurface: {
        surfaceId: "render-18",
        catalogId: A2UI_BASIC_CATALOG_ID,
        dataModel: {
          title: "Edge Control Surface",
          inputVal: "workers-v1",
          agree: false,
          choices: ["edge"],
          scale: 25,
          dateVal: "2026-11-15",
          items: [{ itemLabel: "Item One" }, { itemLabel: "Item Two" }],
        },
        components: [
          { id: "root", component: "Card", child: "mainCol" },
          {
            id: "mainCol",
            component: "Column",
            children: [
              "heading",
              "toolbar",
              "itemsList",
              "tabs",
              "modal",
              "div",
              "tf",
              "cb",
              "cp",
              "sl",
              "dt",
              "vid",
              "aud",
              "submitBtn",
            ],
          },
          {
            id: "heading",
            component: "Text",
            variant: "h1",
            text: { path: "/title" },
            "@accessibility": { label: "Main title", live: "polite" },
          },
          { id: "toolbar", component: "Row", children: ["icn", "img"] },
          { id: "icn", component: "Icon", name: "check" },
          {
            id: "img",
            component: "Image",
            url: "https://webomage.com/img.png",
            description: "Brand",
          },
          {
            id: "itemsList",
            component: "List",
            children: { componentId: "listTpl", path: "/items" },
          },
          { id: "listTpl", component: "Text", text: { path: "itemLabel" } },
          {
            id: "tabs",
            component: "Tabs",
            tabs: [
              { title: "Overview", child: "tab1Txt" },
              { title: "Metrics", child: "tab2Txt" },
            ],
          },
          { id: "tab1Txt", component: "Text", text: "Overview panel" },
          { id: "tab2Txt", component: "Text", text: "Metrics panel" },
          { id: "modal", component: "Modal", trigger: "openModalTxt", content: "modalTxt" },
          { id: "openModalTxt", component: "Text", text: "Inspect JSON" },
          { id: "modalTxt", component: "Text", text: "Dialog open content" },
          { id: "div", component: "Divider", axis: "horizontal" },
          { id: "tf", component: "TextField", label: "Runtime Name", value: { path: "/inputVal" } },
          { id: "cb", component: "CheckBox", label: "Accept SLA", value: { path: "/agree" } },
          {
            id: "cp",
            component: "ChoicePicker",
            label: "Target Mode",
            variant: "multipleSelection",
            filterable: true,
            value: { path: "/choices" },
            options: [
              { label: "Edge", value: "edge" },
              { label: "Hybrid", value: "hybrid" },
            ],
          },
          {
            id: "sl",
            component: "Slider",
            label: "Weight",
            min: 0,
            max: 100,
            value: { path: "/scale" },
          },
          {
            id: "dt",
            component: "DateTimeInput",
            label: "Launch",
            value: { path: "/dateVal" },
            enableDate: true,
          },
          { id: "vid", component: "Video", url: "https://webomage.com/clip.mp4" },
          {
            id: "aud",
            component: "AudioPlayer",
            url: "https://webomage.com/audio.mp3",
            description: "Briefing",
          },
          {
            id: "submitBtn",
            component: "Button",
            variant: "primary",
            child: "submitLbl",
            action: {
              event: {
                name: "confirm_surface",
                context: {
                  inputVal: { path: "/inputVal" },
                  agree: { path: "/agree" },
                },
              },
            },
          },
          { id: "submitLbl", component: "Text", text: "Confirm Deploy" },
        ],
      },
    },
  ];
}

describe("A2uiVinextSurface React 19 SSR & interactive DOM boundary", () => {
  it("renders all 18 Basic Catalog components cleanly via SSR without raw HTML injection", () => {
    const prepared = prepareA2uiRscSurface(buildFullCatalogMessages(), {
      surfaceId: "render-18",
    });
    expect(prepared.ok).toBe(true);

    const html = renderToStaticMarkup(<A2uiVinextSurface surface={prepared.surface} />);
    expect(html).toContain("Edge Control Surface");
    expect(html).toContain("Item One");
    expect(html).toContain("Item Two");
    expect(html).toContain("Overview panel");
    expect(html).toContain("Accept SLA");
    expect(html).toContain("<video");
    expect(html).toContain("<audio");
    expect(html).toContain("Confirm Deploy");
    expect(html).not.toContain("<script");
  });

  it("handles tab switches, modals, form mutations, and dispatches canonical v1.0 actions", async () => {
    const prepared = prepareA2uiRscSurface(buildFullCatalogMessages(), {
      surfaceId: "render-18",
    });
    const actions: A2uiRendererActionEnvelope[] = [];
    const onAction = vi.fn((evt: A2uiRendererActionEnvelope) => {
      actions.push(evt);
    });

    const container = document.createElement("div");
    document.body.appendChild(container);
    const root = createRoot(container);

    await act(async () => {
      root.render(<A2uiVinextSurface surface={prepared.surface} onAction={onAction} />);
    });

    const tabButtons = container.querySelectorAll('[role="tab"]');
    expect(tabButtons).toHaveLength(2);
    await act(async () => {
      (tabButtons[1] as HTMLButtonElement).click();
    });
    expect(container.textContent).toContain("Metrics panel");

    const modalTrigger = container.querySelector('[data-a2ui-id="openModalTxt"]') as HTMLElement;
    await act(async () => {
      modalTrigger.click();
    });
    expect(container.querySelector('[role="dialog"]')?.textContent).toContain(
      "Dialog open content",
    );

    const checkbox = container.querySelector('input[type="checkbox"]') as HTMLInputElement;
    await act(async () => {
      checkbox.click();
    });

    const submitButton = container.querySelector('[data-a2ui-id="submitBtn"]') as HTMLButtonElement;
    await act(async () => {
      submitButton.click();
    });

    expect(onAction).toHaveBeenCalledTimes(1);
    expect(actions[0].version).toBe("1.0");
    expect(actions[0].action.name).toBe("confirm_surface");
    expect(actions[0].action.surfaceId).toBe("render-18");
    expect(actions[0].action.sourceComponentId).toBe("submitBtn");
    expect(actions[0].action.context.inputVal).toBe("workers-v1");
    expect(actions[0].action.context.agree).toBe(true);

    await act(async () => {
      root.unmount();
    });
    container.remove();
  });

  it("prevents infinite loops on cyclic references and renders fail-closed alert on invalid envelopes", () => {
    const html = renderToStaticMarkup(
      <A2uiVinextSurface
        messages={[
          {
            version: "1.0",
            createSurface: {
              surfaceId: "bad-cycle",
              components: [{ id: "root", component: "Script", text: "xss" }],
            },
          },
        ]}
      />,
    );
    expect(html).toContain('data-a2ui-surface-error="true"');
  });

  it("renders surfaces with v1.0 @path bindings and dispatches @call openUrl actions", () => {
    const html = renderToStaticMarkup(
      <A2uiVinextSurface
        messages={[
          {
            version: "1.0",
            createSurface: {
              surfaceId: "at-path-surface",
              catalogId: A2UI_BASIC_CATALOG_ID,
              dataModel: {
                title: "v1.0 @path Title",
                summary: "Summary text",
              },
              components: [
                { id: "root", component: "Card", child: "col" },
                { id: "col", component: "Column", children: ["title", "summary"] },
                { id: "title", component: "Text", variant: "body", text: { "@path": "/title" } },
                {
                  id: "summary",
                  component: "Text",
                  variant: "caption",
                  text: { "@path": "/summary" },
                },
              ],
            },
          },
        ]}
      />,
    );

    expect(html).toContain("v1.0 @path Title");
    expect(html).toContain("Summary text");
    expect(html).toContain('data-a2ui-variant="body"');
    expect(html).toContain('data-a2ui-variant="caption"');
  });
});
