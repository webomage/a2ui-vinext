import {
  basicCatalog,
  MessageProcessor,
  sanitizeMediaUrl,
  STRICT_VALIDATION,
} from "@a2ui/web_core/v1_0";
import { z } from "zod";

export const A2UI_VINEXT_PROTOCOL_VERSION = "1.0" as const;
export const A2UI_SUPPORTED_PROTOCOL_VERSIONS = ["1.0", "v0.9.1", "0.9.1", "v0.9", "v0.8"] as const;

export const A2UI_BASIC_CATALOG_ID =
  "https://a2ui.org/specification/v1_0/catalogs/basic/catalog.json" as const;
export const A2UI_LEGACY_BASIC_CATALOG_ID =
  "https://a2ui.org/specification/v1_0/basic_catalog.json" as const;
export const A2UI_VINEXT_CATALOG_ID = "https://webomage.com/a2ui/vinext/catalog/v1" as const;

export const ALLOWED_A2UI_VINEXT_CATALOG_IDS = new Set<string>([
  A2UI_BASIC_CATALOG_ID,
  A2UI_LEGACY_BASIC_CATALOG_ID,
  "a2ui.org:basic_catalog:v1_0",
  "https://a2ui.org/specification/v0_9/basic_catalog.json",
  "https://a2ui.org/specification/v0_8/standard_catalog_definition.json",
  A2UI_VINEXT_CATALOG_ID,
  "basic",
]);

/**
 * Complete set of 18 official A2UI v1.0 Basic Catalog components
 * (catalogs/basic/v1/catalog.json).
 */
export const BASIC_CATALOG_V1_COMPONENTS = [
  "Text",
  "Image",
  "Icon",
  "Video",
  "AudioPlayer",
  "Row",
  "Column",
  "List",
  "Card",
  "Tabs",
  "Modal",
  "Divider",
  "Button",
  "TextField",
  "CheckBox",
  "ChoicePicker",
  "Slider",
  "DateTimeInput",
] as const;

export type BasicCatalogV1ComponentName = (typeof BASIC_CATALOG_V1_COMPONENTS)[number];

/**
 * Compatibility aliases accepted from v0.8 / webomage catalogs and mapped onto Basic Catalog primitives.
 */
export const COMPAT_ALIAS_COMPONENTS = ["Badge", "Select", "Input", "Audio"] as const;
export type CompatAliasComponentName = (typeof COMPAT_ALIAS_COMPONENTS)[number];

export type SupportedComponentName = BasicCatalogV1ComponentName | CompatAliasComponentName;

export const BASIC_CATALOG_V1_COMPONENT_SET = new Set<string>(BASIC_CATALOG_V1_COMPONENTS);
export const ALL_ALLOWED_COMPONENTS = new Set<string>([
  ...BASIC_CATALOG_V1_COMPONENTS,
  ...COMPAT_ALIAS_COMPONENTS,
]);

const PROTOTYPE_POLLUTION_KEYS = new Set(["__proto__", "constructor", "prototype"]);
const SENSITIVE_KEY_PATTERN =
  /^(?:.*(?:token|secret|password|passwd|apikey|api_key|service_role|private_key|authorization|bearer|credential|cookie|session_id).*)$/i;

function hasControlCharacters(value: string): boolean {
  for (let i = 0; i < value.length; i += 1) {
    const code = value.charCodeAt(i);
    if (code < 0x20 || code === 0x7f) {
      return true;
    }
  }
  return false;
}

export interface A2uiComponentAccessibility {
  label?: unknown;
  description?: unknown;
  live?: "off" | "polite" | "assertive";
  hidden?: unknown;
}

export interface A2uiComponentNode {
  id: string;
  component: SupportedComponentName;
  props: Record<string, unknown>;
  accessibility?: A2uiComponentAccessibility;
  catalogId?: string;
}

export interface A2uiNormalizedSurface {
  surfaceId: string;
  catalogId: string;
  rootId: string;
  sendDataModel: boolean;
  components: Record<string, A2uiComponentNode>;
  componentOrder: string[];
  dataModel: Record<string, unknown>;
  metadata?: Record<string, unknown>;
  deleted?: boolean;
}

export interface A2uiValidationIssue {
  code:
    | "VALIDATION_FAILED"
    | "UNALLOWED_CATALOG"
    | "UNALLOWED_COMPONENT"
    | "UNSAFE_URL"
    | "PROTOTYPE_POLLUTION"
    | "SURFACE_NOT_FOUND";
  surfaceId: string;
  message: string;
  path?: string;
}

