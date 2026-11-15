import {
  type A2uiNormalizedSurface,
  isPlainRecord,
  redactSensitiveDataModelWithCount,
  validateA2uiVinextEnvelope,
} from "../catalog.js";
import { createRendererErrorEvent } from "../server/index.js";

export interface A2uiWorkerStreamOptions {
  /** Maximum permitted single JSONL/SSE line size in bytes (default: 65536). */
  maxLineBytes?: number;
  /** Maximum total frames per stream before closing fail-closed (default: 512). */
  maxMessagesPerStream?: number;
  /** Optional allowed catalog IDs override. */
  allowedCatalogIds?: ReadonlySet<string>;
}

const DEFAULT_MAX_LINE_BYTES = 64 * 1024;
const DEFAULT_MAX_MESSAGES = 512;

function sanitizeOutboundMessage(
  rawObj: Record<string, unknown>,
  surfaces: Record<string, A2uiNormalizedSurface>,
): Record<string, unknown> {
  const cloned = redactSensitiveDataModelWithCount(rawObj).sanitized;
  if (!isPlainRecord(cloned)) {
    return rawObj;
  }
  const createBody = isPlainRecord(cloned.createSurface) ? cloned.createSurface : null;
  if (createBody && typeof createBody.surfaceId === "string") {
    const entry = Object.entries(surfaces).find(([id]) => id === createBody.surfaceId);
    if (entry) {
      return Object.fromEntries([
        ...Object.entries(cloned),
        [
          "createSurface",
          Object.fromEntries([...Object.entries(createBody), ["dataModel", entry[1].dataModel]]),
        ],
      ]);
    }
  }
  return cloned;
}

/**
 * Parses and validates one JSONL or SSE `data:` line on Cloudflare Workers (`workerd`).
 * Always returns either sanitized message objects or a fail-closed `VALIDATION_FAILED` envelope.
 */
export function parseA2uiExpressChunk(
  rawLine: string,
  options: A2uiWorkerStreamOptions & {
    existingSurfaces?: Record<string, A2uiNormalizedSurface>;
  } = {},
): {
  messages: Array<Record<string, unknown>>;
  surfaces: Record<string, A2uiNormalizedSurface>;
  ok: boolean;
} {
  const maxLineBytes = options.maxLineBytes ?? DEFAULT_MAX_LINE_BYTES;
  const trimmed = rawLine.trim();
  const existing = options.existingSurfaces ?? {};

  if (!trimmed || trimmed.startsWith(":")) {
    return { messages: [], surfaces: existing, ok: true };
  }

  const normalizedLine = trimmed.startsWith("data:") ? trimmed.slice(5).trim() : trimmed;
  if (!normalizedLine || normalizedLine === "[DONE]") {
    return { messages: [], surfaces: existing, ok: true };
  }

  const byteLen = new TextEncoder().encode(normalizedLine).byteLength;
  if (byteLen > maxLineBytes) {
    return {
      ok: false,
      surfaces: existing,
      messages: [
        createRendererErrorEvent({
          surfaceId: "stream",
          message: `A2UI stream frame exceeds maxLineBytes (${maxLineBytes})`,
        }) as unknown as Record<string, unknown>,
      ],
    };
  }

  let parsedJson: unknown;
  try {
    parsedJson = JSON.parse(normalizedLine);
  } catch {
    return {
      ok: false,
      surfaces: existing,
      messages: [
        createRendererErrorEvent({
          surfaceId: "stream",
          message: "Malformed JSON in A2UI stream frame",
        }) as unknown as Record<string, unknown>,
      ],
    };
  }

  const validation = validateA2uiVinextEnvelope(parsedJson, {
    allowedCatalogIds: options.allowedCatalogIds,
    existingSurfaces: existing,
  });

  if (!validation.ok) {
    const firstIssue = validation.issues[0];
    return {
      ok: false,
      surfaces: existing,
      messages: [
        createRendererErrorEvent({
          surfaceId: firstIssue?.surfaceId ?? "stream",
          message: firstIssue?.message ?? "A2UI frame failed catalog validation",
          path: firstIssue?.path,
        }) as unknown as Record<string, unknown>,
      ],
    };
  }

  const rawItems = Array.isArray(parsedJson) ? parsedJson : [parsedJson];
  const sanitizedItems = rawItems
    .filter(isPlainRecord)
    .map((item) => sanitizeOutboundMessage(item, validation.surfaces));

  return {
    ok: true,
    surfaces: validation.surfaces,
    messages: sanitizedItems,
  };
}

/**
 * Web Standard `TransformStream` for `workerd` converting raw agent JSONL/SSE text/bytes
 * into validated, secret-stripped NDJSON bytes.
 */
