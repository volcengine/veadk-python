// Applies a stream of A2UI messages into surface state and renders it through
// the component registry.

import type { ReactNode } from "react";
import { resolve as resolveValue, resolveString as resolveStr } from "./bind";
import { getRenderer, type RenderContext } from "./registry";
import type {
  A2uiAction,
  A2uiComponent,
  A2uiMessage,
  DynamicValue,
  SurfaceState,
} from "./types";

/** Set a value at a JSON Pointer path within a (mutable) object. */
function setAtPointer(obj: Record<string, unknown>, pointer: string, value: unknown) {
  const tokens = pointer
    .replace(/^\//, "")
    .split("/")
    .map((t) => t.replace(/~1/g, "/").replace(/~0/g, "~"));
  let cur: Record<string, unknown> = obj;
  for (let i = 0; i < tokens.length - 1; i++) {
    const t = tokens[i];
    if (typeof cur[t] !== "object" || cur[t] == null) cur[t] = {};
    cur = cur[t] as Record<string, unknown>;
  }
  cur[tokens[tokens.length - 1]] = value;
}

/** Build the set of surfaces from an ordered list of A2UI messages. */
export function buildSurfaces(messages: A2uiMessage[]): SurfaceState[] {
  const surfaces = new Map<string, SurfaceState>();

  for (const msg of messages) {
    const m = msg as Record<string, any>;
    if (m.createSurface) {
      const { surfaceId, catalogId } = m.createSurface;
      surfaces.set(surfaceId, {
        surfaceId,
        catalogId,
        components: {},
        dataModel: {},
        rootId: "root",
      });
    } else if (m.updateComponents) {
      const { surfaceId, components } = m.updateComponents;
      let s = surfaces.get(surfaceId);
      if (!s) {
        s = { surfaceId, components: {}, dataModel: {}, rootId: "root" };
        surfaces.set(surfaceId, s);
      }
      for (const comp of components as A2uiComponent[]) {
        s.components[comp.id] = comp;
      }
      if (!s.components[s.rootId]) {
        s.rootId = (components as A2uiComponent[])[0]?.id ?? s.rootId;
      }
    } else if (m.updateDataModel) {
      const { surfaceId, path, value } = m.updateDataModel;
      const s = surfaces.get(surfaceId);
      if (s) setAtPointer(s.dataModel, path, value);
    } else if (m.deleteSurface) {
      surfaces.delete(m.deleteSurface.surfaceId);
    }
  }

  return [...surfaces.values()];
}

function Fallback({ node }: { node: A2uiComponent }) {
  return (
    <details className="a2ui-fallback">
      <summary>Unsupported component: {node.component}</summary>
      <pre>{JSON.stringify(node, null, 2)}</pre>
    </details>
  );
}

export interface SurfaceViewProps {
  surface: SurfaceState;
  onAction: (action: A2uiAction | undefined, node: A2uiComponent) => void;
}

/** Render a single surface starting at its root component. */
export function SurfaceView({ surface, onAction }: SurfaceViewProps) {
  const ctx: RenderContext = {
    surface,
    resolve: (v: DynamicValue) => resolveValue(v, surface.dataModel),
    resolveString: (v: DynamicValue) => resolveStr(v, surface.dataModel),
    dispatchAction: onAction,
    render: (id: string | undefined): ReactNode => {
      if (!id) return null;
      const node = surface.components[id];
      if (!node) return null;
      const Renderer = getRenderer(node.component) ?? Fallback;
      return <Renderer key={id} node={node} ctx={ctx} />;
    },
  };

  return (
    <div className="a2ui-surface" data-a2ui-surface={surface.surfaceId}>
      {ctx.render(surface.rootId)}
    </div>
  );
}