export interface A2uiValidationResult {
  ok: boolean;
  version: "1.0" | "v0.9.1" | "v0.9" | "v0.8";
  issues: A2uiValidationIssue[];
  surfaces: Record<string, A2uiNormalizedSurface>;
  redactedKeyCount: number;
}

export interface A2uiRendererCapabilitiesEnvelope {
  a2uiRendererCapabilities: Record<
    string,
    {
      supportedCatalogIds: string[];
      inlineCatalogs?: Array<Record<string, unknown>>;
    }
  >;
}

export interface A2uiCapabilitiesOptions {
  versions?: Array<"1.0" | "v0.9" | "v0.9.1" | "v0.8">;
  includeInlineCatalogs?: boolean;
  additionalCatalogIds?: string[];
}

export const DynamicStringSchema = z.union([
  z.string(),
  z.object({ path: z.string().min(1) }).passthrough(),
  z.object({ "@path": z.string().min(1) }).passthrough(),
  z.object({ call: z.string().min(1) }).passthrough(),
  z.object({ "@call": z.string().min(1) }).passthrough(),
  z.object({ literalString: z.string() }),
]);

export const DynamicNumberSchema = z.union([
  z.number(),
  z.object({ path: z.string().min(1) }).passthrough(),
  z.object({ "@path": z.string().min(1) }).passthrough(),
  z.object({ call: z.string().min(1) }).passthrough(),
  z.object({ "@call": z.string().min(1) }).passthrough(),
  z.object({ literalNumber: z.number() }),
]);

export const DynamicBooleanSchema = z.union([
  z.boolean(),
  z.object({ path: z.string().min(1) }).passthrough(),
  z.object({ "@path": z.string().min(1) }).passthrough(),
  z.object({ call: z.string().min(1) }).passthrough(),
  z.object({ "@call": z.string().min(1) }).passthrough(),
  z.object({ literalBoolean: z.boolean() }),
]);

export const DynamicStringListSchema = z.union([
  z.array(z.string()),
  z.object({ path: z.string().min(1) }).passthrough(),
  z.object({ "@path": z.string().min(1) }).passthrough(),
  z.object({ literalArray: z.array(z.string()) }),
]);

export const ChildListSchema = z.union([
  z.array(z.string().min(1)),
  z
    .object({
      componentId: z.string().min(1),
      path: z.string().min(1).optional(),
      "@path": z.string().min(1).optional(),
    })
    .refine((data) => Boolean(data["@path"] || data.path), {
      message: "ChildList requires @path or path",
    }),
]);

export const ActionSchema = z.union([
  z.object({
    event: z.object({
      name: z.string().min(1),
      context: z.record(z.string(), z.unknown()).optional(),
      userMessage: DynamicStringSchema.optional(),
    }),
  }),
  z.object({
    functionCall: z
      .object({
        call: z.string().min(1).optional(),
        "@call": z.string().min(1).optional(),
        args: z.record(z.string(), z.unknown()).optional(),
        "@args": z.record(z.string(), z.unknown()).optional(),
        returnType: z.string().optional(),
      })
      .refine((data) => Boolean(data["@call"] || data.call), {
        message: "functionCall requires @call or call",
      }),
  }),
]);

const BaseComponentObjectSchema = z
  .object({
    id: z.string().min(1).max(128),
    component: z.string().min(1).max(64),
  })
  .passthrough();

export function isPlainRecord(value: unknown): value is Record<string, unknown> {
  if (typeof value !== "object" || value === null || Array.isArray(value)) {
    return false;
  }
  const proto = Object.getPrototypeOf(value);
  return proto === Object.prototype || proto === null;
}

export function hasPrototypePollutionKey(value: unknown, depth = 0): boolean {
  if (depth > 16 || typeof value !== "object" || value === null) {
    return false;
  }
  if (Array.isArray(value)) {
    return value.some((item) => hasPrototypePollutionKey(item, depth + 1));
  }
  for (const key of Object.keys(value)) {
    if (PROTOTYPE_POLLUTION_KEYS.has(key)) {
      return true;
    }
    const entry = Object.entries(value).find(([k]) => k === key);
    if (entry && hasPrototypePollutionKey(entry[1], depth + 1)) {
      return true;
    }
  }
  return false;
}

