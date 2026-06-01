import type { ComponentRendererProps } from "../../registry";

// A small emoji map for common Material-style icon names; unknown names fall
// back to a neutral bullet so the layout never breaks.
// Keys are the catalog's camelCase Material icon names.
const ICONS: Record<string, string> = {
  send: "✈️",
  check: "✅",
  close: "✖️",
  star: "⭐",
  favorite: "❤️",
  info: "ℹ️",
  help: "❓",
  error: "⛔",
  calendarToday: "📅",
  event: "📅",
  schedule: "🕒",
  locationOn: "📍",
  accountCircle: "👤",
  mail: "✉️",
  call: "📞",
  home: "🏠",
  settings: "⚙️",
  search: "🔍",
};

export function Icon({ node }: ComponentRendererProps) {
  const name = (node.name as string) ?? "";
  return (
    <span className="a2ui-icon" title={name} aria-label={name}>
      {ICONS[name] ?? "•"}
    </span>
  );
}
