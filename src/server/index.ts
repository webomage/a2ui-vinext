import {
  type A2uiNormalizedSurface,
  type A2uiValidationIssue,
  isPlainRecord,
  redactSensitiveDataModelWithCount,
  validateA2uiVinextEnvelope,
} from "../catalog.js";

export interface A2uiPreparedSurfacePayload {
  ok: boolean;
  surfaceId: string;
  surface: A2uiNormalizedSurface | null;
  issues: A2uiValidationIssue[];
  redactedKeyCount: number;
  preparedAt: string;
}

export interface A2uiRendererActionEnvelope {
  version: "1.0";
  action: {
    name: string;
    surfaceId: string;
    sourceComponentId: string;
    timestamp: string;
    context: Record<string, unknown>;
    userMessage?: string;
  };
}

export interface A2uiRendererErrorEnvelope {
  version: "1.0";
  error: {
    code: "VALIDATION_FAILED" | string;
    surfaceId: string;
    message: string;
    path?: string;
  };
}

/**
 * Merges public server-derived bindings into a surface data model and strips all
 * secret-shaped keys prior to serializing across an RSC or Workers boundary.
 */
export function bindServerDataModel(
  baseModel: Record<string, unknown>,
  serverBindings: Record<string, unknown> = {},
): { dataModel: Record<string, unknown>; redactedKeyCount: number } {
  const merged = Object.fromEntries([
    ...Object.entries(baseModel),
    ...Object.entries(serverBindings),
  ]);
  const redacted = redactSensitiveDataModelWithCount(merged);
  return {
    dataModel: isPlainRecord(redacted.sanitized) ? redacted.sanitized : {},
    redactedKeyCount: redacted.redactedKeyCount,
  };
}

/**
 * Server/RSC entrypoint: validates raw A2UI envelopes fail-closed, binds public server data,
 * strips secrets, and produces a plain JSON-serializable surface payload safe for `"use client"`.
 */
export function prepareA2uiRscSurface(
  rawMessages: unknown,
  options: {
    surfaceId?: string;
    serverBindings?: Record<string, unknown>;
    allowedCatalogIds?: ReadonlySet<string>;
  } = {},
): A2uiPreparedSurfacePayload {
  const validation = validateA2uiVinextEnvelope(rawMessages, {
    allowedCatalogIds: options.allowedCatalogIds,
  });
  const surfaceEntries = Object.entries(validation.surfaces);
  const targetEntry = options.surfaceId
    ? surfaceEntries.find(([id]) => id === options.surfaceId)
    : surfaceEntries[0];

  if (!validation.ok || !targetEntry) {
    return {
      ok: false,
      surfaceId: options.surfaceId ?? targetEntry?.[0] ?? "surface",
      surface: null,
      issues:
        validation.issues.length > 0
          ? validation.issues
          : [
              {
                code: "SURFACE_NOT_FOUND",
                surfaceId: options.surfaceId ?? "surface",
                message: "No valid A2UI surface produced from envelope",
              },
            ],
      redactedKeyCount: validation.redactedKeyCount,
      preparedAt: new Date().toISOString(),
    };
  }

  const [surfaceId, rawSurface] = targetEntry;
  const bound = bindServerDataModel(rawSurface.dataModel, options.serverBindings);

  return {
    ok: true,
    surfaceId,
    surface: {
      ...rawSurface,
      dataModel: bound.dataModel,
    },
    issues: [],
    redactedKeyCount: validation.redactedKeyCount + bound.redactedKeyCount,
    preparedAt: new Date().toISOString(),
  };
}

/**
 * Constructs a canonical A2UI v1.0 `renderer_to_agent.json` action event envelope.
 */
export function createRendererActionEvent(params: {
  name: string;
  surfaceId: string;
  sourceComponentId: string;
  context?: Record<string, unknown>;
  userMessage?: string;
  timestamp?: string;
}): A2uiRendererActionEnvelope {
  const sanitizedContext = redactSensitiveDataModelWithCount(params.context ?? {}).sanitized;
  const action: A2uiRendererActionEnvelope["action"] = {
    name: params.name,
    surfaceId: params.surfaceId,
    sourceComponentId: params.sourceComponentId,
    timestamp: params.timestamp ?? new Date().toISOString(),
    context: isPlainRecord(sanitizedContext) ? sanitizedContext : {},
  };
  if (typeof params.userMessage === "string" && params.userMessage.trim()) {
    action.userMessage = params.userMessage.trim();
  }
  return {
    version: "1.0",
    action,
  };
}

/**
 * Constructs a canonical A2UI v1.0 `renderer_to_agent.json` error event envelope.
 */
export function createRendererErrorEvent(params: {
  surfaceId: string;
  message: string;
  code?: string;
  path?: string;
}): A2uiRendererErrorEnvelope {
  const error: A2uiRendererErrorEnvelope["error"] = {
    code: params.code ?? "VALIDATION_FAILED",
    surfaceId: params.surfaceId,
    message: params.message,
  };
  if (params.path) {
    error.path = params.path;
  }
  return {
    version: "1.0",
    error,
  };
}
