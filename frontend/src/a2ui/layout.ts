// Shared flexbox mapping for Row / Column / List layout components.

const JUSTIFY: Record<string, string> = {
  start: "flex-start",
  center: "center",
  end: "flex-end",
  spaceBetween: "space-between",
  spaceAround: "space-around",
  spaceEvenly: "space-evenly",
  stretch: "stretch",
};

const ALIGN: Record<string, string> = {
  start: "flex-start",
  center: "center",
  end: "flex-end",
  stretch: "stretch",
};

export function justifyToCss(v: unknown): string {
  return JUSTIFY[v as string] ?? "flex-start";
}

export function alignToCss(v: unknown): string {
  return ALIGN[v as string] ?? "stretch";
}
