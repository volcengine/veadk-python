// A2UI v0.9 wire types (https://a2ui.org). Only the parts the renderer needs.

/** A data binding: a JSON Pointer into the surface data model. */
export interface DataBinding {
  path: string;
}

/** A call to a client-registered function. */
export interface FunctionCall {
  call: string;
  args?: Record<string, unknown>;
  returnType?: string;
}

/** A value that may be a literal, a data binding, or a function call. */
export type DynamicValue = string | number | boolean | DataBinding | FunctionCall | unknown;

/** A component node in the flat adjacency list. */
export interface A2uiComponent {
  id: string;
  component: string;
  // component-specific props (child / children / text / name / action / ...)
  [key: string]: unknown;
}

/** An action emitted by an interactive component (e.g. Button).
 *  v0.9 `Action` is a server event `{ event: { name, context } }` (or a
 *  client-side function variant). */
export interface A2uiAction {
  event?: { name?: string; context?: Record<string, unknown> };
  [key: string]: unknown;
}

// ---- Messages (envelope: { version, <oneOf message key> } ) ----

export interface CreateSurfaceMessage {
  version?: string;
  createSurface: {
    surfaceId: string;
    catalogId?: string;
    sendDataModel?: boolean;
    theme?: unknown;
  };
}

export interface UpdateComponentsMessage {
  version?: string;
  updateComponents: {
    surfaceId: string;
    components: A2uiComponent[];
  };
}

export interface UpdateDataModelMessage {
  version?: string;
  updateDataModel: {
    surfaceId: string;
    path: string;
    value: unknown;
  };
}

export interface DeleteSurfaceMessage {
  version?: string;
  deleteSurface: { surfaceId: string };
}

export type A2uiMessage =
  | CreateSurfaceMessage
  | UpdateComponentsMessage
  | UpdateDataModelMessage
  | DeleteSurfaceMessage
  | Record<string, unknown>;

/** Mutable per-surface state held by the renderer. */
export interface SurfaceState {
  surfaceId: string;
  catalogId?: string;
  components: Record<string, A2uiComponent>; // id -> component
  dataModel: Record<string, unknown>;
  rootId: string;
}