export function isSafeUrl(rawUrl: unknown, allowDataImage = false): boolean {
  if (typeof rawUrl !== "string") {
    return false;
  }
  const trimmed = rawUrl.trim();
  if (!trimmed || hasControlCharacters(trimmed)) {
    return false;
  }
  const lower = trimmed.toLowerCase();
  if (
    lower.startsWith("javascript:") ||
    lower.startsWith("vbscript:") ||
    lower.startsWith("file:")
  ) {
    return false;
  }
  if (lower.startsWith("data:")) {
    if (!allowDataImage) {
      return false;
    }
    return /^data:image\/(png|jpeg|jpg|webp|gif);base64,[a-z0-9+/=]+$/i.test(trimmed);
  }
  if (trimmed.startsWith("/") && !trimmed.startsWith("//")) {
    return true;
  }
  if (trimmed.startsWith("#")) {
    return true;
  }
  const coreSanitized = sanitizeMediaUrl(trimmed);
  if (!coreSanitized) {
    return false;
  }
  try {
    const parsed = new URL(trimmed);
    return parsed.protocol === "https:" || parsed.protocol === "http:";
  } catch {
    return false;
  }
}

export function isSensitiveKey(key: string): boolean {
  return SENSITIVE_KEY_PATTERN.test(key.trim());
}

export function redactSensitiveDataModelWithCount(
  value: unknown,
  depth = 0,
): { sanitized: unknown; redactedKeyCount: number } {
  if (depth > 16 || value === null || typeof value !== "object") {
    return { sanitized: value, redactedKeyCount: 0 };
  }
  if (Array.isArray(value)) {
    let total = 0;
    const mapped = value.map((item) => {
      const next = redactSensitiveDataModelWithCount(item, depth + 1);
      total += next.redactedKeyCount;
      return next.sanitized;
    });
    return { sanitized: mapped, redactedKeyCount: total };
  }
  const entries: Array<[string, unknown]> = [];
  let total = 0;
  for (const [key, entryValue] of Object.entries(value)) {
    if (PROTOTYPE_POLLUTION_KEYS.has(key)) {
      continue;
    }
    if (isSensitiveKey(key)) {
      total += 1;
      continue;
    }
    const nested = redactSensitiveDataModelWithCount(entryValue, depth + 1);
    total += nested.redactedKeyCount;
    entries.push([key, nested.sanitized]);
  }
  return {
    sanitized: Object.fromEntries(entries),
    redactedKeyCount: total,
  };
}

export function redactSensitiveDataModel(value: unknown): unknown {
  return redactSensitiveDataModelWithCount(value).sanitized;
}

export function getDataAtPath(model: Record<string, unknown>, rawPath: string): unknown {
  const clean = rawPath.trim();
  if (!clean || clean === "/" || clean === ".") {
    return model;
  }
  const segments = clean
    .replace(/^\//, "")
    .split(/[/.]/)
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0 && !PROTOTYPE_POLLUTION_KEYS.has(segment));

  let cursor: unknown = model;
  for (const segment of segments) {
    if (Array.isArray(cursor)) {
      const idx = Number.parseInt(segment, 10);
      if (!Number.isInteger(idx) || idx < 0 || idx >= cursor.length) {
        return undefined;
      }
      cursor = cursor.at(idx);
      continue;
    }
    if (!isPlainRecord(cursor)) {
      return undefined;
    }
    const found = Object.entries(cursor).find(([k]) => k === segment);
    if (!found) {
      return undefined;
    }
    cursor = found[1];
  }
  return cursor;
}

function setNestedRecord(
  target: Record<string, unknown>,
  segments: string[],
  index: number,
  value: unknown,
): Record<string, unknown> {
  const segment = segments[index];
  if (!segment || PROTOTYPE_POLLUTION_KEYS.has(segment)) {
    return target;
  }
  const map = new Map(Object.entries(target));
  if (index >= segments.length - 1) {
    map.set(segment, value);
  } else {
    const existing = map.get(segment);
    const child = isPlainRecord(existing) ? existing : {};
    map.set(segment, setNestedRecord(child, segments, index + 1, value));
  }
  return Object.fromEntries(map);
}

