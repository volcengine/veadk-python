type PreviewLocation = { component: string; section: string };

const aliases: Record<string, PreviewLocation> = {
  progress: { component: "long-running-state", section: "" },
  "input-header-icon": { component: "input", section: "input-with-header-icon-preview-title" },
  "input-tail-icon": { component: "input", section: "input-with-tail-icon-preview-title" },
  "underline-tabs": { component: "tabs", section: "underline-tabs-preview-title" },
  "pill-tabs": { component: "tabs", section: "preview-pill-tabs-title" },
  "filter-tabs": { component: "tabs", section: "filter-tabs-preview-title" },
  "glass-tabs": { component: "tabs", section: "preview-glass-tabs-title" },
  "resource-card": { component: "card", section: "preview-resource-card-title" },
  "info-card": { component: "card", section: "info-card-preview-title" },
  "promo-card": { component: "card", section: "preview-promo-card-title" },
  "glass-icon-button": { component: "button", section: "glass-icon-button-preview-title" },
  "form-label/form-label-row-title": { component: "form-label-row", section: "form-label-row-title" },
  "button/glass-icon-button-group-preview-title": { component: "glass-icon-button-group", section: "glass-icon-button-group-preview-title" },
  "card/card-layout-preview-title": { component: "card-layout", section: "card-layout-preview-title" },
};

export function resolvePreviewLocation(hash: string): PreviewLocation {
  const path = hash.replace(/^#/, "");
  if (Object.prototype.hasOwnProperty.call(aliases, path)) return aliases[path];
  const [component = "", section = ""] = path.split("/");
  return Object.prototype.hasOwnProperty.call(aliases, component)
    ? { ...aliases[component], section: section || aliases[component].section }
    : { component: component || "button", section };
}
