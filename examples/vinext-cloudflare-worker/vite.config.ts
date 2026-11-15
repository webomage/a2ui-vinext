import { defineConfig } from "vite";
import vinext from "vinext";
import { cloudflare } from "@cloudflare/vite-plugin";
import { vinextA2uiPlugin } from "@webomage/a2ui-vinext/vite";

export default defineConfig({
  plugins: [
    vinextA2uiPlugin(),
    vinext(),
    cloudflare({
      viteEnvironment: {
        name: "rsc",
        childEnvironments: ["ssr"],
      },
    }),
  ],
});
