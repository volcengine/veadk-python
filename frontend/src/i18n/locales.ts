export const SUPPORTED_LOCALES = ["zh-CN", "en-US"] as const;

export type SupportedLocale = (typeof SUPPORTED_LOCALES)[number];

export const DEFAULT_LOCALE: SupportedLocale = "en-US";
export const LOCALE_STORAGE_KEY = "agentkit.studio.locale";

export const LOCALE_METADATA: Record<
  SupportedLocale,
  { dir: "ltr" | "rtl"; nativeName: string }
> = {
  "zh-CN": { dir: "ltr", nativeName: "简体中文" },
  "en-US": { dir: "ltr", nativeName: "English" },
};

export function resolveSupportedLocale(
  locale: string | null | undefined,
): SupportedLocale | null {
  if (!locale) return null;
  const normalized = locale.trim().replace(/_/g, "-").toLowerCase();
  const exactMatch = SUPPORTED_LOCALES.find(
    (supported) => supported.toLowerCase() === normalized,
  );
  if (exactMatch) return exactMatch;
  if (normalized === "zh" || normalized.startsWith("zh-")) return "zh-CN";
  if (normalized === "en" || normalized.startsWith("en-")) return "en-US";
  return null;
}

export function localeCompatibleBackendText(
  value: string | null | undefined,
  locale: string,
): string {
  const text = value?.trim() ?? "";
  if (!text) return "";
  const hasHanText = /\p{Script=Han}/u.test(text);
  return locale.toLowerCase().startsWith("zh") === hasHanText ? text : "";
}

function storedLocale(): SupportedLocale | null {
  if (typeof window === "undefined") return null;
  try {
    return resolveSupportedLocale(window.localStorage.getItem(LOCALE_STORAGE_KEY));
  } catch {
    return null;
  }
}

function browserLocales(): readonly string[] {
  if (typeof navigator === "undefined") return [];
  if (navigator.languages.length > 0) return navigator.languages;
  return navigator.language ? [navigator.language] : [];
}

export function detectLocale(): SupportedLocale {
  const persisted = storedLocale();
  if (persisted) return persisted;

  for (const locale of browserLocales()) {
    const supported = resolveSupportedLocale(locale);
    if (supported) return supported;
  }
  return DEFAULT_LOCALE;
}

export function persistLocale(locale: SupportedLocale): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale);
  } catch {
    // Language switching still works when browser storage is unavailable.
  }
}

export function applyDocumentLocale(locale: SupportedLocale): void {
  if (typeof document === "undefined") return;
  document.documentElement.lang = locale;
  document.documentElement.dir = LOCALE_METADATA[locale].dir;
}
