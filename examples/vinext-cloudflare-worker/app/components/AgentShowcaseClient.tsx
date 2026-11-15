"use client";

import React, { useState } from "react";
import { A2uiVinextSurface } from "@webomage/a2ui-vinext/client";
import type { A2uiNormalizedSurface } from "@webomage/a2ui-vinext/catalog";
import type { A2uiRendererActionEnvelope } from "@webomage/a2ui-vinext/server";

export function AgentShowcaseClient({
  initialSurface,
}: {
  initialSurface: A2uiNormalizedSurface | null;
}): React.ReactElement {
  const [lastAction, setLastAction] = useState<A2uiRendererActionEnvelope | null>(null);

  return (
    <div>
      <A2uiVinextSurface
        surface={initialSurface}
        onAction={async (evt) => {
          setLastAction(evt);
          await fetch("/api/a2ui/action", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(evt),
          }).catch(() => undefined);
        }}
      />
      {lastAction ? (
        <pre data-testid="action-preview">{JSON.stringify(lastAction, null, 2)}</pre>
      ) : null}
    </div>
  );
}