export function setDataAtPath(
  model: Record<string, unknown>,
  rawPath: string | undefined,
  value: unknown,
): Record<string, unknown> {
  const clean = (rawPath ?? "").trim();
  if (!clean || clean === "/" || clean === ".") {
    if (isPlainRecord(value)) {
      return Object.fromEntries([...Object.entries(model), ...Object.entries(value)]);
    }
    return model;
  }
  const segments = clean
    .replace(/^\//, "")
    .split(/[/.]/)
    .map((segment) => segment.trim())
    .filter((segment) => segment.length > 0 && !PROTOTYPE_POLLUTION_KEYS.has(segment));

  if (segments.length === 0) {
    return model;
  }
  return setNestedRecord(model, segments, 0, value);
}

export function resolveDynamicValue(
  binding: unknown,
  dataModel: Record<string, unknown>,
  scopeItem?: Record<string, unknown>,
): unknown {
  if (!isPlainRecord(binding)) {
    return binding;
  }
  if (typeof binding.literalString === "string") return binding.literalString;
  if (typeof binding.literalNumber === "number") return binding.literalNumber;
  if (typeof binding.literalBoolean === "boolean") return binding.literalBoolean;
  if (Array.isArray(binding.literalArray)) return binding.literalArray;

  const rawPath =
    typeof binding["@path"] === "string"
      ? binding["@path"]
      : typeof binding.path === "string"
        ? binding.path
        : null;
  if (rawPath !== null) {
    const trimmedPath = rawPath.trim();
    if (!trimmedPath.startsWith("/") && scopeItem) {
      const scoped = getDataAtPath(scopeItem, trimmedPath);
      if (scoped !== undefined) {
        return scoped;
      }
    }
    return getDataAtPath(dataModel, trimmedPath);
  }

  const rawCall =
    typeof binding["@call"] === "string"
      ? binding["@call"]
      : typeof binding.call === "string"
        ? binding.call
        : null;
  if (rawCall !== null) {
    const rawArgs = isPlainRecord(binding["@args"])
      ? binding["@args"]
      : isPlainRecord(binding.args)
        ? binding.args
        : undefined;
    if (rawCall === "formatString" && rawArgs) {
      const rawValue = rawArgs.value;
      return typeof rawValue === "string" ? rawValue : String(rawValue ?? "");
    }
    return rawArgs ?? "";
  }
  return binding;
}

export function resolveEventContext(
  contextSpec: unknown,
  dataModel: Record<string, unknown>,
  scopeItem?: Record<string, unknown>,
): Record<string, unknown> {
  if (!isPlainRecord(contextSpec)) {
    return {};
  }
  const resolvedEntries: Array<[string, unknown]> = [];
  for (const [key, rawVal] of Object.entries(contextSpec)) {
    if (PROTOTYPE_POLLUTION_KEYS.has(key) || isSensitiveKey(key)) {
      continue;
    }
    resolvedEntries.push([key, resolveDynamicValue(rawVal, dataModel, scopeItem)]);
  }
  return Object.fromEntries(resolvedEntries);
}

function validateComponentUrlFields(
  componentType: SupportedComponentName,
  props: Record<string, unknown>,
  dataModel: Record<string, unknown>,
  surfaceId: string,
  nodeId: string,
): A2uiValidationIssue[] {
  const issues: A2uiValidationIssue[] = [];
  const checkUrlValue = (rawCandidate: unknown, fieldPath: string, allowDataImage = false) => {
    const resolved = resolveDynamicValue(rawCandidate, dataModel);
    if (typeof resolved === "string" && !isSafeUrl(resolved, allowDataImage)) {
      issues.push({
        code: "UNSAFE_URL",
        surfaceId,
        path: `${nodeId}.${fieldPath}`,
        message: `Blocked unsafe URL protocol in ${componentType}.${fieldPath}`,
      });
    }
  };

  if (componentType === "Image") {
    checkUrlValue(props.url ?? props.src, "url", false);
  } else if (componentType === "Video") {
    checkUrlValue(props.url, "url", false);
    if (props.posterUrl !== undefined) {
      checkUrlValue(props.posterUrl, "posterUrl", false);
    }
  } else if (componentType === "AudioPlayer" || componentType === "Audio") {
    checkUrlValue(props.url, "url", false);
  } else if (componentType === "Button") {
    const action = isPlainRecord(props.action) ? props.action : undefined;
    if (action && isPlainRecord(action.functionCall)) {
      const fnCall = action.functionCall;
      const callName =
        typeof fnCall["@call"] === "string"
          ? fnCall["@call"]
          : typeof fnCall.call === "string"
            ? fnCall.call
            : "";
      if (callName === "openUrl") {
        const args = isPlainRecord(fnCall["@args"])
          ? fnCall["@args"]
          : isPlainRecord(fnCall.args)
            ? fnCall.args
            : undefined;
        if (args) {
          checkUrlValue(args.url, "action.functionCall.args.url", false);
        }
      }
    }
    if (props.href !== undefined) {
      checkUrlValue(props.href, "href", false);
    }
  }
  return issues;
}

function validateBasicComponentSchema(
  componentType: SupportedComponentName,
  rawObj: Record<string, unknown>,
): string | null {
  switch (componentType) {
    case "Text": {
      const r = z.object({ text: DynamicStringSchema.optional() }).passthrough().safeParse(rawObj);
      return r.success && rawObj.text !== undefined ? null : "Text requires `text`";
    }
    case "Image": {
      const hasUrl = rawObj.url !== undefined || rawObj.src !== undefined;
      return hasUrl ? null : "Image requires `url`";
    }
    case "Icon": {
      const ok = typeof rawObj.name === "string" || isPlainRecord(rawObj.name);
      return ok ? null : "Icon requires `name`";
    }
    case "Video":
      return rawObj.url !== undefined ? null : "Video requires `url`";
    case "AudioPlayer":
    case "Audio":
      return rawObj.url !== undefined ? null : `${componentType} requires \`url\``;
    case "Row":
    case "Column":
    case "List": {
      if (rawObj.children === undefined) {
        return `${componentType} requires \`children\``;
      }
      const r = ChildListSchema.safeParse(rawObj.children);
      return r.success ? null : `${componentType}.children must be ChildList`;
    }
    case "Card":
      return typeof rawObj.child === "string" && rawObj.child.length > 0
        ? null
        : "Card requires `child` component id";
    case "Tabs": {
      const r = z
        .array(z.object({ title: DynamicStringSchema, child: z.string().min(1) }))
        .min(1)
        .safeParse(rawObj.tabs);
      return r.success ? null : "Tabs requires non-empty `tabs` array of {title, child}";
    }
    case "Modal":
      return typeof rawObj.trigger === "string" && typeof rawObj.content === "string"
        ? null
        : "Modal requires `trigger` and `content` component ids";
    case "Divider": {
      if (rawObj.axis !== undefined && rawObj.axis !== "horizontal" && rawObj.axis !== "vertical") {
        return "Divider.axis must be 'horizontal' or 'vertical'";
      }
      return null;
    }
    case "Button": {
      if (typeof rawObj.child !== "string" && typeof rawObj.label !== "string") {
        return "Button requires `child` id";
      }
      if (!rawObj.action) {
        return "Button requires `action`";
      }
      const r = ActionSchema.safeParse(rawObj.action);
      return r.success ? null : "Button.action must be valid A2UI Action";
    }
    case "TextField":
    case "Input":
      return rawObj.label !== undefined ? null : `${componentType} requires \`label\``;
    case "CheckBox":
      return rawObj.label !== undefined && rawObj.value !== undefined
        ? null
        : "CheckBox requires `label` and `value`";
    case "ChoicePicker":
    case "Select": {
      const r = z
        .array(z.object({ label: DynamicStringSchema, value: z.string() }))
        .safeParse(rawObj.options);
      return r.success ? null : `${componentType} requires \`options\` array`;
    }
    case "Slider":
      return typeof rawObj.max === "number" && rawObj.value !== undefined
        ? null
        : "Slider requires numeric `max` and `value`";
    case "DateTimeInput":
      return rawObj.value !== undefined ? null : "DateTimeInput requires `value`";
    case "Badge":
      return rawObj.text !== undefined || rawObj.label !== undefined
        ? null
        : "Badge requires `text` or `label`";
    default:
      return `Unsupported component: ${String(componentType)}`;
  }
}

function normalizeV08ComponentEntry(
  entry: Record<string, unknown>,
): Record<string, unknown> | null {
  if (typeof entry.component === "string") {
    return entry;
  }
  if (typeof entry.id !== "string" || !isPlainRecord(entry.component)) {
    return null;
  }
  const compKeys = Object.keys(entry.component);
  if (compKeys.length !== 1) {
    return null;
  }
  const typeName = compKeys[0];
  const inner = Object.entries(entry.component).find(([k]) => k === typeName)?.[1];
  const innerObj = isPlainRecord(inner) ? inner : {};
  const merged = Object.fromEntries([
    ["id", entry.id],
    ["component", typeName],
    ...Object.entries(innerObj),
  ]);
  return merged;
}

function detectVersion(rawMessages: unknown[]): "1.0" | "v0.9.1" | "v0.9" | "v0.8" {
  for (const item of rawMessages) {
    if (!isPlainRecord(item)) continue;
    const v = item.version;
    if (v === "1.0") return "1.0";
    if (v === "v0.9.1" || v === "0.9.1") return "v0.9.1";
    if (v === "v0.9") return "v0.9";
    if (item.beginRendering || item.surfaceUpdate || item.dataModelUpdate) return "v0.8";
  }
  return "1.0";
}

function parseRawComponentArray(
  rawList: unknown[],
  surfaceId: string,
  catalogId: string,
  dataModel: Record<string, unknown>,
  issues: A2uiValidationIssue[],
): A2uiComponentNode[] {
  const parsed: A2uiComponentNode[] = [];
  for (const item of rawList) {
    if (!isPlainRecord(item)) {
      issues.push({
        code: "VALIDATION_FAILED",
        surfaceId,
        message: "Component entry must be an object",
      });
      continue;
    }
    const normalizedItem = normalizeV08ComponentEntry(item) ?? item;
    const base = BaseComponentObjectSchema.safeParse(normalizedItem);
    if (!base.success) {
      issues.push({
        code: "VALIDATION_FAILED",
        surfaceId,
        message: "Component must include non-empty `id` and `component`",
      });
      continue;
    }
    const compName = base.data.component;
    if (!ALL_ALLOWED_COMPONENTS.has(compName)) {
      issues.push({
        code: "UNALLOWED_COMPONENT",
        surfaceId,
        path: base.data.id,
        message: `Component "${compName}" is not in the approved Basic Catalog`,
      });
      continue;
    }
    const typedComp = compName as SupportedComponentName;
    const schemaErr = validateBasicComponentSchema(typedComp, normalizedItem);
    if (schemaErr) {
      issues.push({
        code: "VALIDATION_FAILED",
        surfaceId,
        path: base.data.id,
        message: schemaErr,
      });
      continue;
    }
    const propEntries: Array<[string, unknown]> = [];
    for (const [k, v] of Object.entries(normalizedItem)) {
      if (k === "id" || k === "component" || k === "@accessibility" || k === "@catalogId") {
        continue;
      }
      propEntries.push([k, v]);
    }
    const props = Object.fromEntries(propEntries);
    const urlIssues = validateComponentUrlFields(
      typedComp,
      props,
      dataModel,
      surfaceId,
      base.data.id,
    );
    if (urlIssues.length > 0) {
      issues.push(...urlIssues);
      continue;
    }
    const accessibility = isPlainRecord(normalizedItem["@accessibility"])
      ? (normalizedItem["@accessibility"] as A2uiComponentAccessibility)
      : undefined;
    parsed.push({
      id: base.data.id,
      component: typedComp,
      props,
      accessibility,
      catalogId:
        typeof normalizedItem["@catalogId"] === "string" ? normalizedItem["@catalogId"] : catalogId,
    });
  }
  return parsed;
}

export function createVinextMessageProcessor(
  options: { version?: "1.0" | "v0.9" | "v0.8" } = {},
): MessageProcessor {
  return new MessageProcessor([basicCatalog], undefined, {
    version: options.version ?? "1.0",
    validationConfig: STRICT_VALIDATION,
  });
}

export function buildA2uiRendererCapabilities(
  options: A2uiCapabilitiesOptions = {},
): A2uiRendererCapabilitiesEnvelope {
  const versions = options.versions ?? ["1.0"];
  const processor = createVinextMessageProcessor({ version: "1.0" });
  const rawCaps = processor.getRendererCapabilities({
    versions,
    includeInlineCatalogs: options.includeInlineCatalogs ?? false,
  });

  const capMap = new Map<
    string,
    { supportedCatalogIds: string[]; inlineCatalogs?: Array<Record<string, unknown>> }
  >();
  for (const [ver, entry] of Object.entries(rawCaps)) {
    if (!isPlainRecord(entry)) continue;
    const baseIds = Array.isArray(entry.supportedCatalogIds)
      ? entry.supportedCatalogIds.filter((id): id is string => typeof id === "string")
      : [A2UI_BASIC_CATALOG_ID];
    const extraIds = (options.additionalCatalogIds ?? []).filter((id) => !baseIds.includes(id));
    const mergedIds =
      baseIds.length > 0 ? [...baseIds, ...extraIds] : [A2UI_BASIC_CATALOG_ID, ...extraIds];
    const inlineCatalogs = Array.isArray(entry.inlineCatalogs)
      ? (entry.inlineCatalogs as Array<Record<string, unknown>>)
      : undefined;
    capMap.set(
      ver,
      inlineCatalogs
        ? { supportedCatalogIds: mergedIds, inlineCatalogs }
        : { supportedCatalogIds: mergedIds },
    );
  }
  if (!capMap.has("1.0") && versions.includes("1.0")) {
    capMap.set("1.0", {
      supportedCatalogIds: [A2UI_BASIC_CATALOG_ID, ...(options.additionalCatalogIds ?? [])],
    });
  }
  return {
    a2uiRendererCapabilities: Object.fromEntries(capMap),
  };
}

/**
 * Validates A2UI v1.0, v0.9.1, and v0.8 message batches fail-closed.
 * Rejects unallowlisted catalogs/components, prototype-pollution keys, and unsafe URIs,
 * and strips sensitive keys before surfacing any data model to client boundaries.
 */
export function validateA2uiVinextEnvelope(
  rawInput: unknown,
  options: {
    allowedCatalogIds?: ReadonlySet<string>;
    existingSurfaces?: Record<string, A2uiNormalizedSurface>;
  } = {},
): A2uiValidationResult {
  const allowedCatalogs = options.allowedCatalogIds ?? ALLOWED_A2UI_VINEXT_CATALOG_IDS;
  const rawMessages = Array.isArray(rawInput) ? rawInput : [rawInput];
  const version = detectVersion(rawMessages);
  const issues: A2uiValidationIssue[] = [];
  const surfaceMap = new Map<string, A2uiNormalizedSurface>(
    Object.entries(options.existingSurfaces ?? {}),
  );
  let totalRedacted = 0;

  if (hasPrototypePollutionKey(rawInput)) {
    issues.push({
      code: "PROTOTYPE_POLLUTION",
      surfaceId: "global",
      message: "Rejected payload containing reserved prototype key",
    });
    return {
      ok: false,
      version,
      issues,
      surfaces: Object.fromEntries(surfaceMap),
      redactedKeyCount: totalRedacted,
    };
  }

  for (const rawMsg of rawMessages) {
    if (!isPlainRecord(rawMsg)) {
      issues.push({
        code: "VALIDATION_FAILED",
        surfaceId: "global",
        message: "A2UI envelope message must be a JSON object",
      });
      continue;
    }

    const createBody = isPlainRecord(rawMsg.createSurface)
      ? rawMsg.createSurface
      : isPlainRecord(rawMsg.beginRendering)
        ? rawMsg.beginRendering
        : null;
    if (createBody) {
      const body = createBody;
      const surfaceId = typeof body.surfaceId === "string" ? body.surfaceId.trim() : "";
      if (!surfaceId) {
        issues.push({
          code: "VALIDATION_FAILED",
          surfaceId: "global",
          message: "createSurface requires non-empty `surfaceId`",
        });
        continue;
      }
      const catalogId =
        typeof body.catalogId === "string" && body.catalogId.trim()
          ? body.catalogId.trim()
          : A2UI_BASIC_CATALOG_ID;
      if (!allowedCatalogs.has(catalogId)) {
        issues.push({
          code: "UNALLOWED_CATALOG",
          surfaceId,
          message: `Catalog "${catalogId}" is not in allowedCatalogIds`,
        });
        continue;
      }
      const dataRedaction = isPlainRecord(body.dataModel)
        ? redactSensitiveDataModelWithCount(body.dataModel)
        : { sanitized: {}, redactedKeyCount: 0 };
      totalRedacted += dataRedaction.redactedKeyCount;
      const dataModel = isPlainRecord(dataRedaction.sanitized) ? dataRedaction.sanitized : {};
      const rootId = typeof body.root === "string" && body.root.trim() ? body.root.trim() : "root";

      const compMap = new Map<string, A2uiComponentNode>();
      const compOrder: string[] = [];
      if (Array.isArray(body.components)) {
        const nodes = parseRawComponentArray(
          body.components,
          surfaceId,
          catalogId,
          dataModel,
          issues,
        );
        for (const node of nodes) {
          compMap.set(node.id, node);
          compOrder.push(node.id);
        }
      }

      surfaceMap.set(surfaceId, {
        surfaceId,
        catalogId,
        rootId,
        sendDataModel: body.sendDataModel === true,
        components: Object.fromEntries(compMap),
        componentOrder: compOrder,
        dataModel,
        metadata: isPlainRecord(body.metadata) ? body.metadata : undefined,
        deleted: false,
      });
      continue;
    }

    const updateCompBody = isPlainRecord(rawMsg.updateComponents)
      ? rawMsg.updateComponents
      : isPlainRecord(rawMsg.surfaceUpdate)
        ? rawMsg.surfaceUpdate
        : null;
    if (updateCompBody) {
      const body = updateCompBody;
      const surfaceId = typeof body.surfaceId === "string" ? body.surfaceId.trim() : "";
      if (!surfaceId) {
        issues.push({
          code: "VALIDATION_FAILED",
          surfaceId: "global",
          message: "updateComponents requires non-empty `surfaceId`",
        });
        continue;
      }
      const current = surfaceMap.get(surfaceId) ?? {
        surfaceId,
        catalogId: A2UI_BASIC_CATALOG_ID,
        rootId: typeof body.root === "string" && body.root.trim() ? body.root.trim() : "root",
        sendDataModel: false,
        components: {},
        componentOrder: [],
        dataModel: {},
      };
      const rawList = Array.isArray(body.components) ? body.components : [];
      if (rawList.length === 0) {
        issues.push({
          code: "VALIDATION_FAILED",
          surfaceId,
          message: "updateComponents requires non-empty `components` array",
        });
        continue;
      }
      const nodes = parseRawComponentArray(
        rawList,
        surfaceId,
        current.catalogId,
        current.dataModel,
        issues,
      );
      const compMap = new Map<string, A2uiComponentNode>(Object.entries(current.components));
      const orderSet = new Set(current.componentOrder);
      for (const node of nodes) {
        compMap.set(node.id, node);
        orderSet.add(node.id);
      }
      surfaceMap.set(surfaceId, {
        ...current,
        rootId:
          typeof body.root === "string" && body.root.trim() ? body.root.trim() : current.rootId,
        components: Object.fromEntries(compMap),
        componentOrder: Array.from(orderSet),
        deleted: false,
      });
      continue;
    }

    const updateDataBody = isPlainRecord(rawMsg.updateDataModel)
      ? rawMsg.updateDataModel
      : isPlainRecord(rawMsg.dataModelUpdate)
        ? rawMsg.dataModelUpdate
        : null;
    if (updateDataBody) {
      const body = updateDataBody;
      const surfaceId = typeof body.surfaceId === "string" ? body.surfaceId.trim() : "";
      if (!surfaceId) {
        issues.push({
          code: "VALIDATION_FAILED",
          surfaceId: "global",
          message: "updateDataModel requires `surfaceId`",
        });
        continue;
      }
      const current = surfaceMap.get(surfaceId);
      if (!current) {
        issues.push({
          code: "SURFACE_NOT_FOUND",
          surfaceId,
          message: `Cannot updateDataModel for unknown surface "${surfaceId}"`,
        });
        continue;
      }
      const rawValue = body.value ?? body.contents;
      const redaction = redactSensitiveDataModelWithCount(rawValue);
      totalRedacted += redaction.redactedKeyCount;
      const pathValue =
        typeof body["@path"] === "string"
          ? body["@path"]
          : typeof body.path === "string"
            ? body.path
            : undefined;
      const updatedModel = setDataAtPath(current.dataModel, pathValue, redaction.sanitized);
      surfaceMap.set(surfaceId, {
        ...current,
        dataModel: updatedModel,
      });
      continue;
    }

    if (isPlainRecord(rawMsg.deleteSurface)) {
      const surfaceId =
        typeof rawMsg.deleteSurface.surfaceId === "string"
          ? rawMsg.deleteSurface.surfaceId.trim()
          : "";
      if (!surfaceId) {
        issues.push({
          code: "VALIDATION_FAILED",
          surfaceId: "global",
          message: "deleteSurface requires `surfaceId`",
        });
        continue;
      }
      surfaceMap.delete(surfaceId);
      continue;
    }

    issues.push({
      code: "VALIDATION_FAILED",
      surfaceId: "global",
      message: "Unrecognized A2UI envelope message type",
    });
  }

  return {
    ok: issues.length === 0,
    version,
    issues,
    surfaces: Object.fromEntries(surfaceMap),
    redactedKeyCount: totalRedacted,
  };
}
