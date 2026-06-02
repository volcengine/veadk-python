// Component registry: maps an A2UI component name (as it appears in the catalog
// and in `updateComponents`) to a React renderer.
//
// Each agent-sendable component lives in its own directory under
// `components/<Name>/` and self-registers via `register(...)`. To add a custom
// enterprise component, drop a new folder there (see components/index.ts) and a
// matching backend catalog entry (veadk.a2ui.BaseA2UICatalog).

import type { ComponentType, ReactNode } from "react";
import type { A2uiAction, A2uiComponent, DynamicValue, SurfaceState } from "./types";

export interface RenderContext {
  surface: SurfaceState;
  /** Render a child component by id. */
  render: (id: string | undefined) => ReactNode;
  /** Resolve a dynamic value against the surface data model. */
  resolve: (value: DynamicValue) => unknown;
  /** Resolve a dynamic value to a display string. */
  resolveString: (value: DynamicValue) => string;
  /** Dispatch an interactive action back to the agent. */
  dispatchAction: (action: A2uiAction | undefined, node: A2uiComponent) => void;
}

export interface ComponentRendererProps {
  node: A2uiComponent;
  ctx: RenderContext;
}

export type ComponentRenderer = ComponentType<ComponentRendererProps>;

const registry = new Map<string, ComponentRenderer>();

export function register(name: string, renderer: ComponentRenderer): void {
  registry.set(name, renderer);
}

export function getRenderer(name: string): ComponentRenderer | undefined {
  return registry.get(name);
}

export function registeredComponents(): string[] {
  return [...registry.keys()];
}
