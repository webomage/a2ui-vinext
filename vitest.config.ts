import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: {
      "@webomage/a2ui-vinext/catalog": fileURLToPath(new URL("./src/catalog.ts", import.meta.url)),
      "@webomage/a2ui-vinext/client": fileURLToPath(new URL("./src/client/index.ts", import.meta.url)),
      "@webomage/a2ui-vinext/server": fileURLToPath(new URL("./src/server/index.ts", import.meta.url)),
      "@webomage/a2ui-vinext/workers": fileURLToPath(new URL("./src/workers/index.ts", import.meta.url)),
      "@webomage/a2ui-vinext/vite": fileURLToPath(new URL("./src/vite/index.ts", import.meta.url)),
      "@webomage/a2ui-vinext": fileURLToPath(new URL("./src/index.ts", import.meta.url)),
    },
  },
  test: {
    environment: "jsdom",
    include: ["tests/**/*.test.ts", "tests/**/*.test.tsx"],
  },
});
