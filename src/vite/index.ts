import {
  A2UI_BASIC_CATALOG_ID,
  A2UI_VINEXT_CATALOG_ID,
  A2UI_VINEXT_PROTOCOL_VERSION,
  BASIC_CATALOG_V1_COMPONENTS,
  buildA2uiRendererCapabilities,
  validateA2uiVinextEnvelope,
} from "../catalog.js";

export const A2UI_VINEXT_VIRTUAL_ID = "virtual:a2ui-vinext/catalog";
const RESOLVED_VIRTUAL_ID = `\0${A2UI_VINEXT_VIRTUAL_ID}`;

export interface VinextA2uiPluginOptions {
  /** Fail Vite dev/build on invalid `.a2ui.json` fixture edits (default: true). */
  strictFixtures?: boolean;
  /** Additional custom catalog IDs to include in virtual metadata. */
  additionalCatalogIds?: string[];
}

export interface MinimalVitePlugin {
  name: string;
  enforce?: "pre" | "post";
  resolveId?: (id: string) => string | undefined;
  load?: (id: string) => string | undefined;
  config?: () => Record<string, unknown>;
  handleHotUpdate?: (ctx: {
    file: string;
    read: () => Promise<string>;
  }) => Promise<unknown[] | void>;
}

/**
 * Vite / Cloudflare Vinext plugin exposing `virtual:a2ui-vinext/catalog`,
 * RSC client boundary optimization hints, and HMR validation for `.a2ui.json` fixtures.
 */
export function vinextA2uiPlugin(options: VinextA2uiPluginOptions = {}): MinimalVitePlugin {
  const strict = options.strictFixtures !== false;

  return {
    name: "webomage:a2ui-vinext",
    enforce: "pre",
    config() {
      return {
        optimizeDeps: {
          include: ["@webomage/a2ui-vinext/client", "@a2ui/web_core/v1_0"],
        },
        ssr: {
          noExternal: ["@webomage/a2ui-vinext"],
        },
      };
    },
    resolveId(id: string) {
      if (id === A2UI_VINEXT_VIRTUAL_ID) {
        return RESOLVED_VIRTUAL_ID;
      }
      return undefined;
    },
    load(id: string) {
      if (id !== RESOLVED_VIRTUAL_ID) {
        return undefined;
      }
      const capabilities = buildA2uiRendererCapabilities({
        versions: ["1.0", "v0.9"],
        additionalCatalogIds: [A2UI_VINEXT_CATALOG_ID, ...(options.additionalCatalogIds ?? [])],
      });
      const payload = {
        protocolVersion: A2UI_VINEXT_PROTOCOL_VERSION,
        basicCatalogId: A2UI_BASIC_CATALOG_ID,
        components: [...BASIC_CATALOG_V1_COMPONENTS],
        capabilities,
      };
      return `export default ${JSON.stringify(payload, null, 2)};`;
    },
    async handleHotUpdate(ctx) {
      if (!ctx.file.endsWith(".a2ui.json")) {
        return undefined;
      }
      const rawText = await ctx.read();
      let parsed: unknown;
      try {
        parsed = JSON.parse(rawText);
      } catch (err) {
        if (strict) {
          throw new Error(`Invalid JSON in ${ctx.file}: ${(err as Error).message}`);
        }
        return [];
      }
      const result = validateA2uiVinextEnvelope(parsed);
      if (!result.ok && strict) {
        throw new Error(
          `A2UI fixture validation failed in ${ctx.file}: ${result.issues[0]?.message ?? "unknown error"}`,
        );
      }
      return undefined;
    },
  };
}
