// Resolve A2UI dynamic values ({path} bindings and {call} client functions)
// against a surface's data model.

import type { DynamicValue } from "./types";

/** Client-side functions invokable via { "call": name, "args": {...} }. */
export type ClientFunction = (args: Record<string, unknown>) => unknown;

export const clientFunctions: Record<string, ClientFunction> = {
  formatDate(args) {
    const value = args.value ?? args.date ?? args.timestamp;
    if (value == null) return "";
    const d = new Date(value as string | number);
    return isNaN(d.getTime()) ? String(value) : d.toLocaleString();
  },
};

/** Resolve a JSON Pointer (RFC 6901) against the data model. */
function resolvePointer(model: Record<string, unknown>, pointer: string): unknown {
  if (!pointer || pointer === "/") return model;
  const tokens = pointer
    .replace(/^\//, "")
    .split("/")
    .map((t) => t.replace(/~1/g, "/").replace(/~0/g, "~"));
  let current: unknown = model;
  for (const token of tokens) {
    if (current == null || typeof current !== "object") return undefined;
    current = (current as Record<string, unknown>)[token];
  }
  return current;
}

function isBinding(v: unknown): v is { path: string } {
  return typeof v === "object" && v !== null && typeof (v as any).path === "string";
}

function isCall(v: unknown): v is { call: string; args?: Record<string, unknown> } {
  return typeof v === "object" && v !== null && typeof (v as any).call === "string";
}

/** Resolve a dynamic value to a concrete JS value. */
export function resolve(
  value: DynamicValue,
  model: Record<string, unknown>,
): unknown {
  if (isBinding(value)) return resolvePointer(model, value.path);
  if (isCall(value)) {
    const fn = clientFunctions[value.call];
    const args: Record<string, unknown> = {};
    for (const [k, v] of Object.entries(value.args ?? {})) {
      args[k] = resolve(v as DynamicValue, model);
    }
    return fn ? fn(args) : `[unknown fn: ${value.call}]`;
  }
  return value;
}

/** Resolve a dynamic value and coerce to a display string. */
export function resolveString(
  value: DynamicValue,
  model: Record<string, unknown>,
): string {
  const r = resolve(value, model);
  if (r == null) return "";
  return typeof r === "string" ? r : String(r);
}
