"use client";

import React, { useMemo, useState } from "react";
import {
  type A2uiComponentNode,
  type A2uiNormalizedSurface,
  type A2uiValidationIssue,
  isPlainRecord,
  isSafeUrl,
  resolveDynamicValue,
  resolveEventContext,
  setDataAtPath,
  validateA2uiVinextEnvelope,
} from "../catalog.js";
import {
  type A2uiRendererActionEnvelope,
  type A2uiRendererErrorEnvelope,
  createRendererActionEvent,
  createRendererErrorEvent,
} from "../server/index.js";

export interface A2uiVinextSurfaceProps {
  /** Pre-validated surface payload prepared on the server (`prepareA2uiRscSurface`). */
  surface?: A2uiNormalizedSurface | null;
  /** Optional raw A2UI v1.0 / v0.9.1 / v0.8 message array for client streaming updates. */
  messages?: unknown[];
  /** Called whenever a user triggers a component action (`renderer_to_agent` v1.0 envelope). */
  onAction?: (event: A2uiRendererActionEnvelope) => void;
  /** Called when client-side validation rejects an unsafe/invalid payload. */
  onError?: (error: A2uiRendererErrorEnvelope) => void;
  /** Optional class name for root surface container. */
  className?: string;
}

const ICON_GLYPHS: Record<string, string> = {
  accountCircle: "O",
  add: "+",
  arrowBack: "<",
  arrowForward: ">",
  attachFile: "@",
  calendarToday: "#",
  call: "T",
  camera: "C",
  check: "v",
  close: "x",
  delete: "X",
  download: "v",
  edit: "/",
  error: "!",
  favorite: "*",
  help: "?",
  home: "H",
  info: "i",
  lock: "L",
  mail: "M",
  menu: "=",
  notifications: "B",
  refresh: "R",
  search: "Q",
  settings: "S",
  share: "^",
  star: "*",
  upload: "^",
  warning: "!",
};

function asString(val: unknown, fallback = ""): string {
  if (typeof val === "string") return val;
  if (typeof val === "number" || typeof val === "boolean") return String(val);
  return fallback;
}

function asBoolean(val: unknown, fallback = false): boolean {
  if (typeof val === "boolean") return val;
  if (val === "true") return true;
  if (val === "false") return false;
  return fallback;
}

function asNumber(val: unknown, fallback = 0): number {
  if (typeof val === "number" && Number.isFinite(val)) return val;
  if (typeof val === "string" && val.trim() !== "") {
    const parsed = Number(val);
    if (Number.isFinite(parsed)) return parsed;
  }
  return fallback;
}

function asStringArray(val: unknown): string[] {
  if (!Array.isArray(val)) return [];
  return val.filter((item): item is string => typeof item === "string");
}

function getBindingPath(prop: unknown): string | null {
  if (isPlainRecord(prop) && typeof prop.path === "string" && prop.path.trim()) {
    return prop.path.trim();
  }
  return null;
}

function resolveAriaAttrs(
  node: A2uiComponentNode,
  dataModel: Record<string, unknown>,
  scopeItem?: Record<string, unknown>,
): {
  ariaLabel?: string;
  ariaLive?: "off" | "polite" | "assertive";
  title?: string;
  hidden: boolean;
} {
  const a11y = node.accessibility;
  if (!a11y) {
    return { hidden: false };
  }
  const ariaLabel = a11y.label
    ? asString(resolveDynamicValue(a11y.label, dataModel, scopeItem))
    : undefined;
  const title = a11y.description
    ? asString(resolveDynamicValue(a11y.description, dataModel, scopeItem))
    : undefined;
  const hidden = a11y.hidden
    ? asBoolean(resolveDynamicValue(a11y.hidden, dataModel, scopeItem))
    : false;
  const ariaLive =
    a11y.live === "polite" || a11y.live === "assertive" || a11y.live === "off"
      ? a11y.live
      : undefined;
  return { ariaLabel, ariaLive, title, hidden };
}

