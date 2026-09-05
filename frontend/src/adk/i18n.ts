import type { TOptions } from "i18next";
import { i18n } from "../i18n/runtime";

/** Translate ADK client messages at call time so language changes apply immediately. */
export function adkT(key: string, options: TOptions = {}): string {
  return i18n.t(key, { ...options, ns: "adk" });
}

/** Attach the active UI locale without overriding a caller-selected language. */
export function withLocaleHeaders(headers?: HeadersInit): Headers {
  const localized = new Headers(headers);
  if (!localized.has("Accept-Language")) {
    localized.set("Accept-Language", i18n.resolvedLanguage || i18n.language);
  }
  return localized;
}

export function activeLocale(): string {
  return i18n.resolvedLanguage || i18n.language;
}
