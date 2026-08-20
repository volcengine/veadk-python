import type { EChartsOption } from "echarts";
import JSON5 from "json5";

const MAX_OPTION_LENGTH = 200_000;
const UNSAFE_KEYS = new Set(["__proto__", "constructor", "prototype"]);
const EXTERNAL_RESOURCE_PATTERN = /^(?:https?:|data:|blob:|file:|javascript:|image:\/\/)/i;

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function assertSafeData(value: unknown, depth = 0): void {
  if (depth > 30) throw new Error("ECharts option nesting is too deep");
  if (typeof value === "number" && !Number.isFinite(value)) {
    throw new Error("ECharts option contains a non-finite number");
  }
  if (typeof value === "string" && EXTERNAL_RESOURCE_PATTERN.test(value.trim())) {
    throw new Error("ECharts option contains an external resource");
  }
  if (Array.isArray(value)) {
    for (const item of value) assertSafeData(item, depth + 1);
    return;
  }
  if (!isRecord(value)) return;
  for (const [key, child] of Object.entries(value)) {
    if (UNSAFE_KEYS.has(key)) throw new Error("ECharts option contains an unsafe key");
    assertSafeData(child, depth + 1);
  }
}

function unwrapEChartsOption(source: string): string {
  const trimmed = source.trim();
  const assignment = trimmed.match(
    /^(?:(?:const|let|var)\s+)?option\s*=\s*([\s\S]*?)\s*;?$/,
  );
  return assignment?.[1]?.trim() || trimmed;
}

function findClosingParenthesis(source: string, openingIndex: number): number {
  let depth = 1;
  let quote = "";
  let escaped = false;
  let lineComment = false;
  let blockComment = false;

  for (let index = openingIndex + 1; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1];

    if (lineComment) {
      if (char === "\n" || char === "\r") lineComment = false;
      continue;
    }
    if (blockComment) {
      if (char === "*" && next === "/") {
        blockComment = false;
        index += 1;
      }
      continue;
    }
    if (quote) {
      if (escaped) {
        escaped = false;
      } else if (char === "\\") {
        escaped = true;
      } else if (char === quote) {
        quote = "";
      }
      continue;
    }
    if (char === "/" && next === "/") {
      lineComment = true;
      index += 1;
      continue;
    }
    if (char === "/" && next === "*") {
      blockComment = true;
      index += 1;
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }
    if (char === "(") depth += 1;
    if (char === ")") {
      depth -= 1;
      if (depth === 0) return index;
    }
  }
  throw new Error("ECharts graphic constructor is not closed");
}

function toFiniteNumber(value: unknown): number {
  if (typeof value !== "number" || !Number.isFinite(value)) {
    throw new Error("ECharts gradient coordinates must be finite numbers");
  }
  return value;
}

function gradientToData(type: "linear" | "radial", source: string) {
  const args: unknown = JSON5.parse(`[${source}]`);
  assertSafeData(args);
  if (!Array.isArray(args)) throw new Error("Invalid ECharts gradient arguments");

  const coordinateCount = type === "linear" ? 4 : 3;
  if (args.length < coordinateCount + 1 || args.length > coordinateCount + 2) {
    throw new Error("Invalid ECharts gradient argument count");
  }
  const coordinates = args.slice(0, coordinateCount).map(toFiniteNumber);
  const colorStops = args[coordinateCount];
  const global = args[coordinateCount + 1] ?? false;
  if (!Array.isArray(colorStops) || typeof global !== "boolean") {
    throw new Error("Invalid ECharts gradient data");
  }

  return type === "linear"
    ? {
        type,
        x: coordinates[0],
        y: coordinates[1],
        x2: coordinates[2],
        y2: coordinates[3],
        colorStops,
        global,
      }
    : {
        type,
        x: coordinates[0],
        y: coordinates[1],
        r: coordinates[2],
        colorStops,
        global,
      };
}

function findGraphicGradient(source: string, fromIndex: number) {
  const constructorPattern =
    /^(?:new\s+)?echarts\.graphic\.(LinearGradient|RadialGradient)\s*\(/;
  let quote = "";
  let escaped = false;
  let lineComment = false;
  let blockComment = false;

  for (let index = fromIndex; index < source.length; index += 1) {
    const char = source[index];
    const next = source[index + 1];
    if (lineComment) {
      if (char === "\n" || char === "\r") lineComment = false;
      continue;
    }
    if (blockComment) {
      if (char === "*" && next === "/") {
        blockComment = false;
        index += 1;
      }
      continue;
    }
    if (quote) {
      if (escaped) escaped = false;
      else if (char === "\\") escaped = true;
      else if (char === quote) quote = "";
      continue;
    }
    if (char === "/" && next === "/") {
      lineComment = true;
      index += 1;
      continue;
    }
    if (char === "/" && next === "*") {
      blockComment = true;
      index += 1;
      continue;
    }
    if (char === "'" || char === '"') {
      quote = char;
      continue;
    }

    const match = source.slice(index).match(constructorPattern);
    if (match) {
      return {
        index,
        openingIndex: index + match[0].lastIndexOf("("),
        type: match[1] === "LinearGradient" ? "linear" as const : "radial" as const,
      };
    }
  }
  return undefined;
}

function replaceGraphicGradients(source: string): string {
  let normalized = source;
  let searchFrom = 0;

  while (true) {
    const match = findGraphicGradient(normalized, searchFrom);
    if (!match) return normalized;
    const closingIndex = findClosingParenthesis(normalized, match.openingIndex);
    const args = normalized.slice(match.openingIndex + 1, closingIndex);
    const replacement = JSON.stringify(gradientToData(match.type, args));
    normalized = `${normalized.slice(0, match.index)}${replacement}${normalized.slice(closingIndex + 1)}`;
    searchFrom = match.index + replacement.length;
  }
}

export function parseEChartsOption(
  source: string,
  reduceMotion = false,
): EChartsOption {
  if (source.length > MAX_OPTION_LENGTH) {
    throw new Error("ECharts option is too large");
  }
  const normalized = replaceGraphicGradients(unwrapEChartsOption(source));
  let parsed: unknown;
  try {
    parsed = JSON5.parse(normalized);
  } catch (error) {
    if (/\bfunction\s*\(|=>/.test(normalized)) {
      throw new Error("ECharts function callbacks are not supported");
    }
    throw error;
  }
  if (!isRecord(parsed)) throw new Error("ECharts option must be a data object");
  assertSafeData(parsed);

  const option: Record<string, unknown> = { ...parsed };
  option.aria = {
    ...(isRecord(option.aria) ? option.aria : {}),
    enabled: true,
  };

  const tooltip = option.tooltip;
  if (isRecord(tooltip)) {
    option.tooltip = { ...tooltip, renderMode: "richText" };
  } else if (Array.isArray(tooltip)) {
    option.tooltip = tooltip.map((item) => (
      isRecord(item) ? { ...item, renderMode: "richText" } : item
    ));
  }

  if (reduceMotion) option.animation = false;
  return option as EChartsOption;
}