function resolveChildrenRefs(
  childrenProp: unknown,
  dataModel: Record<string, unknown>,
  scopeItem?: Record<string, unknown>,
): Array<{ id: string; scopeItem?: Record<string, unknown>; key: string }> {
  if (Array.isArray(childrenProp)) {
    return childrenProp
      .filter((id): id is string => typeof id === "string" && id.length > 0)
      .map((id, idx) => ({ id, scopeItem, key: `${id}-${idx}` }));
  }
  if (
    isPlainRecord(childrenProp) &&
    typeof childrenProp.componentId === "string" &&
    typeof childrenProp.path === "string"
  ) {
    const rawList = resolveDynamicValue({ path: childrenProp.path }, dataModel, scopeItem);
    const items = Array.isArray(rawList)
      ? rawList
      : isPlainRecord(rawList)
        ? Object.values(rawList)
        : [];
    const templateId = childrenProp.componentId;
    return items.map((entry, idx) => ({
      id: templateId,
      scopeItem: isPlainRecord(entry) ? entry : { value: entry, index: idx },
      key: `${templateId}-${idx}`,
    }));
  }
  return [];
}

function renderTextVariant(variant: unknown, content: string): React.ReactNode {
  switch (variant) {
    case "h1":
      return <h1 data-a2ui-variant="h1">{content}</h1>;
    case "h2":
      return <h2 data-a2ui-variant="h2">{content}</h2>;
    case "h3":
      return <h3 data-a2ui-variant="h3">{content}</h3>;
    case "h4":
      return <h4 data-a2ui-variant="h4">{content}</h4>;
    case "h5":
      return <h5 data-a2ui-variant="h5">{content}</h5>;
    case "caption":
      return <small data-a2ui-variant="caption">{content}</small>;
    default:
      return <p data-a2ui-variant="body">{content}</p>;
  }
}