export function createA2uiJsonlTransformStream(
  options: A2uiWorkerStreamOptions = {},
): TransformStream<string | Uint8Array, Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  const maxLineBytes = options.maxLineBytes ?? DEFAULT_MAX_LINE_BYTES;
  const maxMessages = options.maxMessagesPerStream ?? DEFAULT_MAX_MESSAGES;
  let buffer = "";
  let messageCount = 0;
  let surfaces: Record<string, A2uiNormalizedSurface> = {};

  const flushLine = (
    line: string,
    controller: TransformStreamDefaultController<Uint8Array>,
  ): void => {
    const cleanLine = line.trim();
    if (!cleanLine || cleanLine.startsWith("event:") || cleanLine.startsWith("id:")) {
      return;
    }
    if (messageCount >= maxMessages) {
      return;
    }
    const result = parseA2uiExpressChunk(cleanLine, {
      ...options,
      maxLineBytes,
      existingSurfaces: surfaces,
    });
    surfaces = result.surfaces;
    for (const msg of result.messages) {
      if (messageCount >= maxMessages) break;
      messageCount += 1;
      controller.enqueue(encoder.encode(`${JSON.stringify(msg)}\n`));
    }
  };

  return new TransformStream<string | Uint8Array, Uint8Array>({
    transform(chunk, controller) {
      const text = typeof chunk === "string" ? chunk : decoder.decode(chunk, { stream: true });
      buffer += text;

      if (encoder.encode(buffer).byteLength > maxLineBytes * 4 && !buffer.includes("\n")) {
        buffer = "";
        controller.enqueue(
          encoder.encode(
            `${JSON.stringify(
              createRendererErrorEvent({
                surfaceId: "stream",
                message: `Stream line buffer exceeded safe bound (${maxLineBytes * 4} bytes)`,
              }),
            )}\n`,
          ),
        );
        return;
      }

      const lines = buffer.split(/\r?\n/);
      buffer = lines.pop() ?? "";
      for (const line of lines) {
        flushLine(line, controller);
      }
    },
    flush(controller) {
      const trailing = decoder.decode();
      if (trailing) {
        buffer += trailing;
      }
      if (buffer.trim()) {
        flushLine(buffer, controller);
      }
      buffer = "";
    },
  });
}

/**
 * Web Standard `TransformStream` wrapping validated A2UI envelopes into SSE `event: a2ui` frames.
 */
export function createA2uiSseTransformStream(
  options: A2uiWorkerStreamOptions = {},
): TransformStream<string | Uint8Array, Uint8Array> {
  const decoder = new TextDecoder();
  const encoder = new TextEncoder();
  const jsonlStream = createA2uiJsonlTransformStream(options);
  const writer = jsonlStream.writable.getWriter();
  const reader = jsonlStream.readable.getReader();
  let pumpPromise: Promise<void> = Promise.resolve();

  return new TransformStream<string | Uint8Array, Uint8Array>({
    start(controller) {
      pumpPromise = (async () => {
        try {
          while (true) {
            const { value, done } = await reader.read();
            if (done) break;
            const text = decoder.decode(value, { stream: true });
            for (const line of text.split(/\r?\n/)) {
              if (!line.trim()) continue;
              controller.enqueue(encoder.encode(`event: a2ui\ndata: ${line}\n\n`));
            }
          }
        } catch {
          controller.enqueue(
            encoder.encode(
              `event: a2ui\ndata: ${JSON.stringify(
                createRendererErrorEvent({
                  surfaceId: "stream",
                  message: "Stream processing aborted",
                }),
              )}\n\n`,
            ),
          );
        }
      })();
    },
    async transform(chunk) {
      await writer.write(chunk);
    },
    async flush() {
      await writer.close();
      await pumpPromise;
    },
  });
}

function toWebReadableStream(
  source: ReadableStream<string | Uint8Array> | Iterable<unknown>,
): ReadableStream<string | Uint8Array> {
  if (typeof (source as ReadableStream<unknown>).getReader === "function") {
    return source as ReadableStream<string | Uint8Array>;
  }
  const iterator = (source as Iterable<unknown>)[Symbol.iterator]();
  return new ReadableStream<string | Uint8Array>({
    pull(controller) {
      const next = iterator.next();
      if (next.done) {
        controller.close();
        return;
      }
      const line = typeof next.value === "string" ? next.value : JSON.stringify(next.value);
      controller.enqueue(`${line}\n`);
    },
  });
}

/**
 * Builds a `workerd`-compatible SSE `Response` for A2UI v1.0 / Express agent streams.
 */
export function createA2uiSseResponse(
  source: ReadableStream<string | Uint8Array> | Iterable<unknown>,
  options: A2uiWorkerStreamOptions & { status?: number; headers?: Record<string, string> } = {},
): Response {
  const stream = toWebReadableStream(source).pipeThrough(createA2uiSseTransformStream(options));
  const headers = new Headers({
    "Content-Type": "text/event-stream; charset=utf-8",
    "Cache-Control": "no-store, no-transform",
    "X-Content-Type-Options": "nosniff",
    "X-A2UI-Protocol-Version": "1.0",
    ...options.headers,
  });
  return new Response(stream, {
    status: options.status ?? 200,
    headers,
  });
}

/**
 * Builds a `workerd`-compatible JSONL (`application/x-ndjson`) `Response` for A2UI Express clients.
 */
export function createA2uiJsonlResponse(
  source: ReadableStream<string | Uint8Array> | Iterable<unknown>,
  options: A2uiWorkerStreamOptions & { status?: number; headers?: Record<string, string> } = {},
): Response {
  const stream = toWebReadableStream(source).pipeThrough(createA2uiJsonlTransformStream(options));
  const headers = new Headers({
    "Content-Type": "application/x-ndjson; charset=utf-8",
    "Cache-Control": "no-store, no-transform",
    "X-Content-Type-Options": "nosniff",
    "X-A2UI-Protocol-Version": "1.0",
    ...options.headers,
  });
  return new Response(stream, {
    status: options.status ?? 200,
    headers,
  });
}
