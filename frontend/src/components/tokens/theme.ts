import { useSyncExternalStore } from "react";

export type StudioTheme = "dark" | "light";
const storageKey = "studio-components-theme";
const themeEvent = "studio-theme-change";

/** 默认深色，复用组件预览已有的持久化偏好 */
export function readStudioTheme(): StudioTheme {
  try {
    return localStorage.getItem(storageKey) === "light" ? "light" : "dark";
  } catch {
    return "dark";
  }
}

/** 在根元素切换已有 tokens，使 Portal 内的菜单、Modal 和 Drawer 同步 */
export function applyStudioTheme(theme: StudioTheme) {
  if (typeof document === "undefined") return;
  document.documentElement.dataset.theme = theme;
  document.documentElement.style.colorScheme = theme;
  try {
    localStorage.setItem(storageKey, theme);
  } catch {
    // A restricted storage context still supports switching the current document
  }
  window.dispatchEvent(new Event(themeEvent));
}

function subscribe(onChange: () => void) {
  const onStorage = (event: StorageEvent) => {
    if (event.key === storageKey || event.key === null) applyStudioTheme(readStudioTheme());
  };
  window.addEventListener(themeEvent, onChange);
  window.addEventListener("storage", onStorage);
  return () => {
    window.removeEventListener(themeEvent, onChange);
    window.removeEventListener("storage", onStorage);
  };
}

function snapshot(): StudioTheme {
  const theme = document.documentElement.dataset.theme;
  return theme === "dark" || theme === "light" ? theme : readStudioTheme();
}

export function useStudioTheme() {
  const theme = useSyncExternalStore(subscribe, snapshot, () => "dark" as const);
  return [theme, applyStudioTheme] as const;
}
