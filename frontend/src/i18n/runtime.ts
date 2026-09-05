import i18next from "i18next";
import { initReactI18next } from "react-i18next";

import enAdk from "./resources/en-US/adk.json";
import enApp from "./resources/en-US/app.json";
import enConversation from "./resources/en-US/conversation.json";
import zhAdk from "./resources/zh-CN/adk.json";
import zhApp from "./resources/zh-CN/app.json";
import zhConversation from "./resources/zh-CN/conversation.json";
import {
  applyDocumentLocale,
  DEFAULT_LOCALE,
  detectLocale,
  resolveSupportedLocale,
  SUPPORTED_LOCALES,
} from "./locales";

const initialLocale = detectLocale();

/**
 * Shared i18n instance that is safe to import from non-Vite bundles and tests.
 * The full Studio catalog is attached by index.ts; ADK messages stay available
 * here because API modules can also be bundled independently.
 */
export const i18n = i18next.createInstance();

void i18n.use(initReactI18next).init({
  resources: {
    "en-US": { adk: enAdk, app: enApp, conversation: enConversation },
    "zh-CN": { adk: zhAdk, app: zhApp, conversation: zhConversation },
  },
  lng: initialLocale,
  fallbackLng: DEFAULT_LOCALE,
  supportedLngs: [...SUPPORTED_LOCALES],
  defaultNS: "common",
  interpolation: { escapeValue: false },
  initAsync: false,
});

applyDocumentLocale(initialLocale);
i18n.on("languageChanged", (language) => {
  const locale = resolveSupportedLocale(language) ?? DEFAULT_LOCALE;
  applyDocumentLocale(locale);
});
