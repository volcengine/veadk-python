import type { Resource } from "i18next";
import {
  persistLocale,
  type SupportedLocale,
} from "./locales";
import { i18n } from "./runtime";

type LocaleModule = { default: Record<string, unknown> };

const localeModules = import.meta.glob<LocaleModule>(
  "./resources/*/*.json",
  { eager: true },
);

function buildResources(): Resource {
  const resources: Resource = {};
  for (const [path, module] of Object.entries(localeModules)) {
    const match = path.match(/\/resources\/([^/]+)\/([^/]+)\.json$/);
    if (!match) continue;
    const [, locale, namespace] = match;
    resources[locale] ??= {};
    resources[locale][namespace] = module.default;
  }
  return resources;
}

for (const [locale, namespaces] of Object.entries(buildResources())) {
  for (const [namespace, resource] of Object.entries(namespaces ?? {})) {
    i18n.addResourceBundle(locale, namespace, resource, true, true);
  }
}

export async function changeLanguage(locale: SupportedLocale): Promise<void> {
  persistLocale(locale);
  await i18n.changeLanguage(locale);
}

export { i18n };

export {
  DEFAULT_LOCALE,
  LOCALE_METADATA,
  LOCALE_STORAGE_KEY,
  SUPPORTED_LOCALES,
  resolveSupportedLocale,
  type SupportedLocale,
} from "./locales";
