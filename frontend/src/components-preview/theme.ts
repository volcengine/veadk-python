export type PreviewTheme = "dark" | "light";
const storageKey = "studio-components-theme";

export function readPreviewTheme(): PreviewTheme {
  try {
    return localStorage.getItem(storageKey) === "dark" ? "dark" : "light";
  } catch {
    return "light";
  }
}

export function applyPreviewTheme(theme: PreviewTheme) {
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  try {
    localStorage.setItem(storageKey, theme);
  } catch {
    // Storage can be unavailable in restricted browser contexts; the current theme still applies
  }
}
