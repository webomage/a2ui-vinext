import React from "react";
import { prepareA2uiRscSurface } from "@webomage/a2ui-vinext/server";
import { buildDemoAgentMessages } from "../worker/index.js";
import { AgentShowcaseClient } from "./components/AgentShowcaseClient.js";

export default function HomePage(): React.ReactElement {
  const prepared = prepareA2uiRscSurface(
    buildDemoAgentMessages("Rendered initially via Vite RSC and hydrated on Cloudflare Workers"),
    {
      surfaceId: "vinext-edge-demo",
      serverBindings: {
        runtime: "cloudflare-workerd",
        apiKey: "server-secret-stripped-by-rsc-boundary",
      },
    },
  );

  return (
    <main style={{ maxWidth: "48rem", margin: "2rem auto", padding: "0 1rem" }}>
      <AgentShowcaseClient initialSurface={prepared.surface} />
    </main>
  );
}