export function A2uiVinextSurface({
  surface: initialSurface,
  messages,
  onAction,
  onError,
  className,
}: A2uiVinextSurfaceProps): React.ReactElement | null {
  const validated = useMemo(() => {
    if (Array.isArray(messages) && messages.length > 0) {
      const existing = initialSurface
        ? Object.fromEntries([[initialSurface.surfaceId, initialSurface]])
        : undefined;
      return validateA2uiVinextEnvelope(messages, { existingSurfaces: existing });
    }
    if (initialSurface) {
      return {
        ok: true,
        version: "1.0" as const,
        issues: [] as A2uiValidationIssue[],
        surfaces: Object.fromEntries([[initialSurface.surfaceId, initialSurface]]),
        redactedKeyCount: 0,
      };
    }
    return null;
  }, [initialSurface, messages]);

  const activeSurface = useMemo<A2uiNormalizedSurface | null>(() => {
    if (!validated) return null;
    const entries = Object.values(validated.surfaces);
    return entries.find((entry) => !entry.deleted) ?? null;
  }, [validated]);

  const [localModelOverrides, setLocalModelOverrides] = useState<
    Map<string, Record<string, unknown>>
  >(() => new Map());
  const [activeTabs, setActiveTabs] = useState<Map<string, number>>(() => new Map());
  const [openModals, setOpenModals] = useState<Map<string, boolean>>(() => new Map());
  const [choiceFilters, setChoiceFilters] = useState<Map<string, string>>(() => new Map());

  if (!validated) {
    return null;
  }

  if (!validated.ok) {
    const issue = validated.issues[0];
    const errMessage = issue?.message ?? "Surface failed A2UI validation";
    if (onError) {
      onError(
        createRendererErrorEvent({
          surfaceId: issue?.surfaceId ?? activeSurface?.surfaceId ?? "surface",
          message: errMessage,
          path: issue?.path,
        }),
      );
    }
    return (
      <div
        role="alert"
        data-a2ui-surface-error="true"
        className={className}
        style={{
          border: "1px solid var(--a2ui-error-border, currentColor)",
          padding: "0.75rem 1rem",
          borderRadius: "var(--a2ui-radius, 0.5rem)",
        }}
      >
        Unable to render A2UI surface: {errMessage}
      </div>
    );
  }

  if (!activeSurface) {
    return null;
  }

  const baseDataModel = activeSurface.dataModel;
  const overrideModel = localModelOverrides.get(activeSurface.surfaceId);
  const dataModel = overrideModel
    ? Object.fromEntries([...Object.entries(baseDataModel), ...Object.entries(overrideModel)])
    : baseDataModel;

  const updateModelPath = (path: string | null, nextValue: unknown) => {
    if (!path) return;
    setLocalModelOverrides((prev) => {
      const nextMap = new Map(prev);
      const currentOverride = nextMap.get(activeSurface.surfaceId) ?? {};
      const mergedCurrent = Object.fromEntries([
        ...Object.entries(baseDataModel),
        ...Object.entries(currentOverride),
      ]);
      nextMap.set(activeSurface.surfaceId, setDataAtPath(mergedCurrent, path, nextValue));
      return nextMap;
    });
  };

  const getNodeById = (componentId: string): A2uiComponentNode | undefined => {
    const found = Object.entries(activeSurface.components).find(([id]) => id === componentId);
    return found?.[1];
  };

  const dispatchAction = (node: A2uiComponentNode, scopeItem?: Record<string, unknown>) => {
    const action = isPlainRecord(node.props.action) ? node.props.action : null;
    if (!action) return;

    if (isPlainRecord(action.functionCall) && action.functionCall.call === "openUrl") {
      const args = isPlainRecord(action.functionCall.args) ? action.functionCall.args : {};
      const resolvedUrl = asString(resolveDynamicValue(args.url, dataModel, scopeItem));
      if (isSafeUrl(resolvedUrl)) {
        if (onAction) {
          onAction(
            createRendererActionEvent({
              name: "openUrl",
              surfaceId: activeSurface.surfaceId,
              sourceComponentId: node.id,
              context: { url: resolvedUrl },
            }),
          );
        }
        if (typeof window !== "undefined") {
          window.open(resolvedUrl, "_blank", "noopener,noreferrer");
        }
      }
      return;
    }

    if (isPlainRecord(action.event) && typeof action.event.name === "string") {
      const resolvedContext = resolveEventContext(action.event.context, dataModel, scopeItem);
      const userMessage =
        action.event.userMessage !== undefined
          ? asString(resolveDynamicValue(action.event.userMessage, dataModel, scopeItem))
          : undefined;
      onAction?.(
        createRendererActionEvent({
          name: action.event.name,
          surfaceId: activeSurface.surfaceId,
          sourceComponentId: node.id,
          context: resolvedContext,
          userMessage,
        }),
      );
    }
  };

  const renderNode = (
    componentId: string,
    visited: Set<string>,
    scopeItem?: Record<string, unknown>,
    keySuffix = "",
  ): React.ReactNode => {
    if (visited.has(componentId)) {
      return null;
    }
    const node = getNodeById(componentId);
    if (!node) {
      return null;
    }
    const aria = resolveAriaAttrs(node, dataModel, scopeItem);
    if (aria.hidden) {
      return null;
    }
    const nextVisited = new Set(visited);
    nextVisited.add(componentId);
    const props = node.props;
    const nodeKey = `${node.id}${keySuffix}`;
    const commonAria = {
      "aria-label": aria.ariaLabel,
      "aria-live": aria.ariaLive,
      title: aria.title,
      "data-a2ui-id": node.id,
      "data-a2ui-component": node.component,
    } as const;

    switch (node.component) {
      case "Column":
      case "Row":
      case "List": {
        const isRow =
          node.component === "Row" ||
          (node.component === "List" && props.direction === "horizontal");
        const childrenRefs = resolveChildrenRefs(props.children, dataModel, scopeItem);
        const childElements = childrenRefs.map((ref) =>
          renderNode(ref.id, nextVisited, ref.scopeItem, `-${ref.key}`),
        );
        if (node.component === "List") {
          return (
            <ul
              key={nodeKey}
              {...commonAria}
              style={{
                display: "flex",
                flexDirection: isRow ? "row" : "column",
                gap: "var(--a2ui-gap, 0.5rem)",
                listStyle: "none",
                margin: 0,
                padding: 0,
              }}
            >
              {childElements.map((child, idx) => (
                <li key={`${nodeKey}-li-${idx}`}>{child}</li>
              ))}
            </ul>
          );
        }
        return (
          <div
            key={nodeKey}
            {...commonAria}
            style={{
              display: "flex",
              flexDirection: isRow ? "row" : "column",
              flexWrap: isRow ? "wrap" : undefined,
              gap: "var(--a2ui-gap, 0.75rem)",
            }}
          >
            {childElements}
          </div>
        );
      }

      case "Card": {
        const childId = typeof props.child === "string" ? props.child : "";
        return (
          <section
            key={nodeKey}
            {...commonAria}
            style={{
              border: "1px solid var(--a2ui-border, currentColor)",
              borderRadius: "var(--a2ui-radius, 0.75rem)",
              padding: "var(--a2ui-card-padding, 1rem)",
              background: "var(--a2ui-surface, transparent)",
            }}
          >
            {childId ? renderNode(childId, nextVisited, scopeItem) : null}
          </section>
        );
      }

      case "Divider": {
        const isVertical = props.axis === "vertical";
        return (
          <hr
            key={nodeKey}
            {...commonAria}
            aria-orientation={isVertical ? "vertical" : "horizontal"}
            style={{
              border: 0,
              borderTop: isVertical ? undefined : "1px solid var(--a2ui-border, currentColor)",
              borderLeft: isVertical ? "1px solid var(--a2ui-border, currentColor)" : undefined,
              margin: isVertical ? "0 0.5rem" : "0.5rem 0",
            }}
          />
        );
      }

      case "Text": {
        const content = asString(resolveDynamicValue(props.text, dataModel, scopeItem));
        return (
          <div key={nodeKey} {...commonAria}>
            {renderTextVariant(props.variant, content)}
          </div>
        );
      }

      case "Badge": {
        const label = asString(
          resolveDynamicValue(props.text ?? props.label, dataModel, scopeItem),
        );
        return (
          <span
            key={nodeKey}
            {...commonAria}
            style={{
              display: "inline-flex",
              alignItems: "center",
              padding: "0.15rem 0.5rem",
              borderRadius: "9999px",
              border: "1px solid var(--a2ui-border, currentColor)",
              fontSize: "0.75rem",
            }}
          >
            {label}
          </span>
        );
      }

      case "Image": {
        const url = asString(resolveDynamicValue(props.url ?? props.src, dataModel, scopeItem));
        if (!isSafeUrl(url)) return null;
        const alt = asString(
          resolveDynamicValue(props.description ?? props.alt, dataModel, scopeItem),
        );
        const fit =
          props.fit === "contain" ||
          props.fit === "cover" ||
          props.fit === "fill" ||
          props.fit === "none" ||
          props.fit === "scale-down"
            ? props.fit
            : "cover";
        return (
          <img
            key={nodeKey}
            {...commonAria}
            src={url}
            alt={alt}
            style={{ maxWidth: "100%", objectFit: fit }}
          />
        );
      }

      case "Icon": {
        const rawName = props.name;
        const iconName =
          isPlainRecord(rawName) && typeof rawName.path === "string"
            ? asString(resolveDynamicValue(rawName, dataModel, scopeItem))
            : asString(rawName);
        const glyph = Object.entries(ICON_GLYPHS).find(([k]) => k === iconName)?.[1] ?? "*";
        return (
          <span
            key={nodeKey}
            {...commonAria}
            aria-label={aria.ariaLabel ?? iconName}
            data-icon-name={iconName}
          >
            {glyph}
          </span>
        );
      }

      case "Video": {
        const url = asString(resolveDynamicValue(props.url, dataModel, scopeItem));
        if (!isSafeUrl(url)) return null;
        const poster = props.posterUrl
          ? asString(resolveDynamicValue(props.posterUrl, dataModel, scopeItem))
          : undefined;
        const safePoster = poster && isSafeUrl(poster) ? poster : undefined;
        return (
          <video
            key={nodeKey}
            {...commonAria}
            src={url}
            poster={safePoster}
            controls
            style={{ maxWidth: "100%" }}
          />
        );
      }

      case "AudioPlayer":
      case "Audio": {
        const url = asString(resolveDynamicValue(props.url, dataModel, scopeItem));
        if (!isSafeUrl(url)) return null;
        const desc = asString(resolveDynamicValue(props.description, dataModel, scopeItem));
        return (
          <figure key={nodeKey} {...commonAria} style={{ margin: 0 }}>
            {desc ? <figcaption>{desc}</figcaption> : null}
            <audio src={url} controls />
          </figure>
        );
      }

      case "Tabs": {
        const rawTabs = Array.isArray(props.tabs) ? props.tabs : [];
        const selectedIdx = activeTabs.get(node.id) ?? 0;
        const clampedIdx = selectedIdx >= 0 && selectedIdx < rawTabs.length ? selectedIdx : 0;
        const activeTab = rawTabs.at(clampedIdx);
        return (
          <div key={nodeKey} {...commonAria}>
            <div role="tablist" style={{ display: "flex", gap: "0.5rem" }}>
              {rawTabs.map((tab, idx) => {
                if (!isPlainRecord(tab)) return null;
                const tabTitle = asString(resolveDynamicValue(tab.title, dataModel, scopeItem));
                const isSelected = idx === clampedIdx;
                return (
                  <button
                    key={`${nodeKey}-tab-${idx}`}
                    type="button"
                    role="tab"
                    aria-selected={isSelected}
                    onClick={() =>
                      setActiveTabs((prev) => {
                        const next = new Map(prev);
                        next.set(node.id, idx);
                        return next;
                      })
                    }
                  >
                    {tabTitle}
                  </button>
                );
              })}
            </div>
            {isPlainRecord(activeTab) && typeof activeTab.child === "string" ? (
              <div role="tabpanel">
                {renderNode(activeTab.child, nextVisited, scopeItem, `-tab-${clampedIdx}`)}
              </div>
            ) : null}
          </div>
        );
      }

      case "Modal": {
        const triggerId = typeof props.trigger === "string" ? props.trigger : "";
        const contentId = typeof props.content === "string" ? props.content : "";
        const isOpen = openModals.get(node.id) ?? false;
        const toggleModal = (nextOpen: boolean) => {
          setOpenModals((prev) => {
            const next = new Map(prev);
            next.set(node.id, nextOpen);
            return next;
          });
        };
        return (
          <div key={nodeKey} {...commonAria}>
            <div onClick={() => toggleModal(true)}>
              {triggerId ? renderNode(triggerId, nextVisited, scopeItem, "-trigger") : null}
            </div>
            {isOpen ? (
              <div
                role="dialog"
                aria-modal="true"
                style={{
                  border: "1px solid var(--a2ui-border, currentColor)",
                  padding: "1rem",
                  borderRadius: "var(--a2ui-radius, 0.5rem)",
                }}
              >
                {contentId ? renderNode(contentId, nextVisited, scopeItem, "-modal") : null}
                <button type="button" onClick={() => toggleModal(false)}>
                  Close
                </button>
              </div>
            ) : null}
          </div>
        );
      }

      case "Button": {
        const childId = typeof props.child === "string" ? props.child : "";
        const fallbackLabel = typeof props.label === "string" ? props.label : "Action";
        const variant =
          props.variant === "primary" || props.variant === "borderless" ? props.variant : "default";
        return (
          <button
            key={nodeKey}
            type="button"
            {...commonAria}
            data-variant={variant}
            onClick={() => dispatchAction(node, scopeItem)}
            style={{ cursor: "pointer" }}
          >
            {childId ? renderNode(childId, nextVisited, scopeItem, "-btn") : fallbackLabel}
          </button>
        );
      }

      case "TextField":
      case "Input": {
        const label = asString(resolveDynamicValue(props.label, dataModel, scopeItem));
        const value = asString(resolveDynamicValue(props.value, dataModel, scopeItem));
        const placeholder = props.placeholder
          ? asString(resolveDynamicValue(props.placeholder, dataModel, scopeItem))
          : undefined;
        const path = getBindingPath(props.value);
        const variant = typeof props.variant === "string" ? props.variant : "shortText";
        return (
          <label key={nodeKey} {...commonAria} style={{ display: "grid", gap: "0.25rem" }}>
            <span>{label}</span>
            {variant === "longText" ? (
              <textarea
                value={value}
                placeholder={placeholder}
                onChange={(e) => updateModelPath(path, e.target.value)}
              />
            ) : (
              <input
                type={
                  variant === "obscured" ? "password" : variant === "number" ? "number" : "text"
                }
                value={value}
                placeholder={placeholder}
                onChange={(e) => updateModelPath(path, e.target.value)}
              />
            )}
          </label>
        );
      }

      case "CheckBox": {
        const label = asString(resolveDynamicValue(props.label, dataModel, scopeItem));
        const checked = asBoolean(resolveDynamicValue(props.value, dataModel, scopeItem));
        const path = getBindingPath(props.value);
        return (
          <label
            key={nodeKey}
            {...commonAria}
            style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}
          >
            <input
              type="checkbox"
              checked={checked}
              onChange={(e) => updateModelPath(path, e.target.checked)}
            />
            <span>{label}</span>
          </label>
        );
      }

      case "ChoicePicker":
      case "Select": {
        const label = asString(resolveDynamicValue(props.label, dataModel, scopeItem), "Choose");
        const options = Array.isArray(props.options) ? props.options : [];
        const selected = asStringArray(resolveDynamicValue(props.value, dataModel, scopeItem));
        const singleValue = asString(resolveDynamicValue(props.value, dataModel, scopeItem));
        const isMulti = props.variant === "multipleSelection";
        const path = getBindingPath(props.value);
        const filterText = choiceFilters.get(node.id) ?? "";
        const filteredOptions = options.filter((opt) => {
          if (!isPlainRecord(opt) || !filterText) return true;
          const optLabel = asString(resolveDynamicValue(opt.label, dataModel, scopeItem));
          return optLabel.toLowerCase().includes(filterText.toLowerCase());
        });

        if (!isMulti && node.component === "Select") {
          return (
            <label key={nodeKey} {...commonAria} style={{ display: "grid", gap: "0.25rem" }}>
              <span>{label}</span>
              <select value={singleValue} onChange={(e) => updateModelPath(path, e.target.value)}>
                {filteredOptions.map((opt, idx) => {
                  if (!isPlainRecord(opt) || typeof opt.value !== "string") return null;
                  const optLabel = asString(resolveDynamicValue(opt.label, dataModel, scopeItem));
                  return (
                    <option key={`${nodeKey}-opt-${idx}`} value={opt.value}>
                      {optLabel}
                    </option>
                  );
                })}
              </select>
            </label>
          );
        }

        return (
          <fieldset key={nodeKey} {...commonAria}>
            <legend>{label}</legend>
            {props.filterable === true ? (
              <input
                type="search"
                value={filterText}
                placeholder="Filter options"
                onChange={(e) =>
                  setChoiceFilters((prev) => {
                    const next = new Map(prev);
                    next.set(node.id, e.target.value);
                    return next;
                  })
                }
              />
            ) : null}
            <div style={{ display: "flex", flexDirection: "column", gap: "0.25rem" }}>
              {filteredOptions.map((opt, idx) => {
                if (!isPlainRecord(opt) || typeof opt.value !== "string") return null;
                const optLabel = asString(resolveDynamicValue(opt.label, dataModel, scopeItem));
                const optValue = opt.value;
                const isChecked = isMulti
                  ? selected.includes(optValue)
                  : selected.includes(optValue) || singleValue === optValue;
                return (
                  <label
                    key={`${nodeKey}-choice-${idx}`}
                    style={{ display: "inline-flex", alignItems: "center", gap: "0.5rem" }}
                  >
                    <input
                      type={isMulti ? "checkbox" : "radio"}
                      name={isMulti ? undefined : `${activeSurface.surfaceId}-${node.id}`}
                      checked={isChecked}
                      onChange={() => {
                        if (isMulti) {
                          const nextList = isChecked
                            ? selected.filter((item) => item !== optValue)
                            : [...selected, optValue];
                          updateModelPath(path, nextList);
                        } else {
                          updateModelPath(path, [optValue]);
                        }
                      }}
                    />
                    <span>{optLabel}</span>
                  </label>
                );
              })}
            </div>
          </fieldset>
        );
      }

      case "Slider": {
        const label = asString(resolveDynamicValue(props.label, dataModel, scopeItem));
        const min = typeof props.min === "number" ? props.min : 0;
        const max = typeof props.max === "number" ? props.max : 100;
        const current = asNumber(resolveDynamicValue(props.value, dataModel, scopeItem), min);
        const steps = typeof props.steps === "number" && props.steps > 0 ? props.steps : undefined;
        const stepSize = steps ? (max - min) / steps : undefined;
        const path = getBindingPath(props.value);
        return (
          <label key={nodeKey} {...commonAria} style={{ display: "grid", gap: "0.25rem" }}>
            <span>
              {label ? `${label}: ` : ""}
              {current}
            </span>
            <input
              type="range"
              min={min}
              max={max}
              step={stepSize}
              value={current}
              onChange={(e) => updateModelPath(path, Number(e.target.value))}
            />
          </label>
        );
      }

      case "DateTimeInput": {
        const label = asString(resolveDynamicValue(props.label, dataModel, scopeItem));
        const value = asString(resolveDynamicValue(props.value, dataModel, scopeItem));
        const enableDate = props.enableDate !== false;
        const enableTime = props.enableTime === true;
        const inputType =
          enableDate && enableTime ? "datetime-local" : enableTime ? "time" : "date";
        const minVal = props.min
          ? asString(resolveDynamicValue(props.min, dataModel, scopeItem))
          : undefined;
        const maxVal = props.max
          ? asString(resolveDynamicValue(props.max, dataModel, scopeItem))
          : undefined;
        const path = getBindingPath(props.value);
        return (
          <label key={nodeKey} {...commonAria} style={{ display: "grid", gap: "0.25rem" }}>
            {label ? <span>{label}</span> : null}
            <input
              type={inputType}
              value={value}
              min={minVal}
              max={maxVal}
              onChange={(e) => updateModelPath(path, e.target.value)}
            />
          </label>
        );
      }

      default:
        return null;
    }
  };

  const entryPointId =
    Object.entries(activeSurface.components).find(([id]) => id === activeSurface.rootId)?.[0] ??
    activeSurface.componentOrder[0];

  if (!entryPointId) {
    return null;
  }

  return (
    <div
      data-a2ui-surface-id={activeSurface.surfaceId}
      data-a2ui-catalog-id={activeSurface.catalogId}
      data-a2ui-protocol-version="1.0"
      className={className}
    >
      {renderNode(entryPointId, new Set())}
    </div>
  );
}
